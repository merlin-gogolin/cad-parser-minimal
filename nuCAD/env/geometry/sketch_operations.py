"""
Sketch operations module for nuCAD.

This module provides all sketch-related operatio    # define transform from local sketch frame to global sketch frame
    trsf = gp_Trsf()
    trsf.SetTransformation(local_plane, _current_plane)
    
    local_pt = gp_Pnt(x, y, 0)
    global_pt = local_pt.Transformed(trsf)
    return global_pt.X(), global_pt.Y(), global_pt.Z()uding:
- Sketch plane management
- Basic geometry (lines, arcs, circles)
- Advanced curves (ellipses, splines, beziers)
- Profile closing operations
"""

from typing import Tuple, List, Dict, Optional, Union
import math

# Geometry primitives
from OCC.Core.gp import (
    gp_Pnt, gp_Circ, gp_Vec, gp_Ax2, gp_Elips, gp_Dir, gp_Ax3, gp_Trsf, gp_Ax1
)

# Geometry construction
from OCC.Core.GC import (
    GC_MakeArcOfCircle, GC_MakeCircle
)

# Basic shape builders
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
)

# Curve and surface utilities
from OCC.Core.TColgp import TColgp_Array1OfPnt
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline
from OCC.Core.Geom import Geom_BezierCurve

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape


# ----------------------------------------------------------------------
# Sketch-plane state
# ----------------------------------------------------------------------
_current_plane: Union[gp_Ax3, None] = None
_sketch_edges: List[TopoDS_Shape] = []
_uv_flip: Tuple[int, int] = (1, 1)  # per-sketch input sign adjustment (u, v)
_orient_policy: str = ''


def set_orientation_policy(policy: str):
    """Set orientation policy at runtime.

    Policies:
    - '': default behavior (no generalization; uses existing per-plane tweaks)
    - 'positive': ensure positive sketch inputs map to positive world along the dominant
                  axis of XDirection (for u) and YDirection (for v).
    """
    global _orient_policy
    _orient_policy = (policy or '').strip().lower()


def _dominant_sign(dir_obj: gp_Dir) -> int:
    """Return +1 if dominant component of direction is positive, else -1."""
    x, y, z = dir_obj.X(), dir_obj.Y(), dir_obj.Z()
    ax, ay, az = abs(x), abs(y), abs(z)
    if ax >= ay and ax >= az:
        return 1 if x >= 0 else -1
    if ay >= ax and ay >= az:
        return 1 if y >= 0 else -1
    return 1 if z >= 0 else -1


def _compute_positive_uv_flip(ax3: gp_Ax3) -> Tuple[int, int]:
    """Compute (u,v) input flips so that u and v map to positive world along their dominant axes.

    This does not change the frame; it only adjusts input signs to achieve a positive mapping
    for typical cardinal and near-cardinal orientations.
    """
    xdir = ax3.XDirection()
    ydir = ax3.YDirection()
    u_flip = 1 if _dominant_sign(xdir) >= 0 else -1
    v_flip = 1 if _dominant_sign(ydir) >= 0 else -1
    return (u_flip, v_flip)


def begin_sketch(origin=(0, 0, 0), normal=(0, 0, 1)):
    """
    Initialize a new sketch plane.
    
    Parameters:
        origin: (x, y, z) origin point of the sketch plane
        normal: (x, y, z) normal vector of the sketch plane
    """
    global _current_plane, _sketch_edges, _uv_flip
    _sketch_edges.clear()
    _uv_flip = (1, 1)

    origin = origin if isinstance(origin, tuple) and len(origin) == 3 else (0, 0, 0)
    z = gp_Dir(*normal)

    # Select reference axis for constructing X direction
    # Minimal fix (Option B): if normal is exactly +Y, use ref = -Z to ensure u->+X
    if normal == (0, 1, 0):
        ref = gp_Dir(0, 0, -1)
    else:
        if abs(z.Dot(gp_Dir(0, 0, 1))) < 0.9:
            ref = gp_Dir(0, 0, 1)
        else:
            ref = gp_Dir(0, 1, 0)

    # ---------- MERLIN ADDITION ----------
    if _orient_policy == 'positive':
        # Reverse the cross product order:
        x_vec = gp_Vec(z.Crossed(ref)).Normalized()
    else:
        x_vec = gp_Vec(ref.Crossed(z)).Normalized()  # back to original, keep in mind I changed the 
        # origin setting logic
        # y_vec = gp_Vec(z.Crossed(x_dir)).Normalized()
    # y_dir = gp_Dir(y_vec)
    x_dir = gp_Dir(x_vec)

    _current_plane = gp_Ax3(gp_Pnt(*origin), z, x_dir)

    # Minimal explicit orientation policy:
    # For +Y normal (Front), ensure positive u maps to +X while preserving v→+Z behavior
    # Current frame yields u→-X, v→+Z; flip u input to map positive sketch u to +X.
    # if normal == (0, 1, 0):
    #     _uv_flip = (1, -1)

    # ---------- MERLIN ADDITION ----------
    # Optional general orientation policy (enabled when NUCAD_ORIENT_POLICY=positive)
    if _orient_policy == 'positive':
        _uv_flip = _compute_positive_uv_flip(_current_plane)


