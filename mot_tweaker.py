bl_info = {
    "name": "MOT Animation Tweaker",
    "author": "CarlVercetti & Claude",
    "version": (3, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > MOT Tweaker",
    "description": "Tweak .mot animations with selective motion scaling and clean facial controls",
    "category": "Animation",
}

import bpy
import json
from bpy.props import FloatProperty, PointerProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup

_suppress_update = False

# Mappa delle ossa per gruppo di Scaling
BODY_GROUPS = {
    "torso": ["Node10", "Node11"],
    "hip":   ["Node2", "Node3"],
    "head":  ["Node20", "Node21"],
    "face":  ["Node22", "Node23", "Node24", "Node25", "Node26", "Node27"],
    "arms":  ["Node12", "Node13", "Node14", "Node15", "Node16", "Node17", "Node18", "Node19"],
    "legs":  ["Node4", "Node5", "Node6", "Node7", "Node8", "Node9"],
}

# ============================================================
# TWEAK GROUPS
# ============================================================

TWEAK_GROUPS = {

    # -- CONTROLLI FACCIALI --
    "eyebrows_rot_y": [
        {"bone": "Node23", "prop": "rotation_euler", "axis": 1, "weight": 1.0},
        {"bone": "Node25", "prop": "rotation_euler", "axis": 1, "weight": 1.0},
    ],
    "eyebrows_curve": [
        {"bone": "Node23", "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node25", "prop": "rotation_euler", "axis": 2, "weight": -1.0},
    ],
    "eyes_closed": [
        {"bone": "Node24", "prop": "rotation_euler", "axis": 0, "weight": 1.0},
        {"bone": "Node26", "prop": "rotation_euler", "axis": 0, "weight": 1.0},
    ],
    "jaw_open": [
        {"bone": "Node27", "prop": "rotation_euler", "axis": 0, "weight": 1.0},
    ],

    # -- BARICENTRO / ALTEZZA COMPLETO --
    "low_center": [
        {"bone": "Node2", "prop": "location",       "axis": 1, "weight":  1.0},
        {"bone": "Node4", "prop": "rotation_euler", "axis": 0, "weight":  0.3},
        {"bone": "Node7", "prop": "rotation_euler", "axis": 0, "weight":  0.3},
        {"bone": "Node5", "prop": "rotation_euler", "axis": 0, "weight": -0.5},
        {"bone": "Node8", "prop": "rotation_euler", "axis": 0, "weight": -0.5},
    ],
    "node2_height_only": [{"bone": "Node2", "prop": "location", "axis": 1, "weight": 1.0}],
    "twist_hip": [
        {"bone": "Node3",  "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node10", "prop": "rotation_euler", "axis": 2, "weight": -0.8},
        {"bone": "Node4",  "prop": "rotation_euler", "axis": 2, "weight": -0.8},
        {"bone": "Node7",  "prop": "rotation_euler", "axis": 2, "weight": -0.8},
    ],
    "spine_flex": [{"bone": "Node11", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "hunch": [
        {"bone": "Node10", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
        {"bone": "Node11", "prop": "rotation_euler", "axis": 0, "weight":  0.8},
        {"bone": "Node12", "prop": "rotation_euler", "axis": 0, "weight": -0.3},
        {"bone": "Node16", "prop": "rotation_euler", "axis": 0, "weight": -0.3},
        {"bone": "Node20", "prop": "rotation_euler", "axis": 0, "weight": -0.7},
        {"bone": "Node21", "prop": "rotation_euler", "axis": 0, "weight": -0.5},
    ],
    "lean": [
        {"bone": "Node10", "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node11", "prop": "rotation_euler", "axis": 2, "weight":  0.7},
        {"bone": "Node20", "prop": "rotation_euler", "axis": 2, "weight": -0.7},
    ],
    "leg_stance": [
        {"bone": "Node4", "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node7", "prop": "rotation_euler", "axis": 2, "weight": -1.0},
    ],
    "legs_rot_z": [
        {"bone": "Node4", "prop": "rotation_euler", "axis": 2, "weight": 1.0},
        {"bone": "Node7", "prop": "rotation_euler", "axis": 2, "weight": 1.0},
    ],
    "thighs_pitch": [
        {"bone": "Node4", "prop": "rotation_euler", "axis": 0, "weight": 1.0},
        {"bone": "Node7", "prop": "rotation_euler", "axis": 0, "weight": 1.0},
    ],
    "step_height": [
        {"bone": "Node4", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
        {"bone": "Node7", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
        {"bone": "Node5", "prop": "rotation_euler", "axis": 0, "weight": -0.6},
        {"bone": "Node8", "prop": "rotation_euler", "axis": 0, "weight": -0.6},
    ],
    "shoulder_l_x": [{"bone": "Node12", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "shoulder_l_y": [{"bone": "Node12", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "shoulder_l_z": [{"bone": "Node12", "prop": "rotation_euler", "axis": 2, "weight": 1.0}],
    "arm_l_x": [{"bone": "Node13", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "arm_l_y": [{"bone": "Node13", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "arm_l_z": [{"bone": "Node13", "prop": "rotation_euler", "axis": 2, "weight": 1.0}],
    "elbow_l_flex": [{"bone": "Node14", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "wrist_l_x": [{"bone": "Node15", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "wrist_l_y": [{"bone": "Node15", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "wrist_l_z": [{"bone": "Node15", "prop": "rotation_euler", "axis": 2, "weight": 1.0}],
    "thigh_l_x": [{"bone": "Node4", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "thigh_l_y": [{"bone": "Node4", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "thigh_l_z": [{"bone": "Node4", "prop": "rotation_euler", "axis": 2, "weight": 1.0}],
    "knee_l_flex":  [{"bone": "Node5", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "foot_pitch_l": [{"bone": "Node6", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "shoulder_r_x": [{"bone": "Node16", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "shoulder_r_y": [{"bone": "Node16", "prop": "rotation_euler", "axis": 1, "weight": -1.0}],
    "shoulder_r_z": [{"bone": "Node16", "prop": "rotation_euler", "axis": 2, "weight": -1.0}],
    "arm_r_x": [{"bone": "Node17", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "arm_r_y": [{"bone": "Node17", "prop": "rotation_euler", "axis": 1, "weight": -1.0}],
    "arm_r_z": [{"bone": "Node17", "prop": "rotation_euler", "axis": 2, "weight": -1.0}],
    "elbow_r_flex": [{"bone": "Node18", "prop": "rotation_euler", "axis": 1, "weight": 1.0}],
    "wrist_r_x": [{"bone": "Node19", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "wrist_r_y": [{"bone": "Node19", "prop": "rotation_euler", "axis": 1, "weight": -1.0}],
    "wrist_r_z": [{"bone": "Node19", "prop": "rotation_euler", "axis": 2, "weight": -1.0}],
    "thigh_r_x": [{"bone": "Node7", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "thigh_r_y": [{"bone": "Node7", "prop": "rotation_euler", "axis": 1, "weight": -1.0}],
    "thigh_r_z": [{"bone": "Node7", "prop": "rotation_euler", "axis": 2, "weight": -1.0}],
    "knee_r_flex":  [{"bone": "Node8", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "foot_pitch_r": [{"bone": "Node9", "prop": "rotation_euler", "axis": 0, "weight": 1.0}],
    "shoulder_width": [
        {"bone": "Node12", "prop": "rotation_euler", "axis": 1, "weight":  0.5},
        {"bone": "Node16", "prop": "rotation_euler", "axis": 1, "weight": -0.5},
    ],
    "arm_spread": [
        {"bone": "Node13", "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node17", "prop": "rotation_euler", "axis": 2, "weight": -1.0},
    ],
    "arm_forward": [
        {"bone": "Node13", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
        {"bone": "Node17", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
    ],
    "elbow_flex": [
        {"bone": "Node14", "prop": "rotation_euler", "axis": 1, "weight":  1.0},
        {"bone": "Node18", "prop": "rotation_euler", "axis": 1, "weight": -1.0},
    ],
    "head_tilt": [
        {"bone": "Node21", "prop": "rotation_euler", "axis": 0, "weight":  1.0},
        {"bone": "Node20", "prop": "rotation_euler", "axis": 0, "weight":  0.4},
    ],
    "head_turn": [
        {"bone": "Node21", "prop": "rotation_euler", "axis": 2, "weight":  1.0},
        {"bone": "Node20", "prop": "rotation_euler", "axis": 2, "weight":  0.5},
    ],
}

BACKUP_KEY = "mot_tweaker_backup"

def _backup_action(action):
    if BACKUP_KEY in action:
        return
    backup = {}
    for fc in action.fcurves:
        key = f"{fc.data_path}[{fc.array_index}]"
        backup[key] = [
            (kp.co[1], kp.handle_left[1], kp.handle_right[1])
            for kp in fc.keyframe_points
        ]
    action[BACKUP_KEY] = json.dumps(backup)

def _restore_action(action):
    if BACKUP_KEY not in action:
        return False
    backup = json.loads(action[BACKUP_KEY])
    for fc in action.fcurves:
        key = f"{fc.data_path}[{fc.array_index}]"
        if key in backup:
            orig_data = backup[key]
            kps = fc.keyframe_points
            for i, kp in enumerate(kps):
                if i < len(orig_data):
                    co_y, hl_y, hr_y = orig_data[i]
                    kp.co[1]           = co_y
                    kp.handle_left[1]  = hl_y
                    kp.handle_right[1] = hr_y
            fc.update()
            
    del action[BACKUP_KEY]
    return True

def _get_bone_scale_factor(bone_name, props):
    for group_name, bones in BODY_GROUPS.items():
        if bone_name in bones:
            prop_key = f"scale_{group_name}"
            if hasattr(props, prop_key):
                return getattr(props, prop_key)
    return 1.0

def _reapply_all_tweaks(props):
    global _suppress_update
    if _suppress_update:
        return

    arm = _get_arm()
    if not arm or not arm.animation_data or not arm.animation_data.action:
        return

    action = arm.animation_data.action
    _backup_action(action)

    backup = json.loads(action[BACKUP_KEY])
    totals_by_fcurve = {}

    for group_key, group_entries in TWEAK_GROUPS.items():
        if not hasattr(props, group_key):
            continue

        slider_val = getattr(props, group_key)
        if slider_val == 0.0:
            continue

        for entry in group_entries:
            bone_name = entry["bone"]
            prop      = entry["prop"]
            axis      = entry["axis"]
            weight    = entry["weight"]

            mult = 10.0 if prop == "location" else 1.0
            delta = slider_val * weight * mult

            data_path = f'pose.bones["{bone_name}"].{prop}'
            fc_key = (data_path, axis)

            totals_by_fcurve[fc_key] = totals_by_fcurve.get(fc_key, 0.0) + delta

    for bk_key, orig_data in backup.items():
        try:
            data_path, axis_str = bk_key.rsplit("[", 1)
            axis = int(axis_str.rstrip("]"))
        except ValueError:
            continue

        fc = action.fcurves.find(data_path, index=axis)
        if not fc or len(fc.keyframe_points) == 0:
            continue

        bone_name = ""
        if 'pose.bones["' in data_path:
            bone_name = data_path.split('pose.bones["')[1].split('"]')[0]

        scale_factor = _get_bone_scale_factor(bone_name, props)
        total_delta = totals_by_fcurve.get((data_path, axis), 0.0)

        first_frame_orig_y = orig_data[0][0]

        for i, kp in enumerate(fc.keyframe_points):
            if i >= len(orig_data):
                continue

            orig_y, orig_hl_y, orig_hr_y = orig_data[i]

            hl_offset = orig_y - orig_hl_y
            hr_offset = orig_hr_y - orig_y

            scaled_y = first_frame_orig_y + (orig_y - first_frame_orig_y) * scale_factor
            new_val = scaled_y + total_delta
            
            kp.co[1]           = new_val
            kp.handle_left[1]  = new_val - (hl_offset * scale_factor)
            kp.handle_right[1] = new_val + (hr_offset * scale_factor)

        fc.update()

def _update_callback(self, context):
    _reapply_all_tweaks(self)

def _get_arm():
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0") or bpy.data.objects.get("Node1")
    if arm and arm.type == 'ARMATURE':
        return arm
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            return obj
    return None

class MOTTweakerProps(PropertyGroup):
    show_scaling_panel: BoolProperty(name="Intensità Movimenti (Scaling)", default=False)
    show_face_panel:    BoolProperty(name="Espressioni Facciali", default=False)
    show_main_panel:    BoolProperty(name="Busto, Bacino e Posizione", default=False)
    show_global_arms:   BoolProperty(name="Controlli Braccia Globale & Testa", default=False)
    
    show_left_upper:    BoolProperty(name="SX - Upper Body (Braccio & Spalla)", default=False)
    show_left_lower:    BoolProperty(name="SX - Lower Body (Gamba & Piede)", default=False)
    show_right_upper:   BoolProperty(name="DX - Upper Body (Braccio & Spalla)", default=False)
    show_right_lower:   BoolProperty(name="DX - Lower Body (Gamba & Piede)", default=False)

    # Scaling Factor
    scale_arms:  FloatProperty(name="Movimento Braccia", default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)
    scale_legs:  FloatProperty(name="Movimento Gambe",   default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)
    scale_torso: FloatProperty(name="Movimento Torso",   default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)
    scale_hip:   FloatProperty(name="Movimento Bacino",  default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)
    scale_head:  FloatProperty(name="Movimento Testa",   default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)
    scale_face:  FloatProperty(name="Movimento Faccia",  default=1.0, min=0.0, max=3.0, step=1, update=_update_callback)

    # Faccia
    eyebrows_rot_y: FloatProperty(name="Sopracciglia Inclinazione (Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    eyebrows_curve: FloatProperty(name="Sopracciglia Espressione",      default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    eyes_closed:    FloatProperty(name="Chiusura Occhi (X) [24/26]",     default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    jaw_open:       FloatProperty(name="Apertura Mascella (X) [27]",    default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    # Busto e Corpo
    low_center: FloatProperty(name="Altezza / Baricentro", default=0.0, min=-5.0, max=5.0, step=1, update=_update_callback)
    node2_height_only: FloatProperty(name="Altezza Node2 Isolato", default=0.0, min=-5.0, max=5.0, step=1, update=_update_callback)
    twist_hip: FloatProperty(name="Torsione Bacino Z (Node3)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    spine_flex: FloatProperty(name="Inclinazione Busto Sup. (Node11)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    hunch: FloatProperty(name="Gobbo", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)
    lean: FloatProperty(name="Lean Laterale", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)
    leg_stance: FloatProperty(name="Ampiezza Gambe (Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    legs_rot_z: FloatProperty(name="Rotazione Gambe (Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    thighs_pitch: FloatProperty(name="Inclinazione Gambe (X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    step_height: FloatProperty(name="Altezza Passi", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)

    shoulder_l_x: FloatProperty(name="Spalla SX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    shoulder_l_y: FloatProperty(name="Spalla SX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    shoulder_l_z: FloatProperty(name="Spalla SX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    arm_l_x: FloatProperty(name="Braccio SX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    arm_l_y: FloatProperty(name="Braccio SX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    arm_l_z: FloatProperty(name="Braccio SX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    elbow_l_flex: FloatProperty(name="Gomito SX (Flessione Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    
    wrist_l_x: FloatProperty(name="Polso SX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    wrist_l_y: FloatProperty(name="Polso SX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    wrist_l_z: FloatProperty(name="Polso SX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    thigh_l_x: FloatProperty(name="Gamba SX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    thigh_l_y: FloatProperty(name="Gamba SX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    thigh_l_z: FloatProperty(name="Gamba SX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    knee_l_flex:  FloatProperty(name="Ginocchio SX (Flessione X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    foot_pitch_l: FloatProperty(name="Piede SX (Rotazione X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    shoulder_r_x: FloatProperty(name="Spalla DX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    shoulder_r_y: FloatProperty(name="Spalla DX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    shoulder_r_z: FloatProperty(name="Spalla DX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    arm_r_x: FloatProperty(name="Braccio DX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    arm_r_y: FloatProperty(name="Braccio DX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    arm_r_z: FloatProperty(name="Braccio DX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    elbow_r_flex: FloatProperty(name="Gomito DX (Flessione Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    wrist_r_x: FloatProperty(name="Polso DX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    wrist_r_y: FloatProperty(name="Polso DX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    wrist_r_z: FloatProperty(name="Polso DX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    thigh_r_x: FloatProperty(name="Gamba DX (Asse X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    thigh_r_y: FloatProperty(name="Gamba DX (Asse Y)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    thigh_r_z: FloatProperty(name="Gamba DX (Asse Z)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    knee_r_flex:  FloatProperty(name="Ginocchio DX (Flessione X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    foot_pitch_r: FloatProperty(name="Piede DX (Rotazione X)", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)

    shoulder_width: FloatProperty(name="Larghezza Spalle entrambi", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)
    arm_spread: FloatProperty(name="Apertura Braccia entrambi", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    arm_forward: FloatProperty(name="Braccia Avanti/Indietro", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    elbow_flex: FloatProperty(name="Flessione Gomiti entrambi", default=0.0, min=-1.5, max=1.5, step=1, update=_update_callback)
    head_tilt: FloatProperty(name="Inclinazione Testa", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)
    head_turn: FloatProperty(name="Rotazione Testa", default=0.0, min=-1.0, max=1.0, step=1, update=_update_callback)

class MOT_OT_TweakerReset(Operator):
    bl_idname      = "mot_tweaker.reset"
    bl_label       = "Reset All"
    bl_description = "Restore original fcurve values and reset all sliders"

    def execute(self, context):
        global _suppress_update
        arm = _get_arm()
        if not arm or not arm.animation_data or not arm.animation_data.action:
            self.report({'WARNING'}, "No action found")
            return {'CANCELLED'}

        action = arm.animation_data.action

        _suppress_update = True
        try:
            ok = _restore_action(action)
            if not ok:
                self.report({'WARNING'}, "No backup found — load or modify an animation first")
                return {'CANCELLED'}

            props = context.scene.mot_tweaker
            props.scale_arms = 1.0
            props.scale_legs = 1.0
            props.scale_torso = 1.0
            props.scale_hip = 1.0
            props.scale_head = 1.0
            props.scale_face = 1.0

            for key in TWEAK_GROUPS:
                if hasattr(props, key):
                    setattr(props, key, 0.0)
        finally:
            _suppress_update = False

        self.report({'INFO'}, "Reset to original animation")
        return {'FINISHED'}

class MOT_OT_TweakerClearBackup(Operator):
    bl_idname      = "mot_tweaker.clear_backup"
    bl_label       = "Accept Changes"
    bl_description = "Accept current state as new baseline (clears backup)"

    def execute(self, context):
        global _suppress_update
        arm = _get_arm()
        if not arm or not arm.animation_data or not arm.animation_data.action:
            self.report({'WARNING'}, "No action found")
            return {'CANCELLED'}
        
        action = arm.animation_data.action
        if BACKUP_KEY in action:
            del action[BACKUP_KEY]
            
        _suppress_update = True
        try:
            props = context.scene.mot_tweaker
            props.scale_arms = 1.0
            props.scale_legs = 1.0
            props.scale_torso = 1.0
            props.scale_hip = 1.0
            props.scale_head = 1.0
            props.scale_face = 1.0

            for key in TWEAK_GROUPS:
                if hasattr(props, key):
                    setattr(props, key, 0.0)
        finally:
            _suppress_update = False
                    
        self.report({'INFO'}, "Changes accepted as new baseline")
        return {'FINISHED'}

class VIEW3D_PT_MOTTweaker(Panel):
    bl_label       = "MOT Tweaker"
    bl_idname      = "VIEW3D_PT_mot_tweaker"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "MOT Tweaker"

    def draw(self, context):
        layout = self.layout
        props  = context.scene.mot_tweaker

        arm = _get_arm()
        has_action = arm and arm.animation_data and arm.animation_data.action
        has_backup = has_action and BACKUP_KEY in arm.animation_data.action

        if not has_action:
            layout.label(text="Load a .mot animation first", icon='INFO')
            return

        # 1. Scaling Panel
        box_sc = layout.box()
        row_sc = box_sc.row()
        icon_sc = 'TRIA_DOWN' if props.show_scaling_panel else 'TRIA_RIGHT'
        row_sc.prop(props, "show_scaling_panel", text="Intensità Movimenti (Scaling)", icon=icon_sc, icon_only=False, emboss=False)

        if props.show_scaling_panel:
            col = box_sc.column(align=True)
            col.prop(props, "scale_arms",  text="Braccia", slider=True)
            col.prop(props, "scale_legs",  text="Gambe",   slider=True)
            col.prop(props, "scale_torso", text="Torso",   slider=True)
            col.prop(props, "scale_hip",   text="Bacino",  slider=True)
            col.prop(props, "scale_head",  text="Testa",   slider=True)
            col.prop(props, "scale_face",  text="Faccia",  slider=True)

        # 2. Face Panel
        box_fc = layout.box()
        row_fc = box_fc.row()
        icon_fc = 'TRIA_DOWN' if props.show_face_panel else 'TRIA_RIGHT'
        row_fc.prop(props, "show_face_panel", text="Espressioni Facciali", icon=icon_fc, icon_only=False, emboss=False)

        if props.show_face_panel:
            col = box_fc.column(align=True)
            col.prop(props, "eyebrows_rot_y", slider=True)
            col.prop(props, "eyebrows_curve", slider=True)
            col.prop(props, "eyes_closed",    slider=True)
            col.prop(props, "jaw_open",       slider=True)

        # 3. Busto e Bacino
        box_m = layout.box()
        row_m = box_m.row()
        icon_m = 'TRIA_DOWN' if props.show_main_panel else 'TRIA_RIGHT'
        row_m.prop(props, "show_main_panel", text="Busto, Bacino e Posizione", icon=icon_m, icon_only=False, emboss=False)

        if props.show_main_panel:
            col = box_m.column(align=True)
            col.label(text="Posizione & Baricentro:", icon='BONE_DATA')
            col.prop(props, "low_center", slider=True)
            col.prop(props, "node2_height_only", slider=True)
            col.separator(factor=0.5)

            col.label(text="Bacino & Busto:", icon='BONE_DATA')
            col.prop(props, "twist_hip", slider=True)
            col.prop(props, "spine_flex", slider=True)
            col.prop(props, "hunch", slider=True)
            col.prop(props, "lean", slider=True)
            col.separator(factor=0.5)

            col.label(text="Gambe Globale:", icon='BONE_DATA')
            col.prop(props, "leg_stance", slider=True)
            col.prop(props, "legs_rot_z", slider=True)
            col.prop(props, "thighs_pitch", slider=True)
            col.prop(props, "step_height", slider=True)

        # 4. SX
        box_lu = layout.box()
        row_lu = box_lu.row()
        icon_lu = 'TRIA_DOWN' if props.show_left_upper else 'TRIA_RIGHT'
        row_lu.prop(props, "show_left_upper", text="SX - Upper Body (Braccio & Spalla)", icon=icon_lu, icon_only=False, emboss=False)
        
        if props.show_left_upper:
            col = box_lu.column(align=True)
            col.label(text="Spalla SX (Node12):")
            col.prop(props, "shoulder_l_x", slider=True)
            col.prop(props, "shoulder_l_y", slider=True)
            col.prop(props, "shoulder_l_z", slider=True)
            col.separator(factor=0.5)
            
            col.label(text="Braccio SX (Node13):")
            col.prop(props, "arm_l_x", slider=True)
            col.prop(props, "arm_l_y", slider=True)
            col.prop(props, "arm_l_z", slider=True)
            col.separator(factor=0.5)

            col.label(text="Gomito SX (Node14):")
            col.prop(props, "elbow_l_flex", slider=True)
            col.separator(factor=0.5)

            col.label(text="Polso SX (Node15):")
            col.prop(props, "wrist_l_x", slider=True)
            col.prop(props, "wrist_l_y", slider=True)
            col.prop(props, "wrist_l_z", slider=True)

        box_ll = layout.box()
        row_ll = box_ll.row()
        icon_ll = 'TRIA_DOWN' if props.show_left_lower else 'TRIA_RIGHT'
        row_ll.prop(props, "show_left_lower", text="SX - Lower Body (Gamba & Piede)", icon=icon_ll, icon_only=False, emboss=False)
        
        if props.show_left_lower:
            col = box_ll.column(align=True)
            col.label(text="Coscia / Gamba SX (Node4):")
            col.prop(props, "thigh_l_x", slider=True)
            col.prop(props, "thigh_l_y", slider=True)
            col.prop(props, "thigh_l_z", slider=True)
            col.separator(factor=0.5)

            col.label(text="Ginocchio SX (Node5):")
            col.prop(props, "knee_l_flex", slider=True)
            col.separator(factor=0.5)

            col.label(text="Piede SX (Node6):")
            col.prop(props, "foot_pitch_l", slider=True)

        # 5. DX
        box_ru = layout.box()
        row_ru = box_ru.row()
        icon_ru = 'TRIA_DOWN' if props.show_right_upper else 'TRIA_RIGHT'
        row_ru.prop(props, "show_right_upper", text="DX - Upper Body (Braccio & Spalla)", icon=icon_ru, icon_only=False, emboss=False)
        
        if props.show_right_upper:
            col = box_ru.column(align=True)
            col.label(text="Spalla DX (Node16):")
            col.prop(props, "shoulder_r_x", slider=True)
            col.prop(props, "shoulder_r_y", slider=True)
            col.prop(props, "shoulder_r_z", slider=True)
            col.separator(factor=0.5)

            col.label(text="Braccio DX (Node17):")
            col.prop(props, "arm_r_x", slider=True)
            col.prop(props, "arm_r_y", slider=True)
            col.prop(props, "arm_r_z", slider=True)
            col.separator(factor=0.5)

            col.label(text="Gomito DX (Node18):")
            col.prop(props, "elbow_r_flex", slider=True)
            col.separator(factor=0.5)

            col.label(text="Polso DX (Node19):")
            col.prop(props, "wrist_r_x", slider=True)
            col.prop(props, "wrist_r_y", slider=True)
            col.prop(props, "wrist_r_z", slider=True)

        box_rl = layout.box()
        row_rl = box_rl.row()
        icon_rl = 'TRIA_DOWN' if props.show_right_lower else 'TRIA_RIGHT'
        row_rl.prop(props, "show_right_lower", text="DX - Lower Body (Gamba & Piede)", icon=icon_rl, icon_only=False, emboss=False)
        
        if props.show_right_lower:
            col = box_rl.column(align=True)
            col.label(text="Coscia / Gamba DX (Node7):")
            col.prop(props, "thigh_r_x", slider=True)
            col.prop(props, "thigh_r_y", slider=True)
            col.prop(props, "thigh_r_z", slider=True)
            col.separator(factor=0.5)

            col.label(text="Ginocchio DX (Node8):")
            col.prop(props, "knee_r_flex", slider=True)
            col.separator(factor=0.5)

            col.label(text="Piede DX (Node9):")
            col.prop(props, "foot_pitch_r", slider=True)

        # 6. Globali
        box_ga = layout.box()
        row_ga = box_ga.row()
        icon_ga = 'TRIA_DOWN' if props.show_global_arms else 'TRIA_RIGHT'
        row_ga.prop(props, "show_global_arms", text="Controlli Braccia Globale & Testa", icon=icon_ga, icon_only=False, emboss=False)

        if props.show_global_arms:
            col = box_ga.column(align=True)
            col.label(text="Controlli Braccia Globale:", icon='BONE_DATA')
            col.prop(props, "shoulder_width", slider=True)
            col.prop(props, "arm_spread", slider=True)
            col.prop(props, "arm_forward", slider=True)
            col.prop(props, "elbow_flex", slider=True)
            col.separator(factor=0.5)

            col.label(text="Testa:", icon='BONE_DATA')
            col.prop(props, "head_tilt", slider=True)
            col.prop(props, "head_turn", slider=True)

        layout.separator()

        row = layout.row(align=True)
        row.operator("mot_tweaker.reset",        text="Reset",          icon='LOOP_BACK')
        row.operator("mot_tweaker.clear_backup", text="Accept Changes", icon='CHECKMARK')

        if has_backup:
            layout.label(text="● Unsaved changes", icon='KEYTYPE_MOVING_HOLD_VEC')

classes = [
    MOTTweakerProps,
    MOT_OT_TweakerReset,
    MOT_OT_TweakerClearBackup,
    VIEW3D_PT_MOTTweaker,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mot_tweaker = PointerProperty(type=MOTTweakerProps)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.mot_tweaker

if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()