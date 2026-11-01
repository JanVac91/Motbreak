bl_info = {
    "name": "Outbreak Retarget HD",
    "author": "CarlVercetti & Claude",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > OB Retarget",
    "description": "Converte animazioni FBX/BVH (Mixamo, mocap, UE, Rigify...) sul rig HD di RE Outbreak (Node1-21)",
    "category": "Animation",
}

"""
Outbreak Retarget HD
====================
Trasferisce l'animazione di un'armatura qualsiasi (FBX o BVH importato) sul rig
HD di Resident Evil Outbreak (Node1 e Node2 ossa).

Come lavora
-----------
* Rotazioni: per ogni osso mappato calcola quanto l'osso sorgente si e' ruotato
  rispetto alla sua posa di riferimento (rest o un frame scelto) e applica la
  stessa rotazione all'osso Outbreak rispetto alla sua rest pose (T-pose).
  Il calcolo avviene nello spazio del personaggio (alto / sinistra / avanti
  ricavati dalle ossa), quindi orientamento dell'oggetto, roll delle ossa e
  scala dell'import (Mixamo 0.01, Z-su, Y-su...) non contano.
* Spostamento: la posizione del bacino sorgente viene scalata sulle proporzioni
  Outbreak e divisa in due:
      orizzontale -> Node1.location   (come i .mot originali, parte da 0)
      verticale   -> Node2.location   (scostamento dai 110 di riposo, come
                                       l'importer: l'exporter risomma l'head.y)
* Uscita: una nuova action sul rig, rotazioni Euler XYZ, 60 fps, dal frame 0,
  pronta per Mot_Exporter_Standalone.
* Node22-27 (faccia) e dita/punte dei piedi non vengono mai toccati.
"""

import math
import re

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty,
                       FloatProperty, IntProperty, PointerProperty,
                       StringProperty)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Matrix, Vector

OUT_FPS = 60

# ----------------------------------------------------------------------------
# Mappatura: nodo Outbreak -> nomi possibili dell'osso sorgente
# side: "L" / "R" genera le varianti LeftX, X_L, X.L, L_X ...; None = osso centrale
# I nomi vengono confrontati "normalizzati": minuscolo, solo lettere e numeri,
# senza prefissi tipo "mixamorig:", "mixamorig1_", "Bip01 ", "DEF-".
# ----------------------------------------------------------------------------
NODE_MAP = [
    ("Node3",  "Bacino",            None, ["hips", "pelvis", "hip"]),
    ("Node4",  "Coscia SX",         "L",  ["upleg", "thigh", "upperleg", "femur"]),
    ("Node5",  "Ginocchio SX",      "L",  ["leg", "shin", "calf", "lowerleg", "knee", "tibia"]),
    ("Node6",  "Piede SX",          "L",  ["foot", "ankle"]),
    ("Node7",  "Coscia DX",         "R",  ["upleg", "thigh", "upperleg", "femur"]),
    ("Node8",  "Ginocchio DX",      "R",  ["leg", "shin", "calf", "lowerleg", "knee", "tibia"]),
    ("Node9",  "Piede DX",          "R",  ["foot", "ankle"]),
    ("Node10", "Busto inferiore",   None, ["spine", "spine01", "lowerback", "abdomen", "waist"]),
    ("Node11", "Busto superiore",   None, ["spine2", "spine03", "spine3", "upperchest", "chest",
                                           "spine02", "spine1"]),
    ("Node12", "Spalla SX",         "L",  ["shoulder", "clavicle", "collar", "clav"]),
    ("Node13", "Braccio SX",        "L",  ["arm", "upperarm", "uparm", "humerus"]),
    ("Node14", "Avambraccio SX",    "L",  ["forearm", "lowerarm", "elbow"]),
    ("Node15", "Polso SX",          "L",  ["hand", "wrist"]),
    ("Node16", "Spalla DX",         "R",  ["shoulder", "clavicle", "collar", "clav"]),
    ("Node17", "Braccio DX",        "R",  ["arm", "upperarm", "uparm", "humerus"]),
    ("Node18", "Avambraccio DX",    "R",  ["forearm", "lowerarm", "elbow"]),
    ("Node19", "Polso DX",          "R",  ["hand", "wrist"]),
    ("Node20", "Collo",             None, ["neck", "neck01", "neck1"]),
    ("Node21", "Testa",             None, ["head"]),
]
ROT_NODES = [n[0] for n in NODE_MAP]
PREFIXES = ("mixamorig", "bip001", "bip01", "ccbase", "def")


