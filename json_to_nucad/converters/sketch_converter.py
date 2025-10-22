"""
Sketch feature converter with loop detection and primitive conversion
"""
from typing import Dict, Any, List, Tuple
import sys
import os
import math
import re

# Add the parent directory to sys.path for nuCAD imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nuCAD.env.actions import (
    AddSketch, StartLoop, AddLine, AddArc, AddCircle, AddEllipse,
    AddBezier, AddSpline, SubtractWires, CloseProfile, MakeFace
)
from ..core.base_converter import BaseFeatureConverter


class SketchConverter(BaseFeatureConverter):
    """Converts newSketch features to nuCAD actions with intelligent loop detection"""
    
    def convert(self, feature_data: Dict[str, Any]) -> List:
        """Convert a sketch feature to nuCAD actions"""
        actions = []
        
        # Extract sketch plane and primitives
        sketch_plane = feature_data.get("sketch_plane", "Top")
        primitives = self.get_primitives(feature_data)
        sketch_id = feature_data.get("id")
        
        if not primitives:
            print("Warning: No primitives found in sketch")
            return actions
        
        # Get sketch plane info
        origin, normal, on_face = self._get_sketch_plane_info(sketch_plane)
        
        print(f"    Sketch plane: {sketch_plane} -> on_face: {on_face}")
        
        # Store face reference for coordinate transformation
        self._current_face_ref = on_face
        
        # Create sketch with proper face reference when available
        context_side = None
        if on_face:
            print(f"    Creating face-based sketch on: {on_face}")
            actions.append(AddSketch(on_face=on_face))
            # Persist sketch context (side + face) for downstream extrude direction
            try:
                # face_side is local var in _get_sketch_plane_info; we return side via on_face None.
                # To capture side, re-extract from sketch_plane (cheap).
                side = None
                if isinstance(sketch_plane, list):
                    for ref in sketch_plane:
                        if isinstance(ref, list) and len(ref) >= 2 and ref[0] == "CAP_FACE" and isinstance(ref[1], str):
                            side = ref[1]
                            break
                context_side = side
            except Exception:
                pass
        else:
            print(f"    Creating plane-based sketch at origin: {origin}, normal: {normal}")
            actions.append(AddSketch(origin=origin, normal=normal))

        try:
            self.geometry_tracker.set_last_sketch_context(side=context_side, on_face=on_face, sketch_id=sketch_id)
        except Exception:
            pass
        
        # Convert primitives to actions with loop detection
        sketch_actions = self._convert_sketch_primitives(primitives, sketch_id=sketch_id)
        actions.extend(sketch_actions)
        
        print(f"  Sketch converter generated {len(actions)} actions")
        return actions
    
    def _get_sketch_plane_info(self, plane_name) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], str]:
        """Get origin, normal vector, and face reference for sketch planes"""
        
        # Handle feature references for sketching on faces
        if isinstance(plane_name, list):
            # Look for extrude feature reference and face type specification
            extrude_ref_found = False
            face_type = None
            face_side = None  # "START" or "END"
            extrude_feature_id = None
            
            # Track ALL referenced primitives (edges) from the sketch_plane
            referenced_primitives = []
            for feature_ref in plane_name:
                if isinstance(feature_ref, list):
                    if len(feature_ref) >= 2:
                        feature_type = feature_ref[0]
                        if feature_type == "extrude":
                            extrude_ref_found = True
                            # second element is the extrude feature id
                            extrude_feature_id = feature_ref[1]
                        elif feature_type == "CAP_FACE":
                            # Optional side marker in index 1: "START" or "END"
                            if len(feature_ref) >= 2 and isinstance(feature_ref[1], str):
                                face_side = feature_ref[1]
                            face_type = "CAP_FACE"
                        elif feature_type == "skLineSegment" or feature_type == "skArc":
                            # Collect edge IDs that define the swept face
                            referenced_primitives.append(feature_ref[1])
                    elif len(feature_ref) == 1:
                        # Single-element arrays might specify face type (e.g., SWEPT_FACE)
                        face_type = feature_ref[0]
            
            if extrude_ref_found:
                # Get face reference based on face type specification
                if face_type == "CAP_FACE":
                    # Prefer per-extrude-ID cap face if available to stick to the referenced solid
                    face_ref = None
                    if extrude_feature_id:
                        face_ref = self.geometry_tracker.get_cap_face_for_extrude_id(extrude_feature_id, face_side)
                    if not face_ref:
                        face_ref = self.geometry_tracker.get_cap_face_of_latest_solid(face_side)
                    print(f"      CAP_FACE: {face_ref} (from extrude_id={extrude_feature_id}, side={face_side})")
                elif face_type == "SWEPT_FACE":
                    # Try each referenced edge until we find a mapped face
                    face_ref = None
                    if extrude_feature_id and referenced_primitives:
                        print(f"      SWEPT_FACE: Checking edges {referenced_primitives} for extrude {extrude_feature_id}")
                        for edge_id in referenced_primitives:
                            face_ref = self.geometry_tracker.get_face_for_edge(extrude_feature_id, edge_id)
                            if face_ref:
                                print(f"        ✓ Found mapping: edge {edge_id} -> {face_ref}")
                                break
                            else:
                                print(f"        ✗ No mapping for edge {edge_id}")
                    
                    # Fallback to generic side face lookup
                    if not face_ref and extrude_feature_id:
                        print(f"      No edge mapping found, trying get_side_face_for_extrude_id")
                        face_ref = self.geometry_tracker.get_side_face_for_extrude_id(extrude_feature_id)
                    if not face_ref:
                        print(f"      Still no face, using get_side_face_of_latest_solid")
                        face_ref = self.geometry_tracker.get_side_face_of_latest_solid()
                    
                    print(f"      SWEPT_FACE: {face_ref} (from extrude_id={extrude_feature_id}, edges={referenced_primitives})")
                else:
                    # Default to side face if no specific type
                    face_ref = self.geometry_tracker.get_side_face_of_latest_solid()
                    
                print(f"      Face type: {face_type}, side: {face_side}, selected face: {face_ref}")
                return ((0, 0, 0), (0, 0, 1), face_ref)
            
            # Fallback to default plane if no extrude reference found
            return ((0, 0, 0), (0, 0, 1), None)
        
        # Handle string plane names (predefined planes)
        elif isinstance(plane_name, str):
            plane_configs = {
                "Top": ((0, 0, 0), (0, 0, 1)),
                "Front": ((0, 0, 0), (0, 1, 0)),
                "Right": ((0, 0, 0), (1, 0, 0)),
                "XY": ((0, 0, 0), (0, 0, 1)),
                "XZ": ((0, 0, 0), (0, 1, 0)),
                "YZ": ((0, 0, 0), (1, 0, 0))
            }
            origin, normal = plane_configs.get(plane_name, ((0, 0, 0), (0, 0, 1)))
            return (origin, normal, None)
        
        # Default fallback
        return ((0, 0, 0), (0, 0, 1), None)
    
    def _transform_coordinates_for_face(self, coordinates: List[float]) -> List[float]:
        """Transform coordinates for face-based sketching
        
        Face-based sketching uses a coordinate system where (0,0) is at the face center.
        This method transforms global coordinates to face-centered coordinates.
        """
        # Apply unit conversion ALWAYS (meters to mm with 1000x scaling)
        x = round(coordinates[0] * 1000, 2)
        y = round(coordinates[1] * 1000, 2)
        
        return [x, y]
    
    def scale_coordinates(self, coord_list: List[float]) -> List[float]:
        """Scale coordinates from meters to millimeters."""
        return [c * 1000.0 for c in coord_list]
    
    def parse_unit_value(self, value_str: str) -> float:
        """Parse unit values like '1.0 * inch' and convert to millimeters."""
        import re
        if isinstance(value_str, (int, float)):
            return float(value_str) * 25.4  # Assume inches
        
        if isinstance(value_str, str):
            # Handle various unit formats
            value_str = value_str.strip()
            
            # Try to extract number and unit
            match = re.search(r'([+-]?\d*\.?\d+)\s*\*?\s*(\w+)', value_str)
            if match:
                number = float(match.group(1))
                unit = match.group(2).lower()
                # Convert to millimeters
                unit_conversions = {
                    'inch': 25.4, 'in': 25.4, 'inches': 25.4,
                    'mm': 1.0, 'millimeter': 1.0, 'millimeters': 1.0,
                    'cm': 10.0, 'centimeter': 10.0, 'centimeters': 10.0,
                    'm': 1000.0, 'meter': 1.0, 'meters': 1000.0
                }
                return number * unit_conversions.get(unit, 25.4)
        
        return 25.4  # Default fallback (1 inch)
    
    def _convert_sketch_primitives(self, primitives: Dict[str, Any], sketch_id: str | None = None) -> List:
        """Convert sketch primitives to nuCAD actions with proper loop detection"""
        sketch_actions = []
        
        # Detect and group primitives into loops
        loops = self._detect_loops_and_features(primitives)
        
        print(f"  Detected {len(loops)} loops/features")
        
        # Register loop metadata for downstream features (edge-to-face mapping)
        if isinstance(sketch_id, str):
            loops_metadata = {"loops": []}
            for loop in loops:
                loop_meta = {
                    "type": loop.get("type"),
                    "is_closed": loop.get("is_closed"),
                    "primitives": []
                }
                for primitive in loop.get("primitives", []):
                    prim_meta = {
                        "id": primitive.get("id"),
                        "type": primitive.get("type"),
                    }
                    ptype = primitive.get("type")
                    if ptype == "line":
                        prim_meta["start"] = primitive.get("start")
                        prim_meta["end"] = primitive.get("end")
                    elif ptype == "circle":
                        prim_meta["center"] = primitive.get("center")
                        prim_meta["radius"] = primitive.get("radius")
                    elif ptype == "arc":
                        prim_meta["center"] = primitive.get("center")
                        prim_meta["radius"] = primitive.get("radius")
                        prim_meta["start_angle"] = primitive.get("start_angle")
                        prim_meta["end_angle"] = primitive.get("end_angle")
                    elif ptype == "spline":
                        # Handle both "points" and "control_points" keys
                        points = primitive.get("points") or primitive.get("control_points")
                        prim_meta["control_points"] = points
                        prim_meta["points"] = points
                        prim_meta["start"] = primitive.get("start")
                        prim_meta["end"] = primitive.get("end")
                    elif ptype == "bezier":
                        prim_meta["control_points"] = primitive.get("control_points")
                        prim_meta["start"] = primitive.get("start")
                        prim_meta["end"] = primitive.get("end")
                    loop_meta["primitives"].append(prim_meta)
                loops_metadata["loops"].append(loop_meta)
            try:
                self.geometry_tracker.register_sketch_profile(sketch_id, loops_metadata)
            except Exception:
                pass

        # Separate outer boundaries from holes
        outer_loops, hole_loops = self._separate_outer_and_hole_loops(loops)
        
        # Add all loops to the sketch first
        all_loops = outer_loops + hole_loops
        
        for loop in all_loops:
            # Skip single-segment open loops (construction lines, etc.)
            if len(loop["primitives"]) == 1 and not loop["is_closed"]:
                print(f"    Skipping single open segment (likely construction line)")
                continue
                
            sketch_actions.append(StartLoop())
            
            for primitive in loop["primitives"]:
                action = self._convert_primitive_to_action(primitive)
                if action:
                    sketch_actions.append(action)
            
            sketch_actions.append(CloseProfile())
            
            # Create face for this loop
            sketch_actions.append(MakeFace())
            face_id = self.geometry_tracker.next_face_id()
        
        return sketch_actions
    
    def _detect_loops_and_features(self, primitives: Dict[str, Any]) -> List[Dict]:
        """Detect and group primitives into loops and separate features with improved spline handling"""
        # Separate different types of primitives
        lines = []
        arcs = []
        circles = []
        ellipses = []
        splines = []
        beziers = []
        
        for primitive_id, primitive_data in primitives.items():
            ptype = primitive_data.get("type", "")
            geometry = primitive_data.get("geometry", {})
            
            if ptype == "skLineSegment" and "start" in geometry and "end" in geometry:
                # Transform coordinates for face-based or plane-based sketching
                start = self._transform_coordinates_for_face(geometry["start"])
                end = self._transform_coordinates_for_face(geometry["end"])
                lines.append({
                    "type": "line",
                    "start": start,
                    "end": end,
                    "id": primitive_id
                })
            
            elif ptype == "skCircle" and "center" in geometry and "radius" in geometry:
                # Transform coordinates for face-based or plane-based sketching
                center = self._transform_coordinates_for_face(geometry["center"])
                radius = round(geometry["radius"] * 1000, 2)  # meters to mm with 1000x scaling
                circles.append({
                    "type": "circle",
                    "center": center,
                    "radius": radius,
                    "id": primitive_id
                })
            
            elif ptype == "skArc" and "center" in geometry:
                # Transform coordinates
                center = self._transform_coordinates_for_face(geometry["center"])
                radius = round(geometry.get("radius", 1.0) * 1000, 2)
                start_angle = geometry.get("phi_start", 0)
                end_angle = geometry.get("phi_end", math.pi/2)
                
                # Calculate start, mid, and end points for arc
                p1 = [
                    center[0] + radius * math.cos(start_angle),
                    center[1] + radius * math.sin(start_angle)
                ]
                mid_angle = (start_angle + end_angle) / 2
                p2 = [
                    center[0] + radius * math.cos(mid_angle),
                    center[1] + radius * math.sin(mid_angle)
                ]
                p3 = [
                    center[0] + radius * math.cos(end_angle),
                    center[1] + radius * math.sin(end_angle)
                ]
                
                arcs.append({
                    "type": "arc",
                    "start": p1,
                    "mid": p2,
                    "end": p3,
                    "center": center,
                    "radius": radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                    "id": primitive_id
                })
            
            elif ptype == "skEllipse" and "center" in geometry:
                center = self._transform_coordinates_for_face(geometry["center"])
                major_radius = round(geometry.get("major_radius", 1.0) * 1000, 2)
                minor_radius = round(geometry.get("minor_radius", 0.5) * 1000, 2)
                ellipses.append({
                    "type": "ellipse",
                    "center": center,
                    "major_radius": major_radius,
                    "minor_radius": minor_radius,
                    "id": primitive_id
                })
            
            elif ptype in {
                "skInterpolatedSplineSegment",
                "skInterpolatedSpline",
                "skSplineSegment",
                "skSpline",
            }:
                raw_points = geometry.get("points") or primitive_data.get("points")
                if isinstance(raw_points, list) and len(raw_points) >= 2:
                    control_points = []
                    for point in raw_points:
                        if not isinstance(point, (list, tuple)) or len(point) < 2:
                            continue
                        control_points.append(self._transform_coordinates_for_face(point))
                    
                    if len(control_points) >= 2:
                        spline_entry = {
                            "type": "spline",
                            "points": control_points,
                            "start": control_points[0],
                            "end": control_points[-1],
                            "id": primitive_id
                        }
                        splines.append(spline_entry)
            
            elif ptype in {"skBezier", "skBezierSegment"}:
                raw_points = geometry.get("control_points") or geometry.get("points") or primitive_data.get("control_points")
                if isinstance(raw_points, list) and len(raw_points) >= 2:
                    control_points = []
                    for point in raw_points:
                        if not isinstance(point, (list, tuple)) or len(point) < 2:
                            continue
                        control_points.append(self._transform_coordinates_for_face(point))
                    
                    if len(control_points) >= 2:
                        bezier_entry = {
                            "type": "bezier",
                            "control_points": control_points,
                            "start": control_points[0],
                            "end": control_points[-1],
                            "id": primitive_id
                        }
                        beziers.append(bezier_entry)
        
        # Now find connected loops from lines, arcs, splines, and beziers
        all_segments = lines + arcs + splines + beziers
        loops = self._find_connected_loops(all_segments)
        
        # Calculate areas and collect all closed shapes for sorting
        def calculate_circle_area(circle):
            return math.pi * circle["radius"] ** 2
        
        def calculate_ellipse_area(ellipse):
            return math.pi * ellipse["major_radius"] * ellipse["minor_radius"]
        
        def calculate_spline_area(spline):
            """Calculate approximate area for a closed spline using shoelace formula"""
            points = spline.get("points", [])
            if len(points) < 3:
                return 0.0
            
            area = 0.0
            for i in range(len(points)):
                j = (i + 1) % len(points)
                area += points[i][0] * points[j][1]
                area -= points[j][0] * points[i][1]
            return abs(area) / 2.0
        
        # Collect all closed shapes with their areas
        closed_shapes = []
        
        # Add circles
        for circle in circles:
            closed_shapes.append(("circle", circle, calculate_circle_area(circle)))
        
        # Add ellipses
        for ellipse in ellipses:
            closed_shapes.append(("ellipse", ellipse, calculate_ellipse_area(ellipse)))
        
        # Add closed splines
        for spline in splines:
            if self._points_are_close(spline["start"], spline["end"], tolerance=1e-3 * 1000):
                closed_shapes.append(("spline", spline, calculate_spline_area(spline)))
        
        # Convert closed shapes to loop format and sort by area
        closed_shapes.sort(key=lambda x: x[2], reverse=True)
        result_loops = []
        
        for shape_type, shape, area in closed_shapes:
            if shape_type == "circle":
                result_loops.append({
                    "type": "circle_loop",
                    "primitives": [shape],
                    "is_closed": True
                })
            elif shape_type == "ellipse":
                result_loops.append({
                    "type": "ellipse_loop",
                    "primitives": [shape],
                    "is_closed": True
                })
            elif shape_type == "spline":
                result_loops.append({
                    "type": "spline_loop",
                    "primitives": [shape],
                    "is_closed": True
                })
        
        # Add the loops from connected segments
        result_loops.extend(loops)
        
        return result_loops
    
    def _find_connected_loops(self, segments: List[Dict]) -> List[List[Dict]]:
        """Find connected loops from segments with flexible start/end matching, transposition, and ID-based grouping."""
        all_segments = segments
        loops = []
        used_segments = set()
        
        # Use 1e-6 tolerance as requested, converted to millimeters
        tolerance = 1e-6 * 1000.0  # Convert to millimeters
        
        def extract_base_id(segment_id: str) -> str:
            """Extract base ID from segment ID (e.g., '4NgUrsMrXOQs.0' -> '4NgUrsMrXOQs')."""
            if '.' in segment_id:
                parts = segment_id.split('.')
                if len(parts) >= 2:
                    return parts[0]
            return segment_id
        
        def group_segments_by_base_id(segments: List[Dict]) -> Dict[str, List[Dict]]:
            """Group segments by their base ID."""
            groups = {}
            for segment in segments:
                base_id = extract_base_id(segment.get("id", ""))
                if base_id not in groups:
                    groups[base_id] = []
                groups[base_id].append(segment)
            return groups
        
        def points_equal(p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
            """Check if two points are equal within precise tolerance."""
            distance = math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
            return distance < tolerance
        
        def transpose_segment(segment: Dict) -> Dict:
            """Create a reversed/transposed version of a segment."""
            transposed = {
                "start": segment["end"],
                "end": segment["start"],
                "id": segment["id"],
                "type": segment.get("type", "line")
            }
            
            # Handle type-specific data when transposing
            if segment["type"] == "arc" and "mid" in segment:
                transposed["mid"] = segment["mid"]  # Mid point stays the same
            elif segment["type"] == "spline" and "points" in segment:
                # Reverse the control points for spline
                transposed["points"] = list(reversed(segment["points"]))
            elif segment["type"] == "bezier" and "control_points" in segment:
                # Reverse the control points for bezier
                transposed["control_points"] = list(reversed(segment["control_points"]))
            
            return transposed
        
        def find_next_segment(current_end: Tuple[float, float], remaining_segments: List[Dict]) -> Dict:
            """Find the next segment that connects to current_end, handling all connection types."""
            for segment in remaining_segments:
                seg_start = tuple(segment["start"]) if isinstance(segment["start"], list) else segment["start"]
                seg_end = tuple(segment["end"]) if isinstance(segment["end"], list) else segment["end"]
                
                if points_equal(current_end, seg_start):
                    return segment
                elif points_equal(current_end, seg_end):
                    # Need to transpose this segment
                    return transpose_segment(segment)
            
            return None
        
        def find_connecting_segment(point1: Tuple[float, float], remaining_segments: List[Dict]) -> Tuple[Dict, bool]:
            """Find a segment that connects to point1, return (segment, needs_transpose)."""
            for segment in remaining_segments:
                seg_start = tuple(segment["start"]) if isinstance(segment["start"], list) else segment["start"]
                seg_end = tuple(segment["end"]) if isinstance(segment["end"], list) else segment["end"]
                
                if points_equal(point1, seg_start):
                    return (segment, False)
                elif points_equal(point1, seg_end):
                    return (segment, True)
            
            return (None, False)
        
        def is_closed_loop(loop_segments: List[Dict]) -> bool:
            """Check if a sequence of segments forms a closed loop."""
            if len(loop_segments) < 2:
                return False
            
            first_start = tuple(loop_segments[0]["start"]) if isinstance(loop_segments[0]["start"], list) else loop_segments[0]["start"]
            last_end = tuple(loop_segments[-1]["end"]) if isinstance(loop_segments[-1]["end"], list) else loop_segments[-1]["end"]
            return points_equal(first_start, last_end)
        
        # Build loops using both ID-based grouping AND geometric connection
        # Start by creating initial segments list from all input segments
        remaining_segments = [seg for seg in all_segments]
        
        # Process all segments, trying to form the longest possible connected chains
        while remaining_segments:
            # Pick a starting segment
            current_loop = [remaining_segments.pop(0)]
            
            # Try to extend the loop by connecting more segments
            max_iterations = len(remaining_segments) + 10
            iterations = 0
            while iterations < max_iterations and remaining_segments:
                iterations += 1
                current_end = tuple(current_loop[-1]["end"]) if isinstance(current_loop[-1]["end"], list) else current_loop[-1]["end"]
                
                # Find next connecting segment (prefer same base ID, but allow any geometric match)
                found_connection = False
                current_base_id = extract_base_id(current_loop[-1].get("id", ""))
                
                # First try: find segment with same base ID
                for i, candidate in enumerate(remaining_segments):
                    candidate_base_id = extract_base_id(candidate.get("id", ""))
                    if candidate_base_id == current_base_id and current_base_id != "":
                        seg_start = tuple(candidate["start"]) if isinstance(candidate["start"], list) else candidate["start"]
                        seg_end = tuple(candidate["end"]) if isinstance(candidate["end"], list) else candidate["end"]
                        
                        if points_equal(current_end, seg_start):
                            current_loop.append(remaining_segments.pop(i))
                            found_connection = True
                            break
                        elif points_equal(current_end, seg_end):
                            transposed = transpose_segment(remaining_segments.pop(i))
                            current_loop.append(transposed)
                            found_connection = True
                            break
                
                # Second try: find ANY segment that connects geometrically
                if not found_connection:
                    for i, candidate in enumerate(remaining_segments):
                        seg_start = tuple(candidate["start"]) if isinstance(candidate["start"], list) else candidate["start"]
                        seg_end = tuple(candidate["end"]) if isinstance(candidate["end"], list) else candidate["end"]
                        
                        if points_equal(current_end, seg_start):
                            current_loop.append(remaining_segments.pop(i))
                            found_connection = True
                            break
                        elif points_equal(current_end, seg_end):
                            transposed = transpose_segment(remaining_segments.pop(i))
                            current_loop.append(transposed)
                            found_connection = True
                            break
                
                if not found_connection:
                    break
                
                # Check if loop is closed
                first_start = tuple(current_loop[0]["start"]) if isinstance(current_loop[0]["start"], list) else current_loop[0]["start"]
                last_end = tuple(current_loop[-1]["end"]) if isinstance(current_loop[-1]["end"], list) else current_loop[-1]["end"]
                if points_equal(first_start, last_end):
                    break
            
            # Add the loop if it has segments
            if len(current_loop) >= 1:
                loops.append({
                    "type": "line_loop",
                    "primitives": current_loop,
                    "is_closed": is_closed_loop(current_loop)
                })
        
        return loops
    
    def _order_line_segments(self, line_segments: List[Dict]) -> List[Dict]:
        """Order line segments to form connected chains"""
        if not line_segments:
            return []
        
        ordered_segments = []
        remaining_segments = line_segments.copy()
        
        # Start with the first segment
        current_segment = remaining_segments.pop(0)
        ordered_segments.append(current_segment)
        current_end = current_segment["end"]
        
        # Try to connect segments end-to-start
        while remaining_segments:
            found_connection = False
            
            for i, segment in enumerate(remaining_segments):
                segment_start = segment["start"]
                segment_end = segment["end"]
                
                # Check if this segment connects to current end
                if self._points_are_close(current_end, segment_start):
                    # Direct connection
                    ordered_segments.append(remaining_segments.pop(i))
                    current_end = segment_end
                    found_connection = True
                    break
                elif self._points_are_close(current_end, segment_end):
                    # Reverse connection
                    reversed_segment = {
                        "type": segment["type"],
                        "start": segment_end,
                        "end": segment_start,
                        "id": segment["id"]
                    }
                    if segment["type"] == "spline":
                        reversed_segment["control_points"] = list(reversed(segment.get("control_points", [])))
                    ordered_segments.append(reversed_segment)
                    remaining_segments.pop(i)
                    current_end = segment_start
                    found_connection = True
                    break
            
            if not found_connection:
                break
        
        return ordered_segments
    
    def _points_are_close(self, p1: List[float], p2: List[float], tolerance: float = 1e-6) -> bool:
        """Check if two points are close enough to be considered the same"""
        # Convert tolerance to millimeters if it's in the default range
        if tolerance < 1.0:
            tolerance = tolerance * 1000.0
        distance = math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
        return distance < tolerance
    
    def _is_loop_closed(self, segments: List[Dict]) -> bool:
        """Check if a sequence of line segments forms a closed loop"""
        if len(segments) < 3:
            return False
        
        first_start = segments[0]["start"]
        last_end = segments[-1]["end"]
        
        return self._points_are_close(first_start, last_end)
    
    def _separate_outer_and_hole_loops(self, loops: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Separate outer boundaries from holes using area heuristics"""
        outer_loops = []
        hole_loops = []
        
        for i, loop in enumerate(loops):
            print(f"    Loop {i+1}: {loop['type']}, closed: {loop['is_closed']}, {len(loop['primitives'])} primitives")
            
            # Heuristic: larger loops are likely outer boundaries, smaller ones are holes
            if loop['type'] == 'line_loop' and loop['is_closed']:
                # Calculate rough size of the loop
                all_points = []
                for primitive in loop['primitives']:
                    all_points.extend([primitive['start'], primitive['end']])
                
                if all_points:
                    xs = [p[0] for p in all_points]
                    ys = [p[1] for p in all_points]
                    area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                    
                    # If area is large, it's likely an outer boundary
                    if area > 100:  # Lower threshold for scaled coordinates (1000x)
                        outer_loops.append(loop)
                    else:
                        hole_loops.append(loop)
                else:
                    outer_loops.append(loop)
            elif loop['type'] == 'circle_loop':
                # Small circles are likely holes, large ones might be outer boundaries
                radius = loop['primitives'][0]['radius']
                if radius < 50:  # Arbitrary threshold (scaled by 1000x)
                    hole_loops.append(loop)
                else:
                    outer_loops.append(loop)
            else:
                # Default to outer loop
                outer_loops.append(loop)
        
        return outer_loops, hole_loops
    
    def _convert_primitive_to_action(self, primitive: Dict[str, Any]):
        """Convert a single primitive to a nuCAD action"""
        ptype = primitive.get("type")
        
        if ptype == "line":
            return AddLine(start=tuple(primitive["start"]), end=tuple(primitive["end"]))
        
        elif ptype == "circle":
            return AddCircle(center=tuple(primitive["center"]), radius=primitive["radius"])
        
        elif ptype == "arc":
            # Use pre-calculated 3-point format for AddArc
            if "mid" in primitive:
                p1 = tuple(primitive["start"])
                p2 = tuple(primitive["mid"])
                p3 = tuple(primitive["end"])
                return AddArc(p1=p1, p2=p2, p3=p3)
            else:
                # Fallback: Convert from center/radius/angles to 3-point format
                center = primitive["center"]
                radius = primitive["radius"]
                start_angle = primitive.get("start_angle", 0)
                end_angle = primitive.get("end_angle", math.pi/2)
                
                # Calculate 3 points on the arc: start, middle, end
                p1 = (center[0] + radius * math.cos(start_angle), 
                      center[1] + radius * math.sin(start_angle))
                
                # Middle point at average angle
                mid_angle = (start_angle + end_angle) / 2
                p2 = (center[0] + radius * math.cos(mid_angle), 
                      center[1] + radius * math.sin(mid_angle))
                
                p3 = (center[0] + radius * math.cos(end_angle), 
                      center[1] + radius * math.sin(end_angle))
                
                return AddArc(p1=p1, p2=p2, p3=p3)
        
        elif ptype == "ellipse":
            return AddEllipse(
                center=tuple(primitive["center"]),
                major_axis_dir=(1.0, 0.0),  # Default to horizontal major axis
                major_radius=primitive["major_radius"],
                minor_radius=primitive["minor_radius"]
            )
        
        elif ptype == "spline":
            # Handle both "points" and "control_points" keys
            points = primitive.get("points") or primitive.get("control_points", [])
            if points:
                # Convert to list of tuples for AddSpline
                points_tuples = [tuple(p) if isinstance(p, list) else p for p in points]
                return AddSpline(points=points_tuples)
            else:
                print(f"Warning: Spline primitive missing points data")
                return None
        
        elif ptype == "bezier":
            control_points = primitive.get("control_points", [])
            if control_points:
                # Convert to list of tuples for AddBezier
                points_tuples = [tuple(p) if isinstance(p, list) else p for p in control_points]
                return AddBezier(control_points=points_tuples)
            else:
                print(f"Warning: Bezier primitive missing control_points data")
                return None
        
        else:
            print(f"Warning: Unknown primitive type: {ptype}")
            return None