"""
Extrude feature converter - a simple example to demonstrate the pattern
"""
from typing import Dict, Any, List
import sys
import os

# Add the parent directory to sys.path for nuCAD imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nuCAD.env.actions import Extrude
from ..core.base_converter import BaseFeatureConverter


class ExtrudeConverter(BaseFeatureConverter):
    """Converts extrude features to nuCAD actions"""
    
    def convert(self, feature_data: Dict[str, Any]) -> List:
        """Convert an extrude feature to nuCAD Extrude action"""
        actions = []
        
        parameters = self.get_parameters(feature_data)
        extrude_feature_id = feature_data.get("id")
        operation_type = parameters.get("operationType", "")

        # Record the profile entity types to help downstream face selection (e.g., donut vs disk)
        entities = parameters.get("entities", [])
        # Flatten entities if nested (entities can be [[pairs]] or [pairs])
        flat_entities = entities
        if isinstance(entities, list) and len(entities) > 0 and isinstance(entities[0], list):
            # Check if first element is itself a list of pairs - if so, flatten
            if len(entities[0]) > 0 and isinstance(entities[0][0], list):
                flat_entities = entities[0]
        
        try:
            self.geometry_tracker.register_last_extrude_profile(flat_entities)
            # Also record by extrude feature id for stable face lookup
            self.geometry_tracker.register_extrude_profile(extrude_feature_id, flat_entities)
        except Exception:
            # Non-fatal if structure is unexpected
            pass

        sketch_id = None
        if isinstance(flat_entities, list):
            for pair in flat_entities:
                if isinstance(pair, list) and len(pair) == 2 and pair[1] == "newSketch":
                    sketch_id = pair[0]
                    break
        if sketch_id is None:
            try:
                sketch_id = self.geometry_tracker.get_last_sketch_id()
            except Exception:
                sketch_id = None
        
        # Extract extrude parameters using unit converter
        depth = self.unit_converter.parse_parameter_value(
            parameters.get("depth", {"value": 1.0, "unit": "in"})
        )
        
        # Check for end bound type (BLIND, SYMMETRIC, etc.)
        end_bound = parameters.get("endBound", "")
        is_symmetric = "SYMMETRIC" in end_bound
        
        # Also check for separate "symmetric" parameter (OnShape can use this instead of endBound)
        symmetric_param = parameters.get("symmetric", "false")
        if isinstance(symmetric_param, str):
            symmetric_param = symmetric_param.lower() == "true"
        if symmetric_param:
            is_symmetric = True
        
        # Check for oppositeDirection flag (common in CAD applications)
        opposite_direction = parameters.get("oppositeDirection", "false")
        if isinstance(opposite_direction, str):
            opposite_direction = opposite_direction.lower() == "true"
        
        # Apply direction modifiers
        # 1. Handle SYMMETRIC extrusion (goes equally in both directions)
        direction = "one"  # Default single-direction extrusion
        if is_symmetric:
            # For SYMMETRIC, the depth value represents TOTAL distance
            # nuCAD's direction="symmetric" automatically extrudes ±height, so pass half the total
            direction = "symmetric"
            depth = depth / 2  # nuCAD will extrude ±(depth/2), giving total depth
            print(f"    SYMMETRIC extrusion: ±{depth}mm from sketch plane (total {depth*2}mm)")
        
        # 2. Flip if oppositeDirection is true
        if opposite_direction:
            depth = -depth
            print(f"    Extrude direction flipped due to oppositeDirection=true")
        
        # NOTE: The geometry_utils.py now flips horizontal cap normals to always point UP
        # So we do NOT need to flip the height for START caps anymore - both caps
        # have upward-pointing normals and should use positive height to extrude upward
        
        operation_type = parameters.get("operationType", "NEW")
        
        # Get the face to extrude (use geometry tracker for smart selection)
        face_to_extrude = self.geometry_tracker.get_face_for_extrude()
        
        # Create extrude action
        extrude_action = Extrude(height=depth, faces=[face_to_extrude], direction=direction)
        actions.append(extrude_action)
        
        # Register the operation with geometry tracker
        new_solid = self.geometry_tracker.next_solid_id()
        self.geometry_tracker.register_operation(
            "extrude", 
            inputs=[face_to_extrude], 
            outputs=[new_solid]
        )

        # Map sketch primitives to resulting side faces for downstream references
        try:
            self._register_side_faces_for_extrude(
                extrude_feature_id=extrude_feature_id,
                sketch_id=sketch_id,
                solid_id=new_solid,
                depth=depth,
                entities=entities,
                operation_type=operation_type,
                is_symmetric=is_symmetric
            )
        except Exception:
            pass
        
        return actions

    def _register_side_faces_for_extrude(self, extrude_feature_id: str | None, sketch_id: str | None, solid_id: str, depth: float, entities: list = None, operation_type: str = "", is_symmetric: bool = False):
        if not extrude_feature_id or not sketch_id:
            return

        profile_data = self.geometry_tracker.get_sketch_profile(sketch_id)
        if not profile_data:
            return

        # Extract which specific primitives are being extruded (if specified)
        extruded_primitive_ids = set()
        if entities:
            for entity_ref in entities:
                if isinstance(entity_ref, list):
                    for pair in entity_ref:
                        if isinstance(pair, list) and len(pair) >= 2:
                            entity_id, entity_type = pair[0], pair[1]
                            # Skip the sketch reference itself
                            if entity_type != "newSketch":
                                extruded_primitive_ids.add(entity_id)
        
        loops = profile_data.get("loops", [])
        
        # Build edge sequence only from the extruded loop(s)
        edge_sequence = []
        for loop in loops:
            if not loop.get("is_closed", False):
                continue
            
            loop_primitives = loop.get("primitives", [])
            
            # If specific entities were specified, check if this loop contains any of them
            if extruded_primitive_ids:
                # Check if ANY primitive in this loop is in the extruded set
                loop_has_extruded_primitive = any(
                    p.get("id") in extruded_primitive_ids 
                    for p in loop_primitives
                )
                # If this loop wasn't selected for extrusion, skip it
                if not loop_has_extruded_primitive:
                    continue
            
            # Skip circle-only loops from edge registration (they don't create swept edges)
            if len(loop_primitives) == 1 and loop_primitives[0].get("type") == "circle":
                continue
            
            # Register edges from this loop
            for primitive in loop_primitives:
                primitive_id = primitive.get("id")
                primitive_type = primitive.get("type")
                if not primitive_id or primitive_type not in {"line", "arc", "circle"}:
                    continue
                edge_sequence.append(primitive_id)

        if not edge_sequence:
            return

        if depth < 0:
            edge_sequence = list(reversed(edge_sequence))

        # For ADD operations on existing solids, the first edge in the profile is typically
        # constrained to the base solid and doesn't create a new swept face.
        # We need to skip it from the edge-to-face mapping.
        is_add_operation = "ADD" in operation_type
        if is_add_operation and len(edge_sequence) > 1:
            # Skip the first edge (it's on the base solid)
            print(f"    ADD operation detected - skipping first edge ({edge_sequence[0]}) which is constrained to base solid")
            edge_sequence = edge_sequence[1:]
        
        # Swept faces come FIRST in OpenCASCADE's creation order (verified empirically)
        # Caps appear at the end: indices len(swept_faces) and len(swept_faces)+1
        base_index = 0
        mappings = []
        print(f"    Registering edges for extrude {extrude_feature_id} to solid {solid_id} (operation: {operation_type}):")
        print(f"      Edge sequence: {edge_sequence}")
        for idx, primitive_id in enumerate(edge_sequence):
            face_ref = f"{solid_id}:{base_index + idx}"
            mappings.append((primitive_id, face_ref))
            print(f"      {primitive_id} -> {face_ref}")

        self.geometry_tracker.register_extrude_side_faces(extrude_feature_id, solid_id, mappings)
        
        # NEW: Register metadata for calculating cap face indices
        # This allows downstream features to calculate cap positions based on actual geometry
        num_swept_faces = len(edge_sequence)
        self.geometry_tracker.register_extrude_metadata(
            extrude_feature_id, 
            num_swept_faces,
            operation_type,
            is_symmetric
        )