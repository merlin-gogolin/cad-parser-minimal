"""
Boolean operations module for nuCAD.

This module provides all boolean operations including:
- Fuse (union) operations
- Cut (subtract) operations  
- Common (intersect) operations
"""

from typing import Tuple, List, Dict, Optional

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Solid, topods
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCC.Core.TopExp import TopExp_Explorer

# Boolean operations
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common


def fuse(shape1: TopoDS_Shape, shape2: TopoDS_Shape) -> TopoDS_Shape:
    """
    Fuse (union) two shapes.
    
    Args:
        shape1: First shape
        shape2: Second shape
        
    Returns:
        The fused shape
    """
    result = BRepAlgoAPI_Fuse(shape1, shape2).Shape()
    return result


def cut(shape1: TopoDS_Shape, shape2: TopoDS_Shape) -> TopoDS_Shape:
    """
    Cut (subtract) second shape from first shape.
    
    Args:
        shape1: Shape to cut from
        shape2: Shape to cut with
        
    Returns:
        The cut shape
    """
    result = BRepAlgoAPI_Cut(shape1, shape2).Shape()
    return result


def intersect(shape1: TopoDS_Shape, shape2: TopoDS_Shape) -> TopoDS_Shape:
    """
    Intersect two shapes.
    
    Args:
        shape1: First shape
        shape2: Second shape
        
    Returns:
        The intersection shape
    """
    result = BRepAlgoAPI_Common(shape1, shape2).Shape()
    return result


def boolean_op(shape1, shape2, op_type: str) -> Tuple[TopoDS_Shape, List[TopoDS_Face]]:
    """
    Perform boolean operation between two shapes.
    
    Args:
        shape1: First shape
        shape2: Second shape
        op_type: Type of boolean operation ('cut', 'fuse', 'common')
        
    Returns:
        Tuple of (result_shape, list_of_faces)
    """
    if shape1 is None or shape2 is None:
        raise ValueError("boolean_op: one or both input shapes are None")

    if hasattr(shape1, "IsNull") and shape1.IsNull():
        raise ValueError("boolean_op: shape1 is null/empty")
    if hasattr(shape2, "IsNull") and shape2.IsNull():
        raise ValueError("boolean_op: shape2 is null/empty")

    if op_type == "cut":
        result = BRepAlgoAPI_Cut(shape1, shape2).Shape()
    elif op_type == "fuse":
        result = BRepAlgoAPI_Fuse(shape1, shape2).Shape()
    elif op_type == "common":
        result = BRepAlgoAPI_Common(shape1, shape2).Shape()
    else:
        raise ValueError(f"Unknown Boolean type: {op_type}")

    # Collect faces from the entire result (works for solids and compounds)
    faces: List[TopoDS_Face] = []
    exp = TopExp_Explorer(result, TopAbs_FACE)
    while exp.More():
        faces.append(topods.Face(exp.Current()))
        exp.Next()

    return result, faces
