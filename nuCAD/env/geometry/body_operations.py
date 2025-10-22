"""
Body operations module for nuCAD.

This module provides all body/solid creation operations including:
- Extrude operations
- Revolve operations
- Loft operations
- Sweep operations
"""

from typing import Tuple, List, Dict, Optional
from typing import Tuple, List, Dict, Optional

# Geometry primitives
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax3

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Compound, TopoDS_Solid, topods
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_EDGE, TopAbs_WIRE
from OCC.Core.TopExp import TopExp_Explorer

# Solid builders
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_ThruSections, BRepOffsetAPI_MakePipe
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeWire
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse

# Shape utilities
from OCC.Core.BRepTools import breptools
from OCC.Core.BRep import BRep_Tool, BRep_Builder
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

# Forward declaration for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..shapes import Solid


def extrude(
    shape: TopoDS_Shape,
    height: float,
    opposite_height: Optional[float] = None,
    direction: str = "one",
) -> TopoDS_Shape:
    """
    Extrude a shape along the current sketch plane normal.

    Modes (direction):
    - "symmetric": extrudes forward by `height` and backward by `height` (fused).
    - "two" : extrudes forward by `height` and backward by `opposite_height` (fused).
    - "one" (default): extrudes forward by `height` only.

    Args:
        shape: The shape (typically a Face) to extrude
        height: Extrusion distance in the normal direction (must be > 0)
        opposite_height: For "two" mode, the distance in the opposite direction (> 0)
        direction: "symmetric" | "two" | "one"

    Returns:
        The extruded shape (solid)
    """
    from .sketch_operations import get_current_plane

    current_plane = get_current_plane()
    if current_plane is None:
        raise RuntimeError("No active sketch plane.")

    if height == 0:
        raise ValueError("Extrude height must be non-zero")

    direction = (direction or "symmetric").lower()
    if direction not in {"symmetric", "two", "one"}:
        raise ValueError(f"Invalid extrude direction: {direction}")

    normal_dir = current_plane.Direction()
    vx, vy, vz = normal_dir.X(), normal_dir.Y(), normal_dir.Z()

    # Forward extrude (always)
    vec_fwd = gp_Vec(vx, vy, vz) * float(height)
    solid_fwd = BRepPrimAPI_MakePrism(shape, vec_fwd).Shape()

    if direction == "one":
        return solid_fwd

    if direction == "symmetric":
        vec_bwd = gp_Vec(-vx, -vy, -vz) * float(height)
        solid_bwd = BRepPrimAPI_MakePrism(shape, vec_bwd).Shape()
        return BRepAlgoAPI_Fuse(solid_fwd, solid_bwd).Shape()

    # direction == "two"
    if opposite_height is None or float(opposite_height) == 0.0:
        raise ValueError("opposite_height must be provided and non-zero for two-sided extrusion")
    vec_bwd = gp_Vec(-vx, -vy, -vz) * float(opposite_height)
    solid_bwd = BRepPrimAPI_MakePrism(shape, vec_bwd).Shape()
    return BRepAlgoAPI_Fuse(solid_fwd, solid_bwd).Shape()


def extrude_all_faces(extrude_faces: List[str], solids: List["Solid"],
                      all_faces: Dict[str, Dict], 
                      height: float,
                      direction: str = "one",
                      opposite_height: Optional[float] = None) -> Tuple[TopoDS_Shape, List[TopoDS_Shape]]:    
    """
    Extrude multiple faces and combine them into a compound.
    
    Args:
        extrude_faces: List of face references to extrude
        solids: List of existing solids
        all_faces: Dictionary of all faces
        height: Extrusion height
        direction: Extrusion direction mode ("one", "symmetric", "two")
        opposite_height: Height in opposite direction (for direction="two")
        
    Returns:
        Tuple of (compound_shape, list_of_faces)
    """
    resolved_faces = []
    for face_ref in extrude_faces:
        if ":" in face_ref:
            solid_id, face_idx = face_ref.split(":")
            face_idx = int(face_idx)
            solid = next(s for s in solids if s.id == solid_id)
            face_shape = solid.faces[face_idx].shape
        else:
            face_shape = all_faces[face_ref].shape
        resolved_faces.append((face_ref, face_shape))

    # Extrude all face shapes
    final_solids = [extrude(face_shape, height, opposite_height, direction) for _, face_shape in resolved_faces]

    # Build compound from extruded solids
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for solid in final_solids:
        builder.Add(compound, solid)

    # Extract all faces from the compound
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    # Use topods.Face for casting
    exp = TopExp_Explorer(compound, TopAbs_FACE)
    faces_full = []
    while exp.More():
        faces_full.append(topods.Face(exp.Current()))
        exp.Next()

    return compound, faces_full


