bl_info = {
    "name": "Capcom Outbreak Animation Exporter (V2.5)",
    "author": "CarlVercetti & Claude",
    "version": (2, 5, 0),
    "blender": (3, 0, 0),
    "location": "File > Export > Capcom Outbreak Exporter (.mot)",
    "description": "Export .mot with both structure types + keyframe truncation",
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
        
        for node_idx in node_range:
            node_name = f"Node{node_idx}"
            
            # Trova il target e la sua action
            target = None
            action = None
            data_path_prefix = ""
            target_type = "NOT FOUND"
            
            if arm_is_node0:
                # STRUTTURA ALTERNATIVA: Node0 = Armatura, Node1-27 = Bones
                if node_idx == 0:
                    target = arm
                    target_type = "ARMATURE OBJECT"
                    if arm.animation_data and arm.animation_data.action:
                        action = arm.animation_data.action
                    data_path_prefix = ""
                else:
                    # Node1-27 sono ossa dentro l'armatura Node0
                    if arm.type == 'ARMATURE' and node_name in arm.pose.bones:
                        target = arm.pose.bones[node_name]
                        target_type = "BONE"
                        if arm.animation_data and arm.animation_data.action:
                            action = arm.animation_data.action
                        data_path_prefix = f'pose.bones["{node_name}"].'
            else:
                # STRUTTURA STANDARD: Node0/1 = Empty, Node2 = Armatura, Node3-27 = Bones
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
            
            print(f"\n{node_name} ({target_type}):")
            if target:
                print(f"  Target: {target.name if hasattr(target, 'name') else 'PoseBone'}")
                print(f"  Action: {action.name if action else 'NONE'}")
            else:
                print(f"  Target: NOT FOUND")
            
            # Raccogli i track per questo nodo
            node_tracks = bytearray()
            n_type_flags = 0
            track_count = 0
            track_details = []
            
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
                                print(f"  {track_name}: {len(valid_kf)} keys (total {len(fcurve.keyframe_points)}, {len(fcurve.keyframe_points) - len(valid_kf)} truncated)")
                                # Mostra primi 3 keyframe validi
                                for i, kp in enumerate(valid_kf[:3]):
                                    frame = int(kp.co[0])
                                    value = kp.co[1]
                                    value_scaled = int(round(value * precision))
                                    print(f"    [{i}] Frame {frame}: value={value:.4f} → scaled={value_scaled}")
                                if len(valid_kf) > 3:
                                    print(f"    ... ({len(valid_kf) - 3} more)")
                                track_details.append(f"{track_name}({len(valid_kf)}keys)")
                                keyframes_to_export = valid_kf  # Usa i keyframe filtrati
                            else:
                                print(f"  {track_name}: SKIPPED (all {len(fcurve.keyframe_points)} keys outside range)")
                                # Salta completamente questo track
                                continue
                        else:
                            # Crea keyframes di default (0 e frame_end a valore 0)
                            print(f"  {track_name}: DEFAULT (0 at {frame_start}, 0 at {frame_end})")
                            track_details.append(f"{track_name}(default)")
                            keyframes_to_export = None  # None = crea default
                        
                        track_data = self.create_track(track_id, format_type, keyframes_to_export, precision, frame_start, frame_end)
                        if track_data:
                            node_tracks.extend(track_data)
                            track_count += 1
                            n_type_flags |= track_id
            
            # Scrivi il nodo
            if track_count > 0:
                n_type = 0x80000000 | n_type_flags
                n_sub = track_count
                n_size = 12 + len(node_tracks)
                
                print(f"  Node header: type=0x{n_type:08X}, tracks={n_sub}, size={n_size}")
                
                section_data.extend(struct.pack("<III", n_type, n_sub, n_size))
                section_data.extend(node_tracks)
            else:
                # Nodo vuoto
                print(f"  Node header: EMPTY (0x80000000, 0, 12)")
                section_data.extend(struct.pack("<III", 0x80000000, 0, 12))
        
        return section_data
    
    def calculate_tangents(self, kp, precision):
        """Calcola tangenti c0 (in) e c1 (out) dalle handle di Blender"""
        # Tangente IN (c0) - basata sulla handle sinistra
        delta_x_left = kp.co[0] - kp.handle_left[0]
        if delta_x_left != 0:
            # Calcola slope in unità scalate (value già moltiplicato per precision)
            delta_y_left = (kp.co[1] - kp.handle_left[1]) * precision
            c0 = delta_y_left / delta_x_left
        else:
            c0 = 0.0
        
        # Tangente OUT (c1) - basata sulla handle destra
        delta_x_right = kp.handle_right[0] - kp.co[0]
        if delta_x_right != 0:
            # Calcola slope in unità scalate
            delta_y_right = (kp.handle_right[1] - kp.co[1]) * precision
            c1 = delta_y_right / delta_x_right
        else:
            c1 = 0.0
        
        # Converti in int16
        c0_scaled = int(round(c0))
        c1_scaled = int(round(c1))
        
        # Clamp a int16 range
        c0_scaled = max(-32768, min(32767, c0_scaled))
        c1_scaled = max(-32768, min(32767, c1_scaled))
        
        return c0_scaled, c1_scaled
    
    def create_track(self, track_id, format_type, keyframes, precision, frame_start, frame_end):
        """Crea un track con formato Hermite 16-bit"""
        # Se non ci sono keyframes, crea default
        if keyframes is None:
            # Default: valore 0 a frame_start e frame_end
            num_keys = 2
            t_type = 0x80000000 | (format_type << 16) | track_id
            t_keys = num_keys
            t_size = 12 + (num_keys * 8)
            
            track_data = bytearray()
            track_data.extend(struct.pack("<III", t_type, t_keys, t_size))
            track_data.extend(struct.pack("<hhhh", 0, frame_start, 0, 0))
            track_data.extend(struct.pack("<hhhh", 0, frame_end, 0, 0))
            return track_data
        
        # I keyframe sono già filtrati da build_section
        num_keys = len(keyframes)
        
        if num_keys == 0:
            return None
        
        # Track header
        t_type = 0x80000000 | (format_type << 16) | track_id
        t_keys = num_keys
        t_size = 12 + (num_keys * 8)
        
        track_data = bytearray()
        track_data.extend(struct.pack("<III", t_type, t_keys, t_size))
        
        # Keyframes
        for kp in keyframes:
            frame = int(kp.co[0])
            value_float = kp.co[1]
            
            # Converti valore in 16-bit integer
            value_scaled = int(round(value_float * precision))
            value_scaled = max(-32768, min(32767, value_scaled))
            
            # Calcola tangenti dalle handle di Blender
            c0, c1 = self.calculate_tangents(kp, precision)
            
            # Scrivi keyframe (16-bit Hermite)
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