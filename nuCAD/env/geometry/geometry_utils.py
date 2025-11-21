"""
Core geometry utilities for nuCAD.

This module contains utility functions for geometry operations that are used 
across multiple modules.
"""

from typing import Tuple, List, Dict, Optional, TYPE_CHECKING
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Edge, TopoDS_Wire
from OCC.Core.gp import gp_Ax3, gp_Pnt, gp_Dir

if TYPE_CHECKING:
    from ..shapes import Solid
    from ..base_env import CADState


# ...existing code...
def get_face_data(on_solid_face: Optional[str], origin: Tuple[float, float, float], 
                  normal: Tuple[float, float, float], 
                  solid_index: Dict[str, "Solid"]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Get face data for sketch placement.
    If on_solid_face is provided, pick the point on the face where the normal line
    passes through the world origin (0, 0, 0). For planar faces, use the underlying
    unbounded plane; otherwise project onto the surface.
    
    IMPORTANT: For cap faces (top/bottom of extrusions), this function automatically
    flips the normal to point outward from the solid if it's pointing inward.
    """
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib
    from OCC.Core.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCC.Core.GeomLProp import GeomLProp_SLProps
    from OCC.Core.GeomAdaptor import GeomAdaptor_Surface
    from OCC.Core.GeomAbs import GeomAbs_Plane
    from OCC.Core.gp import gp_Pnt, gp_Vec

    if on_solid_face is not None:
        solid_id, face_idx = on_solid_face.split(":")
        face_idx = int(face_idx)
        solid = solid_index[solid_id]
        face = solid.faces_full[face_idx]

        # underlying surface
        surf = BRep_Tool.Surface(face)
        adaptor = GeomAdaptor_Surface(surf)
        origin_world = gp_Pnt(0.0, 0.0, 0.0)

        if adaptor.GetType() == GeomAbs_Plane:
            # Project onto the infinite plane so trimming doesn't affect the result
            pln = adaptor.Plane()  # gp_Pln
            n_dir = pln.Axis().Direction()  # unit normal
            Q = pln.Location()              # any point on plane

            # P = O - n * ((O - Q) · n)
            d = gp_Vec(Q, origin_world).Dot(gp_Vec(n_dir))
            proj = gp_Pnt(origin_world.X(), origin_world.Y(), origin_world.Z())
            proj.Translate(gp_Vec(n_dir).Multiplied(-d))

            origin = (proj.X(), proj.Y(), proj.Z())
            normal_vec = (n_dir.X(), n_dir.Y(), n_dir.Z())

            # Apply face orientation to get the outward-pointing normal
            # OpenCASCADE faces have FORWARD or REVERSED orientation
            # REVERSED means we need to flip the underlying surface normal
            from OCC.Core.TopAbs import TopAbs_REVERSED
            
            if face.Orientation() == TopAbs_REVERSED:
                # Face is reversed in the solid - flip the normal to point outward
                normal_vec = (-normal_vec[0], -normal_vec[1], -normal_vec[2])
            
            normal = normal_vec

        else:
            # Non-planar: closest point to origin; at that point, O-P is along the surface normal
            projector = GeomAPI_ProjectPointOnSurf(origin_world, surf)
            u, v = projector.LowerDistanceParameters()
            props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
            n = props.Normal()
            p = projector.NearestPoint()

            origin = (p.X(), p.Y(), p.Z())
            normal = (n.X(), n.Y(), n.Z())
    else:
        origin = origin
        normal = normal

    return origin, normal
# ...existing code...


def get_faces_from_references(face_refs: List[str], solid_index: Dict[str, "Solid"]) -> List[TopoDS_Face]:
    """
    Parse face references like ["s0:2", "s0:5"] and return the corresponding TopoDS_Face objects.
    
    Args:
        face_refs: List of face reference strings in format "solid_id:face_index"
        solid_index: Dictionary mapping solid IDs to Solid objects
        
    Returns:
        List of TopoDS_Face objects
    """
    faces = []
    for face_ref in face_refs:
        try:
            solid_id, face_idx = face_ref.split(":")
            face_idx = int(face_idx)
            solid = solid_index[solid_id]
            if face_idx >= len(solid.faces_full):
                raise IndexError(f"Face index {face_idx} out of range for solid {solid_id}")
            faces.append(solid.faces_full[face_idx])
        except (ValueError, KeyError, IndexError) as e:
            raise ValueError(f"Invalid face reference '{face_ref}': {e}")
    
    return faces


def get_shape_from_reference(target_ref: str, solid_index: Dict[str, "Solid"], 
                           state: "CADState") -> TopoDS_Shape:
    """
    Parse geometry reference and return the corresponding TopoDS_Shape.
    
    Args:
        target_ref: Reference string like "s0", "f0", "w0", "s0:2" (face), etc.
        solid_index: Dictionary mapping solid IDs to Solid objects
        state: CAD state containing faces, wires, etc.
        
    Returns:
        TopoDS_Shape object
    """
    # Handle face references like "s0:2"
    if ":" in target_ref:
        solid_id, face_idx = target_ref.split(":")
        face_idx = int(face_idx)
        if solid_id not in solid_index:
            raise ValueError(f"Solid '{solid_id}' not found")
        solid = solid_index[solid_id]
        if face_idx >= len(solid.faces_full):
            raise IndexError(f"Face index {face_idx} out of range for solid {solid_id}")
        return solid.faces_full[face_idx]
    
    # Handle solid references like "s0"
    elif target_ref.startswith("s"):
        if target_ref not in solid_index:
            raise ValueError(f"Solid '{target_ref}' not found")
        return solid_index[target_ref].shape
    
    # Handle face references like "f0"
    elif target_ref.startswith("f"):
        if target_ref not in state.faces:
            raise ValueError(f"Face '{target_ref}' not found")
        face_entry = state.faces[target_ref]
        # Support both dataclass Face and legacy dict storage
        if hasattr(face_entry, "shape"):
            return face_entry.shape
        return face_entry["shape"]
    
    # Handle wire references like "w0"
    elif target_ref.startswith("w"):
        if target_ref not in state.wires:
            raise ValueError(f"Wire '{target_ref}' not found")
        wire_entry = state.wires[target_ref]
        if hasattr(wire_entry, "shape"):
            return wire_entry.shape
        return wire_entry["shape"]
    
    # Handle edge references like "e0"
    elif target_ref.startswith("e"):
        if target_ref not in state.edges:
            raise ValueError(f"Edge '{target_ref}' not found")
        edge_entry = state.edges[target_ref]
        if hasattr(edge_entry, "shape"):
            return edge_entry.shape
        # Fallback to dict style if present
        return edge_entry.get("shape") or edge_entry.get("topo_elem")
    
    else:
        raise ValueError(f"Unknown target reference format: '{target_ref}'")


def create_compound_shape(shapes: List[TopoDS_Shape]) -> TopoDS_Shape:
    """
    Create a compound shape from a list of shapes.
    
    Args:
        shapes: List of TopoDS_Shape objects to combine
        
    Returns:
        TopoDS_Compound containing all input shapes
    """
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.TopoDS import TopoDS_Compound
    
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    
    for shape in shapes:
        builder.Add(compound, shape)
    
    return compound
