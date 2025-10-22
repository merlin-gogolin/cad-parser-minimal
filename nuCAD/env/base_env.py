from .actions import (
    AddSketch, StartLoop, AddLine, AddArc, AddCircle, AddEllipse, 
    AddSpline, AddBezier, 
    CloseProfile, MakeFace, Extrude, Boolean, 
    Fillet, Chamfer, Fillet2D, Chamfer2D, Revolve, Loft, AddSweep, Shell, Mirror, Transform,
    LinearPattern, CircularPattern
)
from .geometry.sketch_operations import (
    begin_sketch, add_line, add_arc, add_circle, add_spline, add_bezier,
    close_profile, get_current_plane
)
from .geometry.face_operations import make_face_with_optional_cut
from .geometry.body_operations import extrude_all_faces
from .geometry.boolean_operations import boolean_op
from .geometry.geometry_utils import (
    get_face_data, get_faces_from_references, get_shape_from_reference, create_compound_shape
)
from .geometry.edge_operations import apply_fillet, apply_chamfer, apply_fillet2d, apply_chamfer2d
from .geometry.body_operations import apply_revolve, apply_loft, apply_sweep
from .geometry.transform_operations import (
    apply_shell, apply_mirror_plane, apply_mirror_line, apply_mirror_point,
    apply_translation_vector, apply_translation_point_to_point, apply_translation_distance_direction,
    apply_rotation_axis, apply_rotation_center_2d, apply_combined_transform
)
from .geometry.pattern_operations import apply_linear_pattern, apply_circular_pattern

from .shapes import (
    Vertex, Wire, Edge, Face, Solid, Compound, CADState
)
from .helper import (
    get_sorted_edge_list, get_sorted_face_list, get_face_dict_for_solid, get_edge_dict_for_solid, 
    compute_bbox, get_edge_vertices
)

from .renderer import nuCADRenderer

from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Solid
from OCC.Core.BRep import BRep_Builder


