"""
Geometry tracking for face, solid, and edge references in nuCAD
"""


class GeometryTracker:
    """Tracks face/solid/edge counters and provides reference management"""
    
    def __init__(self):
        self.face_counter = 0
        self.solid_counter = 0
        self.edge_counter = 0
        self.wire_counter = 0
        
        # Track geometry relationships for more sophisticated referencing
        self.face_to_solid_map = {}  # Maps face IDs to their parent solid
        self.solid_operations = []   # Track operations for debugging
        
        # Feature timeline for predicting solid creation order
        self.feature_timeline = []   # List of (feature_name, feature_type, solid_creates)
        self.current_feature_index = 0

        # Track last extrude profile summary to help map cap-face indices
        # Example stored structure: { 'entity_types': ['skCircle','skCircle'], 'count_by_type': {'skCircle':2} }
        self._last_extrude_profile = None

        # Track extrude feature IDs in creation order and their profiles
        self._extrude_ids_in_order = []            # [extrude_feature_id0, extrude_feature_id1, ...]
        self._extrude_id_to_index = {}             # { extrude_feature_id: solid_index }
        self._extrude_profiles = {}                # { extrude_feature_id: profile_summary }
        self._sketch_profiles = {}                 # { sketch_id: profile_data }
        self._extrude_edge_to_face = {}            # { (extrude_id, primitive_id): face_ref }
        self._last_sketch_id = None
    
    def next_face_id(self) -> str:
        """Get the next face ID (f0, f1, f2, ...)"""
        face_id = f"f{self.face_counter}"
        self.face_counter += 1
        return face_id
    
    def next_solid_id(self) -> str:
        """Get the next solid ID (s0, s1, s2, ...)"""
        solid_id = f"s{self.solid_counter}"
        self.solid_counter += 1
        return solid_id
    
    def next_edge_id(self) -> str:
        """Get the next edge ID (e0, e1, e2, ...)"""
        edge_id = f"e{self.edge_counter}"
        self.edge_counter += 1
        return edge_id
    
    def current_face_id(self) -> str:
        """Get the current (most recent) face ID"""
        return f"f{self.face_counter - 1}" if self.face_counter > 0 else "f0"
    
    def current_solid_id(self) -> str:
        """Get the current (most recent) solid ID"""
        return f"s{self.solid_counter - 1}" if self.solid_counter > 0 else "s0"
    
    def current_edge_id(self) -> str:
        """Get the current (most recent) edge ID"""
        return f"e{self.edge_counter - 1}" if self.edge_counter > 0 else "e0"
    
    def register_operation(self, operation_type: str, inputs: list, outputs: list):
        """Register an operation for tracking and debugging"""
        self.solid_operations.append({
            "type": operation_type,
            "inputs": inputs,
            "outputs": outputs,
            "step": len(self.solid_operations)
        })
    
    def get_face_for_extrude(self) -> str:
        """Smart selection of face for extrude operations"""
        # Use the most recently created face
        return self.current_face_id()
    
    def get_top_face_of_latest_solid(self) -> str:
        """Get a suitable face of the most recently created solid for sketching"""
        # Look backwards in timeline to find extrude operations that have completed
        # before the current feature
        solids_that_will_exist = 0
        for i in range(self.current_feature_index):
            if i < len(self.feature_timeline):
                _, feature_type, creates_solid = self.feature_timeline[i]
                if creates_solid and feature_type == "extrude":
                    solids_that_will_exist += 1
        
        # Only reference a solid if it will definitely exist by execution time
        if solids_that_will_exist > 0:
            # Reference the most recently created solid
            latest_solid_id = solids_that_will_exist - 1
            # Use face index 2 which works better for extruded donut geometry
            return f"s{latest_solid_id}:2"  # Side face of the solid (more reliable)
        
        return None
    
    def get_cap_face_of_latest_solid(self, side: str | None = None) -> str:
        """Get cap face (top/bottom) of the most recently created solid for sketching.

        side: Optional "START" or "END" to disambiguate which cap. If omitted, choose heuristic default.
        """
        # Look backwards in timeline to find extrude operations that have completed
        # before the current feature
        solids_that_will_exist = 0
        for i in range(self.current_feature_index):
            if i < len(self.feature_timeline):
                _, feature_type, creates_solid = self.feature_timeline[i]
                if creates_solid and feature_type == "extrude":
                    solids_that_will_exist += 1
        
        # Only reference a solid if it will definitely exist by execution time
        if solids_that_will_exist > 0:
            # Reference the most recently created solid
            latest_solid_id = solids_that_will_exist - 1
            
            # Heuristic mapping for cap face index based on profile complexity
            # If the profile looks like an annulus (e.g., two circles -> donut), the top cap
            # face often indexes differently in nuCAD. Empirically, s{n}:3 yields the correct cap.
            try:
                if self._last_extrude_profile:
                    count_by_type = self._last_extrude_profile.get('count_by_type', {})
                    num_circles = count_by_type.get('skCircle', 0)
                    # Annulus (donut): map START/END to distinct caps for stability
                    if num_circles >= 2:
                        if side == "START":
                            # For donut, START cap maps to index 2 per observed topology
                            return f"s{latest_solid_id}:2"
                        elif side == "END":
                            return f"s{latest_solid_id}:3"
                        # If side unknown, prefer the empirically stable cap index for donuts
                        return f"s{latest_solid_id}:3"
            except Exception:
                # Fall back to default if anything goes wrong
                pass

            # Non-donut (single-profile) default: return one stable cap index.
            # If we later learn distinct indices for START vs END on simple profiles,
            # we can disambiguate here. For now, both map to :1 to avoid :0.
            return f"s{latest_solid_id}:1"
        
        return None

    def get_cap_face_for_extrude_id(self, extrude_feature_id: str, side: str | None = None) -> str | None:
        """Return cap-face reference for the solid produced by a specific extrude feature.

        Honors donut-like (annulus) profiles by mapping START/END to distinct caps.
        side: Optional "START" or "END"; if omitted, a stable default is chosen.
        """
        if not isinstance(extrude_feature_id, str):
            return None

        if extrude_feature_id not in self._extrude_id_to_index:
            return None

        solid_index = self._extrude_id_to_index[extrude_feature_id]
        profile = self._extrude_profiles.get(extrude_feature_id)

        try:
            if profile:
                count_by_type = profile.get('count_by_type', {})
                num_circles = count_by_type.get('skCircle', 0)
                if num_circles >= 2:
                    # Annulus: distinct caps for START/END
                    if side == "START":
                        return f"s{solid_index}:2"
                    elif side == "END":
                        return f"s{solid_index}:3"
                    # Default donut cap when side unspecified
                    return f"s{solid_index}:3"
        except Exception:
            pass

        # Non-donut default: stable cap index (:1). TODO: Distinguish START/END when indices are known
        return f"s{solid_index}:1"

    # --- Sketch context helpers for extrude direction decisions ---
    def set_last_sketch_context(self, side: str | None = None, on_face: str | None = None, sketch_id: str | None = None):
        self._last_sketch_side = side
        self._last_sketch_on_face = on_face
        if sketch_id is not None:
            self._last_sketch_id = sketch_id

    def get_last_sketch_side(self) -> str | None:
        return getattr(self, '_last_sketch_side', None)

    def get_last_sketch_on_face(self) -> str | None:
        return getattr(self, '_last_sketch_on_face', None)

    def get_last_sketch_id(self) -> str | None:
        return getattr(self, '_last_sketch_id', None)
    
    def get_side_face_of_latest_solid(self) -> str:
        """Get a reliable side face of the most recently created solid for sketching"""
        # Look backwards in timeline to find extrude operations that have completed
        # before the current feature
        solids_that_will_exist = 0
        for i in range(self.current_feature_index):
            if i < len(self.feature_timeline):
                _, feature_type, creates_solid = self.feature_timeline[i]
                if creates_solid and feature_type == "extrude":
                    solids_that_will_exist += 1
        
        # Only reference a solid if it will definitely exist by execution time
        if solids_that_will_exist > 0:
            # Reference the most recently created solid
            latest_solid_id = solids_that_will_exist - 1
            # Use face index 2 for side faces which work reliably
            return f"s{latest_solid_id}:2"  # Side face (technically reliable)
        
        return None

    def get_side_face_for_extrude_id(self, extrude_feature_id: str) -> str | None:
        """Return a side-face reference for the solid produced by a specific extrude feature.

        Uses a stable side-face index (:2) which has been reliable across profiles.
        """
        if not isinstance(extrude_feature_id, str):
            return None
        if extrude_feature_id not in self._extrude_id_to_index:
            return None
        solid_index = self._extrude_id_to_index[extrude_feature_id]
        return f"s{solid_index}:2"
    
    def build_feature_timeline(self, json_data):
        """Build timeline of features and their solid creation patterns"""
        self.feature_timeline = []
        self._extrude_ids_in_order = []
        self._extrude_id_to_index = {}
        for feature_name, feature_data in json_data.items():
            if feature_name.startswith("feature "):
                feature_type = feature_data.get("type", "unknown")
                creates_solid = feature_type == "extrude"  # Add other solid-creating types here
                self.feature_timeline.append((feature_name, feature_type, creates_solid))
                if creates_solid and feature_type == "extrude":
                    extrude_id = feature_data.get("id")
                    if isinstance(extrude_id, str):
                        self._extrude_id_to_index[extrude_id] = len(self._extrude_ids_in_order)
                        self._extrude_ids_in_order.append(extrude_id)
        self._last_sketch_id = None

    def register_sketch_profile(self, sketch_id: str, profile_data: dict):
        if isinstance(sketch_id, str) and isinstance(profile_data, dict):
            self._sketch_profiles[sketch_id] = profile_data

    def get_sketch_profile(self, sketch_id: str):
        if isinstance(sketch_id, str):
            return self._sketch_profiles.get(sketch_id)
        return None

    def register_extrude_side_faces(self, extrude_feature_id: str, solid_id: str, edge_to_face: list):
        if not isinstance(extrude_feature_id, str) or not isinstance(solid_id, str):
            return
        for entry in edge_to_face:
            if not isinstance(entry, tuple) or len(entry) != 2:
                continue
            primitive_id, face_ref = entry
            if isinstance(primitive_id, str) and isinstance(face_ref, str):
                self._extrude_edge_to_face[(extrude_feature_id, primitive_id)] = face_ref

    def get_face_for_edge(self, extrude_feature_id: str, primitive_id: str) -> str | None:
        if not isinstance(extrude_feature_id, str) or not isinstance(primitive_id, str):
            return None
        return self._extrude_edge_to_face.get((extrude_feature_id, primitive_id))
    
    def set_current_feature(self, feature_name: str):
        """Set the current feature being processed for timeline context"""
        for i, (name, _, _) in enumerate(self.feature_timeline):
            if name == feature_name:
                self.current_feature_index = i
                break
    
    def reset(self):
        """Reset all counters for a new conversion"""
        self.face_counter = 0
        self.solid_counter = 0
        self.edge_counter = 0
        self.wire_counter = 0
        self.face_to_solid_map.clear()
        self.solid_operations.clear()
        self.feature_timeline.clear()
        self.current_feature_index = 0
        self._last_extrude_profile = None
        self._extrude_ids_in_order = []
        self._extrude_id_to_index = {}
        self._extrude_profiles = {}
        self._sketch_profiles = {}
        self._extrude_edge_to_face = {}
        self._last_sketch_id = None

    def register_last_extrude_profile(self, entities: list):
        """Record a lightweight summary of the last extrude's profile entities.

        entities: FeatureScript-like list of entity refs, typically
                  [[sketchId, 'newSketch'], [entityId1, 'skCircle'], ...]
        We only care about entity types to detect donut-like profiles.
        """
        if not isinstance(entities, list):
            self._last_extrude_profile = None
            return

        entity_types = []
        for pair in entities:
            # Expect pairs like [id, type]
            if isinstance(pair, list) and len(pair) == 2:
                etype = pair[1]
                # Skip the sketch pair where type == 'newSketch'
                if isinstance(etype, str) and etype != 'newSketch':
                    entity_types.append(etype)

        count_by_type = {}
        for t in entity_types:
            count_by_type[t] = count_by_type.get(t, 0) + 1

        self._last_extrude_profile = {
            'entity_types': entity_types,
            'count_by_type': count_by_type,
        }

    def register_extrude_profile(self, extrude_feature_id: str, entities: list):
        """Record profile summary keyed by extrude feature ID (preferred for later reference)."""
        if not isinstance(extrude_feature_id, str):
            return
        if not isinstance(entities, list):
            self._extrude_profiles[extrude_feature_id] = None
            return

        entity_types = []
        for pair in entities:
            if isinstance(pair, list) and len(pair) == 2:
                etype = pair[1]
                if isinstance(etype, str) and etype != 'newSketch':
                    entity_types.append(etype)

        count_by_type = {}
        for t in entity_types:
            count_by_type[t] = count_by_type.get(t, 0) + 1

        self._extrude_profiles[extrude_feature_id] = {
            'entity_types': entity_types,
            'count_by_type': count_by_type,
        }