bl_info = {
    "name": "PS2 BIN Animation Studio",
    "author": "CarlVercetti & Claude",
    "version": (2, 2, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BIN Studio",
    "description": "Parse .bin (header + offset table + .mot blocks) and preview animations on armature",
    "category": "Animation",
}

import bpy
import os
import struct
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty, PointerProperty
from bpy.types import Panel, Operator, PropertyGroup, UIList

# ============================================================
# LETTURA .BIN (formato semplice: header + tabella offset + .mot)
# Stessa logica di Mots_Extractor_Motbreak.py, adattata per restare
# in memoria invece di scrivere file separati su disco.
# ============================================================

def read_bin_entries(path):
    """
    Legge un .bin e ritorna una lista di dict:
      {"label": str, "bytes": bytes, "section_count": int}
    Una entry per riga della tabella (ogni riga = fino a 5 puntatori
    che vengono concatenati in un unico blob .mot, esattamente come
    fa Mots_Extractor_Motbreak.py).
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

        is_valid_entry = False
        for ptr in record:
            if ptr != 0xFFFFFFFF and ptr != 0:
                is_valid_entry = True
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
        sections_in_anim = 0

        for ptr in entry:
            if ptr == 0xFFFFFFFF or ptr == 0 or ptr >= len(data):
                continue
            try:
                if data[ptr:ptr+2] == b'\x02\x00':
                    size = struct.unpack_from("<I", data, ptr + 8)[0]
                    if size > 0 and (ptr + size) <= len(data):
                        combined.extend(data[ptr: ptr + size])
                        sections_in_anim += 1
            except Exception:
                continue

        if combined:
            entries.append({
                "label":         f"anim_{len(entries):03d} ({sections_in_anim} section)",
                "bytes":         bytes(combined),
                "section_count": sections_in_anim,
                "table_row":     i,
            })

    return entries if entries else None


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


def _on_row_selection(self, context):
    sc = context.scene
    if getattr(sc, "bin_studio_loading", False):
        return
    try:
        bpy.ops.binstudio.load_motion_row()
    except Exception as e:
        print("[BIN Studio] Errore caricamento animazione:", e)


class BINSTUDIO_UL_rows(UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_prop, index):
        layout.label(text=item.label, icon="ANIM")


class BINStudioProps(PropertyGroup):
    bin_path: StringProperty(
        name="File .bin",
        description="File .bin da analizzare",
        subtype='FILE_PATH'
    )
    rows: CollectionProperty(type=BINRowItem)
    row_index: IntProperty(default=0, update=_on_row_selection)
    autoplay: BoolProperty(name="Autoplay", default=True)


CACHED_ENTRIES = None  # lista di dict {"label","bytes","section_count","table_row"}


# ============================================================
# OPERATORI
# ============================================================

class BINSTUDIO_OT_load_bin(Operator):
    bl_idname = "binstudio.load_bin"
    bl_label  = "Analizza .bin"

    def execute(self, context):
        global CACHED_ENTRIES
        sc = context.scene
        props = sc.bin_studio
        path = bpy.path.abspath(props.bin_path)

        if not os.path.isfile(path):
            self.report({'ERROR'}, "Seleziona un file .bin valido.")
            return {'CANCELLED'}

        CACHED_ENTRIES = read_bin_entries(path)
        if not CACHED_ENTRIES:
            self.report({'ERROR'}, "Nessuna animazione trovata in questo .bin.")
            return {'CANCELLED'}

        props.rows.clear()
        for e in CACHED_ENTRIES:
            item = props.rows.add()
            item.label = f"{e['label']}  [{len(e['bytes'])}B]"
            item.row_index = e["table_row"]

        props.row_index = 0
        self.report({'INFO'}, f"Trovate {len(CACHED_ENTRIES)} animazioni nel .bin")
        return {'FINISHED'}


class BINSTUDIO_OT_load_motion_row(Operator):
    bl_idname = "binstudio.load_motion_row"
    bl_label  = "Carica Animazione"

    def execute(self, context):
        global CACHED_ENTRIES
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
            layout.label(text=f"{len(props.rows)} animazioni nel bin")


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