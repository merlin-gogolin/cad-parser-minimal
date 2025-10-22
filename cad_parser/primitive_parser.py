import re
import numpy as np
from .constants import PRIMITIVE_NAMES

def parse_key_value_pairs(obj_str):
    pairs = []
    i = 0
    n = len(obj_str)

    while i < n:
        # === Find the start of the key ===
        while i < n and obj_str[i].isspace():
            i += 1
        if i >= n or obj_str[i] != '"':
            break  # no more key-value pairs

        # === Parse key ===
        i += 1  # skip opening quote
        key_start = i
        while i < n and obj_str[i] != '"':
            i += 1
        key = obj_str[key_start:i]
        i += 1  # skip closing quote

        # === Skip colon ===
        while i < n and obj_str[i] != ':':
            i += 1
        i += 1  # skip colon

        # === Parse value ===
        while i < n and obj_str[i].isspace():
            i += 1

        val_start = i
        stack = []

        while i < n:
            c = obj_str[i]
            if c in '({[':
                stack.append(c)
            elif c in ')}]':
                if stack:
                    stack.pop()
            elif c == ',' and not stack:
                break  # top-level comma => end of value
            i += 1

        value = obj_str[val_start:i].strip()
        pairs.append((key, value))
        i += 1  # skip comma

    return dict(pairs)


