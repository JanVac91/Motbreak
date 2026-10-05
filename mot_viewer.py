bl_info = {
    "name": "MOT Viewer",
    "author": "CarlVercetti & Claude",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > MOT Viewer",
    "description": "Navigate and preview .mot animations on the active armature",
    "category": "Animation",
}

import bpy
import os
import struct

from bpy.props import StringProperty, IntProperty, BoolProperty
from bpy.types import Panel, Operator, PropertyGroup


# ============================================================
# CORE: minimal .mot importer (no deps on external addon)
# ============================================================

ROT_PRECISION   = 2607.5945876
LOC_PRECISION   = 16.0
SCL_PRECISION   = 16.0
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
    0x06: 22,
}


def _disconnect_node2(arm):
    """Se Node1 e Node2 sono bones, disconnette Node2 dal parent e calcola offset Y."""
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


def _load_mot(filepath, arm):
    """Carica un .mot sull'armatura. Restituisce (True, max_frame) o (False, 0)."""
    if not arm or arm.type != 'ARMATURE':
        return False, 0

    # Pulisci animazione precedente
    if arm.animation_data:
        arm.animation_data_clear()
    for bone in arm.pose.bones:
        bone.rotation_mode = 'XYZ'

    is_hd, node2_y_offset = _disconnect_node2(arm)

    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except Exception:
        return False, 0

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
            # sezione mostro o sconosciuta: parti da 0
            node_idx = 0

        node_pos = pos + 20
        section_end = pos + h_size

        for _ in range(h_count):
            if node_pos + 12 > section_end:
                break
            n_type, n_sub, n_size = struct.unpack_from("<III", data, node_pos)
            node_name = f"Node{node_idx}"

            if n_type >= 0x80000000 and n_sub > 0:
                # Trova target
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

                                # Offset visivo HD: solo Node2.LOC_Y
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

                                # Tangenti
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

    # Frame range + loop info
    bpy.context.scene.frame_start   = 0
    bpy.context.scene.frame_end     = max(global_max_frame, 1)
    bpy.context.scene.frame_current = 0

    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action["capcom_loop"]       = file_has_loop
        arm.animation_data.action["capcom_loop_frame"] = file_loop_frame

    return True, global_max_frame


# ============================================================
# PROPERTIES
# ============================================================

class MOTViewerProps(PropertyGroup):
    folder: StringProperty(
        name="Folder",
        description="Folder containing .mot files",
        subtype='DIR_PATH',
    )
    current_index: IntProperty(default=0)
    autoplay: BoolProperty(
        name="Autoplay",
        description="Start playback automatically after loading",
        default=True,
    )

    def get_files(self):
        folder = bpy.path.abspath(self.folder)
        if not os.path.isdir(folder):
            return []
        files = sorted(
            f for f in os.listdir(folder)
            if f.lower().endswith('.mot')
        )
        return files


# ============================================================
# OPERATORS
# ============================================================

def _get_arm():
    """Ritorna la prima armatura trovata in scena (cerca Node2, poi Node0, poi qualsiasi)."""
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    if arm and arm.type == 'ARMATURE':
        return arm
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            return obj
    return None


def _load_and_play(context, filepath):

    arm = _get_arm()
    if not arm:
        return False, "No armature found in scene"
    ok, max_frame = _load_mot(filepath, arm)
    if not ok:
        return False, f"Failed to load {os.path.basename(filepath)}"
    props = context.scene.mot_viewer
    if props.autoplay:
        bpy.ops.screen.animation_cancel(restore_frame=False)
        context.scene.frame_current = 0
        bpy.ops.screen.animation_play()
    return True, ""


