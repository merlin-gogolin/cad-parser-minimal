"""
Solid operations module for nuCAD.

This module provides all solid-related operations including:
- Extrusion operations
- Boolean operations (union, intersection, subtraction)
- Advanced solid creation (revolve, loft, sweep)
"""

from typing import Tuple, List, Dict, Optional
import math

# Geometry primitives
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax3

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Edge, TopoDS_Wire
from OCC.Core.TopAbs import TopAbs_FACE

# Solid builders
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_ThruSections, BRepOffsetAPI_MakePipe

# Boolean operations
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common

# Shape utilities
from OCC.Core.BRepTools import breptools_OuterWire
from OCC.Core.BRep import BRep_Tool

# Forward declaration for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..shapes import Solid


def extrude(shape: TopoDS_Shape, height: float) -> TopoDS_Shape:
    """
    Extrude a shape along its normal direction.
    
    Args:
        shape: The shape to extrude
        height: The height of extrusion
        
    Returns:
        The extruded solid shape
    """
    from .sketch_operations import get_current_plane
    current_plane = get_current_plane()
    if current_plane is None:
        raise RuntimeError("No active sketch plane.")

    normal_dir = current_plane.Direction()
    vec = gp_Vec(normal_dir.X(), normal_dir.Y(), normal_dir.Z()) * height
    return BRepPrimAPI_MakePrism(shape, vec).Shape()


def extrude_all_faces(extrude_faces: List[str], solids: List["Solid"],
                      all_faces: Dict[str, Dict], 
                      height: float) -> List[TopoDS_Shape]:
    """
    Extrude multiple faces by their reference strings.
    
    Args:
        extrude_faces: List of face reference strings
        solids: List of solid objects
        all_faces: Dictionary of face data
        height: Extrusion height
        
    Returns:
        List of extruded solid shapes
    """
    from .face_operations import get_faces_from_references
    
    # Build solid index
    solid_index = {f"s{i}": solid for i, solid in enumerate(solids)}
    
    # Get faces to extrude
    faces_to_extrude = get_faces_from_references(extrude_faces, solid_index)
    
    extruded_shapes = []
    for face in faces_to_extrude:
        # Get the face normal for extrusion direction
        # Use the first edge to determine direction
        wire = breptools_OuterWire(face)
        normal_vec = gp_Vec(0, 0, 1)  # Default to Z direction
        
        # Create extrusion vector
        extrusion_vec = normal_vec * height
        extruded_shape = BRepPrimAPI_MakePrism(face, extrusion_vec).Shape()
        extruded_shapes.append(extruded_shape)
    
    return extruded_shapes


def boolean_op(shape1, shape2, op_type: str) -> Tuple[TopoDS_Shape, List[TopoDS_Face]]:
    """
    Perform boolean operations between two shapes.
    
    Args:
        shape1: First shape
        shape2: Second shape
        op_type: Type of boolean operation ('union', 'intersection', 'subtraction')
        
    Returns:
        Tuple of (resulting_shape, list_of_faces)
    """
    # Normalize operation type to handle user-friendly names
    op_type = op_type.lower().strip()
    
    # Map user-friendly names to technical names
    op_mapping = {
        'union': 'fuse',
        'intersection': 'common', 
        'subtraction': 'cut',
        'subtract': 'cut',
        'difference': 'cut',
        # Technical names (for backward compatibility)
        'fuse': 'fuse',
        'common': 'common',
        'cut': 'cut'
    }
    
    if op_type not in op_mapping:
        valid_ops = list(op_mapping.keys())
        raise ValueError(f"Invalid boolean operation: '{op_type}'. Valid operations: {valid_ops}")
    
    normalized_op = op_mapping[op_type]
    
    if normalized_op == "fuse":
        result = BRepAlgoAPI_Fuse(shape1, shape2).Shape()
    elif normalized_op == "cut":
        result = BRepAlgoAPI_Cut(shape1, shape2).Shape()
    elif normalized_op == "common":
        result = BRepAlgoAPI_Common(shape1, shape2).Shape()
    else:
        raise ValueError(f"Unknown normalized operation: {normalized_op}")
    
    # Extract faces from result (simplified - would need proper face extraction)
    faces = []
    return result, faces


def apply_revolve(
    face: TopoDS_Face,
    axis_point: Tuple[float, float, float],
    axis_direction: Tuple[float, float, float],
    angle: float
) -> TopoDS_Shape:
    """
    Create a solid by revolving a face around an axis.
    
    Args:
        face: The face to revolve
        axis_point: Point on the revolution axis
        axis_direction: Direction of the revolution axis
        angle: Angle of revolution in radians
        
    Returns:
        The revolved solid
    """
    axis_pnt = gp_Pnt(*axis_point)
    axis_dir = gp_Dir(*axis_direction)
    axis = gp_Ax1(axis_pnt, axis_dir)
    
    revolver = BRepPrimAPI_MakeRevol(face, axis, angle)
    return revolver.Shape()


def apply_loft(
    face_shapes: List[TopoDS_Face],
    solid: bool = True,
    ruled: bool = False,
    smooth: bool = True
) -> TopoDS_Shape:
    """
    Loft between a list of faces.
    
    Args:
        face_shapes: List of faces to loft between
        solid: Whether to create a solid (True) or surface (False)
        ruled: Whether to create ruled surfaces
        smooth: Whether to create smooth transitions
        
    Returns:
        The lofted shape
    """
    if len(face_shapes) < 2:
        raise ValueError("At least two faces are required for loft.")

    builder = BRepOffsetAPI_ThruSections(solid, ruled, smooth)

    for face in face_shapes:
        builder.AddWire(breptools_OuterWire(face))

    builder.Build()
    return builder.Shape()


def apply_sweep(
    profile: TopoDS_Shape,
    path: TopoDS_Wire,
    solid: bool = True
) -> TopoDS_Shape:
    """
    Create a shape by sweeping a profile along a path.
    
    Args:
        profile: The profile shape to sweep
        path: The path wire to sweep along
        solid: Whether to create a solid (True) or surface (False)
        
    Returns:
        The swept shape
    """
    pipe = BRepOffsetAPI_MakePipe(path, profile)
    
    if solid:
        # Return the solid shape (default behavior)
        return pipe.Shape()
    else:
        # For surface/shell, we need to create a surface from the profile outline
        # If the profile is a face, we use its outer wire instead
        if profile.ShapeType() == TopAbs_FACE:
            from OCC.Core.BRepTools import breptools_OuterWire
            from OCC.Core.TopoDS import topods_Face
            face = topods_Face(profile)
            outer_wire = breptools_OuterWire(face)
            surface_pipe = BRepOffsetAPI_MakePipe(path, outer_wire)
            return surface_pipe.Shape()
        else:
            # If profile is already a wire/edge, use it directly
            return pipe.Shape()