def norm_name(name):
    n = name.split(":")[-1].split("|")[-1].lower()
    n = re.sub(r"[^a-z0-9]", "", n)
    for p in PREFIXES:
        if n.startswith(p) and len(n) > len(p):
            n = re.sub(r"^\d+", "", n[len(p):])
            break
    return n


def side_variants(base, side):
    if side is None:
        return [base]
    w = "left" if side == "L" else "right"
    s = side.lower()
    return [w + base, base + w, base + s, s + base]


def auto_map(src_arm):
    """Ritorna {nodo: nome osso sorgente} usando i nomi noti."""
    lookup = {}
    for b in src_arm.data.bones:
        lookup.setdefault(norm_name(b.name), b.name)
    used, result = set(), {}
    for node, _label, side, bases in NODE_MAP:
        found = ""
        for base in bases:
            for cand in side_variants(base, side):
                bn = lookup.get(cand)
                if bn and bn not in used:
                    found = bn
                    break
            if found:
                break
        if found:
            used.add(found)
        result[node] = found
    return result


# ----------------------------------------------------------------------------
# Proprieta'
# ----------------------------------------------------------------------------
def poll_armature(_self, obj):
    return obj.type == 'ARMATURE'


def poll_outbreak(_self, obj):
    return obj.type == 'ARMATURE' and "Node1" in obj.data.bones and "Node2" in obj.data.bones


class OBR_MapItem(PropertyGroup):
    node: StringProperty()
    label: StringProperty()
    source: StringProperty(name="Osso sorgente")


class OBR_Settings(PropertyGroup):
    source: PointerProperty(name="Sorgente", type=bpy.types.Object, poll=poll_armature,
                            description="Armatura animata importata da FBX o BVH")
    target: PointerProperty(name="Outbreak HD", type=bpy.types.Object, poll=poll_outbreak,
                            description="Rig Outbreak HD (Node1 e Node2 ossa)")
    mapping: CollectionProperty(type=OBR_MapItem)
    ref_pose: EnumProperty(
        name="Posa di riferimento",
        items=[('REST', "Rest", "La rest pose della sorgente e' una T-pose"),
               ('FRAME', "Frame", "Un frame della sorgente in cui il personaggio e' in T-pose")],
        default='REST')
    ref_frame: IntProperty(name="Frame T-pose", default=0)
    src_fps: FloatProperty(name="FPS sorgente", default=30.0, min=1.0, max=1000.0,
                           description="Mixamo FBX: 30. Mocap BVH: spesso 120 (CMU) o 60")
    use_range: BoolProperty(name="Intervallo personalizzato", default=False)
    frame_from: IntProperty(name="Da", default=1)
    frame_to: IntProperty(name="A", default=100)
    auto_scale: BoolProperty(name="Scala automatica", default=True,
                             description="Scala lo spostamento con il rapporto tra le lunghezze delle gambe")
    scale: FloatProperty(name="Scala", default=1.0, min=0.0001, soft_max=1000.0)
    in_place: BoolProperty(name="Sul posto", default=False,
                           description="Nessuno spostamento orizzontale su Node1")
    ground_lock: BoolProperty(name="Blocca a terra", default=False,
                              description="Alza Node2 se una caviglia scende sotto la sua altezza di riposo")
    key_step: IntProperty(name="Key ogni N frame", default=1, min=1, max=30,
                          description="1 = un keyframe per frame (60 fps). 2 = meta' dei keyframe")


# ----------------------------------------------------------------------------
# Funzioni di calcolo
# ----------------------------------------------------------------------------
def rot3(m):
    return m.to_3x3().normalized()


WORLD_UP = Vector((0.0, 0.0, 1.0))
# Convenzione Outbreak nello spazio armatura: +X sinistra, +Y alto, +Z avanti
OUTBREAK_FRAME = Matrix.Identity(3)


def char_frame(hip, head, lthigh, rthigh, up=None):
    """Matrice 3x3 con colonne (sinistra, alto, avanti) del personaggio.
    up: verticale vera; se manca o non e' plausibile si usa bacino -> testa."""
    body_up = (head - hip).normalized()
    if up is None or up.dot(body_up) < 0.7:
        up = body_up
    up = up.normalized()
    left = lthigh - rthigh
    left = (left - left.dot(up) * up).normalized()
    fwd = left.cross(up).normalized()
    return Matrix((left, up, fwd)).transposed()


