import re
from .constants import PREDEFINED_PLANES

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
    def extract_sketch_plane(description, created_plane_ids, feature_ids, primitive_ids):
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
            for pid in created_plane_ids:
                if pid in content:
                    return pid
            for k, v in PREDEFINED_PLANES.items():
                if k in content:
                    return v
            entities = []
            for fid, ftype in feature_ids:
                if fid in content:
                    entities.append([ftype, fid])
            for pid, pname in primitive_ids:
                if pid in content:
                    entities.append([pname, pid])
            if "CAP_FACE" in content:
                entities.append(["CAP_FACE"])
            if "SWEPT_FACE" in content:
                entities.append(["SWEPT_FACE"])
            if entities:
                return entities
            return content
        return qref
