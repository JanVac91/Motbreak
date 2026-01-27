bl_info = {
    "name": "Capcom Outbreak Animation Importer (V1.4.1 - Debug Y)",
    "author": "Gemini & User",
    "version": (1, 4, 1),
    "blender": (3, 0, 0),
    "location": "File > Import > Capcom Outbreak Anim (.mot)",
    "description": "V1.4.1: Log LOC_Y at Frame 0 for all nodes",
    "category": "Import-Export",
}

import bpy
import struct
from bpy_extras.io_utils import ImportHelper

def apply_capcom_logic_v14(filepath):
    print("\n" + "="*60)
    print(f"IMPORTING: {filepath}")
    print("="*60)
    
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    
    ROT_PRECISION = 2607.5945876 
    LOC_PRECISION = 16.0 
    FACE_PRECISION = 256.0
    SCL_PRECISION = 16.0  

    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.fps_base = 1.0

    if arm:
        if arm.animation_data:
            arm.animation_data_clear()
        if arm.type == 'ARMATURE':
            for bone in arm.pose.bones:
                bone.rotation_mode = 'XYZ'
    
    for i in range(30):
        node = bpy.data.objects.get(f"Node{i}")
        if node and node != arm:
            if node.animation_data:
                node.animation_data_clear()
    
    track_types = {
        0x001: ("SCL_X", "scale", 0),
        0x002: ("SCL_Y", "scale", 1),
        0x004: ("SCL_Z", "scale", 2),
        0x008: ("ROT_X", "rotation_euler", 0),
        0x010: ("ROT_Y", "rotation_euler", 1),
        0x020: ("ROT_Z", "rotation_euler", 2),
        0x040: ("LOC_X", "location", 0),
        0x080: ("LOC_Y", "location", 1),
        0x100: ("LOC_Z", "location", 2),
    }

    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            current_section_offset = 0
            global_node_idx = 0

            while current_section_offset + 20 <= file_size:
                f.seek(current_section_offset)
                h_data = f.read(20)
                h_type, h_count, h_size, h_loop, h_loopFrame = struct.unpack("<IIIIf", h_data)
                
                if h_size == 0 or h_size > file_size:
                    break
                
                section_byte = h_count & 0xFF
                if section_byte == 0x0A: global_node_idx = 0
                elif section_byte == 0x0C: global_node_idx = 10
                elif section_byte == 0x06: global_node_idx = 22
                
                current_node_offset = current_section_offset + 20
                section_end = current_section_offset + h_size

                for n in range(h_count):
                    if current_node_offset + 12 > section_end: 
                        break
                    f.seek(current_node_offset)
                    n_type, n_sub, n_size = struct.unpack("<III", f.read(12))
                    
                    if n_type < 0x80000000:
                        current_node_offset += 4
                        continue
                    
                    node_name = f"Node{global_node_idx}"
                    target = None
                    if arm and arm.name == node_name: 
                        target = arm
                    elif arm and arm.type == 'ARMATURE': 
                        target = arm.pose.bones.get(node_name)
                    if not target: 
                        target = bpy.data.objects.get(node_name)

                    if n_sub > 0:
                        if target:
                            target.rotation_mode = 'XYZ'
                        
                        track_ptr = current_node_offset + 12
                        for s in range(n_sub):
                            f.seek(track_ptr)
                            t_type, t_keys, t_size = struct.unpack("<III", f.read(12))
                            format_type = (t_type >> 16) & 0xFF
                            track_type = t_type & 0xFFF
                            
                            if track_type in track_types:
                                label, prop, idx = track_types[track_type]
                                
                                is_facial = 23 <= global_node_idx <= 26
                                if is_facial and prop == "location":
                                    div = FACE_PRECISION
                                    mult = -1.0
                                elif prop == "scale":
                                    div = SCL_PRECISION
                                    mult = 1.0
                                elif prop == "location":
                                    div = LOC_PRECISION
                                    mult = 1.0
                                else: 
                                    div = ROT_PRECISION
                                    mult = 1.0
                                
                                if target:
                                    for k in range(t_keys):
                                        f.seek(track_ptr + 12 + (k * keyframe_size if k > 0 else 0)) # simplified seek for k=0
                                        # Per loggare il frame 0, leggiamo solo il primo valore
                                        f.seek(track_ptr + 12)
                                        
                                        keyframe_size = 16 if format_type == 0x22 else (8 if format_type == 0x12 else 4)
                                        
                                        if format_type == 0x11:
                                            val, frame = struct.unpack("<hh", f.read(4))
                                            f_val = (val / div) * mult
                                        elif format_type == 0x12:
                                            val, frame, c0, c1 = struct.unpack("<hhhh", f.read(8))
                                            f_val = (val / div) * mult
                                        elif format_type == 0x22:
                                            val_f, frame_f, c0, c1 = struct.unpack("<ffff", f.read(16))
                                            frame = int(frame_f)
                                            f_val = val_f * mult
                                        else:
                                            val, frame = struct.unpack("<hh", f.read(4))
                                            f_val = (val / div) * mult

                                        # DEBUG RICHIESTO: Log Y al frame 0
                                        if label == "LOC_Y" and frame == 0:
                                            print(f"[DEBUG] {node_name} | LOC_Y Frame 0: {f_val:.4f}")

                                        # Torna alla posizione corretta per il loop keyframe originale
                                        f.seek(track_ptr + 12 + (k * keyframe_size))
                                        # ... (ri-lettura per applicazione keyframe)
                                        if format_type == 0x11:
                                            val, frame = struct.unpack("<hh", f.read(4))
                                            f_val = (val / div) * mult
                                        elif format_type == 0x12:
                                            val, frame, c0, c1 = struct.unpack("<hhhh", f.read(8))
                                            f_val = (val / div) * mult
                                        elif format_type == 0x22:
                                            val_f, frame_f, c0, c1 = struct.unpack("<ffff", f.read(16))
                                            frame = int(frame_f)
                                            f_val = val_f * mult
                                        
                                        if prop == "location": 
                                            target.location[idx] = f_val
                                        elif prop == "scale": 
                                            target.scale[idx] = f_val
                                        else: 
                                            target.rotation_euler[idx] = f_val
                                        target.keyframe_insert(data_path=prop, index=idx, frame=frame)
                            
                            track_ptr += t_size
                    
                    current_node_offset += n_size
                    global_node_idx += 1
                    
                current_section_offset += h_size
        
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

class IMPORT_OT_capcom_outbreak_v14(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.capcom_outbreak_v14"
    bl_label = "Import Outbreak v1.4.1"
    filename_ext = ".mot"

    def execute(self, context):
        apply_capcom_logic_v14(self.filepath)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(IMPORT_OT_capcom_outbreak_v14)
    bpy.types.TOPBAR_MT_file_import.append(lambda self, context: self.layout.operator(IMPORT_OT_capcom_outbreak_v14.bl_idname, text="Outbreak Import (.mot)"))

if __name__ == "__main__":
    register()