def bone_depth(b):
    d = 0
    while b.parent:
        d += 1
        b = b.parent
    return d


def ensure_fcurve(action, obj, path, index, group):
    if hasattr(action, "fcurve_ensure_for_datablock"):  # Blender 4.4+
        return action.fcurve_ensure_for_datablock(obj, path, index=index, group_name=group)
    fc = action.fcurves.find(path, index=index)
    if fc is None:
        fc = action.fcurves.new(path, index=index, action_group=group)
    return fc


def write_curve(action, obj, path, index, group, frames, values):
    fc = ensure_fcurve(action, obj, path, index, group)
    kps = fc.keyframe_points
    kps.add(len(frames))
    co = []
    for f, v in zip(frames, values):
        co += [float(f), float(v)]
    kps.foreach_set("co", co)
    for kp in kps:
        kp.interpolation = 'BEZIER'
        kp.handle_left_type = 'AUTO_CLAMPED'
        kp.handle_right_type = 'AUTO_CLAMPED'
    fc.update()


def get_mapping(settings):
    src = settings.source
    return {it.node: it.source for it in settings.mapping
            if it.source and it.source in src.data.bones}


def retarget(context, s):
    scene = context.scene
    src, tgt = s.source, s.target
    if src is None or tgt is None:
        raise RuntimeError("Scegli sorgente e rig Outbreak HD")
    if src == tgt:
        raise RuntimeError("Sorgente e destinazione sono la stessa armatura")
    for n in ("Node1", "Node2", "Node3", "Node4", "Node6", "Node7", "Node9"):
        if n not in tgt.data.bones:
            raise RuntimeError(f"Il rig di destinazione non ha {n}: serve il modello HD")
    if tgt.data.bones["Node2"].use_connect:
        raise RuntimeError("Node2 e' connesso a Node1, quindi non puo' muoversi in verticale. "
                           "Scollegalo (disconnect_node2.py) e riprova")
    act = src.animation_data.action if src.animation_data else None
    if act is None:
        raise RuntimeError("La sorgente non ha un'animazione (action)")

    if len(s.mapping) == 0:
        fill_mapping(s)
    mp = get_mapping(s)
    for n, what in (("Node3", "bacino"), ("Node4", "coscia SX"), ("Node7", "coscia DX"),
                    ("Node6", "piede SX"), ("Node9", "piede DX")):
        if n not in mp:
            raise RuntimeError(f"Manca l'osso sorgente per {n} ({what}): assegnalo nella lista")
    head_node = next((n for n in ("Node21", "Node20", "Node11", "Node10") if n in mp), None)
    if head_node is None:
        raise RuntimeError("Serve almeno un osso del busto, collo o testa nella mappatura")

    # --- intervallo e campionamento ------------------------------------------
    if s.use_range:
        f0, f1 = float(s.frame_from), float(s.frame_to)
    else:
        f0, f1 = act.frame_range[0], act.frame_range[1]
    if f1 <= f0:
        raise RuntimeError("Intervallo di frame non valido")
    step_src = s.src_fps / OUT_FPS
    n_out = int(math.floor((f1 - f0) / step_src + 1e-6)) + 1

    # --- posa di riferimento della sorgente (spazio mondo) -----------------
    depsgraph = context.evaluated_depsgraph_get()
    if s.ref_pose == 'REST':
        W = src.matrix_world
        ref = {b.name: W @ b.matrix_local for b in src.data.bones}
    else:
        scene.frame_set(s.ref_frame)
        depsgraph = context.evaluated_depsgraph_get()
        se = src.evaluated_get(depsgraph)
        W = se.matrix_world
        ref = {pb.name: W @ pb.matrix for pb in se.pose.bones}

    def src_head(m):
        return m.translation.copy()

    # Sorgente: verticale = Z del mondo (FBX e BVH in Blender sono Z-su)
    Fs = char_frame(src_head(ref[mp["Node3"]]), src_head(ref[mp[head_node]]),
                    src_head(ref[mp["Node4"]]), src_head(ref[mp["Node7"]]), up=WORLD_UP)

    # --- rest della destinazione (spazio armatura) ---------------------------
    tb = tgt.data.bones
    rest = {b.name: b.matrix_local.copy() for b in tb}
    rest_inv = {k: v.inverted() for k, v in rest.items()}
    order = sorted(tb, key=bone_depth)
    if rest["Node4"].translation.x < rest["Node7"].translation.x:
        raise RuntimeError("Node4 non e' sul lato +X: il rig non segue la convenzione Outbreak")
    Ft = OUTBREAK_FRAME
    up_t = Ft.col[1].copy()

    # M porta vettori/rotazioni dallo spazio mondo sorgente allo spazio armatura Outbreak
    M = Ft @ Fs.transposed()
    MT = M.transposed()

    # --- scala: lunghezza gamba (bacino -> media caviglie) lungo "alto" ---------
    s_up = Fs.col[1]
    s_ank = (src_head(ref[mp["Node6"]]) + src_head(ref[mp["Node9"]])) * 0.5
    s_leg = (src_head(ref[mp["Node3"]]) - s_ank).dot(s_up)
    t_ank = (rest["Node6"].translation + rest["Node9"].translation) * 0.5
    t_leg = (rest["Node3"].translation - t_ank).dot(up_t)
    if s.auto_scale:
        if s_leg <= 1e-6:
            raise RuntimeError("Non riesco a misurare la gamba della sorgente: controlla la posa di riferimento")
        scale = t_leg / s_leg
        s.scale = scale
    else:
        scale = s.scale
    rest_ankle_h = min(rest["Node6"].translation.dot(up_t), rest["Node9"].translation.dot(up_t))
    floor_h = rest["Node1"].translation.dot(up_t)

    rot_map = [(n, mp[n]) for n in ROT_NODES if n in mp and n in rest]
    ref_rot_T = {n: rot3(ref[b]).transposed() for n, b in rot_map}
    rest_rot = {n: rot3(rest[n]) for n, _b in rot_map}
    hip_ref = src_head(ref[mp["Node3"]])

    # --- campionamento ------------------------------------------------------
    eul = {n: [] for n, _b in rot_map}
    prev = {}
    loc1, loc2 = [], []
    hip0 = None
    for i in range(n_out):
        t = f0 + i * step_src
        fi = int(math.floor(t + 1e-9))
        scene.frame_set(fi, subframe=max(0.0, t - fi))
        depsgraph = context.evaluated_depsgraph_get()
        se = src.evaluated_get(depsgraph)
        W = se.matrix_world
        spb = se.pose.bones

        hip_w = (W @ spb[mp["Node3"]].matrix).translation
        if hip0 is None:
            hip0 = hip_w.copy()
        d_h = M @ (hip_w - hip0) * scale
        horiz = d_h - d_h.dot(up_t) * up_t
        if s.in_place:
            horiz = Vector((0.0, 0.0, 0.0))
        vert = (M @ (hip_w - hip_ref) * scale).dot(up_t)

        des = {}
        for n, b in rot_map:
            delta = rot3(W @ spb[b].matrix) @ ref_rot_T[n]
            des[n] = (M @ delta @ MT) @ rest_rot[n]

        pose, basis = {}, {}
        for b in order:
            nm = b.name
            if b.parent:
                cand = pose[b.parent.name] @ rest_inv[b.parent.name] @ rest[nm]
            else:
                cand = rest[nm].copy()
            if nm == "Node1":
                want = Matrix.Translation(horiz) @ cand
            elif nm == "Node2":
                want = Matrix.Translation(vert * up_t) @ cand
            elif nm in des:
                want = Matrix.Translation(cand.translation) @ des[nm].to_4x4()
            else:
                want = cand
            pose[nm] = want
            basis[nm] = cand.inverted() @ want

        if s.ground_lock:
            ank = min(pose["Node6"].translation.dot(up_t), pose["Node9"].translation.dot(up_t))
            deficit = (rest_ankle_h - floor_h) - (ank - floor_h)
            if deficit > 0:
                vert += deficit
                cand2 = pose["Node2"] @ basis["Node2"].inverted()
                basis["Node2"] = cand2.inverted() @ (Matrix.Translation(vert * up_t) @ cand2)

        loc1.append(basis["Node1"].translation.copy())
        loc2.append(basis["Node2"].translation.copy())
        for n, _b in rot_map:
            q = basis[n].to_quaternion()
            e = q.to_euler('XYZ', prev[n]) if n in prev else q.to_euler('XYZ')
            prev[n] = e
            eul[n].append(e.copy())

    # --- scrittura dell'action -----------------------------------------------
    keep = list(range(0, n_out, s.key_step))
    if keep[-1] != n_out - 1:
        keep.append(n_out - 1)

    for pb in tgt.pose.bones:
        if pb.name in ROT_NODES or pb.name in ("Node1", "Node2"):
            pb.rotation_mode = 'XYZ'
            pb.location = (0, 0, 0)
            pb.rotation_euler = (0, 0, 0)

    name = f"{act.name}_OB"
    new_act = bpy.data.actions.new(name)
    new_act.use_fake_user = True
    tgt.animation_data_create()
    tgt.animation_data.action = new_act

    def put_loc(bone, vals):
        for ax in range(3):
            col = [vals[k][ax] for k in keep]
            if max(abs(v) for v in col) > 1e-4:
                write_curve(new_act, tgt, f'pose.bones["{bone}"].location', ax, bone, keep, col)

    put_loc("Node1", loc1)
    put_loc("Node2", loc2)
    for n, _b in rot_map:
        for ax in range(3):
            write_curve(new_act, tgt, f'pose.bones["{n}"].rotation_euler', ax, n, keep,
                        [eul[n][k][ax] for k in keep])

    scene.render.fps = OUT_FPS
    scene.render.fps_base = 1.0
    scene.frame_start = 0
    scene.frame_end = n_out - 1
    scene.frame_set(0)
    missing = [n for n in ROT_NODES if n not in mp]
    return name, n_out, scale, missing


