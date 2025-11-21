"""
Geometry tracking for face, solid, and edge references in nuCAD
"""

from .topology_analyzer import TopologyAnalyzer


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
        
        # NEW: Topology analyzer for geometry-based face index prediction
        self._topology_analyzer = TopologyAnalyzer()
        self._extrude_topology_info = {}           # { extrude_feature_id: TopologyInfo }
        
        # Track extrusion metadata for calculating face indices
        self._extrude_metadata = {}                # { extrude_feature_id: { 'num_swept_faces': N, 'operation': 'NEW'/'ADD', ... } }
    
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

        NEW: Uses topology analysis when available, falls back to heuristics.
        
        side: Optional "START" or "END" to disambiguate which cap. If omitted, choose heuristic default.
        """
        # Look backwards in timeline to find extrude operations that have completed
        # before the current feature
        solids_that_will_exist = 0
        latest_extrude_id = None
        
        for i in range(self.current_feature_index):
            if i < len(self.feature_timeline):
                _, feature_type, creates_solid = self.feature_timeline[i]
                if creates_solid and feature_type == "extrude":
                    solids_that_will_exist += 1
                    # Track the most recent extrude ID
                    if i < len(self._extrude_ids_in_order):
                        latest_extrude_id = self._extrude_ids_in_order[solids_that_will_exist - 1]
        
        # Only reference a solid if it will definitely exist by execution time
        if solids_that_will_exist > 0:
            latest_solid_id = solids_that_will_exist - 1
            
            # NEW: Try to use topology analysis for the latest extrude
            if latest_extrude_id:
                return self.get_cap_face_for_extrude_id(latest_extrude_id, side)
            
            # FALLBACK: Old heuristic logic if we can't identify the extrude
            # Heuristic mapping for cap face index based on profile complexity
            # If the profile looks like an annulus (e.g., two circles -> donut), the top cap
            # face often indexes differently in nuCAD. Empirically, s{n}:3 yields the correct cap.
            try:
                if self._last_extrude_profile:
                    count_by_type = self._last_extrude_profile.get('count_by_type', {})
                    num_circles = count_by_type.get('skCircle', 0)
                    # OLD HEURISTIC: Annulus (donut) - map START/END to distinct caps for stability
                    if num_circles >= 2:
                        print(f"    ⚠️  Using OLD donut heuristic in get_cap_face_of_latest_solid (num_circles={num_circles})")
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

        NEW: Uses topology analysis instead of hard-coded donut detection.
        Falls back to heuristics if topology analysis unavailable or low confidence.
        
        side: Optional "START" or "END"; if omitted, a stable default is chosen.
        """
        if not isinstance(extrude_feature_id, str):
            return None

        if extrude_feature_id not in self._extrude_id_to_index:
            return None

        solid_index = self._extrude_id_to_index[extrude_feature_id]
        
        # NEW: Try topology analysis first
        topology_info = self._extrude_topology_info.get(extrude_feature_id)
        
        if topology_info and topology_info.confidence >= 0.7:
            # High confidence - use topology analysis results
            cap_faces = topology_info.cap_faces
            
            if cap_faces is None:
                # Complex topology - would need runtime discovery
                print(f"    Complex topology detected ({topology_info.type}), confidence too low for static prediction")
                # Fall through to heuristic fallback below
            else:
                # Use analyzed cap faces
                if side == "START":
                    cap_index = cap_faces[0]
                elif side == "END":
                    cap_index = cap_faces[1]
                else:
                    # Default to END (top cap)
                    cap_index = cap_faces[1]
                
                print(f"    Using topology-analyzed cap face: s{solid_index}:{cap_index} (type={topology_info.type}, confidence={topology_info.confidence:.2f})")
                return f"s{solid_index}:{cap_index}"
        
        # FALLBACK: Old heuristic-based logic (kept for low confidence cases)
        print(f"    Falling back to heuristic cap face selection (confidence={topology_info.confidence if topology_info else 'N/A'})")
        
        profile = self._extrude_profiles.get(extrude_feature_id)

        try:
            if profile:
                count_by_type = profile.get('count_by_type', {})
                num_circles = count_by_type.get('skCircle', 0)
                if num_circles >= 2:
                    # OLD HEURISTIC: Annulus - distinct caps for START/END
                    print(f"    ⚠️  Using OLD donut heuristic (num_circles={num_circles})")
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
        """Return a cap face reference for a SWEPT_FACE that references multiple edges.
        
        When edges from multiple extrusions are referenced, it typically means we want
        a cap face (top/bottom) of the most recent extrude, not a swept side face.
        
        This calculates the cap index based on the actual number of swept faces,
        eliminating hardcoded assumptions about specific indices.
        """
        if not isinstance(extrude_feature_id, str):
            return None
        if extrude_feature_id not in self._extrude_id_to_index:
            return None
        
        solid_index = self._extrude_id_to_index[extrude_feature_id]
        
        # Get metadata about this extrusion
        metadata = self._extrude_metadata.get(extrude_feature_id, {})
        num_swept_faces = metadata.get('num_swept_faces', 0)
        is_symmetric = metadata.get('is_symmetric', False)
        operation = metadata.get('operation', 'NEW')
        
        if num_swept_faces > 0:
            # For SYMMETRIC ADD extrusions:
            # Based on empirical observation from working examples, the bottom cap
            # is at index 2 regardless of the number of swept faces
            if is_symmetric and 'ADD' in operation:
                cap_index = 2  # Bottom cap for symmetric extrusions
                print(f"      Calculated cap face for SYMMETRIC ADD {extrude_feature_id}: using empirical index :{cap_index}")
                return f"s{solid_index}:{cap_index}"
            
            # For other extrusion types:
            # In OpenCASCADE topology for extrusions:
            # - Indices 0 to (N-1): Swept side faces created from extruding edges
            # - After swept faces come cap faces
            cap_index = num_swept_faces
            print(f"      Calculated cap face for {extrude_feature_id}: {num_swept_faces} swept faces → using cap at index :{cap_index}")
            return f"s{solid_index}:{cap_index}"
        
        # If no metadata available, we can't make a good guess
        # This shouldn't happen if extrusions are properly registering metadata
        print(f"      ERROR: No swept face metadata for {extrude_feature_id} - cannot calculate cap face index")
        return None
    
    def register_extrude_metadata(self, extrude_feature_id: str, num_swept_faces: int, operation_type: str = "NEW", is_symmetric: bool = False):
        """Store metadata about an extrusion for later face index calculation.
        
        Args:
            extrude_feature_id: The unique ID of the extrude feature
            num_swept_faces: Number of side faces created by extruding edges
            operation_type: NEW, ADD, etc.
            is_symmetric: Whether this is a symmetric extrusion
        """
        if isinstance(extrude_feature_id, str):
            self._extrude_metadata[extrude_feature_id] = {
                'num_swept_faces': num_swept_faces,
                'operation': operation_type,
                'is_symmetric': is_symmetric
            }
            print(f"      Registered extrude metadata: {extrude_feature_id} has {num_swept_faces} swept faces (symmetric={is_symmetric})")
    
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
        self._extrude_topology_info = {}  # NEW: Clear topology analysis cache

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

    def register_extrude_profile(self, extrude_feature_id: str, entities: list, primitives_dict: dict = None):
        """Record profile summary keyed by extrude feature ID (preferred for later reference).
        
        NEW: Also performs topology analysis to determine expected face indices.
        
        Args:
            extrude_feature_id: The extrude feature ID
            entities: Entity references from the extrude parameters
            primitives_dict: Optional dict of primitive definitions from the source sketch JSON
        """
        if not isinstance(extrude_feature_id, str):
            return
        if not isinstance(entities, list):
            self._extrude_profiles[extrude_feature_id] = None
            return

        # Handle empty entities list - use last sketch
        if len(entities) == 0 or (len(entities) == 1 and isinstance(entities[0], list) and len(entities[0]) == 0):
            # Entities is empty [[]] - extruding the last sketch by default
            sketch_id = self._last_sketch_id
            
            if sketch_id:
                sketch_profile = self.get_sketch_profile(sketch_id)
                
                if sketch_profile:
                    # Build entities list from sketch primitives
                    entities = [["newSketch", sketch_id]]
                    for loop in sketch_profile.get('loops', []):
                        for prim in loop.get('primitives', []):
                            prim_id = prim.get('id')
                            prim_type = prim.get('type')
                            if prim_id and prim_type:
                                # Map type to OnShape primitive name
                                type_map = {
                                    'line': 'skLineSegment',
                                    'arc': 'skArc',
                                    'circle': 'skCircle'
                                }
                                onshape_type = type_map.get(prim_type, prim_type)
                                entities.append([prim_id, onshape_type])
                    
                    # Also build primitives_dict from sketch profile
                    if not primitives_dict:
                        primitives_dict = {}
                        for loop in sketch_profile.get('loops', []):
                            for prim in loop.get('primitives', []):
                                prim_id = prim.get('id')
                                if prim_id:
                                    primitives_dict[prim_id] = prim

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
        
        # NEW: Perform topology analysis
        # If primitives_dict was provided directly, use it
        if primitives_dict:
            try:
                topology_info = self._topology_analyzer.analyze_profile_topology(
                    entities, primitives_dict
                )
                self._extrude_topology_info[extrude_feature_id] = topology_info
                return
            except Exception as e:
                print(f"    Warning: Topology analysis failed for {extrude_feature_id}: {e}")
                self._extrude_topology_info[extrude_feature_id] = None
                return
        
        # Fallback: Try to get primitives from sketch profile
        # Extract sketch_id from entities
        sketch_id = None
        for pair in entities:
            if isinstance(pair, list) and len(pair) == 2 and pair[1] == 'newSketch':
                sketch_id = pair[0]
                break
        
        if sketch_id:
            sketch_profile = self.get_sketch_profile(sketch_id)
            
            if sketch_profile:
                # Build primitives dict from sketch profile
                primitives = {}
                for loop in sketch_profile.get('loops', []):
                    for prim in loop.get('primitives', []):
                        prim_id = prim.get('id')
                        if prim_id:
                            primitives[prim_id] = prim
                
                # Run topology analysis
                try:
                    topology_info = self._topology_analyzer.analyze_profile_topology(
                        entities, primitives
                    )
                    self._extrude_topology_info[extrude_feature_id] = topology_info
                except Exception as e:
                    print(f"    Warning: Topology analysis failed for {extrude_feature_id}: {e}")
                    self._extrude_topology_info[extrude_feature_id] = None