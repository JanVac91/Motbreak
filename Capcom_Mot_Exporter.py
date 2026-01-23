bl_info = {
    "name": "Capcom Outbreak Animation Rebuilder (V2.7 - TANGENT SUPPORT)",
    "author": "CarlVercetti & Gemini AI",
    "version": (2, 7, 0),
    "blender": (3, 0, 0),
    "location": "File > Export > Capcom Outbreak Rebuilder (.mot)",
    "description": "Export con calcolo tangenti Hermite per fluidità PS2. Credits: CarlVercetti, Gemini AI.",
    "category": "Import-Export",
}

import bpy
import struct
import traceback
from bpy_extras.io_utils import ExportHelper
from bpy.props import IntProperty, BoolProperty

class EXPORT_OT_capcom_rebuilder_v2_7(bpy.types.Operator, ExportHelper):
    """Rebuild a Capcom .mot file with Hermite Tangents calculation"""
    bl_idname = "export_anim.capcom_rebuilder_v2_7"
    bl_label = "Export Capcom (.mot)"
    filename_ext = ".mot"
    
    use_loop: BoolProperty(
        name="Enable Animation Loop",
        description="Toggle the start loop flag in the .mot header",
        default=True,
    )
    
    loop_frame: IntProperty(
        name="Loop Start Frame",
        description="The frame number where the loop begins",
        default=0,
        min=-1,
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Loop Configuration", icon='ACTION')
        col = box.column(align=True)
        col.prop(self, "use_loop")
        sub = col.column()
        sub.enabled = self.use_loop
        sub.prop(self, "loop_frame", text="Start Frame")
        
        layout.separator()
        credit_box = layout.box()
        credit_box.label(text="Project Credits", icon='SOLO_ON')
        credit_box.label(text="By CarlVercetti (Research & Fixes)")
        credit_box.label(text="Scripted by Gemini AI")

    def get_original_track_ids(self, file_data, node_offset, n_sub):
        track_ptr = node_offset + 12
        mapping = {}
        known_ids = {
            0x0001: ("rotation_euler", 0), 0x0008: ("rotation_euler", 0),
            0x0002: ("rotation_euler", 1), 0x0010: ("rotation_euler", 1),
            0x0004: ("rotation_euler", 2), 0x0020: ("rotation_euler", 2),
            0x0040: ("location", 0), 0x0080: ("location", 1), 0x0100: ("location", 2),
            0x0400: ("scale", 0), 0x0800: ("scale", 1), 0x1000: ("scale", 2),
        }
        for i in range(n_sub):
            try:
                t_type, t_keys, t_size = struct.unpack("<III", file_data[track_ptr:track_ptr+12])
                base_type = t_type & 0xFFFF
                if base_type in known_ids:
                    mapping[known_ids[base_type]] = t_type
                track_ptr += t_size
            except: break
        return mapping

    def create_track_block(self, fcurve, track_id, div_precision, multiplier=1.0):
        keyframes = sorted(fcurve.keyframe_points, key=lambda k: k.co.x)
        num_keys = len(keyframes)
        track_size = 12 + (num_keys * 8)
        track_data = bytearray()
        track_data.extend(struct.pack("<III", track_id, num_keys, track_size))
        
        for i, k in enumerate(keyframes):
            # Valore e Frame
            val_blender = (k.co.y * multiplier) * div_precision
            int_val = int(round(val_blender))
            int_val = max(-32768, min(32767, int_val))
            frame_idx = int(k.co.x)

            # --- LOGICA TANGENTI HERMITE ---
            # Calcoliamo la pendenza (slope) come (V_next - V_prev) / (F_next - F_prev)
            m_in = 0
            m_out = 0
            
            if 0 < i < num_keys - 1:
                prev_k = keyframes[i-1]
                next_k = keyframes[i+1]
                
                delta_v = (next_k.co.y - prev_k.co.y) * multiplier * div_precision
                delta_f = next_k.co.x - prev_k.co.x
                
                if delta_f != 0:
                    # Calcolo pendenza media del segmento
                    slope = int(round(delta_v / delta_f))
                    m_in = max(-32768, min(32767, slope))
                    m_out = m_in
            
            # Scrittura: Val(h), Frame(h), TangenteIn(h), TangenteOut(h)
            track_data.extend(struct.pack("<hhhh", int_val, frame_idx, m_in, m_out))
            
        return track_data, track_size

    def execute(self, context):
        print(f"\n--- Initializing .mot Rebuild V2.7 | Template: {self.filepath} ---")
        arm = bpy.data.objects.get("Node2")
        if not arm or not arm.animation_data or not arm.animation_data.action:
            self.report({'ERROR'}, "Target 'Node2' non trovato.")
            return {'CANCELLED'}

        action = arm.animation_data.action
        try:
            with open(self.filepath, "rb") as f:
                orig_data = f.read()
        except Exception as e:
            self.report({'ERROR'}, f"IO Error: {e}")
            return {'CANCELLED'}

        new_file_data = bytearray()
        file_cursor = 0
        global_node_idx = 0
        
        ROT_P = 2607.5945876
        LOC_P = 16.0
        FACE_P = 256.0
        final_loop_val = float(self.loop_frame) if self.use_loop else -1.0

        try:
            while file_cursor + 20 <= len(orig_data):
                h_type, h_count, h_size_orig, h_unk, _ = struct.unpack("<IIIIf", orig_data[file_cursor:file_cursor+20])
                header_byte = h_type & 0xFF
                if header_byte == 0x0C: global_node_idx = 10
                elif header_byte == 0x06: global_node_idx = 22
                
                nodes_buffer = bytearray()
                current_node_ptr = file_cursor + 20
                
                for n in range(h_count):
                    if current_node_ptr + 12 > len(orig_data): break
                    n_type, n_sub, n_size = struct.unpack("<III", orig_data[current_node_ptr:current_node_ptr+12])
                    node_name = f"Node{global_node_idx}"
                    is_facial = 23 <= global_node_idx <= 26

                    if n_type >= 0x80000000:
                        id_map = self.get_original_track_ids(orig_data, current_node_ptr, n_sub)
                        tracks_buffer = bytearray()
                        track_count = 0
                        
                        for (prop, axis), full_id in id_map.items():
                            target_path = prop if global_node_idx == 2 else f'pose.bones["{node_name}"].{prop}'
                            fcurve = action.fcurves.find(target_path, index=axis)
                            
                            if fcurve:
                                if is_facial and prop == "location":
                                    current_div, current_mult = FACE_P, -1.0
                                else:
                                    current_div = LOC_P if prop == "location" else ROT_P
                                    current_mult = 1.0
                                
                                t_blob, _ = self.create_track_block(fcurve, full_id, current_div, current_mult)
                                tracks_buffer.extend(t_blob)
                                track_count += 1

                        if track_count > 0:
                            nodes_buffer.extend(struct.pack("<III", n_type, track_count, 12 + len(tracks_buffer)))
                            nodes_buffer.extend(tracks_buffer)
                        else:
                            nodes_buffer.extend(orig_data[current_node_ptr : current_node_ptr + n_size])
                    else:
                        nodes_buffer.extend(orig_data[current_node_ptr : current_node_ptr + n_size])
                    
                    current_node_ptr += n_size
                    global_node_idx += 1
                
                new_file_data.extend(struct.pack("<IIIIf", h_type, h_count, 20 + len(nodes_buffer), h_unk, final_loop_val))
                new_file_data.extend(nodes_buffer)
                file_cursor += h_size_orig

            with open(self.filepath, "wb") as f:
                f.write(new_file_data)
            
            self.report({'INFO'}, "Export Success con Tangenti Hermite")
            return {'FINISHED'}
        except Exception as e:
            print(traceback.format_exc())
            return {'CANCELLED'}

def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_capcom_rebuilder_v2_7.bl_idname, text="Capcom Outbreak Rebuilder (.mot)")

def register():
    bpy.utils.register_class(EXPORT_OT_capcom_rebuilder_v2_7)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(EXPORT_OT_capcom_rebuilder_v2_7)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()