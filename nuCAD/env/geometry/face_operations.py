"""
Face operations module for nuCAD.

This module provides all face-related operations including:
- Face creation with optional cutting
- Face property extraction
- Face reference parsing
"""

from typing import Tuple, List, Dict, Optional
import math

# Geometry primitives
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Vertex, topods
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_VERTEX, TopAbs_IN
from OCC.Core.TopExp import TopExp_Explorer

# Shape builders
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut

# Shape analysis
from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepClass import BRepClass_FaceClassifier
from OCC.Core.ShapeAnalysis import ShapeAnalysis_Surface
from OCC.Core.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCC.Core.GeomLProp import GeomLProp_SLProps

# Bounding box utilities
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add

# Forward declaration for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..shapes import Solid


def make_face_with_optional_cut(wire_shapes: List[TopoDS_Shape], existing_faces: List[TopoDS_Shape], last_face_wire_index: int):
    """
    Given new wire(s), tries to cut into existing_faces if inside AND coplanar.
    Otherwise returns new face.
    
    Args:
        wire_shapes: List of wire shapes to create face from
        existing_faces: List of existing faces to potentially cut into
        
    Returns:
        Tuple of (resulting_shape, was_cut_applied)
    """

    if len(wire_shapes) > 1:
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.BRepGProp import brepgprop
        
        # Calculate wire lengths to determine outer boundary (longest wire)
        wire_lengths = []
        for wire in wire_shapes:
            props = GProp_GProps()
            brepgprop.LinearProperties(wire, props)
            wire_lengths.append((wire, props.Mass()))
        
        # Sort by length (descending) - longest wire is outer boundary
        wire_lengths.sort(key=lambda x: x[1], reverse=True)
        outer_wire = wire_lengths[0][0]
        inner_wires = [w[0] for w in wire_lengths[1:]]
        
        # Create face from outer wire
        outer_face = BRepBuilderAPI_MakeFace(outer_wire).Face()
        result_face = outer_face
        
        # Cut holes by subtracting faces created from inner wires
        for inner_wire in inner_wires:
            inner_face = BRepBuilderAPI_MakeFace(inner_wire).Face()
            result_face = BRepAlgoAPI_Cut(result_face, inner_face).Shape()
        
        return result_face, False

    new_face = BRepBuilderAPI_MakeFace(wire_shapes[0]).Face()

    def _get_first_face(shape):
        """Extract the first face from a shape."""
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        if exp.More():
            return topods.Face(exp.Current())
        return None

    def _new_inside_prev(prev_shape, new_face):
        """Check if new_face is inside prev_shape and coplanar."""
        prev_face = _get_first_face(prev_shape)
        if prev_face is None:
            return False

        # Check if one vertex of new_face lies inside prev_face
        vexp = TopExp_Explorer(new_face, TopAbs_VERTEX)
        if not vexp.More():
            return False
        v = topods.Vertex(vexp.Current())
        p = BRep_Tool.Pnt(v)

        # Get a vertex from prev_face to compare Z-level
        vexp_prev = TopExp_Explorer(prev_face, TopAbs_VERTEX)
        if not vexp_prev.More():
            return False
        p_prev = BRep_Tool.Pnt(topods.Vertex(vexp_prev.Current()))

        # Only cut if they lie on the same Z level (coplanar)
        # if abs(p.Z() - p_prev.Z()) > 1e-5:
        #     return False

        return BRepClass_FaceClassifier(prev_face, p, 1e-7, False, 1e-7).State() == TopAbs_IN
    
    if last_face_wire_index > 1:
        for prev_shape in existing_faces[-1:]:
            if _new_inside_prev(prev_shape, new_face):
                return BRepAlgoAPI_Cut(prev_shape, new_face).Shape(), True

    return new_face, False


def get_face_data(on_solid_face: Optional[str], origin: Tuple[float, float, float], 
                  normal: Tuple[float, float, float], 
                  solid_index: Dict[str, "Solid"]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Extract face data (origin and normal) from a solid face or use provided values.
    
    Args:
        on_solid_face: Optional face reference string like "s0:2"
        origin: Default origin coordinates
        normal: Default normal vector
        solid_index: Dictionary mapping solid IDs to Solid objects
        
    Returns:
        Tuple of (origin, normal) coordinates
    """
    if on_solid_face is not None:
        solid_id, face_idx = on_solid_face.split(":")
        face_idx = int(face_idx)
        solid = solid_index[solid_id]
        face = solid.faces_full[face_idx]

        # compute origin and normal
        surf = BRep_Tool.Surface(face)
        analyzer = ShapeAnalysis_Surface(surf)

        bbox = Bnd_Box()
        brepbndlib_Add(face, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        center = gp_Pnt((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)

        surf = BRep_Tool.Surface(face)
        projector = GeomAPI_ProjectPointOnSurf(center, surf)
        u, v = projector.LowerDistanceParameters()

        props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
        normal_vec = props.Normal()
        origin = (center.X(), center.Y(), center.Z())
        normal = (normal_vec.X(), normal_vec.Y(), normal_vec.Z())
    else:
        origin = origin
        normal = normal

    return origin, normal


def get_faces_from_references(face_refs: List[str], solid_index: Dict[str, "Solid"]) -> List[TopoDS_Face]:
    """
    Parse face references like ["s0:2", "s0:5"] and return the corresponding TopoDS_Face objects.
    
    Args:
        face_refs: List of face reference strings in format "solid_id:face_index"
        solid_index: Dictionary mapping solid IDs to Solid objects
        
    Returns:
        List of TopoDS_Face objects
        
    Raises:
        ValueError: If face reference is invalid or out of range
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