class PrimitiveParser:
    @staticmethod
    def extract_initial_guess(description, feature_id):
        guess_dict = {}
        match = re.search(rf'const\s+initialGuess.*?{re.escape(feature_id)}\s*=\s*{{(.*?)}};', description, re.DOTALL)
        if match:
            for pair in re.findall(r'"([^"]+)"\s*:\s*\[([^\]]+)\]', match.group(1)):
                key, values = pair
                points = [float(v.strip()) for v in values.split(",")]
                guess_dict[key] = points
        return guess_dict

    @staticmethod
    def parse_geometry(ptype, pts):
        if not pts:
            return {}
        if ptype == "skLineSegment" and len(pts) >= 6:
            x0, y0, dx, dy, d1, d2 = pts[:6]
            start = [x0 + dx * d1, y0 + dy * d1]
            end = [x0 + dx * d2, y0 + dy * d2]
            return {"start": start, "end": end}

        elif ptype == "skCircle" and len(pts) >= 5:
            center = pts[0:2]
            radius = abs(pts[4])
            return {"center": center, "radius": radius}

        elif ptype == "skInterpolatedSplineSegment" and len(pts) >= 6:
            count = int(pts[1])//2
            spline_pts = [pts[2 + 2*i:2 + 2*i + 2] for i in range(count)]
            tangents = {
                "start_tangent": pts[-6:-4],
                "end_tangent": pts[-4:-2]
            }
            return {"points": spline_pts, **tangents}

        elif ptype == "skInterpolatedSpline" and len(pts) >= 2:
            spline_pts = [pts[i:i+2] for i in range(2, len(pts), 2)]
            return {"points": spline_pts, "count": len(spline_pts)}

        elif ptype == "skPoint":
            return {"point": pts[0:2]}

        elif ptype == "skEllipse" and len(pts) >= 6:
            center = pts[0:2]
            dir_vec = pts[2:4]
            major = pts[4]
            minor = pts[5]
            return {"center": center, "direction": dir_vec, "major": major, "minor": minor}

        elif ptype == "skArc" and len(pts) >= 8:
            cx, cy = pts[0:2]
            axis = pts[2:4]
            direction = pts[5]
            radius = abs(pts[4])
            phi_start = pts[6]
            phi_end = pts[7]
            if phi_end - phi_start > 2 * np.pi:
                while phi_end - phi_start > 2 * np.pi:
                    phi_end -= 2 * np.pi
            if phi_start - phi_end > 2 * np.pi:
                while phi_start - phi_end > 2 * np.pi:
                    phi_start -= 2 * np.pi

            # Step 1: angle of axis w.r.t. x-axis
            axis_angle = np.arctan2(axis[1], axis[0])

            # Step 2: re-express phi angles w.r.t x-axis
            new_phi_start = phi_start + axis_angle
            new_phi_end = phi_end + axis_angle

            # Step 3: enforce CCW direction
            if direction == 1:  # originally clockwise
                new_phi_start, new_phi_end = axis_angle - phi_end, axis_angle - phi_start

            if new_phi_end < new_phi_start:
                new_phi_end += 2 * np.pi  # Ensure CCW direction

            return {
                "center": (cx, cy),
                "radius": radius,
                "phi_start": new_phi_start,
                "phi_end": new_phi_end
            }

        elif ptype == "skSplineSegment":
            count = int(pts[3])
            spline_pts = [pts[2*i:2*i+2] for i in range(2, count + 2)]
            return {"points": spline_pts, "count": count}

        else:
            return {"unknown": {}}

    @staticmethod
    def extract_sketch_primitives(description, initial_guess, primitive_ids):
        primitives = {}
        for pname in PRIMITIVE_NAMES:
            if pname == "skImage":
                continue
            if pname == "skText":
                for match in re.finditer(
                    rf'{pname}\s*\(\s*sketch\s*,\s*"([^"]+)"\s*,\s*\{{[^}}]*"text"\s*:\s*"([^"]+)"',
                    description
                ):
                    pid = match.group(1)
                    text_content = match.group(2)
                    pts = initial_guess.get(pid, [])
                    primitives[pid] = {
                        "type": pname,
                        "points": pts,
                        "geometry": {"text": text_content}
                    }
                    primitive_ids.append((pid, pname))

            # Match pattern: skLineSegment(sketch, "ID", { "construction": true/false, ... });
            pattern = rf'{pname}\s*\(\s*sketch\s*,\s*"([^"]+)"\s*,\s*\{{[^}}]*"construction"\s*:\s*(true|false)'
            for match in re.finditer(pattern, description):
                pid = match.group(1)
                construction = match.group(2) == "true"
                pts = initial_guess.get(pid, [])
                primitives[pid] = {
                    "type": pname,
                    "points": pts,
                    "geometry": PrimitiveParser.parse_geometry(pname, pts),
                    "construction": construction
                }
                primitive_ids.append((pid, pname))
        return primitives
    
    @staticmethod
    def extract_parameters(description, feature_type, feature_ids, primitive_ids):
        result = {}

        # Step 1: Extract variable assignments before extrude call
        assignments = {}

        # Match pattern: var name; { block }
        # pattern = re.compile(
        #     r'var\s+(\w+)\s*;\s*\{\s*([^}]+)\s*\}', re.DOTALL
        # )
        pattern = re.compile(rf'var\s+(\w+);\n(.*?)\n', re.DOTALL)

        for match in pattern.finditer(description):
            var_name = match.group(1)
            block = match.group(2).strip()
            if block:
                assignments[var_name] = block

        extrude_match = re.search(
            rf'{re.escape(feature_type)}\s*\([^,]+,\s*[^,]+,\s*(\{{.*?}}\s*)\);',
            description,
            re.DOTALL
        )
        if not extrude_match:
            return {}

        extrude_body = extrude_match.group(1)

        clean_input = extrude_body.strip()[1:-1].strip()
        parsed = parse_key_value_pairs(clean_input)
        for key, raw_value in parsed.items():
            raw_value = raw_value.strip()
            # Handle qUnion([...])
            if raw_value.startswith("qUnion(["):
                inner = re.search(r'qUnion\(\[(.*)\]\)', raw_value)
                if inner:
                    elements = [e.strip() for e in inner.group(1).split(",") if e.strip()]
                    
                    # Check if there are multiple query variables
                    query_vars = [elem for elem in elements if "_query" in elem and elem in assignments]
                    
                    if len(query_vars) >= 1:
                        entities = []
                        # Create separate entries for each query variable
                        for i, query_var in enumerate(query_vars):
                            resolved_text = assignments[query_var]
                            query_resolved = []
                            # Search for any feature_ids or primitive_ids used
                            for fid, ftype in feature_ids:
                                if fid in resolved_text:
                                    query_resolved.append((fid, ftype))
                            for pid, ptype in primitive_ids:
                                if pid in resolved_text:
                                    query_resolved.append((pid, ptype))
                            
                            # Create a unique key for this query
                            entities.append(query_resolved)
                        result[key] = entities
                    else:
                        # Single query or no queries - use original logic
                        resolved = []
                        for elem in elements:
                            if elem in assignments:
                                # Extract everything between `=` and first `;`
                                resolved_text = assignments[elem]
                                # Search for any feature_ids or primitive_ids used
                                for fid, ftype in feature_ids:
                                    if fid in resolved_text:
                                        resolved.append((fid, ftype))
                                for pid, ptype in primitive_ids:
                                    if pid in resolved_text:
                                        resolved.append((pid, ptype))
                            else:
                                # If not found, assume it's a raw id like "my_id"
                                elem_stripped = elem.strip('"')
                                if elem_stripped in feature_ids or elem_stripped in primitive_ids:
                                    resolved.append(elem_stripped)

                        result[key] = resolved
                else:
                    result[key] = []
            elif "value" in raw_value:
                # Handle value extraction from "{ 'value' : try(25 * millimeter), 'expression' : "25 mm" }.value"
                value_match = re.search(r'\{\s*\'value\'\s*:\s*([^,]+),\s*\'expression\'\s*:\s*"([^"]+)"\s*\}\.value', raw_value)
                if value_match:
                    value = value_match.group(1).strip()
                    expression = value_match.group(2).strip()
                    split_expression = expression.split()
                    result[key] = {"default": value, "value": split_expression[0], "unit": split_expression[1] if len(split_expression) > 1 else ""}
                else:
                    print(f"Warning: Could not parse value for key '{key}' in raw_value: {raw_value}")
                    result[key] = raw_value
            else:
                result[key] = raw_value

        return result