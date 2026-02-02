bl_info = {
    "name": "Capcom Outbreak Animation Importer (V1.5)",
    "author": "Gemini & User",
    "version": (1, 5, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > Capcom Outbreak Anim (.mot)",
    "description": "V1.5: Append mode to add animation to current action",
    "category": "Import-Export",
}

import bpy
import struct
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty

def apply_capcom_logic_v15(filepath, append_mode=False, frame_offset=0):
    print("\n" + "="*60)
    print(f"IMPORTING: {filepath}")
    if append_mode:
        print(f"MODE: APPEND (starting at frame {frame_offset})")
    else:
        print(f"MODE: REPLACE (clear existing animation)")
    print("="*60)
    
    arm = bpy.data.objects.get("Node2") or bpy.data.objects.get("Node0")
    
    ROT_PRECISION = 2607.5945876 
    LOC_PRECISION = 16.0 
    FACE_PRECISION = 256.0
    SCL_PRECISION = 16.0  

    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.fps_base = 1.0

    if arm:
        # Solo in modalità REPLACE, pulisci le animazioni
        if not append_mode:
            if arm.animation_data:
                arm.animation_data_clear()
            if arm.type == 'ARMATURE':
                for bone in arm.pose.bones:
                    bone.rotation_mode = 'XYZ'
        else:
            # In modalità APPEND, assicurati che rotation_mode sia XYZ
            if arm.type == 'ARMATURE':
                for bone in arm.pose.bones:
                    bone.rotation_mode = 'XYZ'
    
    # Solo in modalità REPLACE, pulisci animazioni Node0/Node1
    if not append_mode:
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
            section_num = 0

            while current_section_offset + 20 <= file_size:
                f.seek(current_section_offset)
                h_data = f.read(20)
                h_type, h_count, h_size, h_loop, h_loopFrame = struct.unpack("<IIIIf", h_data)
                
                if h_size == 0 or h_size > file_size:
                    break
                
                section_byte = h_count & 0xFF
                section_name = "UNKNOWN"
                if section_byte == 0x0A:
                    global_node_idx = 0
                    section_name = "LOWER (0x0A)"
                elif section_byte == 0x0C:
                    global_node_idx = 10
                    section_name = "UPPER (0x0C)"
                elif section_byte == 0x06:
                    global_node_idx = 22
                    section_name = "FACE (0x06)"
                
                section_num += 1
                print(f"\n{'='*60}")
                print(f"SECTION {section_num}: {section_name}")
                print(f"  Offset: 0x{current_section_offset:08X}")
                print(f"  Node count: {h_count}")
                print(f"  Size: {h_size} bytes")
                print(f"  Loop: {h_loop}, Loop Frame: {h_loopFrame}")
                print(f"{'='*60}")
                
                current_node_offset = current_section_offset + 20
                section_end = current_section_offset + h_size

                for n in range(h_count):
                    if current_node_offset + 12 > section_end: 
                        break
                    f.seek(current_node_offset)
                    n_type, n_sub, n_size = struct.unpack("<III", f.read(12))
                    
                    node_name = f"Node{global_node_idx}"
                    
                    # Determina il tipo di target
                    target = None
                    target_type = "NOT FOUND"
                    if arm and arm.name == node_name:
                        target = arm
                        target_type = "ARMATURE OBJECT"
                    elif arm and arm.type == 'ARMATURE':
                        target = arm.pose.bones.get(node_name)
                        if target:
                            target_type = "BONE"
                    if not target:
                        target = bpy.data.objects.get(node_name)
                        if target:
                            target_type = "SEPARATE OBJECT"
                    
                    print(f"\n  Node{global_node_idx} ({target_type}):")
                    print(f"    n_type: 0x{n_type:08X}")
                    print(f"    Tracks found: {n_sub}")
                    print(f"    Node size: {n_size} bytes")
                    
                    # Se il nodo ha n_type < 0x80000000, skippa ma logga
                    if n_type < 0x80000000:
                        print(f"    Operation: SKIPPED (invalid n_type)")
                        current_node_offset += 4
                        global_node_idx += 1
                        continue
                    
                    # Variabili per tracciare frame range
                    min_frame = float('inf')
                    max_frame = float('-inf')
                    track_list = []

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
                                track_list.append(f"{label}({t_keys}keys)")
                                
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
                                
                                keyframe_size = 16 if format_type == 0x22 else (8 if format_type == 0x12 else 4)
                                
                                if target:
                                    for k in range(t_keys):
                                        f.seek(track_ptr + 12 + (k * keyframe_size))
                                        
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
                                        
                                        # In modalità APPEND, aggiungi l'offset
                                        adjusted_frame = frame + frame_offset
                                        
                                        # Traccia frame range (con offset)
                                        if adjusted_frame < min_frame:
                                            min_frame = adjusted_frame
                                        if adjusted_frame > max_frame:
                                            max_frame = adjusted_frame
                                        
                                        if prop == "location": 
                                            target.location[idx] = f_val
                                        elif prop == "scale": 
                                            target.scale[idx] = f_val
                                        else: 
                                            target.rotation_euler[idx] = f_val
                                        target.keyframe_insert(data_path=prop, index=idx, frame=adjusted_frame)
                            
                            track_ptr += t_size
                        
                        # Stampa i dettagli delle tracce trovate
                        if track_list:
                            print(f"    Tracks: {', '.join(track_list)}")
                        if min_frame != float('inf'):
                            print(f"    Frame range: {int(min_frame)} → {int(max_frame)}")
                            if append_mode:
                                print(f"    Operation: KEYFRAMES APPENDED (offset: +{frame_offset})")
                            else:
                                print(f"    Operation: KEYFRAMES INSERTED")
                        else:
                            print(f"    Operation: NO KEYFRAMES (empty tracks)")
                    else:
                        print(f"    Operation: EMPTY NODE (no tracks)")
                    
                    current_node_offset += n_size
                    global_node_idx += 1
                    
                current_section_offset += h_size
        
        print(f"\n{'='*60}")
        print("IMPORT COMPLETED")
        print(f"{'='*60}\n")
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

class IMPORT_OT_capcom_outbreak_v15(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.capcom_outbreak_v15"
    bl_label = "Import Outbreak v1.5"
    filename_ext = ".mot"
    
    append_mode: BoolProperty(
        name="Append Mode",
        description="Add animation to current action starting at timeline cursor (don't clear existing animation)",
        default=False,
    )

    def execute(self, context):
        # Ottieni la posizione corrente del cursore nella timeline
        current_frame = context.scene.frame_current
        
        # Se append_mode è attivo, usa il frame corrente come offset
        frame_offset = current_frame if self.append_mode else 0
        
        apply_capcom_logic_v15(self.filepath, append_mode=self.append_mode, frame_offset=frame_offset)
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_capcom_outbreak_v15.bl_idname, text="Outbreak Import (.mot)")

def register():
    bpy.utils.register_class(IMPORT_OT_capcom_outbreak_v15)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_capcom_outbreak_v15)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()