def fill_mapping(s):
    s.mapping.clear()
    found = auto_map(s.source) if s.source else {}
    for node, label, _side, _bases in NODE_MAP:
        it = s.mapping.add()
        it.node = node
        it.label = label
        it.source = found.get(node, "")


# ----------------------------------------------------------------------------
# Operatori
# ----------------------------------------------------------------------------
class OBR_OT_build_map(Operator):
    bl_idname = "obr.build_map"
    bl_label = "Rileva ossa"
    bl_description = "Riempie la mappatura riconoscendo i nomi delle ossa (Mixamo, BVH, UE, Rigify, Biped)"

    def execute(self, context):
        s = context.scene.obr
        if s.source is None:
            self.report({'ERROR'}, "Scegli prima l'armatura sorgente")
            return {'CANCELLED'}
        fill_mapping(s)
        n = sum(1 for it in s.mapping if it.source)
        self.report({'INFO'}, f"Riconosciute {n} ossa su {len(s.mapping)}")
        return {'FINISHED'}


class OBR_OT_retarget(Operator):
    bl_idname = "obr.retarget"
    bl_label = "Converti animazione"
    bl_description = "Crea una nuova action sul rig Outbreak HD"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.obr
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            name, n, scale, missing = retarget(context, s)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        msg = f"Creata '{name}': {n} frame a {OUT_FPS} fps, scala {scale:.4f}"
        if missing:
            msg += f". Senza sorgente (restano fermi): {', '.join(missing)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ----------------------------------------------------------------------------
