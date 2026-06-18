import struct
import os
import sys

# Section type → (name, node_count)
# Nodes are sequential: each section starts where the previous ended.
# Human:  0x0A(10) + 0x0C(12) + 0x06(6) + 0x04(4) + 0x04(4) = 36 nodes
# Monster id23: 0x1D(29)
# Monster id43: 0x0C(12) + 0x07(7) + 0x04(4) + 0x0E(14) + 0x10(16) = 53 nodes
SECTION_TYPES = {
    0x0A: ("LOWER",   10),
    0x0C: ("UPPER",   12),
    0x06: ("FACE",     6),
    0x04: ("HANDS",    4),
    0x1D: ("MONSTER", 29),
    0x07: ("MON_07",   7),
    0x0E: ("MON_0E",  14),
    0x10: ("MON_10",  16),
    0x16: ("MON_16",  22),  # id12 monster - single block
}

def is_valid_section(data, ptr):
    """Check if ptr points to a valid section header (02 00 00 80 ...)"""
    if ptr == 0 or ptr == 0xFFFFFFFF or ptr + 12 > len(data):
        return False
    h_type = struct.unpack("<I", data[ptr:ptr+4])[0]
    if h_type != 0x80000002:
        return False
    h_count = struct.unpack("<I", data[ptr+4:ptr+8])[0]
    h_size  = struct.unpack("<I", data[ptr+8:ptr+12])[0]
    section_byte = h_count & 0xFF
    if section_byte not in SECTION_TYPES:
        return False
    if h_size == 0 or ptr + h_size > len(data):
        return False
    return True

def get_section_info(data, ptr):
    """Returns (section_name, node_count, size) for a valid section."""
    h_count = struct.unpack("<I", data[ptr+4:ptr+8])[0]
    h_size  = struct.unpack("<I", data[ptr+8:ptr+12])[0]
    section_byte = h_count & 0xFF
    name, node_count = SECTION_TYPES.get(section_byte, (f"UNK_{section_byte:02X}", 0))
    return name, node_count, h_size

def detect_ptrs_per_row(data, desc_start, min_data_offset):
    """
    Auto-detect how many pointers per table row.

    Strategy: read the FIRST ROW only (up to min_data_offset),
    then count how many 4-byte slots that row contains.
    A row ends when we see a second valid section of the SAME type
    as the first section found in the row (meaning a new row started).
    """
    pos = desc_start
    first_section_type = None
    slot_count = 0

    while pos + 4 <= min_data_offset:
        ptr = struct.unpack("<I", data[pos:pos+4])[0]

        if is_valid_section(data, ptr):
            h_count = struct.unpack("<I", data[ptr+4:ptr+8])[0]
            section_byte = h_count & 0xFF
            if first_section_type is None:
                # First valid section found - this is what starts each row
                first_section_type = section_byte
                slot_count += 1
            elif section_byte == first_section_type:
                # We hit the same section type again = new row started
                break
            else:
                slot_count += 1
        else:
            # Empty slot (0 or 0xFFFFFFFF)
            if first_section_type is not None:
                slot_count += 1
            # else: leading padding before first valid ptr, skip
        
        pos += 4

    if slot_count == 0:
        print("WARNING: Could not detect row size, defaulting to 5 (human)")
        return 5

    # Log first row contents for debugging
    names = []
    scan = desc_start
    for _ in range(slot_count):
        if scan + 4 > len(data):
            break
        ptr = struct.unpack("<I", data[scan:scan+4])[0]
        if is_valid_section(data, ptr):
            name, node_count, _ = get_section_info(data, ptr)
            names.append(f"{name}({node_count})")
        else:
            names.append("EMPTY")
        scan += 4

    print(f"First row sections: {' + '.join(names)}")
    print(f"Detected {slot_count} pointer(s) per row")
    return slot_count

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

    # 2. Scan table with 4-byte steps to find minimum data offset
    animation_table = []
    min_data_offset = len(data)
    pos = desc_start

    print(f"--- TABLE ANALYSIS (Start: {hex(desc_start)}) ---")

    # First pass: find min_data_offset by scanning all 4-byte values
    scan_pos = desc_start
    while scan_pos + 4 <= len(data):
        val = struct.unpack("<I", data[scan_pos:scan_pos+4])[0]
        if val != 0 and val != 0xFFFFFFFF and val < min_data_offset:
            if is_valid_section(data, val):
                min_data_offset = val
        scan_pos += 4
        if scan_pos >= min_data_offset:
            break

    print(f"Minimum data offset (data start): {hex(min_data_offset)}")

    # 3. Auto-detect how many pointers per row
    ptrs_per_row = detect_ptrs_per_row(data, desc_start, min_data_offset)
    row_size = ptrs_per_row * 4

    # 4. Build animation table with detected row size
    pos = desc_start
    while pos + row_size <= min_data_offset:
        if pos + row_size > len(data):
            break

        fmt = "<" + "I" * ptrs_per_row
        record = struct.unpack(fmt, data[pos:pos+row_size])

        # Only add row if at least one pointer is valid
        if any(is_valid_section(data, ptr) for ptr in record):
            animation_table.append(record)

        pos += row_size

    print(f"Table end detected at: {hex(pos)}")
    print(f"Total animations found: {len(animation_table)}")
    print("-" * 60)

    # 5. Extract and merge sections per animation
    output_folder = os.path.join(os.path.dirname(filepath), f"{file_basename}_Exported_Mots")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    extracted_count = 0

    for i, entry in enumerate(animation_table):
        combined_mot = bytearray()
        section_names = []

        for ptr in entry:
            if not is_valid_section(data, ptr):
                continue
            name, node_count, size = get_section_info(data, ptr)
            combined_mot.extend(data[ptr:ptr+size])
            section_names.append(f"{name}({node_count})")

        if combined_mot:
            out_name = f"{file_basename}_{extracted_count:03d}.mot"
            sections_str = " + ".join(section_names)
            print(f"Exporting {out_name} | Row {i+1:03d} | {sections_str}")

            with open(os.path.join(output_folder, out_name), "wb") as f:
                f.write(combined_mot)

            extracted_count += 1

    print("-" * 60)
    print(f"Extraction finished! {extracted_count} files saved in: {output_folder}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_mot_final(sys.argv[1])
    else:
        print("Please drag and drop the .bin file onto this script.")
    os.system("pause")