class nuCADEnv:
    def __init__(self, viz=False, render_setting=None, orient_policy: str | None = None):
        self.viz = viz
        if self.viz:
            self.renderer = nuCADRenderer(render_setting)
            # Display coordinate axes if enabled
            if render_setting and render_setting.get("show_axes", False):
                self.renderer.display_coordinate_axes()
        # Optional orientation policy for sketches
        if orient_policy is not None:
            try:
                from .geometry.sketch_operations import set_orientation_policy
                set_orientation_policy(orient_policy)
            except Exception as e:
                # Non-fatal: continue without policy if import fails
                pass
        self.reset()
        self.current_wire_edges = []
        self.last_face_wire_index = 0


    def reset(self):
        self.current_shape = None
        self.actions = []
        self.edge_count = 0
        self.face_count = 0
        self.solid_count = 0
        self.wire_count = 0
        self.sketch_count = 0
        self.active_sketch = None

        self.current_wire_edges = []
        self.last_face_wire_index = 0

        # store cad state 
        self.state = CADState() 
        
        # Track replacement relationships: original_id -> replacement_id
        self.replacement_map = {}
        
        # Track which geometry is currently active (not replaced)
        self.active_solid_ids = set()
        self.active_face_ids = set()
        self.active_edge_ids = set()
        self.active_wire_ids = set()

        # store brep graph

        self.brep_graph = {
            "edge_to_wire": {},
            "wire_to_face": {},
            "face_to_solid": {}
        }

        self.shape_history = {
            "faces": {},
            "solids": {},
            "wires": {},
            "sketches": {}
        }

        self.solid_index = {}

        return self.get_observation()


    def step(self, action):
        if self._check_done():
            raise RuntimeError("Simulation ended. Call reset().")

        self.actions.append(action)

        shape, metadata = self._apply_action(action)     

        if shape is not None:
            self.current_shape = shape

        if isinstance(action, (AddLine, AddArc, AddCircle, AddEllipse)):
            self.current_wire_edges.append(shape)
            eid = f"e{self.edge_count}"
            self.edge_count += 1

            if isinstance(action, AddLine):
                start, end = action.start, action.end
                # Ensure coordinates are 3D
                if len(start) == 2:
                    start = (start[0], start[1], 0.0)
                if len(end) == 2:
                    end = (end[0], end[1], 0.0)
            elif isinstance(action, AddArc):
                start, end = action.points[0], action.points[2]
                # Ensure coordinates are 3D
                if len(start) == 2:
                    start = (start[0], start[1], 0.0)
                if len(end) == 2:
                    end = (end[0], end[1], 0.0)
            elif isinstance(action, AddCircle):
                # For circles, use center as both start and end, ensure 3D
                center = action.center
                if len(center) == 2:
                    center = (center[0], center[1], 0.0)
                start = end = center
            elif isinstance(action, AddEllipse):
                # For ellipses, use center as both start and end, ensure 3D
                center = action.center
                if len(center) == 2:
                    center = (center[0], center[1], 0.0)
                start = end = center

            # Create edge data structure
            edge_data = Edge(
                id=eid,
                vertices=(start, end),
                shape=shape
            )
            
            self.state.edges[eid] = edge_data
            
            # Track this edge as active
            self.active_edge_ids.add(eid)

        elif isinstance(action, CloseProfile):
            all_edges = list(self.state.edges.items())
            used_edge_ids = [
                eid for eid, edata in all_edges
                if edata.shape in self.current_wire_edges
            ]

            wid = f"w{self.wire_count}"
            self.wire_count += 1

            # Create wire data structure using the Wire dataclass
            edge_objects = [self.state.edges[eid] for eid in used_edge_ids]
            wire_data = Wire(
                id=wid,
                edges=edge_objects,
                shape=shape
            )
            
            self.state.wires[wid] = wire_data
            self.shape_history["wires"][wid] = shape
            self.active_sketch["wires"].append(wid)
            self.state.sketches[self.active_sketch["id"]] = self.active_sketch

            # Track this wire as active
            self.active_wire_ids.add(wid)

            for eid in used_edge_ids:
                self.brep_graph["edge_to_wire"].setdefault(eid, []).append(wid)

            self.current_wire_edges = []


        elif isinstance(action, MakeFace):
            new_wire_ids = metadata
            fid = f"f{self.face_count}"
            self.face_count += 1

            # Get all edge IDs from the wires
            all_edges = []
            for wid in new_wire_ids:
                wire_data = self.state.wires[wid]
                # Wire dataclass has .edges attribute containing Edge objects
                edge_ids = [edge.id for edge in wire_data.edges]
                all_edges.extend(edge_ids)
            
            # Note: Edge objects don't track their faces - faces track their edges instead

            # Create face data structure
            edge_objects = [self.state.edges[eid] for eid in all_edges]
            
            # Calculate centroid (simple approximation from edge vertices)
            all_vertices = []
            for edge in edge_objects:
                all_vertices.extend(edge.vertices)
            
            if all_vertices:
                centroid = (
                    sum(v[0] for v in all_vertices) / len(all_vertices),
                    sum(v[1] for v in all_vertices) / len(all_vertices),
                    sum(v[2] for v in all_vertices) / len(all_vertices)
                )
            else:
                centroid = (0.0, 0.0, 0.0)
            
            face_data = Face(
                id=fid,
                edges=edge_objects,
                centroid=centroid,
                shape=shape
            )
            
            self.state.faces[fid] = face_data
            
            # Track this face as active
            self.active_face_ids.add(fid)
            
            # When edges are used to create a face, they may no longer be independently active
            # (depends on your design choice - keep them active or not)
            # For now, let's keep edges active until they're consumed by extrusion
            
            for wid in new_wire_ids:
                self.brep_graph["wire_to_face"][wid] = fid

            self.shape_history["faces"][fid] = shape
            self.current_face_id = fid


        obs = self.get_observation()
        reward = self._compute_reward()
        done = self._check_done()
        return obs, reward, done, {}


    def list_edges(self, solid_id):
        shape = self.solid_index[solid_id].shape
        edge_list = get_sorted_edge_list(shape)

        return {
            f"e{i}": Edge(
                id=f"e{i}",
                vertices=(a, b),
                shape=shape
            )
            for i, (_, (a, b), shape) in enumerate(edge_list)
        }



    def list_faces(self, solid_id):
        from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopoDS import TopoDS_Face, TopoDS_Edge, TopoDS_Vertex
        from OCC.Core.BRep import BRep_Tool

        shape = self.solid_index[solid_id].shape
        edge_dict = self.list_edges(solid_id)

        face_list = get_sorted_face_list(shape, edge_dict)

        result = {
            f"f{i}_{solid_id}": Face(
                id=f"f{i}_{solid_id}",
                centroid=center,
                shape=face,
                edges=edges
            )
            for i, (center, face, edges) in enumerate(face_list)
        }

        return result


    def render(self, export_video=False, video_path=None, show_axes=None):
        if self.viz:
            # Always render all active geometry to show whatever the user just drew/created
            # This ensures we see edges, faces, solids, or combinations thereof
            self.render_all_active_geometry()
            
            # Optionally show coordinate axes
            if show_axes is not None:
                if show_axes:
                    self.show_coordinate_axes()
                else:
                    self.hide_coordinate_axes()
                    
            if export_video and video_path:
                self.renderer.save_video(video_path)

    def render_all_solids(self):
        """Render all solids in the scene, not just the current shape"""
        if self.viz:
            self.renderer.render_all_solids(self.state, self.actions[-1] if self.actions else None)

    def render_all_active_geometry(self):
        """Render all active geometry in the scene (not replaced by newer versions)"""
        if self.viz:
            # Get all active geometry (solids, faces, edges)
            active_geometry = self.get_active_geometry()
            self.renderer.render_active_geometry(active_geometry, self.actions[-1] if self.actions else None)

    def get_observation(self):
        return {
            "num_edges": len(self.state.edges),
            "num_faces": len(self.state.faces),
            "num_solids": len(self.state.solids),
            "last_action": self.actions[-1] if self.actions else None,
            "state": self.state,
            "brep_graph": self.brep_graph
        }


    def _apply_action(self, action):


        if isinstance(action, AddSketch):
 
            origin, normal = get_face_data(action.on_face, action.origin, 
                                           action.normal, self.solid_index)

            begin_sketch(origin=origin, normal=normal)

            sk_id = f"sk{self.sketch_count}"
            self.active_sketch = {
                "origin": origin,
                "normal": normal,
                "id": sk_id,
                "wires": []
            }
            self.last_face_wire_index = 0  # ← Reset for new sketch

            self.shape_history["sketches"][sk_id] = self.active_sketch  
            self.sketch_count += 1
            return None, None

        elif isinstance(action, StartLoop):
            self.current_wire_edges = []
            return None, None

        elif isinstance(action, AddLine):
            return add_line(action.start, action.end), None

        elif isinstance(action, AddArc):
            return add_arc(*action.points), None 

        elif isinstance(action, AddCircle):
            return add_circle(center=action.center, radius=action.radius), None

        elif isinstance(action, AddEllipse):
            from .geometry.sketch_operations import add_ellipse  
            shape = add_ellipse(
                center=action.center,
                major_axis_dir=action.major_axis_dir,
                major_radius=action.major_radius,
                minor_radius=action.minor_radius
            )
            return shape, None


        elif isinstance(action, AddSpline):
            return add_spline(action.points), None

        elif isinstance(action, AddBezier):
            return add_bezier(action.control_points), None


        elif isinstance(action, CloseProfile):
            return close_profile(self.shape_history), None
                    
        elif isinstance(action, MakeFace):
            new_wire_ids = self.active_sketch["wires"][self.last_face_wire_index:]
            self.last_face_wire_index = len(self.active_sketch["wires"])
            wire_shapes = [self.shape_history["wires"][wid] for wid in new_wire_ids]

            existing_face_shapes = [fdata.shape for fdata in self.state.faces.values()]

            shape, is_cut = make_face_with_optional_cut(wire_shapes, existing_face_shapes, self.last_face_wire_index)

            if is_cut and self.last_face_wire_index > 1:
                for prev_fid, fdata in self.state.faces.items():
                    if fdata.shape in existing_face_shapes:
                        self.shape_history["faces"][prev_fid] = shape
                        # Note: Can't modify frozen Face object, need to replace it
                        # For now, just update the history
                        if self.viz:
                            self.renderer.clear()
                        break
                return shape, new_wire_ids

            # Normal face creation
            return shape, new_wire_ids


        elif isinstance(action, Extrude):

            compound, faces_full = extrude_all_faces(action.faces, self.state.solids, 
                                                     self.state.faces, action.height,
                                                     action.direction, action.opposite_height)

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            # Sorted edges and faces
            edges_sorted = get_edge_dict_for_solid(sid, compound)
            faces_sorted = get_face_dict_for_solid(sid, compound, edges_sorted)

            # Bounding box
            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(compound)

            # Save as Solid dataclass
            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=compound,
                faces_full=faces_full  
            )

            self.state.solids.append(solid_obj)
            self.solid_index[solid_obj.id] = solid_obj
            
            # Add the new solid to active geometry tracking
            self.active_solid_ids.add(sid)
            
            # Remove the extruded faces from active faces (they're now part of the solid)
            for face_id in action.faces:
                self.active_face_ids.discard(face_id)
                
            self.shape_history["solids"][sid] = compound
            self.current_shape = compound
            self.current_solid_id = sid  

            return compound, None


        elif isinstance(action, Boolean):

            shape1 = self.solid_index[action.solid1].shape
            shape2 = self.solid_index[action.solid2].shape

            result_solid, faces_full = boolean_op(shape1, shape2, op_type=action.type)


            sid = f"s{self.solid_count}"
            self.solid_count += 1

            # Sorted edges and faces
            edges_sorted = get_edge_dict_for_solid(sid, result_solid)
            faces_sorted = get_face_dict_for_solid(sid, result_solid, edges_sorted)

            # Bounding box
            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(result_solid)

            # Save as Solid dataclass
            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=result_solid, 
                faces_full=faces_full  
            )

            self.solid_index[solid_obj.id] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = result_solid
            self.current_shape = result_solid
            self.current_solid_id = sid  

            # Update active solid tracking: remove input solids, add result solid
            self.active_solid_ids.discard(action.solid1)
            self.active_solid_ids.discard(action.solid2)
            self.active_solid_ids.add(sid)
            
            # Update replacement tracking
            if action.solid1 in self.replacement_map:
                self.replacement_map[action.solid1].add(sid)
            else:
                self.replacement_map[action.solid1] = {sid}
            
            if action.solid2 in self.replacement_map:
                self.replacement_map[action.solid2].add(sid)
            else:
                self.replacement_map[action.solid2] = {sid}

            if self.viz:
                self.renderer.clear() 

            return result_solid, None


        elif isinstance(action, Fillet):

            solid_id = action.solid or self.current_solid_id
            shape = self.solid_index[solid_id].shape

            # Find edge by ID
            edge_dict = self.list_edges(solid_id=solid_id)
            # Normalize possible edge identifier variants
            raw_edge = action.edge
            # Accept list/tuple like ["e0"] or ("e0",)
            if isinstance(raw_edge, (list, tuple)):
                raw_edge = raw_edge[0] if raw_edge else None
            target_edge = edge_dict.get(raw_edge) if isinstance(raw_edge, str) else None
            if target_edge is None and isinstance(raw_edge, str):
                # Accept composite ids like 's0e0' by extracting trailing 'eN'
                try:
                    import re
                    m = re.search(r"e\d+$", raw_edge)
                    if m:
                        target_edge = edge_dict.get(m.group(0))
                except Exception:
                    pass

            if target_edge is None:
                raise ValueError(f"Edge '{action.edge}' not found in solid '{solid_id}'")

            filleted_shape, faces_full = apply_fillet(shape, target_edge.shape, action.radius) 

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            # Sorted edges and faces
            edges_sorted = get_edge_dict_for_solid(sid, filleted_shape)
            faces_sorted = get_face_dict_for_solid(sid, filleted_shape, edges_sorted)

            # Bounding box
            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(filleted_shape)

            # Save as Solid dataclass
            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=filleted_shape, 
                faces_full=faces_full  

            )

            self.solid_index[solid_obj.id] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = filleted_shape

            # Update edges for the new solid
            new_edges = self.list_edges(solid_id=sid)
            self.state.edges.update(new_edges)

            # Track replacement: original solid is replaced by filleted solid
            self.replacement_map[solid_id] = sid
            self.active_solid_ids.discard(solid_id)  # Remove original from active
            self.active_solid_ids.add(sid)  # Add filleted solid to active

            self.current_shape = filleted_shape
            self.current_solid_id = sid

            if self.viz:
                self.renderer.clear() 

            return filleted_shape, None


        elif isinstance(action, Chamfer):

            solid_id = action.solid or self.current_solid_id
            shape = self.solid_index[solid_id].shape

            # Find edge by ID
            edge_dict = self.list_edges(solid_id=solid_id)
            raw_edge = action.edge
            if isinstance(raw_edge, (list, tuple)):
                raw_edge = raw_edge[0] if raw_edge else None
            target_edge = edge_dict.get(raw_edge) if isinstance(raw_edge, str) else None
            if target_edge is None and isinstance(raw_edge, str):
                try:
                    import re
                    m = re.search(r"e\d+$", raw_edge)
                    if m:
                        target_edge = edge_dict.get(m.group(0))
                except Exception:
                    pass

            if target_edge is None:
                raise ValueError(f"Edge '{action.edge}' not found in solid '{solid_id}'")

            chamfered_shape, faces_full = apply_chamfer(shape, target_edge.shape, action.distance)

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            # Sorted edges and faces
            edges_sorted = get_edge_dict_for_solid(sid, chamfered_shape)
            faces_sorted = get_face_dict_for_solid(sid, chamfered_shape, edges_sorted)

            # Bounding box
            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(chamfered_shape)

            # Save as Solid dataclass
            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=chamfered_shape, 
                faces_full=faces_full 
            )

            self.solid_index[solid_obj.id] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = chamfered_shape

            # Update edges for the new solid
            new_edges = self.list_edges(solid_id=sid)
            self.state.edges.update(new_edges)

            # Track replacement: original solid is replaced by chamfered solid
            self.replacement_map[solid_id] = sid
            self.active_solid_ids.discard(solid_id)  # Remove original from active
            self.active_solid_ids.add(sid)  # Add chamfered solid to active

            self.current_shape = chamfered_shape
            self.current_solid_id = sid

            if self.viz:
                self.renderer.clear() 

            return chamfered_shape, None


        elif isinstance(action, Revolve):
            face_id = action.face
            face_data = self.state.faces.get(face_id)
            if not face_data:
                raise ValueError(f"Face '{face_id}' not found.")

            face_shape = face_data.shape

            # Get edge shape if edge is specified
            edge_shape = None
            if action.edge:
                edge_entry = self.state.edges.get(action.edge)
                if edge_entry is None:
                    raise ValueError(f"Edge '{action.edge}' not found.")
                edge_shape = edge_entry.shape

            # Call revolve with edge or axis
            revolved_shape = apply_revolve(
                face=face_shape,
                direction=action.direction,
                angle=action.angle,
                angles=action.angles,
                axis_point=action.axis_point,
                axis_dir=action.axis_dir,
                edge=edge_shape
            )

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            edges_sorted = get_edge_dict_for_solid(sid, revolved_shape)
            faces_sorted = get_face_dict_for_solid(sid, revolved_shape, edges_sorted)

            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(revolved_shape)

            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=revolved_shape,
                faces_full=list(faces_sorted.values())
            )

            self.solid_index[sid] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = revolved_shape

            new_edges = self.list_edges(sid)
            self.state.edges.update(new_edges)

            self.current_shape = revolved_shape
            self.current_solid_id = sid

            # Update active solid tracking
            self.active_solid_ids.add(sid)
            
            # Remove the face that was revolved from active tracking
            self.active_face_ids.discard(face_id)

            if self.viz:
                self.renderer.clear()

            return revolved_shape, None


        elif isinstance(action, Loft):
            face_ids = action.faces
            face_shapes = []

            for fid in face_ids:
                fdata = self.state.faces.get(fid)
                if fdata is None:
                    raise ValueError(f"Face '{fid}' not found.")
                face_shapes.append(fdata.shape)

            loft_shape = apply_loft(
                face_shapes=face_shapes,
                solid=action.solid,
                ruled=action.ruled,
                smooth=action.smooth
            )

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            edges_sorted = get_edge_dict_for_solid(sid, loft_shape)
            faces_sorted = get_face_dict_for_solid(sid, loft_shape, edges_sorted)

            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(loft_shape)

            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=loft_shape,
                faces_full=list(faces_sorted.values())
            )

            self.solid_index[sid] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = loft_shape

            new_edges = self.list_edges(sid)
            self.state.edges.update(new_edges)

            self.current_shape = loft_shape
            self.current_solid_id = sid

            # Update active solid tracking
            self.active_solid_ids.add(sid)
            
            # Remove the faces that were lofted from active tracking
            for fid in face_ids:
                self.active_face_ids.discard(fid)

            if self.viz:
                self.renderer.clear()

            return loft_shape, None


        elif isinstance(action, AddSweep):
            # Get profile shape (face or wire)
            profile_shape = None
            if action.profile.startswith('f'):
                # Profile is a face
                face_data = self.state.faces.get(action.profile)
                if face_data is None:
                    raise ValueError(f"Face '{action.profile}' not found.")
                profile_shape = face_data.shape
            elif action.profile.startswith('w'):
                # Profile is a wire
                wire_data = self.state.wires.get(action.profile)
                if wire_data is None:
                    raise ValueError(f"Wire '{action.profile}' not found.")
                profile_shape = wire_data.shape
            else:
                raise ValueError(f"Invalid profile reference: {action.profile}")

            # Get path shape (wire or edge)
            path_shape = None
            if action.path.startswith('w'):
                # Path is a wire
                wire_data = self.state.wires.get(action.path)
                if wire_data is None:
                    raise ValueError(f"Wire '{action.path}' not found.")
                path_shape = wire_data.shape
            elif action.path.startswith('e'):
                # Path is an edge
                edge_data = self.state.edges.get(action.path)
                if edge_data is None:
                    raise ValueError(f"Edge '{action.path}' not found.")
                path_shape = edge_data.shape
            else:
                raise ValueError(f"Invalid path reference: {action.path}")

            # Apply sweep operation
            swept_shape = apply_sweep(
                profile_shape=profile_shape,
                path_shape=path_shape,
                solid=action.solid,
                frenet=action.frenet,
                twist_angle=action.twist_angle,
                scale_factor=action.scale_factor
            )

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            edges_sorted = get_edge_dict_for_solid(sid, swept_shape)
            faces_sorted = get_face_dict_for_solid(sid, swept_shape, edges_sorted)

            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(swept_shape)

            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=swept_shape,
                faces_full=list(faces_sorted.values())
            )

            self.solid_index[sid] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = swept_shape

            new_edges = self.list_edges(sid)
            self.state.edges.update(new_edges)

            self.current_shape = swept_shape
            self.current_solid_id = sid

            # Update active solid tracking
            self.active_solid_ids.add(sid)
            
            # Remove the profile from active tracking if it was a face
            if action.profile.startswith('f'):
                self.active_face_ids.discard(action.profile)
            
            # Remove the path from active tracking if it was a wire
            if action.path.startswith('w'):
                self.active_wire_ids.discard(action.path)

            if self.viz:
                self.renderer.clear()

            return swept_shape, None


        elif isinstance(action, Shell):

            solid_id = action.solid
            if solid_id not in self.solid_index:
                raise ValueError(f"Solid '{solid_id}' not found")
            
            shape = self.solid_index[solid_id].shape

            # Get faces to remove using face references
            faces_to_remove = get_faces_from_references(action.faces_to_remove, self.solid_index)

            if not faces_to_remove:
                raise ValueError("No valid faces found to remove for shell operation")

            # Apply shell operation
            shelled_shape, faces_full = apply_shell(
                shape, 
                faces_to_remove, 
                action.thickness, 
                action.inward
            )

            sid = f"s{self.solid_count}"
            self.solid_count += 1

            # Sorted edges and faces
            edges_sorted = get_edge_dict_for_solid(sid, shelled_shape)
            faces_sorted = get_face_dict_for_solid(sid, shelled_shape, edges_sorted)

            # Bounding box
            xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(shelled_shape)

            # Save as Solid dataclass
            solid_obj = Solid(
                id=sid,
                faces=list(faces_sorted.values()),
                bbox_min=(xmin, ymin, zmin),
                bbox_max=(xmax, ymax, zmax),
                shape=shelled_shape, 
                faces_full=faces_full 
            )

            self.solid_index[solid_obj.id] = solid_obj
            self.state.solids.append(solid_obj)
            self.shape_history["solids"][sid] = shelled_shape

            # Update edges for the new solid
            new_edges = self.list_edges(solid_id=sid)
            self.state.edges.update(new_edges)

            self.current_shape = shelled_shape
            self.current_solid_id = sid

            # Update active solid tracking: replace the original solid with the shelled one
            self.active_solid_ids.discard(solid_id)
            self.active_solid_ids.add(sid)
            
            # Update replacement tracking
            if solid_id in self.replacement_map:
                self.replacement_map[solid_id].add(sid)
            else:
                self.replacement_map[solid_id] = {sid}

            if self.viz:
                self.renderer.clear() 

            return shelled_shape, None


        elif isinstance(action, Mirror):
            
            # Get the target shape to mirror
            target_shape = get_shape_from_reference(action.target, self.solid_index, self.state)
            
            # Apply the appropriate mirror operation
            if action.mirror_type == "plane":
                mirrored_shape = apply_mirror_plane(
                    target_shape, 
                    action.plane_origin, 
                    action.plane_normal
                )
            elif action.mirror_type == "line":
                mirrored_shape = apply_mirror_line(
                    target_shape,
                    action.line_point,
                    action.line_direction
                )
            elif action.mirror_type == "point":
                mirrored_shape = apply_mirror_point(
                    target_shape,
                    action.point
                )
            else:
                raise ValueError(f"Unknown mirror type: {action.mirror_type}")
            
            # Initialize the return shape
            return_shape = mirrored_shape
            
            # Handle copy_original flag
            if action.copy_original:
                # Create compound shape containing both original and mirrored shapes
                # Determine the type of geometry we're mirroring
                if action.target.startswith("s") and ":" not in action.target:
                    # Mirroring a solid - create compound solid
                    sid = f"s{self.solid_count}"
                    self.solid_count += 1
                    
                    # Create compound shape from original and mirrored shapes
                    compound_shape = create_compound_shape([target_shape, mirrored_shape])
                    
                    # Extract faces from compound shape
                    from OCC.Core.TopExp import TopExp_Explorer
                    from OCC.Core.TopAbs import TopAbs_FACE
                    from OCC.Core.TopoDS import topods
                    exp = TopExp_Explorer(compound_shape, TopAbs_FACE)
                    faces_full = []
                    while exp.More():
                        faces_full.append(topods.Face(exp.Current()))
                        exp.Next()
                    
                    # Sorted edges and faces for the compound
                    edges_sorted = get_edge_dict_for_solid(sid, compound_shape)
                    faces_sorted = get_face_dict_for_solid(sid, compound_shape, edges_sorted)
                    
                    # Bounding box of the compound
                    xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(compound_shape)
                    
                    # Save as Solid dataclass (represents the compound)
                    solid_obj = Solid(
                        id=sid,
                        faces=list(faces_sorted.values()),
                        bbox_min=(xmin, ymin, zmin),
                        bbox_max=(xmax, ymax, zmax),
                        shape=compound_shape,  # The compound contains both original and mirror
                        faces_full=faces_full
                    )
                    
                    self.solid_index[solid_obj.id] = solid_obj
                    self.state.solids.append(solid_obj)
                    self.shape_history["solids"][sid] = compound_shape
                    
                    # Update edges for the compound solid
                    new_edges = self.list_edges(solid_id=sid)
                    self.state.edges.update(new_edges)
                    
                    # Set current shape to the compound 
                    self.current_shape = solid_obj.shape
                    self.current_solid_id = sid
                    
                    # Return the compound shape so it becomes the current_shape in step()
                    return_shape = compound_shape
                    
                elif action.target.startswith("f"):
                    # Mirroring a face - create compound face
                    fid = f"f{self.face_count}"
                    self.face_count += 1
                    
                    # Create compound from original and mirrored faces
                    compound_shape = create_compound_shape([target_shape, mirrored_shape])
                    
                    # Store compound face in state
                    face_data = Face(
                        id=fid,
                        edges=[],  # Compound faces don't have individual edges tracked
                        centroid=(0, 0, 0),  # Could calculate proper centroid if needed
                        shape=compound_shape
                    )
                    self.state.faces[fid] = face_data
                    
                    self.current_shape = compound_shape
                    return_shape = compound_shape
                    
                else:
                    # For other geometry types, just update current shape
                    self.current_shape = mirrored_shape
                    return_shape = mirrored_shape
                    
            else:
                # Transform original in place (replace original)
                if action.target.startswith("s") and ":" not in action.target:
                    # Update existing solid
                    solid_id = action.target
                    if solid_id not in self.solid_index:
                        raise ValueError(f"Solid '{solid_id}' not found")
                    
                    # Update the solid with mirrored shape
                    original_solid = self.solid_index[solid_id]
                    
                    # Extract faces from mirrored shape
                    from OCC.Core.TopExp import TopExp_Explorer
                    from OCC.Core.TopAbs import TopAbs_FACE
                    from OCC.Core.TopoDS import topods
                    exp = TopExp_Explorer(mirrored_shape, TopAbs_FACE)
                    faces_full = []
                    while exp.More():
                        faces_full.append(topods.Face(exp.Current()))
                        exp.Next()
                    
                    # Update bounding box
                    xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(mirrored_shape)
                    
                    # Update solid object
                    updated_solid = Solid(
                        id=solid_id,
                        faces=original_solid.faces,  # Keep existing face references
                        bbox_min=(xmin, ymin, zmin),
                        bbox_max=(xmax, ymax, zmax),
                        shape=mirrored_shape,
                        faces_full=faces_full
                    )
                    
                    self.solid_index[solid_id] = updated_solid
                    self.shape_history["solids"][solid_id] = mirrored_shape
                    
                    self.current_shape = mirrored_shape
                    self.current_solid_id = solid_id
                    
                else:
                    # For other geometry types, update in place
                    self.current_shape = mirrored_shape
            
            # Update active tracking based on the operation
            if action.copy_original:
                if action.target.startswith("s") and ":" not in action.target:
                    # For solids: replace original with compound
                    self.active_solid_ids.discard(action.target)
                    self.active_solid_ids.add(sid)
                elif action.target.startswith("f"):
                    # For faces: replace original with compound
                    self.active_face_ids.discard(action.target)
                    self.active_face_ids.add(fid)
            # If not copy_original, the original shape is modified in place, so no tracking change needed
            
            if self.viz:
                self.renderer.clear()
            
            return return_shape, None

        elif isinstance(action, Transform):
            
            # Get the target shape to transform
            target_shape = get_shape_from_reference(action.target, self.solid_index, self.state)
            
            # Apply the appropriate transformation operation
            if action.operation == "translate":
                if action.translation_type == "vector":
                    transformed_shape = apply_translation_vector(
                        target_shape, 
                        action.translation_vector
                    )
                elif action.translation_type == "point_to_point":
                    transformed_shape = apply_translation_point_to_point(
                        target_shape,
                        action.from_point,
                        action.to_point
                    )
                elif action.translation_type == "distance_direction":
                    transformed_shape = apply_translation_distance_direction(
                        target_shape,
                        action.distance,
                        action.direction
                    )
                else:
                    raise ValueError(f"Unknown translation type: {action.translation_type}")
                    
            elif action.operation == "rotate":
                if action.rotation_type == "axis":
                    transformed_shape = apply_rotation_axis(
                        target_shape,
                        action.rotation_axis_point,
                        action.rotation_axis_direction,
                        action.rotation_angle
                    )
                elif action.rotation_type == "center_2d":
                    transformed_shape = apply_rotation_center_2d(
                        target_shape,
                        action.rotation_center,
                        action.rotation_plane_normal,
                        action.rotation_angle
                    )
                elif action.rotation_type == "coordinate_axis":
                    # Convert coordinate axis to axis rotation
                    if action.coordinate_axis == "x":
                        axis_direction = (1.0, 0.0, 0.0)
                    elif action.coordinate_axis == "y":
                        axis_direction = (0.0, 1.0, 0.0)
                    elif action.coordinate_axis == "z":
                        axis_direction = (0.0, 0.0, 1.0)
                    else:
                        raise ValueError(f"Unknown coordinate axis: {action.coordinate_axis}")
                    
                    transformed_shape = apply_rotation_axis(
                        target_shape,
                        (0.0, 0.0, 0.0),  # Origin point
                        axis_direction,
                        action.rotation_angle
                    )
                else:
                    raise ValueError(f"Unknown rotation type: {action.rotation_type}")
                    
            elif action.operation == "combined":
                # Apply combined transformations in sequence
                transformed_shape = apply_combined_transform(target_shape, action.transforms)
                
            else:
                raise ValueError(f"Unknown transform operation: {action.operation}")
            
            # Initialize the return shape
            return_shape = transformed_shape
            
            # Handle copy_original flag
            if action.copy_original:
                # Create compound shape containing both original and transformed shapes
                # Determine the type of geometry we're transforming
                if action.target.startswith("s") and ":" not in action.target:
                    # Transforming a solid - create compound solid
                    sid = f"s{self.solid_count}"
                    self.solid_count += 1
                    
                    # Create compound shape from original and transformed shapes
                    compound_shape = create_compound_shape([target_shape, transformed_shape])
                    
                    # Extract faces from compound shape
                    from OCC.Core.TopExp import TopExp_Explorer
                    from OCC.Core.TopAbs import TopAbs_FACE
                    from OCC.Core.TopoDS import topods
                    exp = TopExp_Explorer(compound_shape, TopAbs_FACE)
                    faces_full = []
                    while exp.More():
                        faces_full.append(topods.Face(exp.Current()))
                        exp.Next()
                    
                    # Sorted edges and faces for the compound
                    edges_sorted = get_edge_dict_for_solid(sid, compound_shape)
                    faces_sorted = get_face_dict_for_solid(sid, compound_shape, edges_sorted)
                    
                    # Bounding box of the compound
                    xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(compound_shape)
                    
                    # Save as Solid dataclass (represents the compound)
                    solid_obj = Solid(
                        id=sid,
                        faces=list(faces_sorted.values()),
                        bbox_min=(xmin, ymin, zmin),
                        bbox_max=(xmax, ymax, zmax),
                        shape=compound_shape,  # The compound contains both original and transformed
                        faces_full=faces_full
                    )
                    
                    self.solid_index[solid_obj.id] = solid_obj
                    self.state.solids.append(solid_obj)
                    self.shape_history["solids"][sid] = compound_shape
                    
                    # Update edges for the compound solid
                    new_edges = self.list_edges(solid_id=sid)
                    self.state.edges.update(new_edges)
                    
                    # Set current shape to the compound 
                    self.current_shape = solid_obj.shape
                    self.current_solid_id = sid
                    
                    # Return the compound shape so it becomes the current_shape in step()
                    return_shape = compound_shape
                    
                elif action.target.startswith("f"):
                    # Transforming a face - create compound face
                    fid = f"f{self.face_count}"
                    self.face_count += 1
                    
                    # Create compound from original and transformed faces
                    compound_shape = create_compound_shape([target_shape, transformed_shape])
                    
                    # Store compound face in state
                    face_data = Face(
                        id=fid,
                        edges=[],  # Compound faces don't have individual edges tracked
                        centroid=(0, 0, 0),  # Could calculate proper centroid if needed
                        shape=compound_shape
                    )
                    self.state.faces[fid] = face_data
                    
                    self.current_shape = compound_shape
                    return_shape = compound_shape
                    
                else:
                    # For other geometry types, just update current shape
                    self.current_shape = transformed_shape
                    return_shape = transformed_shape
                    
            else:
                # Transform original in place (replace original)
                if action.target.startswith("s") and ":" not in action.target:
                    # Update existing solid
                    solid_id = action.target
                    if solid_id not in self.solid_index:
                        raise ValueError(f"Solid '{solid_id}' not found")
                    
                    # Update the solid with transformed shape
                    original_solid = self.solid_index[solid_id]
                    
                    # Extract faces from transformed shape
                    from OCC.Core.TopExp import TopExp_Explorer
                    from OCC.Core.TopAbs import TopAbs_FACE
                    from OCC.Core.TopoDS import topods
                    exp = TopExp_Explorer(transformed_shape, TopAbs_FACE)
                    faces_full = []
                    while exp.More():
                        faces_full.append(topods.Face(exp.Current()))
                        exp.Next()
                    
                    # Update bounding box
                    xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(transformed_shape)
                    
                    # Update solid object
                    updated_solid = Solid(
                        id=solid_id,
                        faces=original_solid.faces,  # Keep existing face references
                        bbox_min=(xmin, ymin, zmin),
                        bbox_max=(xmax, ymax, zmax),
                        shape=transformed_shape,
                        faces_full=faces_full
                    )
                    
                    self.solid_index[solid_id] = updated_solid
                    self.shape_history["solids"][solid_id] = transformed_shape
                    
                    self.current_shape = transformed_shape
                    self.current_solid_id = solid_id
                    
                else:
                    # For other geometry types, update in place
                    self.current_shape = transformed_shape
            
            # Update active tracking based on the operation
            if action.copy_original:
                if action.target.startswith("s") and ":" not in action.target:
                    # For solids: replace original with compound
                    self.active_solid_ids.discard(action.target)
                    self.active_solid_ids.add(sid)
                elif action.target.startswith("f"):
                    # For faces: replace original with compound
                    self.active_face_ids.discard(action.target)
                    self.active_face_ids.add(fid)
            # If not copy_original, the original shape is modified in place, so no tracking change needed
            
            if self.viz:
                self.renderer.clear()
            
            return return_shape, None

        elif isinstance(action, LinearPattern):
            
            # Get the target shape to pattern
            target_shape = get_shape_from_reference(action.target, self.solid_index, self.state)
            
            # Apply linear pattern
            pattern_shape = apply_linear_pattern(
                target_shape,
                action.direction,
                action.count,
                action.spacing,
                action.include_original
            )
            
            # Handle pattern based on geometry type - follow Transform pattern
            if action.target.startswith("s") and ":" not in action.target:
                # Patterning a solid - replace target solid with pattern compound
                target_solid_id = action.target
                
                # Extract faces from pattern compound
                from OCC.Core.TopExp import TopExp_Explorer
                from OCC.Core.TopAbs import TopAbs_FACE
                from OCC.Core.TopoDS import topods
                exp = TopExp_Explorer(pattern_shape, TopAbs_FACE)
                faces_full = []
                while exp.More():
                    faces_full.append(topods.Face(exp.Current()))
                    exp.Next()
                
                # Sorted edges and faces for the pattern
                edges_sorted = get_edge_dict_for_solid(target_solid_id, pattern_shape)
                faces_sorted = get_face_dict_for_solid(target_solid_id, pattern_shape, edges_sorted)
                
                # Bounding box of the pattern
                xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(pattern_shape)
                
                # Update the existing solid with pattern compound
                updated_solid = Solid(
                    id=target_solid_id,
                    faces=list(faces_sorted.values()),
                    bbox_min=(xmin, ymin, zmin),
                    bbox_max=(xmax, ymax, zmax),
                    shape=pattern_shape,
                    faces_full=faces_full
                )
                
                self.solid_index[target_solid_id] = updated_solid
                self.shape_history["solids"][target_solid_id] = pattern_shape
                
                # Update the solid in state.solids list
                for i, solid in enumerate(self.state.solids):
                    if solid.id == target_solid_id:
                        self.state.solids[i] = updated_solid
                        break
                
                # Update active_solids: remove old solid and add new pattern solids
                # The pattern replaces the target solid, so tracking remains the same
                # (target_solid_id is still active, just with updated shape)
                
                # Update edges for the pattern solid
                new_edges = self.list_edges(solid_id=target_solid_id)
                self.state.edges.update(new_edges)
                
                # Build complete scene with all active solids
                self.current_shape = self._build_current_scene_shape()
                self.current_solid_id = target_solid_id
                
            elif action.target.startswith("f"):
                # Patterning a face - replace target face with pattern compound
                target_face_id = action.target
                
                # Update the existing face with pattern compound
                face_data = Face(
                    id=target_face_id,
                    edges=[],  # Pattern faces don't have individual edges tracked
                    centroid=(0, 0, 0),  # Could calculate proper centroid if needed
                    shape=pattern_shape
                )
                self.state.faces[target_face_id] = face_data
                
                self.current_shape = pattern_shape
                
            else:
                # For other geometry types, just update current shape
                self.current_shape = pattern_shape
            
            if self.viz:
                self.renderer.clear()
            
            # Return the complete scene, not just the pattern
            return self.current_shape, None

        elif isinstance(action, CircularPattern):
            
            # Get the target shape to pattern
            target_shape = get_shape_from_reference(action.target, self.solid_index, self.state)
            
            # Determine axis direction
            if action.axis == "x":
                axis_direction = (1.0, 0.0, 0.0)
            elif action.axis == "y":
                axis_direction = (0.0, 1.0, 0.0)
            elif action.axis == "z":
                axis_direction = (0.0, 0.0, 1.0)
            else:
                axis_direction = action.axis_direction
    
            # Apply circular pattern
            pattern_shape = apply_circular_pattern(
                target_shape,
                action.center_point,
                axis_direction,
                action.angle,
                action.count,
                action.include_original
            )            
            # Handle pattern based on geometry type - follow Transform pattern
            if action.target.startswith("s") and ":" not in action.target:
                # Patterning a solid - replace target solid with pattern compound
                target_solid_id = action.target
                
                # Extract faces from pattern compound
                from OCC.Core.TopExp import TopExp_Explorer
                from OCC.Core.TopAbs import TopAbs_FACE
                from OCC.Core.TopoDS import topods
                exp = TopExp_Explorer(pattern_shape, TopAbs_FACE)
                faces_full = []
                while exp.More():
                    faces_full.append(topods.Face(exp.Current()))
                    exp.Next()
                
                # Sorted edges and faces for the pattern
                edges_sorted = get_edge_dict_for_solid(target_solid_id, pattern_shape)
                faces_sorted = get_face_dict_for_solid(target_solid_id, pattern_shape, edges_sorted)
                
                # Bounding box of the pattern
                xmin, ymin, zmin, xmax, ymax, zmax = compute_bbox(pattern_shape)
                
                # Update the existing solid with pattern compound
                updated_solid = Solid(
                    id=target_solid_id,
                    faces=list(faces_sorted.values()),
                    bbox_min=(xmin, ymin, zmin),
                    bbox_max=(xmax, ymax, zmax),
                    shape=pattern_shape,
                    faces_full=faces_full
                )
                
                self.solid_index[target_solid_id] = updated_solid
                self.shape_history["solids"][target_solid_id] = pattern_shape
                
                # Update the solid in state.solids list
                for i, solid in enumerate(self.state.solids):
                    if solid.id == target_solid_id:
                        self.state.solids[i] = updated_solid
                        break
                
                # Update active_solids: remove old solid and add new pattern solids  
                # The pattern replaces the target solid, so tracking remains the same
                # (target_solid_id is still active, just with updated shape)
                
                # Update edges for the pattern solid
                new_edges = self.list_edges(solid_id=target_solid_id)
                self.state.edges.update(new_edges)
                
                # Build complete scene with all active solids
                self.current_shape = self._build_current_scene_shape()
                self.current_solid_id = target_solid_id
                
            elif action.target.startswith("f"):
                # Patterning a face - replace target face with pattern compound
                target_face_id = action.target
                
                # Update the existing face with pattern compound
                face_data = Face(
                    id=target_face_id,
                    edges=[],  # Pattern faces don't have individual edges tracked
                    centroid=(0, 0, 0),  # Could calculate proper centroid if needed
                    shape=pattern_shape
                )
                self.state.faces[target_face_id] = face_data
                
                self.current_shape = pattern_shape
                
            else:
                # For other geometry types, just update current shape
                self.current_shape = pattern_shape
            
            if self.viz:
                self.renderer.clear()
             # Return the complete scene, not just the pattern
            return self.current_shape, None

        elif isinstance(action, Fillet2D):
            # Find the two target edges in the current sketch by ID, using state.edges
            ed1 = self.state.edges.get(action.edge1)
            ed2 = self.state.edges.get(action.edge2)
            if ed1 is None or ed2 is None:
                raise ValueError(f"Edge(s) {action.edge1}, {action.edge2} not found in state.edges.")
            plane = get_current_plane()  # Always pass gp_Ax3
            fillet_edge, trimmed_ed1, trimmed_ed2 = apply_fillet2d(ed1.shape, ed2.shape, action.radius, plane)

            # Overwrite the original edge entries in state.edges with the trimmed versions
            trimmed_ed1_vertices = get_edge_vertices(trimmed_ed1)
            trimmed_ed2_vertices = get_edge_vertices(trimmed_ed2)
            fillet_edge_vertices = get_edge_vertices(fillet_edge)
            
            self.state.edges[action.edge1] = Edge(id=action.edge1, vertices=trimmed_ed1_vertices, shape=trimmed_ed1)
            self.state.edges[action.edge2] = Edge(id=action.edge2, vertices=trimmed_ed2_vertices, shape=trimmed_ed2)

            # Add the fillet edge as a new entry
            eid = f"e{self.edge_count}"
            self.edge_count += 1
            self.state.edges[eid] = Edge(id=eid, vertices=fillet_edge_vertices, shape=fillet_edge)
            
            # Track the new fillet edge as active
            self.active_edge_ids.add(eid)

            # Update current_wire_edges: remove the two originals, insert trimmed1, fillet, trimmed2 in correct order
            idx1 = self.current_wire_edges.index(ed1.shape)
            idx2 = self.current_wire_edges.index(ed2.shape)
            if idx2 < idx1:
                idx1, idx2 = idx2, idx1
                trimmed_ed1, trimmed_ed2 = trimmed_ed2, trimmed_ed1
            # Remove higher index first
            for idx in sorted([idx1, idx2], reverse=True):
                del self.current_wire_edges[idx]
            self.current_wire_edges.insert(idx1, trimmed_ed1)
            self.current_wire_edges.insert(idx1 + 1, fillet_edge)
            self.current_wire_edges.insert(idx1 + 2, trimmed_ed2)

            # Also update the global _sketch_edges to stay in sync
            from .geometry.sketch_operations import sync_sketch_edges
            sync_sketch_edges(self.current_wire_edges)

            return fillet_edge, None

        elif isinstance(action, Chamfer2D):
            # Find the two target edges in the current sketch by ID, using state.edges
            ed1 = self.state.edges.get(action.edge1)
            ed2 = self.state.edges.get(action.edge2)
            if ed1 is None or ed2 is None:
                raise ValueError(f"Edge(s) {action.edge1}, {action.edge2} not found in state.edges.")
            plane = get_current_plane()  # Always pass gp_Ax3
            chamfer_edge, trimmed_ed1, trimmed_ed2 = apply_chamfer2d(ed1.shape, ed2.shape, action.distance, plane)

            # Overwrite the original edge entries in state.edges with the trimmed versions
            trimmed_ed1_vertices = get_edge_vertices(trimmed_ed1)
            trimmed_ed2_vertices = get_edge_vertices(trimmed_ed2)
            chamfer_edge_vertices = get_edge_vertices(chamfer_edge)
            
            self.state.edges[action.edge1] = Edge(id=action.edge1, vertices=trimmed_ed1_vertices, shape=trimmed_ed1)
            self.state.edges[action.edge2] = Edge(id=action.edge2, vertices=trimmed_ed2_vertices, shape=trimmed_ed2)

            # Add the chamfer edge as a new entry
            eid = f"e{self.edge_count}"
            self.edge_count += 1
            self.state.edges[eid] = Edge(id=eid, vertices=chamfer_edge_vertices, shape=chamfer_edge)
            
            # Track the new chamfer edge as active
            self.active_edge_ids.add(eid)

            # Update current_wire_edges: remove the two originals, insert trimmed1, chamfer, trimmed2 in correct order
            idx1 = self.current_wire_edges.index(ed1.shape)
            idx2 = self.current_wire_edges.index(ed2.shape)
            if idx2 < idx1:
                idx1, idx2 = idx2, idx1
                trimmed_ed1, trimmed_ed2 = trimmed_ed2, trimmed_ed1
            # Remove higher index first
            for idx in sorted([idx1, idx2], reverse=True):
                del self.current_wire_edges[idx]
            self.current_wire_edges.insert(idx1, trimmed_ed1)
            self.current_wire_edges.insert(idx1 + 1, chamfer_edge)
            self.current_wire_edges.insert(idx1 + 2, trimmed_ed2)

            # Also update the global _sketch_edges to stay in sync
            from .geometry.sketch_operations import sync_sketch_edges
            sync_sketch_edges(self.current_wire_edges)

            return chamfer_edge, None
        else:
            raise ValueError(f"Unknown action: {action}")

    def _compute_reward(self):
        return 0

    def _check_done(self):
        return False

    # def export(self, type="stl", filename="output"):
    #     from OCC.Extend.DataExchange import write_stl_file, write_step_file

    #     if self.current_shape is None:
    #         print("[WARN] No shape to export.")
    #         return

    #     if type == "stl":
    #         write_stl_file(self.current_shape, f"{filename}.stl")
    #         print("[INFO] STL file exported:", f"{filename}.stl")
    #     elif type == "step":
    #         write_step_file(self.current_shape, f"{filename}.step")
    #         print("[INFO] STEP file exported:", f"{filename}.step")
    #     else:
    #         print(f"[ERROR] Unsupported export type: {type}")

    def export(self, type="stl", filename="output", linear_deflection=0.001, angular_deflection=0.05):
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Extend.DataExchange import write_stl_file, write_step_file

        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)

        for solid in self.state.solids:
            builder.Add(compound, solid.shape)

        self.current_shape = compound

        if self.current_shape is None:
            print("[WARN] No shape to export.")
            return

        # Increase mesh resolution BEFORE exporting
        BRepMesh_IncrementalMesh(self.current_shape, linear_deflection, False, angular_deflection, True)

        if type == "stl":
            write_stl_file(self.current_shape, f"{filename}.stl")
            print("[INFO] STL file exported:", f"{filename}.stl")
        elif type == "step":
            write_step_file(self.current_shape, f"{filename}.step")
            print("[INFO] STEP file exported:", f"{filename}.step")
        else:
            print(f"[ERROR] Unsupported export type: {type}")

    
    def _build_current_scene_shape(self):
        """
        Build a compound shape containing all active solids in the scene.
        Uses the active geometry tracking system.
        """
        active_shapes = self.get_active_shapes()
        if not active_shapes:
            return None
        
        # Extract all individual solids from active_shapes
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Iterator
        from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND
        
        individual_solids = []
        
        for i, shape in enumerate(active_shapes):
            if shape.ShapeType() == TopAbs_SOLID:
                individual_solids.append(shape)
            elif shape.ShapeType() == TopAbs_COMPOUND:
                def extract_solids_from_compound(compound_shape):
                    iterator = TopoDS_Iterator(compound_shape)
                    while iterator.More():
                        child_shape = iterator.Value()
                        if child_shape.ShapeType() == TopAbs_SOLID:
                            individual_solids.append(child_shape)
                        elif child_shape.ShapeType() == TopAbs_COMPOUND:
                            extract_solids_from_compound(child_shape)
                        iterator.Next()
                
                extract_solids_from_compound(shape)
            
        # print(f"DEBUG: Extracted {len(individual_solids)} individual solids from {len(self.active_solids)} active shapes")
        # print(f"DEBUG: Building compound with {len(individual_solids)} solids")
            
        if len(individual_solids) == 0:
            return None
        elif len(individual_solids) == 1:
            return individual_solids[0]
        else:
            # Create compound containing all individual solids
            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            
            for solid in individual_solids:
                builder.Add(compound, solid)
            
            # Verify the compound was built correctly
            from OCC.Core.TopExp import TopExp_Explorer
            exp = TopExp_Explorer(compound, TopAbs_SOLID)
            verification_count = 0
            while exp.More():
                verification_count += 1
                exp.Next()
            # print(f"DEBUG: Built compound contains {verification_count} solids (expected {len(individual_solids)})")
                
            return compound
    
    def _add_solid_to_scene(self, solid_obj):
        """
        Add a solid to both the state and active geometry tracking.
        Maintains consistency between the two representations.
        """
        self.state.solids.append(solid_obj)
        self.solid_index[solid_obj.id] = solid_obj
        
        # Add the solid to active geometry tracking
        self.active_solid_ids.add(solid_obj.id)
    
    def get_active_shapes(self):
        """Get the shapes of all currently active geometry"""
        active_shapes = []
        
        # Add active solids
        for solid_id in self.active_solid_ids:
            if solid_id in self.solid_index:
                active_shapes.append(self.solid_index[solid_id].shape)
        
        # Add active faces
        for face_id in self.active_face_ids:
            if face_id in self.state.faces:
                active_shapes.append(self.state.faces[face_id].shape)
        
        # Add active edges
        for edge_id in self.active_edge_ids:
            if edge_id in self.state.edges:
                active_shapes.append(self.state.edges[edge_id].shape)
        
        # Add active wires (if we track them)
        # for wire_id in self.active_wire_ids:
        #     if wire_id in self.state.wires:
        #         active_shapes.append(self.state.wires[wire_id].shape)
        
        return active_shapes

    def get_active_geometry(self):
        """Get all currently active geometry objects (not replaced by newer versions)"""
        active_geometry = []
        
        # Add active solids
        for solid_id in self.active_solid_ids:
            if solid_id in self.solid_index:
                active_geometry.append(self.solid_index[solid_id])
        
        # Add active faces
        for face_id in self.active_face_ids:
            if face_id in self.state.faces:
                active_geometry.append(self.state.faces[face_id])
        
        # Add active edges
        for edge_id in self.active_edge_ids:
            if edge_id in self.state.edges:
                active_geometry.append(self.state.edges[edge_id])
        
        # Add active wires
        for wire_id in self.active_wire_ids:
            if wire_id in self.state.wires:
                active_geometry.append(self.state.wires[wire_id])
        
        return active_geometry

    def set_renderer_visibility(self, **kwargs):
        """
        Set visibility options for the renderer
        
        Args:
            show_solids: Show/hide solid objects
            show_faces: Show/hide face objects
            show_edges: Show/hide edge objects
            show_wires: Show/hide wire objects (sketch paths)
            show_points: Show/hide vertices/points from geometry
            show_action_points: Show/hide points from the last action
            face_transparency: Transparency for faces (0.0 = opaque, 1.0 = fully transparent)
        """
        if self.viz and self.renderer:
            self.renderer.set_visibility(**kwargs)

    def get_renderer_visibility(self):
        """Get current renderer visibility settings"""
        if self.viz and self.renderer:
            return self.renderer.get_visibility()
        return {}

    def show_only_solids(self):
        """Show only solid objects in the renderer"""
        if self.viz and self.renderer:
            self.renderer.show_only_solids()

    def show_only_sketches(self):
        """Show only sketch elements (edges, wires, points) in the renderer"""
        if self.viz and self.renderer:
            self.renderer.show_only_sketches()

    def show_everything(self):
        """Show all geometry types in the renderer"""
        if self.viz and self.renderer:
            self.renderer.show_everything()

    def hide_everything(self):
        """Hide all geometry types in the renderer"""
        if self.viz and self.renderer:
            self.renderer.hide_everything()

    def show_coordinate_axes(self, length=100.0, axis_thickness=2.0):
        """Display coordinate axes at the origin"""
        if self.viz and self.renderer:
            self.renderer.display_coordinate_axes(length=length, thickness=axis_thickness)

    def hide_coordinate_axes(self):
        """Hide coordinate axes"""
        if self.viz and self.renderer:
            self.renderer.hide_coordinate_axes()

    def get_selected_entity_ids(self):
        """Return currently selected entity IDs if inspector selection manager is attached.
        Safe no-op if inspector not in use.
        """
        sel_mgr = getattr(self, 'selection_manager', None)
        if sel_mgr and hasattr(sel_mgr, 'get_selected_ids'):
            try:
                return sel_mgr.get_selected_ids()
            except Exception:
                return []
        return []
