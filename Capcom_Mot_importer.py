bl_info = {
    "name": "Capcom Outbreak Animation Importer (V1.3.1)",
    "author": "Gemini & User",
    "version": (1, 3, 1),
    "blender": (3, 0, 0),
    "location": "File > Import > Capcom Outbreak Anim (.mot)",
    "description": "V1.3.1: Fixed section detection using h_count byte",
    "category": "Import-Export",
}

import bpy
import struct
from bpy_extras.io_utils import ImportHelper

def apply_capcom_logic_v12_summary(filepath, armature_name="Node2"):
    arm = bpy.data.objects.get(armature_name)
    ROT_PRECISION = 2607.5945876 
    LOC_PRECISION = 16.0 
    FACE_PRECISION = 256.0 

    # --- PULIZIA COMPLETA TUTTI I NODI ---
    if arm:
        # Pulisci i keyframe dell'armatura
        if arm.animation_data:
            arm.animation_data_clear()
        
        # Reset tutti i bones
        for bone in arm.pose.bones:
            bone.rotation_mode = 'XYZ'
        print(f"Ripuliti {len(arm.pose.bones)} bones dell'armatura")
    
    # Pulisci anche eventuali oggetti Node separati
    for i in range(30):  # Node0-Node29 per sicurezza
        node = bpy.data.objects.get(f"Node{i}")
        if node:
            if node.animation_data:
                node.animation_data_clear()
    
    loop_info = []  # Stores loop messages for the UI

    print(f"\n{'='*100}\nANIMATION TRACK SUMMARY\n{'='*100}")

    track_map = {}
    prefixes = [0x80120000, 0x80110000, 0x80000000]
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
                
                print(f"\n>>> SECTION at offset {current_section_offset:#x}")
                print(f"    h_type: {h_type:#x}, h_count: {h_count}, h_size: {h_size}, h_loop: {h_loop}, h_loopFrame: {h_loopFrame}")
                
                if h_size == 0 or h_size > file_size: 
                    print(f"    BREAK: h_size invalid ({h_size})")
                    break
                
                # Il byte che identifica la sezione è h_count!
                section_byte = h_count & 0xFF
                print(f"    section_byte: {section_byte:#x}")
                
                # --- IDENTIFICAZIONE SEZIONE ---
                if section_byte == 0x0A:
                    section_name = "LOWER"
                    global_node_idx = 0
                elif section_byte == 0x0C:
                    section_name = "UPPER"
                    global_node_idx = 10
                elif section_byte == 0x06:
                    section_name = "FACE"
                    global_node_idx = 22
                else:
                    section_name = "UNKNOWN"
                    
                print(f"    Section identified as: {section_name}")
                print(f"    global_node_idx starts at: {global_node_idx}")
                
                # --- LOOP DETECTION ---
                if h_loop != 0:
                    msg = f"LOOP DETECTED: {section_name} at frame {h_loopFrame}"
                    loop_info.append(msg)
                    print(f"!!! {msg} !!!")
                
                current_node_offset = current_section_offset + 20
                section_end = current_section_offset + h_size

                for n in range(h_count):
                    if current_node_offset + 12 > section_end: 
                        print(f"    Node {n}: BREAK - offset {current_node_offset:#x} exceeds section end {section_end:#x}")
                        break
                    f.seek(current_node_offset)
                    n_type, n_sub, n_size = struct.unpack("<III", f.read(12))
                    
                    print(f"    Node {n} (will be Node{global_node_idx}): offset={current_node_offset:#x}, n_type={n_type:#x}, n_sub={n_sub}, n_size={n_size}")
                    
                    if n_type < 0x80000000:
                        print(f"      SKIP: n_type < 0x80000000")
                        current_node_offset += 4
                        continue

                    node_name = f"Node{global_node_idx}"
                    target = arm.pose.bones.get(node_name) if arm else None
                    if not target: 
                        target = bpy.data.objects.get(node_name)
                    
                    is_facial = 23 <= global_node_idx <= 26

                    if n_sub > 0:
                        if target: 
                            target.rotation_mode = 'XYZ'
                        track_ptr = current_node_offset + 12
                        
                        for s in range(n_sub):
                            f.seek(track_ptr)
                            t_type, t_keys, t_size = struct.unpack("<III", f.read(12))
                            
                            print(f"      Track {s}: t_type={t_type:#x}, t_keys={t_keys}, t_size={t_size}")
                            
                            if t_type in track_map:
                                label, prop, idx = track_map[t_type]
                                
                                if is_facial and prop == "location":
                                    current_div = FACE_PRECISION
                                    multiplier = -1.0
                                else:
                                    current_div = LOC_PRECISION if prop == "location" else ROT_PRECISION
                                    multiplier = 1.0
                                
                                f.seek(track_ptr + 12)
                                val_first, frame_start, _, _ = struct.unpack("<hhhh", f.read(8))
                                f.seek(track_ptr + 12 + ((t_keys-1)*8))
                                val_last, frame_end, _, _ = struct.unpack("<hhhh", f.read(8))

                                print(f"TRACK: {node_name} | Type: {label} | Keys: {t_keys} | Frame: {frame_start}-{frame_end} | Raw Start: {val_first} | Raw End: {val_last} | Div: {current_div}")

                                for k in range(t_keys):
                                    f.seek(track_ptr + 12 + (k*8))
                                    val, frame, _, _ = struct.unpack("<hhhh", f.read(8))
                                    f_val = (val / current_div) * multiplier
                                    
                                    if target:
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
                
        print(f"\n{'='*100}\nSUMMARY END\n{'='*100}")
        return True, loop_info
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, [str(e)]

class IMPORT_OT_capcom_outbreak_summary(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.capcom_outbreak_summary"
    bl_label = "Import Capcom (.mot)"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".mot"

    def execute(self, context):
        success, loops = apply_capcom_logic_v12_summary(self.filepath)
        
        if success and loops:
            # Popup corretto con closure per accedere a loops
            def draw(self, context):
                for msg in loops:
                    self.layout.label(text=msg)
            
            context.window_manager.popup_menu(draw, title="Loop Information", icon='LOOP_FORWARDS')
        
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_capcom_outbreak_summary.bl_idname, text="Outbreak Import (.mot)")

def register():
    bpy.utils.register_class(IMPORT_OT_capcom_outbreak_summary)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_capcom_outbreak_summary)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()