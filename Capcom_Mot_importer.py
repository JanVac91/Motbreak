bl_info = {
    "name": "Capcom Outbreak Animation Importer (V1.4.0)",
    "author": "Gemini & User",
    "version": (1, 4, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > Capcom Outbreak Anim (.mot)",
    "description": "V1.4.0: Correct interpolation types support",
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
    SCL_PRECISION = 16.0  # Scale usa una precision diversa! 
    
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
    
    # Mappa dei track types (solo i bit bassi)
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
                
                print(f"\n[SECTION] Nodes: {h_count} (Start Node{global_node_idx})")

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
                    
                    # Trova il target
                    target = None
                    if arm and arm.name == node_name: 
                        target = arm
                    elif arm and arm.type == 'ARMATURE': 
                        target = arm.pose.bones.get(node_name)
                    if not target: 
                        target = bpy.data.objects.get(node_name)

                    if n_sub > 0:
                        print(f" -> {node_name}: {n_sub} tracks")
                        
                        if target:
                            target.rotation_mode = 'XYZ'
                        
                        track_ptr = current_node_offset + 12
                        for s in range(n_sub):
                            f.seek(track_ptr)
                            t_type, t_keys, t_size = struct.unpack("<III", f.read(12))
                            
                            # Estrai formato e tipo
                            format_type = (t_type >> 16) & 0xFF  # byte alto
                            track_type = t_type & 0xFFF          # bit bassi
                            
                            # Determina interpolazione
                            if format_type == 0x11:
                                interp = "Linear-16bit"
                                keyframe_size = 4  # 2 bytes value + 2 bytes frame
                            elif format_type == 0x12:
                                interp = "Hermite-16bit"
                                keyframe_size = 8  # value, frame, curve0, curve1
                            elif format_type == 0x22:
                                interp = "Hermite-32bit"
                                keyframe_size = 16  # 4 floats
                            else:
                                interp = f"Unknown-{format_type:02x}"
                                keyframe_size = 8  # Fallback
                            
                            # Trova il tipo di track
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
                                else:  # rotation
                                    div = ROT_PRECISION
                                    mult = 1.0
                                
                                print(f"    Track {s}: {label} | {interp} | {t_keys} keys")
                                
                                # Leggi keyframes
                                if target:
                                    for k in range(t_keys):
                                        f.seek(track_ptr + 12 + (k * keyframe_size))
                                        
                                        if format_type == 0x11:  # Linear 16-bit
                                            val, frame = struct.unpack("<hh", f.read(4))
                                            # Applica divisione per 16-bit integer
                                            f_val = (val / div) * mult
                                        elif format_type == 0x12:  # Hermite 16-bit
                                            val, frame, curve0, curve1 = struct.unpack("<hhhh", f.read(8))
                                            # Applica divisione per 16-bit integer
                                            f_val = (val / div) * mult
                                        elif format_type == 0x22:  # Hermite 32-bit float
                                            val_f, frame_f, curve0, curve1 = struct.unpack("<ffff", f.read(16))
                                            frame = int(frame_f)
                                            # NON dividere - è già un float!
                                            f_val = val_f * mult
                                        else:
                                            val, frame = struct.unpack("<hh", f.read(4))
                                            f_val = (val / div) * mult
                                        
                                        if prop == "location": 
                                            target.location[idx] = f_val
                                        elif prop == "scale": 
                                            target.scale[idx] = f_val
                                        else: 
                                            target.rotation_euler[idx] = f_val
                                        target.keyframe_insert(data_path=prop, index=idx, frame=frame)
                            else:
                                print(f"    Track {s}: UNKNOWN type {hex(track_type)} | {interp}")
                            
                            track_ptr += t_size
                    
                    current_node_offset += n_size
                    global_node_idx += 1
                    
                current_section_offset += h_size
        
        # SETUP IK
        if arm and arm.type == 'ARMATURE':
            print("\n--- Setting up IK constraints ---")
            for b_name, chain in [("Node9", 3), ("Node6", 3), ("Node19", 4), ("Node15", 4)]:
                bone = arm.pose.bones.get(b_name)
                if bone:
                    for c in bone.constraints:
                        if c.type == 'IK': 
                            bone.constraints.remove(c)
                    ik = bone.constraints.new('IK')
                    ik.chain_count = chain
                    print(f"  IK on {b_name} (chain: {chain})")

        print("\n" + "="*60 + "\nIMPORT COMPLETE\n" + "="*60)
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

class IMPORT_OT_capcom_outbreak_v14(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.capcom_outbreak_v14"
    bl_label = "Import Outbreak v1.4.0"
    filename_ext = ".mot"

    def execute(self, context):
        apply_capcom_logic_v14(self.filepath)
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_capcom_outbreak_v14.bl_idname, text="Outbreak Import (.mot)")

def register():
    bpy.utils.register_class(IMPORT_OT_capcom_outbreak_v14)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_capcom_outbreak_v14)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()