def _to_global_3d(x: float, y: float) -> Tuple[float, float, float]:
    """
    Convert 2D sketch coordinates to 3D global coordinates.
    
    Parameters:
        x: X coordinate in sketch plane
        y: Y coordinate in sketch plane
        
    Returns:
        Tuple of (x, y, z) in global coordinates
    """
    if _current_plane is None:
        raise RuntimeError("No active sketch plane. Call begin_sketch() first.")
    
    # define local sketch frame: XY plane at origin
    local_plane = gp_Ax3()

    # define transform from local sketch frame to global sketch frame
    trsf = gp_Trsf()
    trsf.SetTransformation(_current_plane, local_plane)
    
    # Apply per-plane input flips so positive sketch values map to positive world axes
    ux = x * _uv_flip[0]
    uy = y * _uv_flip[1]
    local_pt = gp_Pnt(ux, uy, 0)
    global_pt = local_pt.Transformed(trsf)
    return global_pt.X(), global_pt.Y(), global_pt.Z()


# ----------------------------------------------------------------------
# Basic geometry operations
# ----------------------------------------------------------------------

def add_line(start: Tuple[float, float], end: Tuple[float, float]) -> TopoDS_Shape:
    """
    Add a line in current sketch; `start`, `end` are 2-D (x, y) on plane.
    
    Parameters:
        start: (x, y) start point in sketch coordinates
        end: (x, y) end point in sketch coordinates
        
    Returns:
        Edge shape representing the line
    """
    global _sketch_edges
    p1 = gp_Pnt(*_to_global_3d(*start))
    p2 = gp_Pnt(*_to_global_3d(*end))
    edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
    _sketch_edges.append(edge)
    return edge


def add_arc(*args, radius=None, center=None, start_angle=None, end_angle=None) -> TopoDS_Shape:
    """
    Supports two arc types:
    1. Three-point arc: add_arc(p1, p2, p3)
    2. Center-radius-angle arc: add_arc(center=(...), radius=..., start_angle=..., end_angle=...)

    Parameters:
        For three-point arc:
            p1, p2, p3: Three points defining the arc
        For center-radius-angle arc:
            center: (x, y) center point in sketch coordinates
            radius: Arc radius
            start_angle: Start angle in radians
            end_angle: End angle in radians

    Returns:
        Edge shape representing the arc
    """
    global _sketch_edges

    if len(args) == 3 and radius is None:
        # 3-point arc
        p1, p2, p3 = args
        gp1 = gp_Pnt(*_to_global_3d(*p1))
        gp2 = gp_Pnt(*_to_global_3d(*p2))
        gp3 = gp_Pnt(*_to_global_3d(*p3))
        arc_geom = GC_MakeArcOfCircle(gp1, gp2, gp3).Value()

    elif center and radius and start_angle is not None and end_angle is not None:
        # Arc by center + angle
        gp_center = gp_Pnt(*_to_global_3d(*center))
        circ = gp_Circ(_current_plane.Ax2().Translated(gp_center.XYZ()), radius)
        ax2 = _current_plane.Ax2()
        vec = gp_Vec(ax2.Location(), gp_center)
        translated_ax2 = ax2.Translated(vec)
        circ = GC_MakeCircle(translated_ax2, radius).Value()
        arc_geom = GC_MakeArcOfCircle(circ, start_angle, end_angle, True).Value()

    else:
        raise ValueError("Invalid arc input. Provide either three points or center+radius+angle range.")

    edge = BRepBuilderAPI_MakeEdge(arc_geom).Edge()
    _sketch_edges.append(edge)
    return edge


def add_circle(center: Tuple[float, float], radius: float) -> TopoDS_Shape:
    """
    Add a circle to the current sketch.
    
    Parameters:
        center: (x, y) center point in sketch coordinates
        radius: Circle radius
        
    Returns:
        Edge shape representing the circle
    """
    global _sketch_edges

    cx, cy, cz = _to_global_3d(*center)
    gp_center = gp_Pnt(cx, cy, cz)

    ax2 = _current_plane.Ax2()
    vec = gp_Vec(ax2.Location(), gp_center)
    ax2_translated = ax2.Translated(vec)

    circ = GC_MakeCircle(ax2_translated, radius).Value()
    edge = BRepBuilderAPI_MakeEdge(circ).Edge()
    _sketch_edges.append(edge)
    return edge


