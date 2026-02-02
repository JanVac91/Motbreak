bl_info = {
    "name": "Capcom Outbreak Animation Exporter (V2.6)",
    "author": "CarlVercetti & Claude",
    "version": (2, 6, 0),
    "blender": (3, 0, 0),
    "location": "File > Export > Capcom Outbreak Exporter (.mot)",
    "description": "Export .mot - Node0→Node2 only if Node2 is empty",
    "category": "Import-Export",
}

import bpy
import struct
from bpy_extras.io_utils import ExportHelper
from bpy.props import IntProperty, BoolProperty
import os

class EXPORT_OT_capcom_mot_v2(bpy.types.Operator, ExportHelper):
    bl_idname = "export_anim.capcom_mot_v2"
    bl_label = "Export Capcom (.mot)"
    filename_ext = ".mot"
    
    use_loop: BoolProperty(
        name="Enable Loop",
        description="Enable animation loop",
        default=False,
    )
    
    loop_frame: IntProperty(
        name="Loop Frame",
        description="Frame where loop starts",
        default=0,
        min=0,
    )

    def execute(self, context):
        print("\n" + "="*60)
        print("EXPORTING ANIMATION")
        print("="*60)
        
        # Cerca l'armatura - può essere Node2 o Node0
        arm = bpy.data.objects.get("Node2")
        arm_is_node0 = False
        
        if not arm or arm.type != 'ARMATURE':
            arm = bpy.data.objects.get("Node0")
            if arm and arm.type == 'ARMATURE':
                arm_is_node0 = True
                print("STRUCTURE: Node0 is ARMATURE (alternative structure)")
            else:
                self.report({'ERROR'}, "No armature found (searched Node2 and Node0)")
                return {'CANCELLED'}
        else:
            print("STRUCTURE: Node2 is ARMATURE (standard structure)")
        
        print(f"Armature: {arm.name}")
        
        # Trova il frame range
        frame_start = int(context.scene.frame_start)
        frame_end = int(context.scene.frame_end)
        
        print(f"Frame range: {frame_start} → {frame_end}")
        print(f"Loop: {self.use_loop}, Loop Frame: {self.loop_frame}")
        
        ROT_PRECISION = 2607.5945876
        LOC_PRECISION = 16.0
        SCL_PRECISION = 16.0
        
        # Definizione track types (formato 0x12 = Hermite 16-bit)
        FORMAT_HERMITE_16 = 0x0012
        
        track_defs = [
            (0x001, "scale", 0, SCL_PRECISION),
            (0x002, "scale", 1, SCL_PRECISION),
            (0x004, "scale", 2, SCL_PRECISION),
            (0x008, "rotation_euler", 0, ROT_PRECISION),
            (0x010, "rotation_euler", 1, ROT_PRECISION),
            (0x020, "rotation_euler", 2, ROT_PRECISION),
            (0x040, "location", 0, LOC_PRECISION),
            (0x080, "location", 1, LOC_PRECISION),
            (0x100, "location", 2, LOC_PRECISION),
        ]
        
        file_data = bytearray()
        
        # LOWER SECTION (Node0-9)
        print("\n" + "="*60)
        print("BUILDING LOWER SECTION (Node0-9)")
        print("="*60)
        lower_section = self.build_section(arm, range(0, 10), track_defs, FORMAT_HERMITE_16, frame_start, frame_end, force_rotation=False, arm_is_node0=arm_is_node0)
        
        # Header LOWER
        h_type_lower = 0x80000002
        h_count_lower = 0x0A
        h_size_lower = 20 + len(lower_section)
        h_loop = 1 if self.use_loop else 0
        h_loopFrame = float(self.loop_frame) if self.use_loop else 0.0
        
        print(f"\nLOWER header: type=0x{h_type_lower:08X}, count={h_count_lower}, size={h_size_lower}")
        print(f"LOWER section: {len(lower_section)} bytes")
        
        file_data.extend(struct.pack("<IIIIf", h_type_lower, h_count_lower, h_size_lower, h_loop, h_loopFrame))
        file_data.extend(lower_section)
        
        # UPPER SECTION (Node10-21)
        print("\n" + "="*60)
        print("BUILDING UPPER SECTION (Node10-21)")
        print("="*60)
        upper_section = self.build_section(arm, range(10, 22), track_defs, FORMAT_HERMITE_16, frame_start, frame_end, force_rotation=True, arm_is_node0=arm_is_node0)
        
        # Header UPPER
        h_type_upper = 0x80000002
        h_count_upper = 0x0C
        h_size_upper = 20 + len(upper_section)
        
        print(f"\nUPPER header: type=0x{h_type_upper:08X}, count={h_count_upper}, size={h_size_upper}")
        print(f"UPPER section: {len(upper_section)} bytes")
        
        file_data.extend(struct.pack("<IIIIf", h_type_upper, h_count_upper, h_size_upper, h_loop, h_loopFrame))
        file_data.extend(upper_section)
        
        # Salva file
        try:
            with open(self.filepath, "wb") as f:
                f.write(file_data)
            
            print("\n" + "="*60)
            print(f"EXPORT COMPLETE")
            print(f"File: {self.filepath}")
            print(f"Total: {len(file_data)} bytes")
            print(f"LOWER: {len(lower_section)} bytes")
            print(f"UPPER: {len(upper_section)} bytes")
            print("="*60 + "\n")
            
            self.report({'INFO'}, f"Export successful: {len(file_data)} bytes")
            return {'FINISHED'}
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
    
    def build_section(self, arm, node_range, track_defs, format_type, frame_start, frame_end, force_rotation=False, arm_is_node0=False):
        """Costruisce una sezione (LOWER o UPPER)"""
        section_data = bytearray()
        
        # Pre-check: se Node0=armatura, controlla se Node2 ha già animazioni
        node2_has_animations = False
        node0_has_animations = False
        
        if arm_is_node0:
            # Controlla Node2 (bone)
            if arm.type == 'ARMATURE' and "Node2" in arm.pose.bones and arm.animation_data and arm.animation_data.action:
                action = arm.animation_data.action
                for fc in action.fcurves:
                    if fc.data_path.startswith('pose.bones["Node2"].'):
                        node2_has_animations = True
                        break
            
            # Controlla Node0 (bone, non l'oggetto armatura)
            if arm.type == 'ARMATURE' and "Node0" in arm.pose.bones and arm.animation_data and arm.animation_data.action:
                action = arm.animation_data.action
                for fc in action.fcurves:
                    if fc.data_path.startswith('pose.bones["Node0"].'):
                        node0_has_animations = True
                        break
            
            if node0_has_animations and node2_has_animations:
                print("\nWARNING: Both Node0 and Node2 have animations!")
                print("  Node2 animations will be kept, Node0 animations will be ignored")
            elif node0_has_animations and not node2_has_animations:
                print("\nNOTE: Node0 has animations, Node2 is empty")
                print("  Node0 animations will be moved to Node2 in the export")
        
        for node_idx in node_range:
            node_name = f"Node{node_idx}"
            
            # Trova il target e la sua action
            target = None
            action = None
            data_path_prefix = ""
            target_type = "NOT FOUND"
            write_empty_node0 = False
            use_node0_for_node2 = False
            
            if arm_is_node0:
                # STRUTTURA ALTERNATIVA: Node0 = Armatura, Node1-27 = Bones
                if node_idx == 0:
                    # Node0 viene scritto vuoto se le sue animazioni vanno in Node2
                    if node0_has_animations and not node2_has_animations:
                        print(f"\n{node_name} (ARMATURE OBJECT - WILL BE FORCED EMPTY):")
                        print(f"  Note: Animations will be moved to Node2")
                        write_empty_node0 = True
                    else:
                        # Node0 normale (o Node2 ha già animazioni)
                        print(f"\n{node_name} (ARMATURE OBJECT):")
                    
                    target = arm
                    target_type = "ARMATURE OBJECT"
                    if arm.animation_data and arm.animation_data.action:
                        action = arm.animation_data.action
                    data_path_prefix = ""
                
                elif node_idx == 2:
                    # Node2: usa animazioni Node0 solo se Node2 vuoto e Node0 pieno
                    if node0_has_animations and not node2_has_animations:
                        print(f"\n{node_name} (BONE - receives Node0 bone animations):")
                        # Usa le animazioni di Node0 bone
                        if arm.type == 'ARMATURE' and "Node0" in arm.pose.bones:
                            target = arm.pose.bones["Node0"]
                            target_type = "BONE Node0 (writing as Node2)"
                            if arm.animation_data and arm.animation_data.action:
                                action = arm.animation_data.action
                            data_path_prefix = 'pose.bones["Node0"].'
                            use_node0_for_node2 = True
                        else:
                            target = None
                    else:
                        # Node2 normale (usa le sue animazioni o è vuoto)
                        print(f"\n{node_name} (BONE):")
                        if arm.type == 'ARMATURE' and node_name in arm.pose.bones:
                            target = arm.pose.bones[node_name]
                            target_type = "BONE"
                            if arm.animation_data and arm.animation_data.action:
                                action = arm.animation_data.action
                            data_path_prefix = f'pose.bones["{node_name}"].'
                
                else:
                    # Node1, Node3-27 sono ossa dentro l'armatura Node0
                    print(f"\n{node_name} (BONE):")
                    if arm.type == 'ARMATURE' and node_name in arm.pose.bones:
                        target = arm.pose.bones[node_name]
                        target_type = "BONE"
                        if arm.animation_data and arm.animation_data.action:
                            action = arm.animation_data.action
                        data_path_prefix = f'pose.bones["{node_name}"].'
            else:
                # STRUTTURA STANDARD: Node0/1 = Empty, Node2 = Armatura, Node3-27 = Bones
                print(f"\n{node_name}:")
                if node_idx in [0, 1]:
                    target = bpy.data.objects.get(node_name)
                    if target:
                        target_type = "SEPARATE OBJECT"
                        if target.animation_data and target.animation_data.action:
                            action = target.animation_data.action
                    data_path_prefix = ""
                elif node_idx == 2:
                    if arm.name == node_name:
                        target = arm
                        target_type = "ARMATURE OBJECT"
                        if arm.animation_data and arm.animation_data.action:
                            action = arm.animation_data.action
                        data_path_prefix = ""
                else:
                    # Node3-21 sono ossa dentro l'armatura
                    if arm.type == 'ARMATURE' and node_name in arm.pose.bones:
                        target = arm.pose.bones[node_name]
                        target_type = "BONE"
                        if arm.animation_data and arm.animation_data.action:
                            action = arm.animation_data.action
                        data_path_prefix = f'pose.bones["{node_name}"].'
            
            if target:
                print(f"  Target: {target.name if hasattr(target, 'name') else 'PoseBone'} ({target_type})")
                print(f"  Action: {action.name if action else 'NONE'}")
                if use_node0_for_node2:
                    print(f"  Using Node0 bone animations")
            else:
                print(f"  Target: NOT FOUND")
            
            # Raccogli i track per questo nodo
            node_tracks = bytearray()
            n_type_flags = 0
            track_count = 0
            
            track_names = {
                0x001: "SCL_X", 0x002: "SCL_Y", 0x004: "SCL_Z",
                0x008: "ROT_X", 0x010: "ROT_Y", 0x020: "ROT_Z",
                0x040: "LOC_X", 0x080: "LOC_Y", 0x100: "LOC_Z"
            }
            
            for track_id, prop, axis, precision in track_defs:
                # Costruisci il data path
                if target and hasattr(target, prop):
                    data_path = f"{data_path_prefix}{prop}" if data_path_prefix else prop
                    
                    # Cerca fcurve nell'action
                    fcurve = None
                    if action:
                        fcurve = action.fcurves.find(data_path, index=axis)
                    
                    # Node3-21: forza sempre ROT_X, Y, Z
                    is_rotation = prop == "rotation_euler"
                    is_bone = node_idx >= 3 and node_idx <= 21
                    
                    has_keyframes = fcurve and len(fcurve.keyframe_points) > 0
                    should_export = has_keyframes or (force_rotation and is_bone and is_rotation)
                    
                    track_name = track_names.get(track_id, f"UNKNOWN_{track_id:03X}")
                    
                    if should_export:
                        # Crea il track
                        keyframes_to_export = None
                        
                        if has_keyframes:
                            # Filtra keyframe nel range
                            valid_kf = [kp for kp in fcurve.keyframe_points if frame_start <= kp.co[0] <= frame_end]
                            
                            if len(valid_kf) > 0:
                                print(f"  {track_name}: {len(valid_kf)} keys")
                                keyframes_to_export = valid_kf
                            else:
                                continue
                        else:
                            # Crea keyframes di default
                            print(f"  {track_name}: DEFAULT")
                            keyframes_to_export = None
                        
                        track_data = self.create_track(track_id, format_type, keyframes_to_export, precision, frame_start, frame_end)
                        if track_data:
                            node_tracks.extend(track_data)
                            track_count += 1
                            n_type_flags |= track_id
            
            # Scrivi il nodo
            if write_empty_node0:
                # Node0 sempre vuoto anche se ha track
                print(f"  Node header: FORCED EMPTY")
                section_data.extend(struct.pack("<III", 0x80000000, 0, 12))
            elif track_count > 0:
                n_type = 0x80000000 | n_type_flags
                n_sub = track_count
                n_size = 12 + len(node_tracks)
                
                print(f"  Node header: tracks={n_sub}, size={n_size}")
                
                section_data.extend(struct.pack("<III", n_type, n_sub, n_size))
                section_data.extend(node_tracks)
            else:
                print(f"  Node header: EMPTY")
                section_data.extend(struct.pack("<III", 0x80000000, 0, 12))
        
        return section_data
    
    def calculate_tangents(self, kp, precision):
        """Calcola tangenti c0 (in) e c1 (out) dalle handle di Blender"""
        delta_x_left = kp.co[0] - kp.handle_left[0]
        if delta_x_left != 0:
            delta_y_left = (kp.co[1] - kp.handle_left[1]) * precision
            c0 = delta_y_left / delta_x_left
        else:
            c0 = 0.0
        
        delta_x_right = kp.handle_right[0] - kp.co[0]
        if delta_x_right != 0:
            delta_y_right = (kp.handle_right[1] - kp.co[1]) * precision
            c1 = delta_y_right / delta_x_right
        else:
            c1 = 0.0
        
        c0_scaled = int(round(c0))
        c1_scaled = int(round(c1))
        
        c0_scaled = max(-32768, min(32767, c0_scaled))
        c1_scaled = max(-32768, min(32767, c1_scaled))
        
        return c0_scaled, c1_scaled
    
    def create_track(self, track_id, format_type, keyframes, precision, frame_start, frame_end):
        """Crea un track con formato Hermite 16-bit"""
        if keyframes is None:
            num_keys = 2
            t_type = 0x80000000 | (format_type << 16) | track_id
            t_keys = num_keys
            t_size = 12 + (num_keys * 8)
            
            track_data = bytearray()
            track_data.extend(struct.pack("<III", t_type, t_keys, t_size))
            track_data.extend(struct.pack("<hhhh", 0, frame_start, 0, 0))
            track_data.extend(struct.pack("<hhhh", 0, frame_end, 0, 0))
            return track_data
        
        num_keys = len(keyframes)
        
        if num_keys == 0:
            return None
        
        t_type = 0x80000000 | (format_type << 16) | track_id
        t_keys = num_keys
        t_size = 12 + (num_keys * 8)
        
        track_data = bytearray()
        track_data.extend(struct.pack("<III", t_type, t_keys, t_size))
        
        for kp in keyframes:
            frame = int(kp.co[0])
            value_float = kp.co[1]
            
            value_scaled = int(round(value_float * precision))
            value_scaled = max(-32768, min(32767, value_scaled))
            
            c0, c1 = self.calculate_tangents(kp, precision)
            
            track_data.extend(struct.pack("<hhhh", value_scaled, frame, c0, c1))
        
        return track_data

def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_capcom_mot_v2.bl_idname, text="Capcom Outbreak (.mot)")

def register():
    bpy.utils.register_class(EXPORT_OT_capcom_mot_v2)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(EXPORT_OT_capcom_mot_v2)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()