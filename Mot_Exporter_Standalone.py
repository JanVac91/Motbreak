bl_info = {
    "name": "Capcom Outbreak Animation Exporter (V2.3)",
    "author": "CarlVercetti & Claude",
    "version": (2, 3, 0),
    "blender": (3, 0, 0),
    "location": "File > Export > Capcom Outbreak Exporter (.mot)",
    "description": "Export .mot with Node0/Node1 object animations",
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
        arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
        if not arm:
            self.report({'ERROR'}, "Armature 'Node2' not found")
            return {'CANCELLED'}
        
        # Trova il frame range
        frame_start = int(context.scene.frame_start)
        frame_end = int(context.scene.frame_end)
        
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
        lower_section = self.build_section(arm, range(0, 10), track_defs, FORMAT_HERMITE_16, frame_start, frame_end, force_rotation=False)
        
        # Header LOWER
        h_type_lower = 0x80000002
        h_count_lower = 0x0A
        h_size_lower = 20 + len(lower_section)
        h_loop = 1 if self.use_loop else 0
        h_loopFrame = float(self.loop_frame) if self.use_loop else 0.0
        
        file_data.extend(struct.pack("<IIIIf", h_type_lower, h_count_lower, h_size_lower, h_loop, h_loopFrame))
        file_data.extend(lower_section)
        
        # UPPER SECTION (Node10-21)
        upper_section = self.build_section(arm, range(10, 22), track_defs, FORMAT_HERMITE_16, frame_start, frame_end, force_rotation=True)
        
        # Header UPPER
        h_type_upper = 0x80000002
        h_count_upper = 0x0C
        h_size_upper = 20 + len(upper_section)
        
        file_data.extend(struct.pack("<IIIIf", h_type_upper, h_count_upper, h_size_upper, h_loop, h_loopFrame))
        file_data.extend(upper_section)
        
        # Salva file
        try:
            with open(self.filepath, "wb") as f:
                f.write(file_data)
            
            print(f"\nExported: {len(file_data)} bytes")
            print(f"LOWER section: {len(lower_section)} bytes")
            print(f"UPPER section: {len(upper_section)} bytes")
            
            self.report({'INFO'}, f"Export successful: {len(file_data)} bytes")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
    
    def build_section(self, arm, node_range, track_defs, format_type, frame_start, frame_end, force_rotation=False):
        """Costruisce una sezione (LOWER o UPPER)"""
        section_data = bytearray()
        
        for node_idx in node_range:
            node_name = f"Node{node_idx}"
            
            # Trova il target e la sua action
            target = None
            action = None
            data_path_prefix = ""
            
            if node_idx in [0, 1]:
                # Node0 e Node1 sono oggetti separati
                target = bpy.data.objects.get(node_name)
                if target and target.animation_data and target.animation_data.action:
                    action = target.animation_data.action
                data_path_prefix = ""
                
            elif node_idx == 2:
                # Node2 è l'armatura stessa
                if arm.name == node_name:
                    target = arm
                    if arm.animation_data and arm.animation_data.action:
                        action = arm.animation_data.action
                    data_path_prefix = ""
                    
            else:
                # Node3-21 sono ossa dentro l'armatura
                if arm.type == 'ARMATURE' and node_name in arm.pose.bones:
                    target = arm.pose.bones[node_name]
                    if arm.animation_data and arm.animation_data.action:
                        action = arm.animation_data.action
                    data_path_prefix = f'pose.bones["{node_name}"].'
            
            # Raccogli i track per questo nodo
            node_tracks = bytearray()
            n_type_flags = 0
            track_count = 0
            
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
                    
                    if should_export:
                        # Crea il track
                        if has_keyframes:
                            keyframes = fcurve.keyframe_points
                        else:
                            # Crea keyframes di default (0 e frame_end a valore 0)
                            keyframes = None
                        
                        track_data = self.create_track(track_id, format_type, keyframes, precision, frame_start, frame_end)
                        if track_data:
                            node_tracks.extend(track_data)
                            track_count += 1
                            n_type_flags |= track_id
            
            # Scrivi il nodo
            if track_count > 0:
                n_type = 0x80000000 | n_type_flags
                n_sub = track_count
                n_size = 12 + len(node_tracks)
                
                section_data.extend(struct.pack("<III", n_type, n_sub, n_size))
                section_data.extend(node_tracks)
            else:
                # Nodo vuoto
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