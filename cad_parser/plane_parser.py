import re
import base64
import zlib
from .constants import PREDEFINED_PLANES

def decompress_query(compressed_str):
    """
    Decompress OnShape qCompressed() query strings.
    Format: qCompressed(1.0, "&1ed$<base64_data>", id)
    """
    try:
        # Extract the base64 data from qCompressed(1.0, "...", id)
        match = re.search(r'qCompressed\s*\([^,]+,\s*"([^"]+)"', compressed_str)
        if not match:
            return None
        
        data = match.group(1)
        # Remove the &1ed$ prefix (OnShape version marker)
        if data.startswith("&1ed$"):
            data = data[5:]
        
        # Base64 decode then decompress
        decoded = base64.b64decode(data)
        decompressed = zlib.decompress(decoded)
        return decompressed.decode('utf-8')
    except Exception:
        return None

def extract_query_assignment(description, qref):
    # Match the entire assignment line: var qref; ... (up to but not including the semicolon and ending newline)
    pattern = rf'var {re.escape(qref)};\n(.*?)\n'
    match = re.search(pattern, description)
    if match:
        return match.group(1).strip()
    return None

class PlaneParser:
    @staticmethod
    def extract_created_planes(description):
        return re.findall(r'\bid\s*\+\s*"([^"]+)"(?=.*?cPlane\s*\()', description)

    @staticmethod
    def extract_sketch_plane(description, created_plane_ids, feature_ids, primitive_ids, feature_names=None, primitive_names=None):
        match = re.search(r'sketchPlane"\s*:\s*qUnion\s*\(\s*\[([^\]]+)\]', description)
        if not match:
            return "unknown"
        qref = match.group(1).strip()

        # query_def_match = re.search(rf'{qref}\s*=\s*(.*?)\);', description)
        # if query_def_match:
        #     content = query_def_match.group(1)
        assignment = extract_query_assignment(description, qref)
        if assignment:
            content = assignment
            
            # Check if this is a compressed query
            if "qCompressed" in content:
                decompressed = decompress_query(content)
                if decompressed:
                    # Extract operation IDs and face types from decompressed query
                    entities = []
                    
                    # Look for extrude operation ID (format: S11.9$Fq3SRIpNQ3Zam5R_0)
                    extrude_match = re.search(r'S\d+\.\d+\$([A-Za-z0-9_]+)opExtrude', decompressed)
                    if extrude_match:
                        extrude_id = extrude_match.group(1)
                        extrude_name = feature_names.get(extrude_id, "Unknown") if feature_names else "Unknown"
                        entities.append(["extrude", extrude_id, extrude_name])
                    
                    # Look for sketch ID (format: S11.6$Fea64cIJHKHcjTF_0)
                    sketch_match = re.search(r'S\d+\.\d+\$([A-Za-z0-9_]+)(?:wireOp|opExtrude)', decompressed)
                    if sketch_match:
                        sketch_id = sketch_match.group(1)
                        # Only add if it's not the extrude ID we already found
                        if not extrude_match or sketch_id != extrude_match.group(1):
                            sketch_name = feature_names.get(sketch_id, "Unknown") if feature_names else "Unknown"
                            entities.append(["newSketch", sketch_id, sketch_name])
                    
                    # Check for CAP_FACE with side information
                    if "CAP_FACE" in decompressed:
                        # Look for isStart field: isStartT (TRUE=START/bottom) or isStartF (FALSE=END/top)
                        is_start_match = re.search(r'isStart([TF])', decompressed)
                        if is_start_match:
                            is_start = is_start_match.group(1) == 'T'
                            side = "START" if is_start else "END"
                            entities.append(["CAP_FACE", side])
                        else:
                            # No side specified
                            entities.append(["CAP_FACE"])
                    
                    if "SWEPT_FACE" in decompressed:
                        entities.append(["SWEPT_FACE"])
                    
                    if entities:
                        return entities
                    
                    # If we couldn't parse the query, fall back to original content
                    content = assignment
            
            for pid in created_plane_ids:
                if pid in content:
                    return pid
            for k, v in PREDEFINED_PLANES.items():
                if k in content:
                    return v
            entities = []
            for fid, ftype in feature_ids:
                if fid in content:
                    fname = feature_names.get(fid, "Unknown") if feature_names else "Unknown"
                    entities.append([ftype, fid, fname])
            for pid, pname in primitive_ids:
                if pid in content:
                    friendly_name = primitive_names.get(pid, "Unknown") if primitive_names else "Unknown"
                    entities.append([pname, pid, friendly_name])
            if "CAP_FACE" in content:
                entities.append(["CAP_FACE"])
            if "SWEPT_FACE" in content:
                entities.append(["SWEPT_FACE"])
            if entities:
                return entities
            return content
        return qref
