import bpy
import struct
import traceback
from bpy_extras.io_utils import ExportHelper

class EXPORT_OT_capcom_outbreak_logged(bpy.types.Operator, ExportHelper):
    bl_idname = "export_anim.capcom_outbreak_logged"
    bl_label = "Export Capcom (.mot)"
    filename_ext = ".mot"

    def find_fcurve_agnostic(self, node_name, prop, axis):
        """Cerca la curva e logga la sorgente trovata"""
        for obj in bpy.data.objects:
            if not (obj.animation_data and obj.animation_data.action):
                continue
            
            act = obj.animation_data.action
            
            # Caso A: Osso (PoseBone)
            bone_path = f'pose.bones["{node_name}"].{prop}'
            f = act.fcurves.find(bone_path, index=axis)
            if f:
                return f, f"OSSO in {obj.name} ({act.name})"
            
            # Caso B: Oggetto (Empty/Armature)
            if obj.name == node_name:
                f = act.fcurves.find(prop, index=axis)
                if f:
                    return f, f"OGGETTO {obj.name} ({act.name})"
        
        return None, "NON TROVATO (Default 0)"

    def create_track_block(self, fcurve, track_id, div_precision):
        if not fcurve or len(fcurve.keyframe_points) == 0:
            track_data = bytearray(struct.pack("<III", track_id, 1, 20))
            track_data.extend(struct.pack("<hhhh", 0, 0, 0, 0))
            return track_data

        keys = sorted(fcurve.keyframe_points, key=lambda k: k.co.x)
        track_data = bytearray(struct.pack("<III", track_id, len(keys), 12 + (len(keys) * 8)))
        
        for i, k in enumerate(keys):
            val = int(round(k.co.y * div_precision))
            val = max(-32768, min(32767, val))
            frame = int(k.co.x)
            m = 0
            if len(keys) > 1 and 0 < i < len(keys) - 1:
                df = keys[i+1].co.x - keys[i-1].co.x
                if df != 0:
                    m = int(round(((keys[i+1].co.y - keys[i-1].co.y) * div_precision) / df))
            track_data.extend(struct.pack("<hhhh", val, frame, m, m))
        return track_data

    def execute(self, context):
        mapping = {
            0x0001: "ROT_X", 0x0008: "ROT_X", 0x0002: "ROT_Y", 0x0010: "ROT_Y",
            0x0004: "ROT_Z", 0x0020: "ROT_Z", 0x0040: "LOC_X", 0x0080: "LOC_Y", 0x0100: "LOC_Z",
        }
        
        # Mapping tecnico per le proprietà di Blender
        prop_map = {
            "ROT": "rotation_euler",
            "LOC": "location"
        }

        print("\n" + "="*80)
        print(f"INIZIO ESPORTAZIONE: {self.filepath}")
        print("="*80)

        try:
            with open(self.filepath, "rb") as f:
                orig_data = f.read()
            
            new_file = bytearray()
            cursor = 0
            g_idx = 0
            ROT_P, LOC_P = 2607.5945876, 16.0

            while cursor + 20 <= len(orig_data):
                h_type, h_count, h_size, h_unk, h_loop = struct.unpack("<IIIIf", orig_data[cursor:cursor+20])
                nodes_buf = bytearray()
                n_ptr = cursor + 20
                
                s_byte = h_count & 0xFF
                if s_byte == 0x0A: g_idx = 0
                elif s_byte == 0x0C: g_idx = 10
                
                print(f"\n--- SEZIONE {hex(h_type)} ({h_count} nodi) ---")

                for n in range(h_count):
                    n_type, n_sub, n_size = struct.unpack("<III", orig_data[n_ptr:n_ptr+12])
                    node_name = f"Node{g_idx}"
                    
                    if n_type >= 0x80000000 and n_sub > 0:
                        print(f"\n[{node_name}] processing...")
                        track_cursor = n_ptr + 12
                        node_tracks_buf = bytearray()
                        
                        for s in range(n_sub):
                            t_type, _, t_size = struct.unpack("<III", orig_data[track_cursor:track_cursor+12])
                            base_id = t_type & 0xFFFF
                            
                            label = mapping.get(base_id, "UNK")
                            fcurve = None
                            
                            if label != "UNK":
                                p_type = label.split('_')[0]
                                p_axis = "XYZ".find(label.split('_')[1])
                                fcurve, source = self.find_fcurve_agnostic(node_name, prop_map[p_type], p_axis)
                                keys_num = len(fcurve.keyframe_points) if fcurve else 0
                                print(f"  > Traccia {s} ({label}): {source} | Keys: {keys_num}")
                            
                            div = LOC_P if (base_id >= 0x40) else ROT_P
                            node_tracks_buf.extend(self.create_track_block(fcurve, t_type, div))
                            track_cursor += t_size
                        
                        nodes_buf.extend(struct.pack("<III", n_type, n_sub, 12 + len(node_tracks_buf)))
                        nodes_buf.extend(node_tracks_buf)
                    else:
                        nodes_buf.extend(orig_data[n_ptr : n_ptr + n_size])
                    
                    n_ptr += n_size
                    g_idx += 1
                
                new_file.extend(struct.pack("<IIIIf", h_type, h_count, 20 + len(nodes_buf), h_unk, h_loop))
                new_file.extend(nodes_buf)
                cursor += h_size

            with open(self.filepath, "wb") as f:
                f.write(new_file)
            
            print("\n" + "="*80)
            print("ESPORTAZIONE COMPLETATA CON SUCCESSO")
            print("="*80)
            return {'FINISHED'}

        except Exception as e:
            print(f"\nERRORE CRITICO: {str(e)}")
            print(traceback.format_exc())
            return {'CANCELLED'}

def register():
    bpy.utils.register_class(EXPORT_OT_capcom_outbreak_logged)
    bpy.types.TOPBAR_MT_file_export.append(lambda self, context: self.layout.operator(EXPORT_OT_capcom_outbreak_logged.bl_idname, text="Outbreak Universal (Logged) (.mot)"))

if __name__ == "__main__":
    register()