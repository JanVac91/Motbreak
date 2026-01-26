bl_info = {
    "name": "Capcom Outbreak Animation Importer (V1.3.6)",
    "author": "Gemini & User",
    "version": (1, 3, 6),
    "blender": (3, 0, 0),
    "location": "File > Import > Capcom Outbreak Anim (.mot)",
    "description": "V1.3.6: Ultra-Detailed Track Logging + Full Features",
    "category": "Import-Export",
}

import bpy
import struct
from bpy_extras.io_utils import ImportHelper

def apply_capcom_logic_v136(filepath):
    print("\n" + "="*60)
    print(f"DEBUG SCAN FOR: {filepath}")
    print("="*60)
    
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    
    ROT_PRECISION = 2607.5945876 
    LOC_PRECISION = 16.0 
    FACE_PRECISION = 256.0 
    
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
    
    track_map = {}
    prefixes = [0x80220000, 0x80120000, 0x80110000, 0x80000000]
    for p in prefixes:
        for b in [0x0001, 0x0008]: track_map[p | b] = ("ROT_X", "rotation_euler", 0)
        for b in [0x0002, 0x0010]: track_map[p | b] = ("ROT_Y", "rotation_euler", 1)
        for b in [0x0004, 0x0020]: track_map[p | b] = ("ROT_Z", "rotation_euler", 2)
        track_map[p | 0x0040] = ("LOC_X", "location", 0)
        track_map[p | 0x0080] = ("LOC_Y", "location", 1)
        track_map[p | 0x0100] = ("LOC_Z", "location", 2)
        track_map[p | 0x0400] = ("SCL_X", "scale", 0)
        track_map[p | 0x0800] = ("SCL_Y", "scale", 1)
        track_map[p | 0x1000] = ("SCL_Z", "scale", 2)

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
                
                section_byte = h_count & 0xFF
                if section_byte == 0x0A: global_node_idx = 0
                elif section_byte == 0x0C: global_node_idx = 10
                elif section_byte == 0x06: global_node_idx = 22
                
                print(f"\n[SECTION] Nodes: {h_count} (Start G_Idx: {global_node_idx})")

                current_node_offset = current_section_offset + 20
                section_end = current_section_offset + h_size

                for n in range(h_count):
                    if current_node_offset + 12 > section_end: break
                    f.seek(current_node_offset)
                    n_type, n_sub, n_size = struct.unpack("<III", f.read(12))
                    
                    node_name = f"Node{global_node_idx}"
                    
                    if n_type >= 0x80000000:
                        print(f" -> {node_name} (Flag: {hex(n_type)}) has {n_sub} tracks:")
                        
                        target = None
                        if arm and arm.name == node_name: target = arm
                        elif arm and arm.type == 'ARMATURE': target = arm.pose.bones.get(node_name)
                        if not target: target = bpy.data.objects.get(node_name)

                        track_ptr = current_node_offset + 12
                        for s in range(n_sub):
                            f.seek(track_ptr)
                            t_type, t_keys, t_size = struct.unpack("<III", f.read(12))
                            
                            status = "UNKNOWN"
                            if t_type in track_map:
                                label, prop, idx = track_map[t_type]
                                status = f"MAPPED ({label})"
                                
                                if target:
                                    target.rotation_mode = 'XYZ'
                                    is_facial = 23 <= global_node_idx <= 26
                                    div = FACE_PRECISION if (is_facial and prop == "location") else (LOC_PRECISION if prop == "location" else ROT_PRECISION)
                                    mult = -1.0 if (is_facial and prop == "location") else 1.0
                                    
                                    for k in range(t_keys):
                                        f.seek(track_ptr + 12 + (k*8))
                                        val, frame, _, _ = struct.unpack("<hhhh", f.read(8))
                                        f_val = (val / div) * mult
                                        if prop == "location": target.location[idx] = f_val
                                        elif prop == "scale": target.scale[idx] = f_val
                                        else: target.rotation_euler[idx] = f_val
                                        target.keyframe_insert(data_path=prop, index=idx, frame=frame)
                            
                            print(f"    Track {s}: ID {hex(t_type)} | Keys: {t_keys} | {status}")
                            track_ptr += t_size
                        
                        if not target:
                            print(f"    [!] WARNING: Target {node_name} not found in Blender!")
                    
                    current_node_offset += n_size
                    global_node_idx += 1
                current_section_offset += h_size
        
        # SETUP IK
        if arm and arm.type == 'ARMATURE':
            for b_name, chain in [("Node9", 3), ("Node6", 3), ("Node19", 4), ("Node15", 4)]:
                bone = arm.pose.bones.get(b_name)
                if bone:
                    for c in bone.constraints:
                        if c.type == 'IK': bone.constraints.remove(c)
                    ik = bone.constraints.new('IK')
                    ik.chain_count = chain

        print("\n" + "="*60 + "\nSCAN COMPLETE\n" + "="*60)
        return True
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        return False

class IMPORT_OT_capcom_outbreak_v136(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.capcom_outbreak_v136"
    bl_label = "Import Outbreak v1.3.6"
    filename_ext = ".mot"

    def execute(self, context):
        apply_capcom_logic_v136(self.filepath)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(IMPORT_OT_capcom_outbreak_v136)
    bpy.types.TOPBAR_MT_file_import.append(lambda self, context: self.layout.operator(IMPORT_OT_capcom_outbreak_v136.bl_idname, text="Outbreak Import v1.3.6 (.mot)"))

if __name__ == "__main__":
    register()