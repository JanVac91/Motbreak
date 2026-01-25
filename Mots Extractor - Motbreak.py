import struct
import os
import sys

def extract_mot_final(filepath):
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        print(f"Error: File {filepath} not found.")
        return

    file_basename = os.path.splitext(os.path.basename(filepath))[0]
    with open(filepath, "rb") as f:
        data = f.read()

    # 1. Get descriptor start from header (bytes 12-15)
    try:
        desc_start = struct.unpack("<I", data[12:16])[0]
    except Exception as e:
        print(f"Error reading BIN header: {e}")
        return

    # 2. Scan table to find the minimum offset (boundary)
    animation_table = []
    min_data_offset = len(data)
    pos = desc_start

    print(f"--- TABLE ANALYSIS (Start: {hex(desc_start)}) ---")
    
    # First pass: find the boundary and collect 20-byte entries
    while pos < min_data_offset:
        if pos + 20 > len(data):
            break
            
        record = struct.unpack("<IIIII", data[pos:pos+20])
        
        is_valid_entry = False
        for ptr in record:
            if ptr != 0xFFFFFFFF and ptr != 0:
                is_valid_entry = True
                if ptr < min_data_offset:
                    min_data_offset = ptr
        
        # Stop if we've reached the data we just found
        if pos >= min_data_offset:
            break

        animation_table.append(record)
        pos += 20

    print(f"Table end detected at: {hex(pos)}")
    print(f"Minimum data offset (data start): {hex(min_data_offset)}")
    print(f"Total animations found: {len(animation_table)}")
    print("-" * 60)

    # 3. Debug animation entries
    for i, entry in enumerate(animation_table):
        ptr_hex = [f"{p:08X}" if p != 0xFFFFFFFF else "--------" for p in entry]
        print(f"Anim {i+1:03d} | L:{ptr_hex[0]} U:{ptr_hex[1]} F:{ptr_hex[2]} R:{ptr_hex[3]} L:{ptr_hex[4]}")

    # 4. Extraction and Merging
    # Folder name format: FileName_Exported_Mots
    output_folder = os.path.join(os.path.dirname(filepath), f"{file_basename}_Exported_Mots")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    extracted_count = 0
    for i, entry in enumerate(animation_table):
        combined_mot = bytearray()
        sections_in_anim = 0
        
        for ptr in entry:
            if ptr == 0xFFFFFFFF or ptr == 0 or ptr >= len(data):
                continue
                
            try:
                # MOT section header (02 00) check and size at offset + 8
                if data[ptr:ptr+2] == b'\x02\x00':
                    size = struct.unpack("<I", data[ptr+8:ptr+12])[0]
                    if size > 0 and (ptr + size) <= len(data):
                        combined_mot.extend(data[ptr : ptr + size])
                        sections_in_anim += 1
            except:
                continue

        if combined_mot:
            out_name = f"{file_basename}_{i+1:03d}.mot"
            with open(os.path.join(output_folder, out_name), "wb") as f:
                f.write(combined_mot)
            extracted_count += 1

    print(f"\nExtraction finished! {extracted_count} files saved in: {output_folder}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_mot_final(sys.argv[1])
    else:
        print("Please drag and drop the .bin file onto this script.")
    os.system("pause")