# Pannello
# ----------------------------------------------------------------------------
class OBR_PT_panel(Panel):
    bl_label = "Outbreak Retarget HD"
    bl_idname = "OBR_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "OB Retarget"

    def draw(self, context):
        s = context.scene.obr
        lay = self.layout
        col = lay.column(align=True)
        col.prop(s, "source")
        col.prop(s, "target")
        lay.operator("obr.build_map", icon='BONE_DATA')

        if len(s.mapping):
            box = lay.box()
            box.label(text="Mappatura (Node22-27 esclusi)")
            for it in s.mapping:
                row = box.row(align=True)
                row.alert = not it.source
                row.label(text=f"{it.node}  {it.label}")
                if s.source:
                    row.prop_search(it, "source", s.source.data, "bones", text="")
                else:
                    row.prop(it, "source", text="")

        box = lay.box()
        box.label(text="Opzioni")
        box.prop(s, "ref_pose")
        if s.ref_pose == 'FRAME':
            box.prop(s, "ref_frame")
        box.prop(s, "src_fps")
        box.prop(s, "use_range")
        if s.use_range:
            row = box.row(align=True)
            row.prop(s, "frame_from")
            row.prop(s, "frame_to")
        box.prop(s, "auto_scale")
        row = box.row()
        row.enabled = not s.auto_scale
        row.prop(s, "scale")
        box.prop(s, "in_place")
        box.prop(s, "ground_lock")
        box.prop(s, "key_step")

        lay.separator()
        lay.operator("obr.retarget", icon='ARMATURE_DATA')
        lay.label(text="Il rig Outbreak deve essere in T-pose in rest", icon='INFO')


classes = (OBR_MapItem, OBR_Settings, OBR_OT_build_map, OBR_OT_retarget, OBR_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.obr = PointerProperty(type=OBR_Settings)


def unregister():
    del bpy.types.Scene.obr
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