# ----------------------------------------------------------------------
# Advanced curve operations
# ----------------------------------------------------------------------

def add_ellipse(center: Tuple[float, float], major_axis_dir: Tuple[float, float], 
                major_radius: float, minor_radius: float) -> TopoDS_Shape:
    """
    Add an ellipse to the current sketch.

    Parameters:
        center: (x, y) center point on sketch plane
        major_axis_dir: (dx, dy) direction vector of major axis
        major_radius: length of major radius
        minor_radius: length of minor radius
        
    Returns:
        Edge shape representing the ellipse
    """
    global _sketch_edges

    cx, cy, cz = _to_global_3d(*center)
    direction = gp_Dir(major_axis_dir[0], major_axis_dir[1], 0.0)
    gp_center = gp_Pnt(cx, cy, cz)

    ax2 = _current_plane.Ax2().Translated(gp_Vec(_current_plane.Location(), gp_center))
    ax2 = gp_Ax2(gp_center, _current_plane.Axis().Direction(), direction)

    ellipse = gp_Elips(ax2, major_radius, minor_radius)
    edge = BRepBuilderAPI_MakeEdge(ellipse).Edge()

    _sketch_edges.append(edge)
    return edge


def add_spline(points: List[Tuple[float, float]]) -> TopoDS_Shape:
    """
    Add a spline curve to the current sketch.
    
    Parameters:
        points: List of (x, y) control points in sketch coordinates
        
    Returns:
        Edge shape representing the spline
    """
    global _sketch_edges
    array = TColgp_Array1OfPnt(1, len(points))
    for i, pt in enumerate(points, 1):
        x, y, z = _to_global_3d(*pt)
        array.SetValue(i, gp_Pnt(x, y, z))
    # spline = GeomAPI_PointsToBSpline(array).Curve()
    if len(points) > 70:
        degree = 3
    else:
        degree = 2
    spline = GeomAPI_PointsToBSpline(array, degree, degree).Curve()
    edge = BRepBuilderAPI_MakeEdge(spline).Edge()
    _sketch_edges.append(edge)
    return edge


def add_bezier(control_points: List[Tuple[float, float]]) -> TopoDS_Shape:
    """
    Add a Bezier curve to the current sketch.
    
    Parameters:
        control_points: List of (x, y) control points in sketch coordinates
        
    Returns:
        Edge shape representing the Bezier curve
    """
    global _sketch_edges
    array = TColgp_Array1OfPnt(1, len(control_points))
    for i, pt in enumerate(control_points, 1):
        x, y, z = _to_global_3d(*pt)
        array.SetValue(i, gp_Pnt(x, y, z))
    bezier = Geom_BezierCurve(array)
    edge = BRepBuilderAPI_MakeEdge(bezier).Edge()
    _sketch_edges.append(edge)
    return edge


# ----------------------------------------------------------------------
# Profile operations
# ----------------------------------------------------------------------

def close_profile(shape_history: Dict) -> TopoDS_Shape:
    """
    Convert accumulated sketch edges to a wire, then clear edge list.
    
    Parameters:
        shape_history: Dictionary to store shape history (for compatibility)
        
    Returns:
        Wire shape representing the closed profile
    """
    wire_builder = BRepBuilderAPI_MakeWire()
    for e in _sketch_edges:
        wire_builder.Add(e)
    _sketch_edges.clear()
    wire = wire_builder.Wire()
    return wire


# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------

def get_current_sketch_edges() -> List[TopoDS_Shape]:
    """
    Get the current list of sketch edges.
    
    Returns:
        List of edge shapes in the current sketch
    """
    return _sketch_edges.copy()


def clear_sketch_edges():
    """Clear all sketch edges."""
    global _sketch_edges
    _sketch_edges.clear()


def sync_sketch_edges(edges):
    """Sync global _sketch_edges with provided edge list."""
    global _sketch_edges
    _sketch_edges.clear()
    _sketch_edges.extend(edges)


def get_current_plane() -> gp_Ax3:
    """
    Get the current sketch plane.
    
    Returns:
        Current sketch plane coordinate system
        
    Raises:
        RuntimeError: If no sketch plane is active
    """
    if _current_plane is None:
        raise RuntimeError("No active sketch plane. Call begin_sketch() first.")
    return _current_plane


def is_sketch_active() -> bool:
    """
    Check if a sketch plane is currently active.
    
    Returns:
        True if a sketch plane is active, False otherwise
    """
    return _current_plane is not None