class MOT_OT_LoadFolder(Operator):
    bl_idname  = "mot_viewer.load_folder"
    bl_label   = "Load Folder"
    bl_description = "Scan folder and load the first .mot file"

    def execute(self, context):
        props = context.scene.mot_viewer
        files = props.get_files()
        if not files:
            self.report({'WARNING'}, "No .mot files found in folder")
            return {'CANCELLED'}
        props.current_index = 0
        folder = bpy.path.abspath(props.folder)
        filepath = os.path.join(folder, files[0])
        ok, err = _load_and_play(context, filepath)
        if not ok:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, f"[1/{len(files)}] {files[0]}")
        return {'FINISHED'}


class MOT_OT_Next(Operator):
    bl_idname  = "mot_viewer.next"
    bl_label   = "Next"
    bl_description = "Load next .mot file"

    def execute(self, context):
        props = context.scene.mot_viewer
        files = props.get_files()
        if not files:
            self.report({'WARNING'}, "No .mot files loaded")
            return {'CANCELLED'}
        props.current_index = (props.current_index + 1) % len(files)
        folder   = bpy.path.abspath(props.folder)
        filepath = os.path.join(folder, files[props.current_index])
        ok, err  = _load_and_play(context, filepath)
        if not ok:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, f"[{props.current_index+1}/{len(files)}] {files[props.current_index]}")
        return {'FINISHED'}


class MOT_OT_Prev(Operator):
    bl_idname  = "mot_viewer.prev"
    bl_label   = "Prev"
    bl_description = "Load previous .mot file"

    def execute(self, context):
        props = context.scene.mot_viewer
        files = props.get_files()
        if not files:
            self.report({'WARNING'}, "No .mot files loaded")
            return {'CANCELLED'}
        props.current_index = (props.current_index - 1) % len(files)
        folder   = bpy.path.abspath(props.folder)
        filepath = os.path.join(folder, files[props.current_index])
        ok, err  = _load_and_play(context, filepath)
        if not ok:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, f"[{props.current_index+1}/{len(files)}] {files[props.current_index]}")
        return {'FINISHED'}


class MOT_OT_StopPlay(Operator):
    bl_idname  = "mot_viewer.stop"
    bl_label   = "Stop"
    bl_description = "Stop playback"

    def execute(self, context):
        bpy.ops.screen.animation_cancel(restore_frame=False)
        return {'FINISHED'}


# ============================================================
# PANEL
# ============================================================

class VIEW3D_PT_MOTViewer(Panel):
    bl_label      = "MOT Viewer"
    bl_idname     = "VIEW3D_PT_mot_viewer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "MOT Viewer"

    def draw(self, context):
        layout = self.layout
        props  = context.scene.mot_viewer
        files  = props.get_files()
        total  = len(files)

        # Folder picker
        layout.prop(props, "folder", text="")

        # Load button
        row = layout.row()
        row.scale_y = 1.2
        row.operator("mot_viewer.load_folder", icon='FILE_FOLDER')

        layout.separator()

        # Status: current file name + index
        if total > 0:
            idx  = props.current_index
            name = files[idx] if idx < total else "—"
            box  = layout.box()
            col  = box.column(align=True)
            col.label(text=name, icon='ANIM')
            col.label(text=f"{idx+1} / {total}")
        else:
            layout.label(text="No .mot files found", icon='INFO')

        layout.separator()

        # Prev / Next
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("mot_viewer.prev", icon='PLAY_REVERSE', text="Prev")
        row.operator("mot_viewer.next", icon='PLAY',         text="Next")

        # Stop
        row2 = layout.row()
        row2.operator("mot_viewer.stop", icon='PAUSE', text="Stop")

        layout.separator()

        # Autoplay toggle
        layout.prop(props, "autoplay", toggle=True)


# ============================================================
# REGISTRATION
# ============================================================

classes = [
    MOTViewerProps,
    MOT_OT_LoadFolder,
    MOT_OT_Next,
    MOT_OT_Prev,
    MOT_OT_StopPlay,
    VIEW3D_PT_MOTViewer,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mot_viewer = bpy.props.PointerProperty(type=MOTViewerProps)
    bpy.context.scene.render.fps = 60



def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.mot_viewer


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
