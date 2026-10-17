bl_info = {
    "name": "PS2 BIN Animation Studio",
    "author": "CarlVercetti & Claude",
    "version": (2, 6, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BIN Studio",
    "description": "Parse .bin (header + offset table + .mot blocks), preview animations on armature and save edited keyframe values back into the .bin",
    "category": "Animation",
}

import bpy
import os
import struct
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty, PointerProperty, EnumProperty
from bpy.types import Panel, Operator, PropertyGroup, UIList
from bpy_extras.io_utils import ExportHelper, ImportHelper

# ============================================================
# LETTURA .BIN (formato semplice: header + tabella offset + .mot)
# Stessa logica di Mots_Extractor_Motbreak.py, adattata per restare
# in memoria invece di scrivere file separati su disco.
# ============================================================

def read_bin_entries(path):
    """
    Legge un .bin e ritorna (entries, data) oppure None.

    entries = lista di dict:
      {"label": str, "bytes": bytes, "section_count": int,
       "table_row": int, "blocks": [(ptr, size), ...]}

    "blocks" contiene offset e dimensione, nel .bin originale, di ogni
    blocco concatenato in "bytes": serve per riscrivere le modifiche
    esattamente nella stessa posizione.

    data = bytes dell'intero .bin (copia di lavoro in memoria).
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return None

    if len(data) < 16:
        return None

    try:
        desc_start = struct.unpack_from("<I", data, 12)[0]
    except struct.error:
        return None

    if desc_start <= 0 or desc_start >= len(data):
        return None

    # --- Trova il confine della tabella (stesso algoritmo dell'extractor) ---
    animation_table = []
    min_data_offset = len(data)
    pos = desc_start

    while pos < min_data_offset:
        if pos + 20 > len(data):
            break
        record = struct.unpack_from("<IIIII", data, pos)

        for ptr in record:
            if ptr != 0xFFFFFFFF and ptr != 0:
                if ptr < min_data_offset:
                    min_data_offset = ptr

        if pos >= min_data_offset:
            break

        animation_table.append(record)
        pos += 20

    if not animation_table:
        return None

    # --- Estrazione: per ogni riga, concatena i blocchi validi ---
    entries = []
    for i, entry in enumerate(animation_table):
        combined = bytearray()
        blocks = []
        block_slots = []

        for slot, ptr in enumerate(entry):
            if ptr == 0xFFFFFFFF or ptr == 0 or ptr >= len(data):
                continue
            try:
                if data[ptr:ptr+2] == b'\x02\x00':
                    size = struct.unpack_from("<I", data, ptr + 8)[0]
                    if size > 0 and (ptr + size) <= len(data):
                        combined.extend(data[ptr: ptr + size])
                        blocks.append((ptr, size))
                        block_slots.append(slot)
            except Exception:
                continue

        if combined:
            sections_in_anim = len(blocks)
            entries.append({
                "label":         f"anim_{len(entries):03d} ({sections_in_anim} section)",
                "bytes":         bytes(combined),
                "section_count": sections_in_anim,
                "table_row":     i,
                "blocks":        blocks,
                "block_slots":   block_slots,   # slot della tabella: 0 lower, 1 upper, 2 face, 3-4 hand
                "anim_no":       len(entries),
            })

    if not entries:
        return None
    return entries, data, desc_start, len(animation_table)


# ============================================================
# MOT PARSER (identico a mot_viewer.py, ma prende bytes in
# memoria invece di un filepath)
# ============================================================

ROT_PRECISION      = 2607.5945876
LOC_PRECISION      = 16.0
SCL_PRECISION      = 16.0
FACE_PRECISION     = 256.0
FACE_PRECISION_ALT = 512.0

TRACK_TYPES = {
    0x001: ("scale",          0),
    0x002: ("scale",          1),
    0x004: ("scale",          2),
    0x008: ("rotation_euler", 0),
    0x010: ("rotation_euler", 1),
    0x020: ("rotation_euler", 2),
    0x040: ("location",       0),
    0x080: ("location",       1),
    0x100: ("location",       2),
}

SECTION_NODE_START = {
    0x0A: 0,
    0x0C: 10,
    0x0D: 10,   # UPPER + 1 nodo extra: 13 nodi consecutivi, Node10 -> Node22
    0x06: 22,
}


def _disconnect_node2(arm):
    node2_y_offset = 0.0
    if "Node1" not in arm.pose.bones or "Node2" not in arm.pose.bones:
        return False, node2_y_offset
    prev_mode = arm.mode
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb2 = arm.data.edit_bones.get("Node2")
    if eb2:
        if eb2.use_connect:
            eb2.use_connect = False
        node2_y_offset = eb2.head.y
    bpy.ops.object.mode_set(mode=prev_mode)
    return True, node2_y_offset


def apply_mot_bytes(data, arm):
    """
    Applica i bytes di un .mot (già in memoria, letto dal .bin) sull'armatura.
    Logica IDENTICA a _load_mot di mot_viewer.py: unica differenza è che
    prende 'data' direttamente invece di aprire un file.
    """
    if not arm or arm.type != 'ARMATURE':
        return False, 0

    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.fps_base = 1.0

    if arm.animation_data:
        arm.animation_data_clear()

    prev_active = bpy.context.view_layer.objects.active
    prev_mode   = arm.mode
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    bpy.ops.object.mode_set(mode=prev_mode)
    bpy.context.view_layer.objects.active = prev_active

    for bone in arm.pose.bones:
        bone.rotation_mode = 'XYZ'

    is_hd, node2_y_offset = _disconnect_node2(arm)

    file_size = len(data)
    pos = 0
    global_max_frame = 0
    hands_count = 0
    file_has_loop = False
    file_loop_frame = 0

    while pos + 20 <= file_size:
        h_type, h_count, h_size, h_loop, h_loopFrame = struct.unpack_from("<IIIIf", data, pos)
        if h_type != 0x80000002 or h_size == 0 or pos + h_size > file_size:
            break

        if h_loop == 1:
            file_has_loop = True
            file_loop_frame = int(h_loopFrame)

        section_byte = h_count & 0xFF

        if section_byte in SECTION_NODE_START:
            node_idx = SECTION_NODE_START[section_byte]
        elif section_byte == 0x04:
            node_idx = 28 if hands_count == 0 else 32
            hands_count += 1
        else:
            node_idx = 0

        node_pos = pos + 20
        section_end = pos + h_size

        for _ in range(h_count):
            if node_pos + 12 > section_end:
                break
            n_type, n_sub, n_size = struct.unpack_from("<III", data, node_pos)
            node_name = f"Node{node_idx}"

            if n_type >= 0x80000000 and n_sub > 0:
                target = None
                if arm.name == node_name:
                    target = arm
                elif node_name in arm.pose.bones:
                    target = arm.pose.bones[node_name]

                if target:
                    if hasattr(target, 'rotation_mode'):
                        target.rotation_mode = 'XYZ'

                    track_ptr = node_pos + 12
                    for _ in range(n_sub):
                        if track_ptr + 12 > section_end:
                            break
                        t_type, t_keys, t_size = struct.unpack_from("<III", data, track_ptr)
                        fmt   = (t_type >> 16) & 0xFF
                        t_id  = t_type & 0xFFF

                        if t_id in TRACK_TYPES:
                            prop, idx = TRACK_TYPES[t_id]

                            is_facial = 23 <= node_idx <= 27
                            if is_facial and prop == "location":
                                div = -(FACE_PRECISION_ALT if node_idx in (24, 26) else FACE_PRECISION)
                            elif prop == "scale":
                                div = SCL_PRECISION
                            elif prop == "location":
                                div = LOC_PRECISION
                            else:
                                div = ROT_PRECISION

                            kf_size = 16 if fmt == 0x22 else (8 if fmt == 0x12 else 4)

                            for k in range(t_keys):
                                kp = track_ptr + 12 + k * kf_size
                                if kp + kf_size > len(data):
                                    break

                                c0 = c1 = 0
                                if fmt == 0x11:
                                    val, frame = struct.unpack_from("<hh", data, kp)
                                    f_val = val / div
                                elif fmt == 0x12:
                                    val, frame, c0, c1 = struct.unpack_from("<hhhh", data, kp)
                                    f_val = val / div
                                elif fmt == 0x22:
                                    vf, ff, c0, c1 = struct.unpack_from("<ffff", data, kp)
                                    frame = int(ff)
                                    f_val = vf
                                else:
                                    val, frame = struct.unpack_from("<hh", data, kp)
                                    f_val = val / div

                                write_val = f_val
                                if is_hd and prop == "location" and idx == 1 and node_name == "Node2":
                                    write_val = f_val - node2_y_offset

                                if prop == "location":
                                    target.location[idx] = write_val
                                elif prop == "scale":
                                    target.scale[idx] = write_val
                                else:
                                    target.rotation_euler[idx] = write_val

                                target.keyframe_insert(data_path=prop, index=idx, frame=frame)

                                if frame > global_max_frame:
                                    global_max_frame = frame

                                if not arm.animation_data or not arm.animation_data.action:
                                    pass
                                else:
                                    action = arm.animation_data.action
                                    if isinstance(target, bpy.types.Object):
                                        fc = action.fcurves.find(prop, index=idx)
                                    else:
                                        dp = f'pose.bones["{node_name}"].{prop}'
                                        fc = action.fcurves.find(dp, index=idx)
                                    if fc:
                                        for kfp in fc.keyframe_points:
                                            if abs(kfp.co[0] - frame) < 0.01:
                                                kfp.handle_left_type  = 'FREE'
                                                kfp.handle_right_type = 'FREE'
                                                dy_l = (c0 * 1.0) / div
                                                dy_r = (c1 * 1.0) / div
                                                kfp.handle_left[0]  = kfp.co[0] - 1.0
                                                kfp.handle_left[1]  = kfp.co[1] - dy_l
                                                kfp.handle_right[0] = kfp.co[0] + 1.0
                                                kfp.handle_right[1] = kfp.co[1] + dy_r
                                                break

                        track_ptr += t_size

            node_pos += n_size if n_size > 0 else 4
            node_idx += 1

        pos += h_size

    bpy.context.scene.frame_start   = 0
    bpy.context.scene.frame_end     = max(global_max_frame, 1)
    bpy.context.scene.frame_current = 0

    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action["capcom_loop"]       = file_has_loop
        arm.animation_data.action["capcom_loop_frame"] = file_loop_frame

    return True, global_max_frame


# ============================================================
# MOT REBUILDER (operazione inversa di apply_mot_bytes)
# Rigenera i blocchi (sezioni) di un .mot a partire dalle fcurve:
#  - tracce esistenti: vengono riscritte con TUTTI i keyframe attuali
#    (valore, frame, tangenti), quindi key aggiunte/tolte cambiano la
#    dimensione di traccia, nodo e sezione;
#  - tracce nuove (canale con keyframe ma assente nel blocco): create
#    in formato 0x12, nell'ordine standard delle tracce;
#  - tutto cio' che non viene toccato (nodi senza bone, mani, padding)
#    e' copiato byte per byte.
# ============================================================

TRACK_ORDER   = [0x001, 0x002, 0x004, 0x008, 0x010, 0x020, 0x040, 0x080, 0x100]
NEW_TRACK_FMT = 0x12
DEFAULT_VALUE = {"scale": 1.0, "rotation_euler": 0.0, "location": 0.0}
EPS           = 1e-6

# Slot della tabella (5 puntatori per riga): lower, upper, face, hand, hand
SLOT_SPECS = {
    0: ("lower", 0x0A, range(0, 10)),
    1: ("upper", 0x0C, range(10, 22)),
    2: ("face",  0x06, range(22, 28)),
}
KNOWN_SECTION_BYTES = (0x0A, 0x0C, 0x0D, 0x06, 0x04)
EMPTY_NODE = struct.pack("<III", 0x80000000, 0, 12)


def _clamp_i16(v):
    return max(-32768, min(32767, int(round(v))))


def _div_for(node_idx, prop):
    if 23 <= node_idx <= 27 and prop == "location":
        return -(FACE_PRECISION_ALT if node_idx in (24, 26) else FACE_PRECISION)
    if prop == "scale":
        return SCL_PRECISION
    if prop == "location":
        return LOC_PRECISION
    return ROT_PRECISION


def _kf_size(fmt):
    return 16 if fmt == 0x22 else (8 if fmt == 0x12 else 4)


class _RebuildCtx:
    """Stato condiviso durante la rigenerazione di un'animazione."""

    def __init__(self, arm):
        self.arm = arm
        self.action = arm.animation_data.action if (arm and arm.animation_data) else None
        self.is_hd = "Node1" in arm.pose.bones and "Node2" in arm.pose.bones
        self.node2_y_offset = 0.0
        if self.is_hd:
            b2 = arm.data.bones.get("Node2")
            if b2:
                self.node2_y_offset = b2.head_local.y
        self._cache = {}
        self.warnings = []
        self.keys_before = 0
        self.keys_after = 0
        self.tracks_new = 0
        self.tracks_const_skipped = 0

    def target(self, node_name):
        if self.arm.name == node_name:
            return self.arm
        if node_name in self.arm.pose.bones:
            return self.arm.pose.bones[node_name]
        return None

    def keys(self, target, node_name, prop, idx):
        """Lista [(frame_int, keyframe_point)] ordinata per frame, o None."""
        if isinstance(target, bpy.types.Object):
            dp = prop
        else:
            dp = f'pose.bones["{node_name}"].{prop}'
        key = (dp, idx)
        if key not in self._cache:
            fc = self.action.fcurves.find(dp, index=idx) if self.action else None
            if fc and len(fc.keyframe_points) > 0:
                by_frame = {}
                for kp in fc.keyframe_points:
                    by_frame[int(round(kp.co[0]))] = kp
                self._cache[key] = [(f, by_frame[f]) for f in sorted(by_frame)]
            else:
                self._cache[key] = None
        return self._cache[key]

    def file_value(self, node_name, prop, idx, kp):
        v = kp.co[1]
        # Ripristina l'offset visivo di Node2.LOC_Y (modelli HD)
        if self.is_hd and prop == "location" and idx == 1 and node_name == "Node2":
            v += self.node2_y_offset
        return v


def _is_default_constant(prop, keys):
    d = DEFAULT_VALUE[prop]
    return all(abs(kp.co[1] - d) < EPS for _, kp in keys)


def _encode_keys(ctx, fmt, keys, node_name, prop, idx, div):
    out = bytearray()
    for frame, kp in keys:
        value = ctx.file_value(node_name, prop, idx, kp)

        dxl = kp.co[0] - kp.handle_left[0]
        c0 = ((kp.co[1] - kp.handle_left[1]) * div / dxl) if dxl != 0 else 0.0
        dxr = kp.handle_right[0] - kp.co[0]
        c1 = ((kp.handle_right[1] - kp.co[1]) * div / dxr) if dxr != 0 else 0.0

        if fmt == 0x22:
            out += struct.pack("<ffff", value, float(frame), c0, c1)
        elif fmt == 0x12:
            out += struct.pack("<hhhh", _clamp_i16(value * div), _clamp_i16(frame),
                               _clamp_i16(c0), _clamp_i16(c1))
        else:
            # 0x11 e formati sconosciuti da 4 byte: solo valore e frame
            out += struct.pack("<hh", _clamp_i16(value * div), _clamp_i16(frame))
    return bytes(out)


def _make_track(t_type, nkeys, key_bytes, tail=b""):
    return struct.pack("<III", t_type, nkeys, 12 + len(key_bytes) + len(tail)) + key_bytes + tail


def _rebuild_node(ctx, data, node_pos, node_end, n_type, n_sub, node_idx):
    """Ritorna i byte aggiornati di un nodo (stessa posizione logica)."""
    node_name = f"Node{node_idx}"
    raw = bytes(data[node_pos:node_end])

    if n_type < 0x80000000 or node_end - node_pos < 12:
        return raw
    target = ctx.target(node_name)
    if target is None:
        return raw

    # --- tracce esistenti ---
    parsed = []   # (t_id, t_type, t_keys, pos, size)
    track_ptr = node_pos + 12
    for _ in range(n_sub):
        if track_ptr + 12 > node_end:
            break
        t_type, t_keys, t_size = struct.unpack_from("<III", data, track_ptr)
        if t_size < 12 or track_ptr + t_size > node_end:
            break
        parsed.append((t_type & 0xFFF, t_type, t_keys, track_ptr, t_size))
        track_ptr += t_size
    node_tail = bytes(data[track_ptr:node_end])
    unparsed = n_sub - len(parsed)

    final = []        # [(t_id, bytes)] nell'ordine in cui verranno scritte
    existing = set()
    for t_id, t_type, t_keys, tpos, tsize in parsed:
        existing.add(t_id)
        ctx.keys_before += t_keys
        if t_id in TRACK_TYPES:
            prop, idx = TRACK_TYPES[t_id]
            keys = ctx.keys(target, node_name, prop, idx)
            if keys:
                fmt = (t_type >> 16) & 0xFF
                used = 12 + t_keys * _kf_size(fmt)
                tail = bytes(data[tpos + used: tpos + tsize]) if tsize > used else b""
                kb = _encode_keys(ctx, fmt, keys, node_name, prop, idx, _div_for(node_idx, prop))
                final.append((t_id, _make_track(t_type, len(keys), kb, tail)))
                ctx.keys_after += len(keys)
                continue
            ctx.warnings.append(f"{node_name} {prop}[{idx}]: nessun keyframe, traccia lasciata com'era")
        final.append((t_id, bytes(data[tpos:tpos + tsize])))
        ctx.keys_after += t_keys

    # --- tracce nuove (canali con keyframe ma senza traccia nel blocco) ---
    new_flags = 0
    for t_id in TRACK_ORDER:
        if t_id in existing:
            continue
        prop, idx = TRACK_TYPES[t_id]
        keys = ctx.keys(target, node_name, prop, idx)
        if not keys:
            continue
        if _is_default_constant(prop, keys):
            ctx.tracks_const_skipped += 1
            continue
        kb = _encode_keys(ctx, NEW_TRACK_FMT, keys, node_name, prop, idx, _div_for(node_idx, prop))
        t_type = 0x80000000 | (NEW_TRACK_FMT << 16) | t_id
        pos = len(final)
        for i, (eid, _b) in enumerate(final):
            if eid > t_id:
                pos = i
                break
        final.insert(pos, (t_id, _make_track(t_type, len(keys), kb)))
        new_flags |= t_id
        ctx.tracks_new += 1
        ctx.keys_after += len(keys)

    body = b"".join(b for _, b in final)
    header = struct.pack("<III", n_type | new_flags, len(final) + unparsed,
                         12 + len(body) + len(node_tail))
    return header + body + node_tail


def rebuild_mot_sections(data, ctx):
    """
    Ripercorre i blocchi di 'data' (bytes concatenati di una entry) e ne
    rigenera ognuno dalle fcurve.
    Ritorna (lista_byte_per_sezione, True se ha consumato tutti i byte).
    """
    sections = []
    size = len(data)
    pos = 0
    hands_count = 0

    while pos + 20 <= size:
        h_type, h_count, h_size, _l, _lf = struct.unpack_from("<IIIIf", data, pos)
        if h_type != 0x80000002 or h_size == 0 or pos + h_size > size:
            break

        section_byte = h_count & 0xFF
        if section_byte in SECTION_NODE_START:
            node_idx = SECTION_NODE_START[section_byte]
        elif section_byte == 0x04:
            node_idx = 28 if hands_count == 0 else 32
            hands_count += 1
        else:
            node_idx = 0

        section_end = pos + h_size
        node_pos = pos + 20
        body = bytearray()
        for _ in range(h_count):
            if node_pos + 12 > section_end:
                break
            n_type, n_sub, n_size = struct.unpack_from("<III", data, node_pos)
            span = n_size if n_size > 0 else 4
            node_end = min(node_pos + span, section_end)
            body += _rebuild_node(ctx, data, node_pos, node_end, n_type, n_sub, node_idx)
            node_pos += span
            node_idx += 1

        trailing = bytes(data[min(node_pos, section_end):section_end])
        header = bytearray(data[pos:pos + 20])
        struct.pack_into("<I", header, 8, 20 + len(body) + len(trailing))
        sections.append(bytes(header) + bytes(body) + trailing)
        pos += h_size

    return sections, pos == size


def _build_new_section(ctx, slot, loop_bytes, frame_start, frame_end):
    """
    Crea da zero un blocco mancante (lower/upper/face) dalle fcurve.
    Ritorna None se non c'e' nessun keyframe significativo da scrivere.
    loop_bytes = 8 byte (loop + loopFrame) copiati dagli altri blocchi dell'animazione.
    Per l'upper le rotazioni dei bone Node3-21 vengono sempre scritte
    (come fa l'exporter), con 2 key di default se il canale e' vuoto.
    """
    _name, _sec_byte, nodes = SLOT_SPECS[slot]
    sec_byte = SLOT_SPECS[slot][1]
    body = bytearray()
    real = False

    for node_idx in nodes:
        node_name = f"Node{node_idx}"
        target = ctx.target(node_name)
        tracks = bytearray()
        flags = 0
        count = 0

        if target is not None:
            for t_id in TRACK_ORDER:
                prop, idx = TRACK_TYPES[t_id]
                keys = ctx.keys(target, node_name, prop, idx)
                const = (not keys) or _is_default_constant(prop, keys)
                force = (slot == 1 and 3 <= node_idx <= 21 and prop == "rotation_euler")
                if const and not force:
                    if keys:
                        ctx.tracks_const_skipped += 1
                    continue

                t_type = 0x80000000 | (NEW_TRACK_FMT << 16) | t_id
                if const:
                    kb = (struct.pack("<hhhh", 0, _clamp_i16(frame_start), 0, 0) +
                          struct.pack("<hhhh", 0, _clamp_i16(frame_end), 0, 0))
                    nkeys = 2
                else:
                    kb = _encode_keys(ctx, NEW_TRACK_FMT, keys, node_name, prop, idx,
                                      _div_for(node_idx, prop))
                    nkeys = len(keys)
                    real = True
                    ctx.tracks_new += 1
                    ctx.keys_after += nkeys
                tracks += _make_track(t_type, nkeys, kb)
                flags |= t_id
                count += 1

        if count:
            body += struct.pack("<III", 0x80000000 | flags, count, 12 + len(tracks)) + bytes(tracks)
        else:
            body += EMPTY_NODE

    if not real:
        return None
    header = struct.pack("<III", 0x80000002, len(nodes), 20 + len(body)) + loop_bytes
    # h_count: per il blocco usiamo il numero di nodi (0x0A, 0x0C, 0x06)
    assert len(nodes) == sec_byte
    return header + bytes(body)


def _get_active_armature():
    obj = bpy.context.active_object
    if obj and obj.type == 'ARMATURE':
        return obj
    for o in bpy.context.selected_objects:
        if o.type == 'ARMATURE':
            return o
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    if arm and arm.type == 'ARMATURE':
        return arm
    for o in bpy.data.objects:
        if o.type == 'ARMATURE':
            return o
    return None


# ============================================================
# PROPRIETÀ E STATO
# ============================================================

class BINRowItem(PropertyGroup):
    label: StringProperty(name="Animazione")
    row_index: IntProperty()
    modified: BoolProperty(
        name="Modificata",
        description="Modificata in memoria e non ancora salvata su disco",
        default=False,
    )


def _on_row_selection(self, context):
    sc = context.scene
    if getattr(sc, "bin_studio_loading", False):
        return
    try:
        bpy.ops.binstudio.load_motion_row()
    except Exception as e:
        print("[BIN Studio] Errore caricamento animazione:", e)


def _on_row_selection2(self, context):
    sc = context.scene
    if getattr(sc, "bin_studio_loading", False):
        return
    try:
        bpy.ops.binstudio.load_motion_row2()
    except Exception as e:
        print("[BIN Studio] Errore anteprima bin secondario:", e)


class BINSTUDIO_UL_rows(UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_prop, index):
        prefix = "* " if item.modified else ""
        layout.label(text=prefix + item.label, icon="ANIM")


class BINStudioProps(PropertyGroup):
    bin_path: StringProperty(
        name="File .bin",
        description="File .bin da analizzare",
        subtype='FILE_PATH'
    )
    rows: CollectionProperty(type=BINRowItem)
    row_index: IntProperty(default=0, update=_on_row_selection)
    autoplay: BoolProperty(name="Autoplay", default=True)

    # --- bin secondario (sorgente) ---
    bin2_path: StringProperty(
        name="Bin secondario",
        description="Secondo .bin (opzionale) da cui prendere animazioni per il principale",
        subtype='FILE_PATH'
    )
    rows2: CollectionProperty(type=BINRowItem)
    row_index2: IntProperty(default=0, update=_on_row_selection2)
    replace_scope: EnumProperty(
        name="Sostituisci",
        description="Quali blocchi dell'animazione del principale vengono sostituiti",
        items=[
            ('ALL',   "Tutto",       "Tutti i blocchi dell'animazione sorgente (lower, upper, face, hand)"),
            ('LOWER', "Solo lower",  "Solo il blocco lower"),
            ('UPPER', "Solo upper",  "Solo il blocco upper"),
            ('FACE',  "Solo face",   "Solo il blocco face"),
        ],
        default='ALL',
    )


CACHED_ENTRIES = None  # lista di dict {"label","bytes","section_count","table_row","blocks"}
CACHED_BIN     = None  # bytearray: copia di lavoro in memoria dell'intero .bin


CACHED_DESC_START = 0  # offset della tabella dei puntatori nel .bin
CACHED_TABLE_ROWS = 0  # numero di righe della tabella (5 puntatori da 4 byte ciascuna)

CACHED2_ENTRIES = None  # bin secondario (sola lettura): stesse entry del principale
CACHED2_BIN     = None
SHOWING_SRC     = False  # True se l'armatura mostra un'animazione del bin secondario


def _rebuild_entry_bytes(entry):
    """Ricostruisce entry['bytes'] dalla copia in memoria del .bin."""
    entry["bytes"] = b"".join(bytes(CACHED_BIN[p:p + s]) for p, s in entry["blocks"])


def _row_label(e):
    e["label"] = f"anim_{e['anim_no']:03d} ({e['section_count']} section)"
    return f"{e['label']}  [{len(e['bytes'])}B]"


def _read_slot(row, slot):
    """Puntatore grezzo (0xFFFFFFFF = vuoto) dello slot 'slot' della riga 'row'."""
    off = CACHED_DESC_START + 20 * row + 4 * slot
    return struct.unpack_from("<I", CACHED_BIN, off)[0]


def _apply_edits(edits, creates, row, cur_entry):
    """
    Applica al .bin in memoria:
      edits   = {ptr_originale: (vecchia_size, nuovi_byte)}  blocchi riscritti
      creates = {slot: byte}  blocchi nuovi per la riga 'row' (aggiunti in coda al file)
    Come lo swapper: il primo blocco resta dov'e', i blocchi dopo un blocco
    che cambia lunghezza scorrono, nessun allineamento. I 5 puntatori di ogni
    riga della tabella vengono riscritti una volta sola per campo.
    Aggiorna offset/size dei blocchi di TUTTE le entry in cache.
    """
    global CACHED_BIN
    old = CACHED_BIN
    table_end = CACHED_DESC_START + 20 * CACHED_TABLE_ROWS

    items = sorted(edits.items())
    if items and items[0][0] < table_end:
        raise ValueError("un blocco da riscrivere si trova prima della fine della tabella")

    out = bytearray()
    cur = 0
    deltas = []
    for ptr, (old_size, new) in items:
        if ptr < cur:
            raise ValueError("blocchi sovrapposti")
        out += old[cur:ptr]
        out += new
        cur = ptr + old_size
        deltas.append((ptr, len(new) - old_size))
    out += old[cur:]

    def remap(p):
        return p + sum(d for q, d in deltas if q < p)

    # --- tabella: ogni puntatore valido viene rimappato una sola volta ---
    old_len = len(old)
    for r in range(CACHED_TABLE_ROWS):
        for j in range(5):
            off = CACHED_DESC_START + 20 * r + 4 * j
            v = struct.unpack_from("<I", out, off)[0]
            if v in (0, 0xFFFFFFFF) or v >= old_len:
                continue
            struct.pack_into("<I", out, off, remap(v))

    # --- cache: nuovi offset/size per tutte le entry ---
    for e in CACHED_ENTRIES:
        e["blocks"] = [(remap(p), len(edits[p][1]) if p in edits else s) for p, s in e["blocks"]]

    # --- blocchi mancanti: in coda al file + puntatore nello slot ---
    created = {}
    for slot in sorted(creates):
        new_ptr = len(out)
        out += creates[slot]
        struct.pack_into("<I", out, CACHED_DESC_START + 20 * row + 4 * slot, new_ptr)
        created[slot] = (new_ptr, len(creates[slot]))
    if created:
        pairs = [(s, b) for s, b in zip(cur_entry["block_slots"], cur_entry["blocks"]) if s not in created]
        pairs += list(created.items())
        pairs.sort(key=lambda t: t[0])
        cur_entry["block_slots"] = [s for s, _b in pairs]
        cur_entry["blocks"] = [b for _s, b in pairs]
        cur_entry["section_count"] = len(pairs)

    CACHED_BIN = out
    for e in CACHED_ENTRIES:
        _rebuild_entry_bytes(e)


SLOT_NAMES = ["lower", "upper", "face", "hand", "hand"]


def _parse_mot_sections(mot):
    """
    Divide un .mot nelle sue sezioni e le assegna agli slot della tabella:
    0x0A -> lower, 0x0C/0x0D -> upper, 0x06 -> face, 0x04 -> prima hand (slot 3)
    e seconda hand (slot 4). Ritorna {slot: byte_sezione} (byte invariati).
    Solleva ValueError se il file non e' valido o contiene tipi non gestiti (mostri).
    """
    size = len(mot)
    if size < 20:
        raise ValueError("file .mot troppo corto")
    slots = {}
    pos = 0
    hands = 0
    while pos < size:
        if pos + 20 > size:
            raise ValueError("dati finali non validi nel .mot")
        h_type, h_count, h_size, _l, _lf = struct.unpack_from("<IIIIf", mot, pos)
        if h_type != 0x80000002 or h_size < 20 or pos + h_size > size:
            raise ValueError(f"sezione non valida all'offset {pos}")
        sb = h_count & 0xFF
        if sb == 0x0A:
            slot = 0
        elif sb in (0x0C, 0x0D):
            slot = 1
        elif sb == 0x06:
            slot = 2
        elif sb == 0x04:
            slot = 3 + hands
            hands += 1
            if slot > 4:
                raise ValueError("il .mot contiene piu' di 2 blocchi hand")
        else:
            raise ValueError(f"tipo di sezione 0x{sb:02X} non gestito (animazione mostro?)")
        if slot in slots:
            raise ValueError(f"il .mot contiene due sezioni per lo slot {SLOT_NAMES[slot]}")
        slots[slot] = bytes(mot[pos:pos + h_size])
        pos += h_size
    return slots


def _table_cell_counts():
    """{puntatore: quante celle della tabella lo usano} (per riconoscere i blocchi condivisi)."""
    counts = {}
    for r in range(CACHED_TABLE_ROWS):
        for j in range(5):
            v = struct.unpack_from("<I", CACHED_BIN, CACHED_DESC_START + 20 * r + 4 * j)[0]
            if v not in (0, 0xFFFFFFFF):
                counts[v] = counts.get(v, 0) + 1
    return counts


def plan_replace(mot, entry, row, only_slots=None):
    """
    Prepara la sostituzione dell'animazione 'entry' (riga 'row') con le sezioni di 'mot'
    (un .mot oppure i byte di un'animazione di un altro .bin).
    - le sezioni sostituiscono i blocchi degli slot corrispondenti (byte invariati);
    - only_slots=None: sostituzione totale; gli slot che 'mot' non ha restano com'erano ma
      con loop/loopFrame di 'mot';
    - only_slots={slot,...}: sostituzione parziale; si usano solo quegli slot e il blocco
      nuovo prende il loop/loopFrame dell'animazione di destinazione;
    - slot di destinazione vuoto (FFFFFFFF): blocco nuovo in coda al file + puntatore;
    - blocco da cambiare condiviso con altre righe, o non riconosciuto: NON lo tocco, il blocco
      nuovo va in coda al file e cambia solo il puntatore di questa riga.
    Ritorna (edits, creates, warnings, info) da passare a _apply_edits.
    """
    new_slots = _parse_mot_sections(mot)
    if not all(CACHED_BIN[p + 4] in KNOWN_SECTION_BYTES for p, _s in entry["blocks"]):
        raise ValueError("animazione di tipo mostro: non gestita")

    first_ptr = entry["blocks"][0][0]
    if only_slots is None:
        loop_bytes = next(iter(new_slots.values()))[12:20]
        fix_kept = True
    else:
        missing = [s for s in sorted(only_slots) if s not in new_slots]
        new_slots = {s: b for s, b in new_slots.items() if s in only_slots}
        if not new_slots:
            raise ValueError("l'animazione sorgente non ha il blocco " +
                             ", ".join(SLOT_NAMES[s] for s in missing))
        loop_bytes = bytes(CACHED_BIN[first_ptr + 12:first_ptr + 20])
        new_slots = {s: b[:12] + loop_bytes + b[20:] for s, b in new_slots.items()}
        fix_kept = False

    desired = dict(new_slots)         # slot -> byte del blocco da scrivere
    loop_fixed = []
    if fix_kept:
        for slot, (ptr, size) in zip(entry["block_slots"], entry["blocks"]):
            if slot in new_slots:
                continue
            blk = bytes(CACHED_BIN[ptr:ptr + size])
            if blk[12:20] != loop_bytes:
                desired[slot] = blk[:12] + loop_bytes + blk[20:]
                loop_fixed.append(slot)

    counts = _table_cell_counts()
    known = dict(zip(entry["block_slots"], entry["blocks"]))
    edits, creates, warnings = {}, {}, []
    isolated, added = [], []
    for slot, newb in desired.items():
        cur = _read_slot(row, slot)
        if cur in (0, 0xFFFFFFFF):
            creates[slot] = newb                         # slot vuoto: blocco nuovo in coda
            added.append(slot)
            continue
        pair = known.get(slot)
        if pair is None or pair[0] != cur:
            creates[slot] = newb                         # blocco non riconosciuto: non lo modifico
            warnings.append(f"slot {SLOT_NAMES[slot]}: blocco non riconosciuto, sostituito con uno nuovo in coda")
            continue
        if counts.get(cur, 0) > 1:
            creates[slot] = newb                         # condiviso: isolo
            isolated.append(slot)
            continue
        ptr, size = pair
        if bytes(CACHED_BIN[ptr:ptr + size]) != newb:
            edits[ptr] = (size, newb)

    info = {"replaced": sorted(new_slots), "kept": sorted(set(entry["block_slots"]) - set(new_slots)),
            "isolated": isolated, "loop_fixed": loop_fixed, "added": added}
    return edits, creates, warnings, info


# ============================================================
# OPERATORI
# ============================================================

class BINSTUDIO_OT_load_bin(Operator):
    bl_idname = "binstudio.load_bin"
    bl_label  = "Analizza .bin"

    def execute(self, context):
        global CACHED_ENTRIES, CACHED_BIN, CACHED_DESC_START, CACHED_TABLE_ROWS
        sc = context.scene
        props = sc.bin_studio
        path = bpy.path.abspath(props.bin_path)

        if not os.path.isfile(path):
            self.report({'ERROR'}, "Seleziona un file .bin valido.")
            return {'CANCELLED'}

        result = read_bin_entries(path)
        if not result:
            self.report({'ERROR'}, "Nessuna animazione trovata in questo .bin.")
            return {'CANCELLED'}

        CACHED_ENTRIES, data, CACHED_DESC_START, CACHED_TABLE_ROWS = result
        CACHED_BIN = bytearray(data)

        props.rows.clear()
        for e in CACHED_ENTRIES:
            item = props.rows.add()
            item.label = _row_label(e)
            item.row_index = e["table_row"]
            item.modified = False

        props.row_index = 0
        self.report({'INFO'}, f"Trovate {len(CACHED_ENTRIES)} animazioni nel .bin")
        return {'FINISHED'}


class BINSTUDIO_OT_load_motion_row(Operator):
    bl_idname = "binstudio.load_motion_row"
    bl_label  = "Carica Animazione"

    def execute(self, context):
        global CACHED_ENTRIES, SHOWING_SRC
        sc = context.scene
        props = sc.bin_studio
        arm = _get_active_armature()

        if not arm:
            self.report({'ERROR'}, "Nessuna armatura trovata in scena!")
            return {'CANCELLED'}

        if not CACHED_ENTRIES or not props.rows:
            return {'CANCELLED'}

        idx = max(0, min(props.row_index, len(CACHED_ENTRIES) - 1))
        entry = CACHED_ENTRIES[idx]

        sc.bin_studio_loading = True
        try:
            ok, max_frame = apply_mot_bytes(entry["bytes"], arm)
            if ok and props.autoplay and not context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
                context.scene.frame_current = 0
                bpy.ops.screen.animation_play()
        finally:
            sc.bin_studio_loading = False

        if not ok:
            self.report({'ERROR'}, "Caricamento fallito")
            return {'CANCELLED'}

        SHOWING_SRC = False
        self.report({'INFO'}, f"{entry['label']}: {max_frame} frames")
        return {'FINISHED'}


class BINSTUDIO_OT_step_row(Operator):
    bl_idname = "binstudio.step_row"
    bl_label  = "Step"
    delta: IntProperty(default=1)

    def execute(self, context):
        props = context.scene.bin_studio
        n = len(props.rows)
        if not n:
            return {'CANCELLED'}
        props.row_index = (props.row_index + self.delta) % n
        return {'FINISHED'}


class BINSTUDIO_OT_save_anim(Operator):
    bl_idname = "binstudio.save_anim"
    bl_label  = "Salva animazione"
    bl_description = (
        "Riscrive nel .bin in memoria l'animazione selezionata partendo dai keyframe attuali "
        "(valori, key aggiunte/tolte, tracce nuove, blocchi mancanti) e aggiorna gli offset. "
        "Temporaneo: il file su disco non viene toccato"
    )

    def execute(self, context):
        global CACHED_ENTRIES, CACHED_BIN
        props = context.scene.bin_studio

        if not CACHED_ENTRIES or CACHED_BIN is None or not props.rows:
            self.report({'ERROR'}, "Nessun .bin caricato.")
            return {'CANCELLED'}
        if _show_src_guard(self):
            return {'CANCELLED'}

        arm = _get_active_armature()
        if not arm:
            self.report({'ERROR'}, "Nessuna armatura trovata in scena!")
            return {'CANCELLED'}

        idx = max(0, min(props.row_index, len(CACHED_ENTRIES) - 1))
        entry = CACHED_ENTRIES[idx]

        ctx = _RebuildCtx(arm)
        if not ctx.action:
            self.report({'ERROR'}, "L'armatura non ha nessuna animazione da salvare.")
            return {'CANCELLED'}

        # --- 1) rigenera i blocchi esistenti ---
        sections, complete = rebuild_mot_sections(entry["bytes"], ctx)
        if not complete or len(sections) != len(entry["blocks"]):
            self.report({'ERROR'}, "Struttura del blocco non riconosciuta: salvataggio annullato.")
            return {'CANCELLED'}

        edits = {}
        for (ptr, size), new in zip(entry["blocks"], sections):
            if bytes(CACHED_BIN[ptr:ptr + size]) != new:
                edits[ptr] = (size, new)

        # --- 2) blocchi mancanti (slot 0 lower, 1 upper, 2 face con puntatore FFFFFFFF) ---
        creates = {}
        row = entry["table_row"]
        scene = context.scene
        first_ptr = entry["blocks"][0][0]
        loop_bytes = bytes(CACHED_BIN[first_ptr + 12:first_ptr + 20])
        is_known = all(CACHED_BIN[p + 4] in KNOWN_SECTION_BYTES for p, _s in entry["blocks"])
        for slot in (0, 1, 2):
            if _read_slot(row, slot) not in (0, 0xFFFFFFFF):
                continue   # slot occupato (anche se il blocco non e' tra quelli riconosciuti)
            sec = _build_new_section(ctx, slot, loop_bytes, scene.frame_start, scene.frame_end)
            if not sec:
                continue
            if not is_known:
                ctx.warnings.append(f"blocco {SLOT_SPECS[slot][0]} non creato: animazione di tipo non gestito")
                continue
            creates[slot] = sec

        warnings = list(ctx.warnings)
        if ctx.tracks_const_skipped:
            warnings.append(f"{ctx.tracks_const_skipped} canali con keyframe tutti al valore di default ignorati")

        if not edits and not creates:
            self.report({'INFO'}, f"{entry['label']}: nessuna differenza da salvare.")
            if warnings:
                self.report({'WARNING'}, " | ".join(warnings[:6]))
            return {'FINISHED'}

        # --- 3) applica al .bin in memoria: scorrimento blocchi + puntatori ---
        changed_ptrs = set(edits)
        shared = [i for i, e in enumerate(CACHED_ENTRIES)
                  if i != idx and any(p in changed_ptrs for p, _s in e["blocks"])]
        try:
            _apply_edits(edits, creates, row, entry)
        except ValueError as ex:
            self.report({'ERROR'}, f"Salvataggio annullato: {ex}")
            return {'CANCELLED'}

        for i in [idx] + shared:
            if i < len(props.rows):
                props.rows[i].modified = True
        for i, e in enumerate(CACHED_ENTRIES):
            if i < len(props.rows):
                props.rows[i].label = _row_label(e)

        parts = [f"{entry['label']}: {len(edits)} blocchi riscritti",
                 f"keyframe {ctx.keys_before} -> {ctx.keys_after}"]
        if ctx.tracks_new:
            parts.append(f"{ctx.tracks_new} tracce nuove")
        if creates:
            parts.append("blocchi creati: " + ", ".join(SLOT_SPECS[s][0] for s in sorted(creates)))
        if shared:
            parts.append("blocchi condivisi, cambiate anche le anim: " + ", ".join(str(i) for i in shared))
        self.report({'INFO'}, " | ".join(parts))
        if warnings:
            self.report({'WARNING'}, " | ".join(warnings[:6]))
        return {'FINISHED'}


class BINSTUDIO_OT_replace_mot(Operator, ImportHelper):
    bl_idname = "binstudio.replace_mot"
    bl_label  = "Replace (.mot)"
    bl_description = (
        "Sostituisce l'animazione selezionata con un file .mot. Le sezioni presenti nel .mot "
        "(lower, upper, face, hand) sostituiscono quelle originali; le altre restano. "
        "Gli offset del .bin vengono ricalcolati. Temporaneo: il file su disco non viene toccato"
    )

    filename_ext = ".mot"
    filter_glob: StringProperty(default="*.mot", options={'HIDDEN'})

    def invoke(self, context, event):
        props = context.scene.bin_studio
        if CACHED_BIN is None or not props.rows:
            self.report({'ERROR'}, "Nessun .bin caricato.")
            return {'CANCELLED'}
        if _show_src_guard(self):
            return {'CANCELLED'}
        folder = os.path.dirname(bpy.path.abspath(props.bin_path))
        if folder:
            self.filepath = folder + os.sep
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        global CACHED_ENTRIES, CACHED_BIN
        props = context.scene.bin_studio

        if not CACHED_ENTRIES or CACHED_BIN is None or not props.rows:
            self.report({'ERROR'}, "Nessun .bin caricato.")
            return {'CANCELLED'}

        if _show_src_guard(self):
            return {'CANCELLED'}

        idx = max(0, min(props.row_index, len(CACHED_ENTRIES) - 1))
        entry = CACHED_ENTRIES[idx]
        row = entry["table_row"]

        try:
            with open(self.filepath, "rb") as f:
                mot = f.read()
        except Exception as ex:
            self.report({'ERROR'}, f"Impossibile leggere il .mot: {ex}")
            return {'CANCELLED'}

        try:
            edits, creates, warnings, info = plan_replace(mot, entry, row)
        except ValueError as ex:
            self.report({'ERROR'}, f"Replace annullato: {ex}")
            return {'CANCELLED'}

        if not edits and not creates:
            self.report({'INFO'}, f"{entry['label']}: il .mot e' identico all'animazione attuale.")
            return {'FINISHED'}

        label = entry["label"]
        try:
            _apply_edits(edits, creates, row, entry)
        except ValueError as ex:
            self.report({'ERROR'}, f"Replace annullato: {ex}")
            return {'CANCELLED'}

        props.rows[idx].modified = True
        for i, e in enumerate(CACHED_ENTRIES):
            if i < len(props.rows):
                props.rows[i].label = _row_label(e)

        names = lambda slots: ", ".join(SLOT_NAMES[s] for s in slots) or "-"
        parts = [f"{label}: sostituiti [{names(info['replaced'])}]", f"mantenuti [{names(info['kept'])}]"]
        if info["isolated"]:
            parts.append(f"blocchi condivisi isolati [{names(info['isolated'])}] (le altre anim non cambiano)")
        if info["loop_fixed"]:
            parts.append(f"loop aggiornato su [{names(info['loop_fixed'])}]")
        self.report({'INFO'}, " | ".join(parts))
        if warnings:
            self.report({'WARNING'}, " | ".join(warnings[:6]))

        # Mostra subito la nuova animazione
        try:
            bpy.ops.binstudio.load_motion_row()
        except Exception as ex:
            self.report({'WARNING'}, f"Animazione sostituita ma non ricaricata: {ex}")
        return {'FINISHED'}


SCOPE_SLOTS = {'ALL': None, 'LOWER': {0}, 'UPPER': {1}, 'FACE': {2}}
SCOPE_NAMES = {'ALL': "tutto", 'LOWER': "solo lower", 'UPPER': "solo upper", 'FACE': "solo face"}


def _show_src_guard(op):
    """True (e errore riportato) se l'armatura sta mostrando un'animazione del bin secondario."""
    if SHOWING_SRC:
        op.report({'ERROR'}, "Stai visualizzando un'animazione del bin secondario: "
                             "seleziona (o ricarica) un'animazione del bin principale.")
        return True
    return False


class BINSTUDIO_OT_load_bin2(Operator):
    bl_idname = "binstudio.load_bin2"
    bl_label  = "Analizza bin secondario"
    bl_description = "Legge il bin secondario (sola lettura, usato come sorgente di animazioni)"

    def execute(self, context):
        global CACHED2_ENTRIES, CACHED2_BIN
        sc = context.scene
        props = sc.bin_studio
        path = bpy.path.abspath(props.bin2_path)

        if not os.path.isfile(path):
            self.report({'ERROR'}, "Seleziona un file .bin secondario valido.")
            return {'CANCELLED'}

        result = read_bin_entries(path)
        if not result:
            self.report({'ERROR'}, "Nessuna animazione trovata nel bin secondario.")
            return {'CANCELLED'}

        CACHED2_ENTRIES, data, _ds, _nr = result
        CACHED2_BIN = bytes(data)

        props.rows2.clear()
        for e in CACHED2_ENTRIES:
            item = props.rows2.add()
            item.label = _row_label(e)
            item.row_index = e["table_row"]
            item.modified = False

        sc.bin_studio_loading = True      # non far partire l'anteprima da sola
        try:
            props.row_index2 = 0
        finally:
            sc.bin_studio_loading = False
        self.report({'INFO'}, f"Bin secondario: {len(CACHED2_ENTRIES)} animazioni")
        return {'FINISHED'}


class BINSTUDIO_OT_load_motion_row2(Operator):
    bl_idname = "binstudio.load_motion_row2"
    bl_label  = "Anteprima (bin secondario)"
    bl_description = "Carica sull'armatura l'animazione selezionata nel bin secondario"

    def execute(self, context):
        global SHOWING_SRC
        sc = context.scene
        props = sc.bin_studio
        arm = _get_active_armature()

        if not arm:
            self.report({'ERROR'}, "Nessuna armatura trovata in scena!")
            return {'CANCELLED'}
        if not CACHED2_ENTRIES or not props.rows2:
            return {'CANCELLED'}

        idx = max(0, min(props.row_index2, len(CACHED2_ENTRIES) - 1))
        entry = CACHED2_ENTRIES[idx]

        sc.bin_studio_loading = True
        try:
            ok, max_frame = apply_mot_bytes(entry["bytes"], arm)
            if ok and props.autoplay and not context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
                context.scene.frame_current = 0
                bpy.ops.screen.animation_play()
        finally:
            sc.bin_studio_loading = False

        if not ok:
            self.report({'ERROR'}, "Caricamento fallito")
            return {'CANCELLED'}

        SHOWING_SRC = True
        self.report({'INFO'}, f"[secondario] {entry['label']}: {max_frame} frames")
        return {'FINISHED'}


class BINSTUDIO_OT_step_row2(Operator):
    bl_idname = "binstudio.step_row2"
    bl_label  = "Step (secondario)"
    delta: IntProperty(default=1)

    def execute(self, context):
        props = context.scene.bin_studio
        n = len(props.rows2)
        if not n:
            return {'CANCELLED'}
        props.row_index2 = (props.row_index2 + self.delta) % n
        return {'FINISHED'}


class BINSTUDIO_OT_replace_from_src(Operator):
    bl_idname = "binstudio.replace_from_src"
    bl_label  = "Replace dal bin secondario"
    bl_description = (
        "Sostituisce l'animazione selezionata del bin principale con quella selezionata del "
        "bin secondario (tutto, solo lower, solo upper o solo face). Gli slot vuoti vengono "
        "riempiti in fondo al file. Temporaneo: il file su disco non viene toccato"
    )

    def execute(self, context):
        global CACHED_ENTRIES, CACHED_BIN
        props = context.scene.bin_studio

        if not CACHED_ENTRIES or CACHED_BIN is None or not props.rows:
            self.report({'ERROR'}, "Nessun .bin principale caricato.")
            return {'CANCELLED'}
        if not CACHED2_ENTRIES or not props.rows2:
            self.report({'ERROR'}, "Analizza prima il bin secondario.")
            return {'CANCELLED'}

        idx = max(0, min(props.row_index, len(CACHED_ENTRIES) - 1))
        idx2 = max(0, min(props.row_index2, len(CACHED2_ENTRIES) - 1))
        entry = CACHED_ENTRIES[idx]
        src = CACHED2_ENTRIES[idx2]
        row = entry["table_row"]
        scope = props.replace_scope

        try:
            edits, creates, warnings, info = plan_replace(src["bytes"], entry, row, SCOPE_SLOTS[scope])
        except ValueError as ex:
            self.report({'ERROR'}, f"Replace annullato: {ex}")
            return {'CANCELLED'}

        if not edits and not creates:
            self.report({'INFO'}, f"{entry['label']}: nessuna differenza, l'animazione e' gia' uguale.")
            return {'FINISHED'}

        label = entry["label"]
        try:
            _apply_edits(edits, creates, row, entry)
        except ValueError as ex:
            self.report({'ERROR'}, f"Replace annullato: {ex}")
            return {'CANCELLED'}

        props.rows[idx].modified = True
        for i, e in enumerate(CACHED_ENTRIES):
            if i < len(props.rows):
                props.rows[i].label = _row_label(e)

        names = lambda slots: ", ".join(SLOT_NAMES[s] for s in slots) or "-"
        parts = [f"{label} <- [sec] {src['label']} ({SCOPE_NAMES[scope]})",
                 f"sostituiti [{names(info['replaced'])}]"]
        if info["added"]:
            parts.append(f"aggiunti in coda al file [{names(info['added'])}]")
        if info["kept"] and scope == 'ALL':
            parts.append(f"mantenuti [{names(info['kept'])}]")
        if info["isolated"]:
            parts.append(f"blocchi condivisi isolati [{names(info['isolated'])}] (le altre anim non cambiano)")
        if info["loop_fixed"]:
            parts.append(f"loop aggiornato su [{names(info['loop_fixed'])}]")
        self.report({'INFO'}, " | ".join(parts))
        if warnings:
            self.report({'WARNING'}, " | ".join(warnings[:6]))

        # Mostra subito il risultato (anteprima del principale)
        try:
            bpy.ops.binstudio.load_motion_row()
        except Exception as ex:
            self.report({'WARNING'}, f"Animazione sostituita ma non ricaricata: {ex}")
        return {'FINISHED'}


class BINSTUDIO_OT_save_bin_file(Operator, ExportHelper):
    bl_idname = "binstudio.save_bin_file"
    bl_label  = "Salva .bin su disco"
    bl_description = (
        "Scrive su disco il .bin con tutte le modifiche fatte in memoria. "
        "Il file browser parte dal .bin aperto: puoi sovrascriverlo o scegliere un altro nome"
    )

    filename_ext = ".bin"
    filter_glob: StringProperty(default="*.*", options={'HIDDEN'})
    check_extension = None  # non forzare l'estensione scelta dall'utente

    def invoke(self, context, event):
        if CACHED_BIN is None:
            self.report({'ERROR'}, "Nessun .bin caricato.")
            return {'CANCELLED'}
        props = context.scene.bin_studio
        path = bpy.path.abspath(props.bin_path)
        if path:
            self.filepath = path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        global CACHED_ENTRIES, CACHED_BIN
        if CACHED_BIN is None:
            self.report({'ERROR'}, "Nessun .bin caricato.")
            return {'CANCELLED'}

        try:
            with open(self.filepath, "wb") as f:
                f.write(bytes(CACHED_BIN))
        except Exception as e:
            self.report({'ERROR'}, f"Salvataggio fallito: {e}")
            return {'CANCELLED'}

        props = context.scene.bin_studio
        for item in props.rows:
            item.modified = False

        self.report({'INFO'}, f"Salvato: {self.filepath} ({len(CACHED_BIN)} byte)")
        return {'FINISHED'}


# ============================================================
# PANNELLO UI
# ============================================================

class BINSTUDIO_PT_panel(Panel):
    bl_label      = "BIN Animation Studio"
    bl_idname     = "BINSTUD_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category   = "BIN Studio"

    def draw(self, context):
        sc    = context.scene
        props = sc.bin_studio
        layout = self.layout

        layout.prop(props, "bin_path", text="")
        layout.operator("binstudio.load_bin", icon='FILE_REFRESH', text="Analizza .bin")

        arm = _get_active_armature()
        if arm:
            layout.label(text=f"Rig attivo: {arm.name}", icon="ARMATURE_DATA")
        else:
            layout.label(text="Nessun rig selezionato!", icon="ERROR")

        if props.rows:
            layout.separator()
            layout.template_list("BINSTUDIO_UL_rows", "", props, "rows", props, "row_index", rows=10)

            row = layout.row(align=True)
            row.operator("binstudio.step_row", text="Prev", icon='TRIA_LEFT').delta = -1
            row.operator("binstudio.step_row", text="Next", icon='TRIA_RIGHT').delta = 1

            layout.prop(props, "autoplay")
            layout.operator("binstudio.load_motion_row", text="Ricarica Animazione", icon='PLAY')
            layout.operator("binstudio.replace_mot", text="Replace da .mot...", icon='IMPORT')

            layout.separator()
            box = layout.box()
            box.label(text="Salvataggio", icon='FILE_TICK')
            col = box.column(align=True)
            col.operator("binstudio.save_anim", text="Salva animazione (temporaneo)", icon='FILE_TICK')
            col.operator("binstudio.save_bin_file", text="Salva .bin su disco...", icon='EXPORT')

            n_mod = sum(1 for r in props.rows if r.modified)
            if n_mod:
                box.label(text=f"* {n_mod} modificate, non salvate su disco", icon='ERROR')

            layout.label(text=f"{len(props.rows)} animazioni nel bin")

        # --- bin secondario (sorgente) ---
        layout.separator()
        box2 = layout.box()
        box2.label(text="Bin secondario (sorgente)", icon='LINKED')
        box2.prop(props, "bin2_path", text="")
        box2.operator("binstudio.load_bin2", icon='FILE_REFRESH', text="Analizza bin secondario")
        if props.rows2:
            box2.template_list("BINSTUDIO_UL_rows", "src", props, "rows2", props, "row_index2", rows=6)
            r2 = box2.row(align=True)
            r2.operator("binstudio.step_row2", text="Prev", icon='TRIA_LEFT').delta = -1
            r2.operator("binstudio.step_row2", text="Next", icon='TRIA_RIGHT').delta = 1
            box2.operator("binstudio.load_motion_row2", text="Anteprima", icon='PLAY')
            box2.label(text="In anteprima: " + ("bin secondario" if SHOWING_SRC else "bin principale"), icon='INFO')
            if props.rows:
                col2 = box2.column(align=True)
                col2.prop(props, "replace_scope", text="")
                col2.operator("binstudio.replace_from_src", text="Replace nel bin principale", icon='IMPORT')
            box2.label(text=f"{len(props.rows2)} animazioni nel bin secondario")


# ============================================================
# REGISTRAZIONE
# ============================================================

classes = [
    BINRowItem,
    BINSTUDIO_UL_rows,
    BINStudioProps,
    BINSTUDIO_OT_load_bin,
    BINSTUDIO_OT_load_motion_row,
    BINSTUDIO_OT_step_row,
    BINSTUDIO_OT_save_anim,
    BINSTUDIO_OT_replace_mot,
    BINSTUDIO_OT_load_bin2,
    BINSTUDIO_OT_load_motion_row2,
    BINSTUDIO_OT_step_row2,
    BINSTUDIO_OT_replace_from_src,
    BINSTUDIO_OT_save_bin_file,
    BINSTUDIO_PT_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bin_studio = PointerProperty(type=BINStudioProps)
    bpy.types.Scene.bin_studio_loading = BoolProperty(default=False)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.bin_studio
    if hasattr(bpy.types.Scene, "bin_studio_loading"):
        del bpy.types.Scene.bin_studio_loading


if __name__ == "__main__":
    register()