def revolve(
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


def apply_revolve(
    face: TopoDS_Face,
    direction: str,
    angle: float,
    angles: Optional[Tuple[float, float]] = None,
    axis_point: Optional[Tuple[float, float, float]] = None,
    axis_dir: Optional[Tuple[float, float, float]] = None,
    edge: Optional[TopoDS_Edge] = None
) -> TopoDS_Shape:
    """
    Revolve a face around a given axis or edge with various direction options.
    
    Args:
        face: The face to revolve
        direction: Direction mode ("one", "symmetric", "two")
        angle: Angle of revolution in degrees
        angles: Tuple of angles for "two" direction mode
        axis_point: Point on the revolution axis
        axis_dir: Direction of the revolution axis
        edge: Optional edge to use as axis
        
    Returns:
        The revolved solid
    """
    if edge:
        curve = BRepAdaptor_Curve(edge)
        ax = curve.Line().Position()
        axis = gp_Ax1(ax.Location(), ax.Direction())
    elif axis_point is not None and axis_dir is not None:
        pt = gp_Pnt(*axis_point)
        dir = gp_Dir(*axis_dir)
        axis = gp_Ax1(pt, dir)
    else:
        raise ValueError("Either edge or both axis_point and axis_dir must be provided")

    if direction == "one":
        return BRepPrimAPI_MakeRevol(face, axis, angle * (3.14159265 / 180.0), True).Shape()
    elif direction == "symmetric":
        half_angle = angle / 2
        from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
        s1 = BRepPrimAPI_MakeRevol(face, axis, half_angle * (3.14159265 / 180.0), True).Shape()
        s2 = BRepPrimAPI_MakeRevol(face, axis.Reversed(), half_angle * (3.14159265 / 180.0), True).Shape()
        return BRepAlgoAPI_Fuse(s1, s2).Shape()
    elif direction == "two":
        a1, a2 = angles
        from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
        s1 = BRepPrimAPI_MakeRevol(face, axis, a1 * (3.14159265 / 180.0), True).Shape()
        s2 = BRepPrimAPI_MakeRevol(face, axis.Reversed(), a2 * (3.14159265 / 180.0), True).Shape()
        return BRepAlgoAPI_Fuse(s1, s2).Shape()
    else:
        raise ValueError(f"Invalid direction: {direction}")


def loft(
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
        builder.AddWire(breptools.OuterWire(face))

    builder.Build()
    return builder.Shape()


def apply_loft(
    face_shapes: List[TopoDS_Face],
    solid: bool = True,
    ruled: bool = False,
    smooth: bool = True
) -> TopoDS_Shape:
    """
    Apply loft operation between a list of faces.
    
    Args:
        face_shapes: List of faces to loft between
        solid: Whether to create a solid (True) or surface (False)
        ruled: Whether to create ruled surfaces
        smooth: Whether to create smooth transitions
        
    Returns:
        The lofted shape
    """
    return loft(face_shapes, solid, ruled, smooth)


def sweep(
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
            from OCC.Core.TopoDS import topods
            face = topods.Face(profile)
            outer_wire = breptools.OuterWire(face)
            surface_pipe = BRepOffsetAPI_MakePipe(path, outer_wire)
            return surface_pipe.Shape()
        else:
            # If profile is already a wire/edge, use it directly
            return pipe.Shape()


def apply_sweep(
    profile_shape: TopoDS_Shape,
    path_shape: TopoDS_Shape,
    solid: bool = True,
    frenet: bool = True,
    twist_angle: Optional[float] = None,
    scale_factor: Optional[float] = None
) -> TopoDS_Shape:
    """
    Apply sweep operation to create a shape by sweeping a profile along a path.
    
    Args:
        profile_shape: Face or Wire to sweep
        path_shape: Wire or Edge to sweep along
        solid: Whether to create a solid (True) or surface (False)
        frenet: Whether to use Frenet frame for sweep orientation
        twist_angle: Optional twist angle in degrees
        scale_factor: Optional scaling factor along the path
        
    Returns:
        The swept shape
    """
    # Convert path to wire if it's an edge
    if path_shape.ShapeType() == TopAbs_EDGE:
        path_wire = BRepBuilderAPI_MakeWire(path_shape).Wire()
    elif path_shape.ShapeType() == TopAbs_WIRE:
        path_wire = path_shape
    else:
        raise ValueError("Path must be a wire or edge")
    
    return sweep(profile_shape, path_wire, solid)
