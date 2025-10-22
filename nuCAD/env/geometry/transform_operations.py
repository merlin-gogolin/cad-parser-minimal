"""
Transform operations module for nuCAD.

This module provides all transformation operations including:
- Shell operations
- Mirror operations
- General transform operations
"""

import math
from typing import Tuple, List, Dict, Optional

# Geometry primitives
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Ax3, gp_Pln, gp_Trsf, gp_GTrsf

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Edge, topods
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer

# Transform operations
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_GTransform
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid


def shell(shape: TopoDS_Shape, faces_to_remove: List[TopoDS_Face], 
          thickness: float, tolerance: float = 1e-3) -> TopoDS_Shape:
    """
    Create a shell by removing faces and applying thickness.
    
    Args:
        shape: The shape to shell
        faces_to_remove: List of faces to remove
        thickness: Wall thickness
        tolerance: Tolerance for operation
        
    Returns:
        The shelled shape
    """
    from OCC.Core.TopTools import TopTools_ListOfShape
    
    # Convert list of faces to TopTools_ListOfShape for OpenCASCADE
    faces_list = TopTools_ListOfShape()
    for face in faces_to_remove:
        faces_list.Append(face)
    
    shell_builder = BRepOffsetAPI_MakeThickSolid()
    shell_builder.MakeThickSolidByJoin(shape, faces_list, thickness, tolerance)
    
    # Check if operation succeeded
    if not shell_builder.IsDone():
        raise RuntimeError("Shell operation failed - check geometry and parameters")
    
    return shell_builder.Shape()


def apply_shell(shape: TopoDS_Shape, faces_to_remove: List[TopoDS_Face], 
                thickness: float, inward: bool = True) -> Tuple[TopoDS_Shape, List[TopoDS_Face]]:
    """
    Apply shell operation to a shape.
    
    Args:
        shape: The shape to shell
        faces_to_remove: List of faces to remove
        thickness: Wall thickness
        inward: True for inward shelling, False for outward
        
    Returns:
        Tuple of (shelled_shape, list_of_faces)
    """
    # Apply thickness direction based on inward flag
    actual_thickness = thickness if inward else -thickness
    
    shelled_shape = shell(shape, faces_to_remove, actual_thickness)
    
    # Extract all faces from the result
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopoDS import topods
    exp = TopExp_Explorer(shelled_shape, TopAbs_FACE)
    faces = []
    while exp.More():
        faces.append(topods.Face(exp.Current()))
        exp.Next()
    
    return shelled_shape, faces


