"""
Edge operations module for nuCAD.

This module provides all edge-related operations including:
- Fillet operations
- Chamfer operations
"""

from typing import Tuple, List, Dict, Optional

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Face, topods
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer

# Edge modification operations
from OCC.Core.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
from OCC.Core.ChFi2d import ChFi2d_AnaFilletAlgo, ChFi2d_ChamferAPI
from OCC.Core.gp import gp_Pln


def apply_fillet(shape: TopoDS_Shape, edge: TopoDS_Shape, 
                 radius: float) -> Tuple[TopoDS_Shape, List[TopoDS_Face]]:
    """
    Apply fillet to an edge with specified radius.
    
    Args:
        shape: The shape to fillet
        edge: The edge to fillet
        radius: The fillet radius
        
    Returns:
        Tuple of (filleted_shape, list_of_faces)
    """
    mk_fillet = BRepFilletAPI_MakeFillet(shape)
    mk_fillet.Add(radius, edge)
    filleted_shape = mk_fillet.Shape()

    # Extract all faces
    exp = TopExp_Explorer(filleted_shape, TopAbs_FACE)
    faces = []
    while exp.More():
        faces.append(topods.Face(exp.Current()))
        exp.Next()

    return filleted_shape, faces


def apply_chamfer(shape: TopoDS_Shape, edge: TopoDS_Shape, 
                  distance: float) -> Tuple[TopoDS_Shape, List[TopoDS_Face]]:
    """
    Apply chamfer to an edge with specified distance.
    
    Args:
        shape: The shape to chamfer
        edge: The edge to chamfer
        distance: The chamfer distance
        
    Returns:
        Tuple of (chamfered_shape, list_of_faces)
    """
    mk_chamfer = BRepFilletAPI_MakeChamfer(shape)
    mk_chamfer.Add(distance, edge)
    chamfered_shape = mk_chamfer.Shape()

    # Extract all faces
    exp = TopExp_Explorer(chamfered_shape, TopAbs_FACE)
    faces = []
    while exp.More():
        faces.append(topods.Face(exp.Current()))
        exp.Next()

    return chamfered_shape, faces


def apply_fillet2d(ed1: TopoDS_Edge, ed2: TopoDS_Edge, radius: float, plane=None):
    """
    Create a 2D fillet between two edges on a plane using ChFi2d_AnaFilletAlgo.
    plane: can be gp_Ax3 or gp_Pln. If gp_Ax3, will convert to gp_Pln.
    Returns: (fillet_edge, trimmed_ed1, trimmed_ed2)
    """
    if plane is None:
        plane = gp_Pln()  # Default XY
    elif hasattr(plane, 'Location') and hasattr(plane, 'Direction'):
        # Convert gp_Ax3 to gp_Pln
        plane = gp_Pln(plane.Location(), plane.Direction())
    
    # Use the fillet algorithm
    fillet_algo = ChFi2d_AnaFilletAlgo()
    fillet_algo.Init(ed1, ed2, plane)
    fillet_algo.Perform(radius)
    fillet_edge = fillet_algo.Result(ed1, ed2)
    return fillet_edge, ed1, ed2


def apply_chamfer2d(ed1: TopoDS_Edge, ed2: TopoDS_Edge, distance: float, plane=None):
    """
    Create a 2D chamfer between two edges on a plane using ChFi2d_ChamferAPI.
    plane: can be gp_Ax3 or gp_Pln. If gp_Ax3, will convert to gp_Pln.
    Returns: (chamfer_edge, trimmed_ed1, trimmed_ed2)
    """
    if plane is None:
        plane = gp_Pln()  # Default XY
    elif hasattr(plane, 'Location') and hasattr(plane, 'Direction'):
        # Convert gp_Ax3 to gp_Pln
        plane = gp_Pln(plane.Location(), plane.Direction())
    
    # Use the chamfer algorithm
    chamfer_algo = ChFi2d_ChamferAPI()
    chamfer_algo.Init(ed1, ed2)
    chamfer_algo.Perform()
    chamfer_edge = chamfer_algo.Result(ed1, ed2, distance, distance)
    return chamfer_edge, ed1, ed2