def mirror_plane(shape: TopoDS_Shape, plane_origin: Tuple[float, float, float], 
                 plane_normal: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Mirror a shape across a plane.
    
    Args:
        shape: The shape to mirror
        plane_origin: Point on the mirror plane
        plane_normal: Normal vector of the mirror plane
        
    Returns:
        The mirrored shape
    """
    origin = gp_Pnt(*plane_origin)
    normal = gp_Dir(*plane_normal)
    
    # Create a coordinate system for the mirror plane
    # gp_Ax2 needs origin and normal direction
    ax2 = gp_Ax2(origin, normal)
    
    mirror_transform = gp_Trsf()
    mirror_transform.SetMirror(ax2)
    
    transformer = BRepBuilderAPI_Transform(shape, mirror_transform)
    return transformer.Shape()


def apply_mirror_plane(shape: TopoDS_Shape, plane_origin: Tuple[float, float, float], 
                       plane_normal: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply mirror operation across a plane.
    
    Args:
        shape: The shape to mirror
        plane_origin: Point on the mirror plane
        plane_normal: Normal vector of the mirror plane
        
    Returns:
        The mirrored shape
    """
    return mirror_plane(shape, plane_origin, plane_normal)


def mirror_line(shape: TopoDS_Shape, line_point: Tuple[float, float, float],
                line_direction: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Mirror a shape across a line.
    
    Args:
        shape: The shape to mirror
        line_point: Point on the mirror line
        line_direction: Direction vector of the mirror line
        
    Returns:
        The mirrored shape
    """
    point = gp_Pnt(*line_point)
    direction = gp_Dir(*line_direction)
    axis = gp_Ax1(point, direction)
    
    mirror_transform = gp_Trsf()
    mirror_transform.SetMirror(axis)
    
    transformer = BRepBuilderAPI_Transform(shape, mirror_transform)
    return transformer.Shape()


def apply_mirror_line(shape: TopoDS_Shape, line_point: Tuple[float, float, float],
                      line_direction: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply mirror operation across a line.
    
    Args:
        shape: The shape to mirror
        line_point: Point on the mirror line
        line_direction: Direction vector of the mirror line
        
    Returns:
        The mirrored shape
    """
    return mirror_line(shape, line_point, line_direction)


def mirror_point(shape: TopoDS_Shape, point: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Mirror a shape across a point.
    
    Args:
        shape: The shape to mirror
        point: The mirror point
        
    Returns:
        The mirrored shape
    """
    mirror_point = gp_Pnt(*point)
    
    mirror_transform = gp_Trsf()
    mirror_transform.SetMirror(mirror_point)
    
    transformer = BRepBuilderAPI_Transform(shape, mirror_transform)
    return transformer.Shape()


def apply_mirror_point(shape: TopoDS_Shape, point: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply mirror operation across a point.
    
    Args:
        shape: The shape to mirror
        point: The mirror point
        
    Returns:
        The mirrored shape
    """
    return mirror_point(shape, point)


def translate(shape: TopoDS_Shape, vector: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Translate a shape by a vector.
    
    Args:
        shape: The shape to translate
        vector: Translation vector
        
    Returns:
        The translated shape
    """
    translation_vec = gp_Vec(*vector)
    transform = gp_Trsf()
    transform.SetTranslation(translation_vec)
    
    transformer = BRepBuilderAPI_Transform(shape, transform)
    return transformer.Shape()


def apply_translation_vector(shape: TopoDS_Shape, translation_vector: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply translation by vector.
    
    Args:
        shape: The shape to translate
        translation_vector: Translation vector
        
    Returns:
        The translated shape
    """
    return translate(shape, translation_vector)


def apply_translation_point_to_point(shape: TopoDS_Shape, from_point: Tuple[float, float, float], 
                                     to_point: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply translation from one point to another.
    
    Args:
        shape: The shape to translate
        from_point: Starting point
        to_point: Ending point
        
    Returns:
        The translated shape
    """
    from_pt = gp_Pnt(*from_point)
    to_pt = gp_Pnt(*to_point)
    translation_vec = gp_Vec(from_pt, to_pt)
    
    return translate(shape, (translation_vec.X(), translation_vec.Y(), translation_vec.Z()))


def apply_translation_distance_direction(shape: TopoDS_Shape, distance: float, 
                                       direction: Tuple[float, float, float]) -> TopoDS_Shape:
    """
    Apply translation by distance and direction.
    
    Args:
        shape: The shape to translate
        distance: Translation distance
        direction: Translation direction
        
    Returns:
        The translated shape
    """
    dir_vec = gp_Vec(*direction)
    dir_vec.Normalize()
    translation_vec = dir_vec * distance
    
    return translate(shape, (translation_vec.X(), translation_vec.Y(), translation_vec.Z()))


def rotate(shape: TopoDS_Shape, axis_point: Tuple[float, float, float],
           axis_direction: Tuple[float, float, float], angle: float) -> TopoDS_Shape:
    """
    Rotate a shape around an axis.
    
    Args:
        shape: The shape to rotate
        axis_point: Point on the rotation axis
        axis_direction: Direction of the rotation axis
        angle: Rotation angle in radians
        
    Returns:
        The rotated shape
    """
    point = gp_Pnt(*axis_point)
    direction = gp_Dir(*axis_direction)
    axis = gp_Ax1(point, direction)
    
    rotation_transform = gp_Trsf()
    rotation_transform.SetRotation(axis, angle)
    
    transformer = BRepBuilderAPI_Transform(shape, rotation_transform)
    return transformer.Shape()


def apply_rotation_axis(shape: TopoDS_Shape, axis_point: Tuple[float, float, float],
                        axis_direction: Tuple[float, float, float], angle: float) -> TopoDS_Shape:
    """
    Apply rotation around an axis.
    
    Args:
        shape: The shape to rotate
        axis_point: Point on the rotation axis
        axis_direction: Direction of the rotation axis
        angle: Rotation angle in radians
        
    Returns:
        The rotated shape
    """
    return rotate(shape, axis_point, axis_direction, angle)


def apply_rotation_center_2d(shape: TopoDS_Shape, center_point: Tuple[float, float, float],
                             plane_normal: Tuple[float, float, float], angle: float) -> TopoDS_Shape:
    """
    Apply 2D rotation around a center point.
    
    Args:
        shape: The shape to rotate
        center_point: Center of rotation
        plane_normal: Normal vector of the rotation plane
        angle: Rotation angle in degrees
        
    Returns:
        The rotated shape
    """
    # Rotation around the specified plane normal
    return rotate(shape, center_point, plane_normal, math.radians(angle))


def apply_combined_transform(shape: TopoDS_Shape, transforms: List[dict]) -> TopoDS_Shape:
    """
    Apply multiple transformations in sequence.
    
    Args:
        shape: The shape to transform
        transforms: List of transformation dictionaries
        
    Returns:
        The transformed shape
    """
    result = shape
    for transform in transforms:
        if transform['type'] == 'translate':
            result = translate(result, transform['vector'])
        elif transform['type'] == 'rotate':
            result = rotate(result, transform['axis_point'], transform['axis_direction'], transform['angle'])
        elif transform['type'] == 'mirror_plane':
            result = mirror_plane(result, transform['plane_origin'], transform['plane_normal'])
        elif transform['type'] == 'mirror_line':
            result = mirror_line(result, transform['line_point'], transform['line_direction'])
        elif transform['type'] == 'mirror_point':
            result = mirror_point(result, transform['point'])
        else:
            raise ValueError(f"Unknown transform type: {transform['type']}")
    
    return result
