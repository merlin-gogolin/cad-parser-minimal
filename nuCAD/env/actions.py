from dataclasses import dataclass
from typing import List, Tuple, Optional, Union



# sketch opeartions 

@dataclass
class AddSketch:
    origin: Tuple[float, float, float] = None
    normal: Tuple[float, float, float] = None
    on_face: str = None  

@dataclass
class StartLoop:
    pass

# line 
@dataclass
class AddLine:
    start: Tuple[float, float]  # 2D coordinates (x, y) on sketch plane
    end: Tuple[float, float]    # 2D coordinates (x, y) on sketch plane


# arc 
@dataclass
class AddArc:
    p1: Tuple[float, float]
    p2: Tuple[float, float]
    p3: Tuple[float, float]

    @property
    def points(self):
        return [self.p1, self.p2, self.p3]

# circle 
@dataclass
class AddCircle:
    center: Tuple[float, float]
    radius: float


# ellipse
@dataclass
class AddEllipse:
    center: Tuple[float, float]              # (x, y)
    major_axis_dir: Tuple[float, float]      # direction vector (dx, dy)
    major_radius: float
    minor_radius: float


# spline 
@dataclass
class AddSpline:
    points: List[Tuple[float, float]]  # At least 2 points (x, y)


@dataclass
class AddBezier:
    control_points: List[Tuple[float, float]]  # At least 2 points (x, y)


# wire/face operations 

@dataclass
class UnionWires:
    wire1: str  # e.g., "w0"
    wire2: str  # e.g., "w1"

@dataclass
class SubtractWires:
    main_wire: str     # e.g., "w0"
    subtract_wire: str # e.g., "w1"


@dataclass
class CloseProfile:
    pass


@dataclass
class MakeFace:
    operation: str = "cut"  # can be "cut", "union", etc.


# extrusion and body operations

@dataclass
class Extrude:
    height: float
    faces: List[str] = None  # Optional argument for face IDs
    direction: str = "one"  # "one", "symmetric", or "two"
    opposite_height: Optional[float] = None  # For direction="two"


@dataclass
class Boolean:
    type: str           # "union"/"fuse", "intersection"/"common", "subtraction"/"cut"
    solid1: str         # e.g., "s0"
    solid2: str         # e.g., "s1"
    
    def __post_init__(self):
        """Validate and normalize boolean operation type."""
        # Map user-friendly names to OpenCASCADE names
        type_mapping = {
            "union": "fuse",
            "fuse": "fuse",
            "intersection": "common", 
            "common": "common",
            "subtraction": "cut",
            "cut": "cut"
        }
        
        if self.type not in type_mapping:
            valid_types = list(type_mapping.keys())
            raise ValueError(f"Invalid boolean type '{self.type}'. Valid types: {valid_types}")
        
        # Normalize to OpenCASCADE name for internal use
        self.type = type_mapping[self.type]


# edge operations

@dataclass
class Fillet:
    edge: str          # e.g., "e4"
    radius: float      # e.g., 0.1
    solid: Optional[str] = None  # optional, defaults to current solid


@dataclass
class Chamfer:
    edge: str           # e.g., "e4"
    distance: float       # e.g., 0.1
    solid: Optional[str] = None  # optional, defaults to current solid


@dataclass
class Fillet2D:
    edge1: str         # First edge id (e.g., "e0")
    edge2: str         # Second edge id (e.g., "e1")
    radius: float      # Fillet radius
    wire: Optional[str] = None  # Optional: wire/sketch id if needed for context


@dataclass
class Chamfer2D:
    edge1: str         # First edge id (e.g., "e0")
    edge2: str         # Second edge id (e.g., "e1")
    distance: float    # Chamfer distance
    wire: Optional[str] = None  # Optional: wire/sketch id if needed for context


@dataclass
class Revolve:
    face: str
    direction: str  # "one", "symmetric", or "two"
    angle: Optional[float] = None
    angles: Optional[Tuple[float, float]] = None
    axis_point: Optional[Tuple[float, float, float]] = None
    axis_dir: Optional[Tuple[float, float, float]] = None
    edge: Optional[str] = None

    def __post_init__(self):
        if self.direction in {"one", "symmetric"} and self.angle is None:
            raise ValueError("angle must be set for 'one' or 'symmetric' direction")
        if self.direction == "two" and self.angles is None:
            raise ValueError("angles must be set for 'two' direction")
        if not self.edge and (self.axis_point is None or self.axis_dir is None):
            raise ValueError("Either 'edge' or both 'axis_point' and 'axis_dir' must be provided")


@dataclass(frozen=True)
class Loft:
    faces: List[str]                      # e.g., ["f1", "f3", "f5"]
    solid: bool = True                    # if True, try to make a solid
    ruled: bool = False                   # optional: straight connection between profiles
    smooth: bool = True                   # if False, use corner interpolation


@dataclass
class AddSweep:
    profile: str                          # face or wire to sweep (e.g., "f0", "w0")
    path: str                             # wire or edge to sweep along (e.g., "w1", "e5")
    solid: bool = True                    # if True, try to make a solid; if False, make a shell
    frenet: bool = False                  # if True, use Frenet frame; if False, use corrected frame
    twist_angle: Optional[float] = None   # optional twist angle in radians
    scale_factor: Optional[float] = None  # optional scaling factor along path


@dataclass
class Shell:
    solid: str                           # e.g., "s0" - the solid to shell
    faces_to_remove: List[str]           # e.g., ["s0:2", "s0:5"] - faces to remove for opening
    thickness: float                     # shell thickness (positive value)
    inward: bool = True                  # True for inward shelling, False for outward
    
    def __post_init__(self):
        if self.thickness <= 0:
            raise ValueError("thickness must be positive")
        if not self.faces_to_remove:
            raise ValueError("faces_to_remove cannot be empty - at least one face must be specified")


@dataclass
class Mirror:
    target: str                                        # What to mirror: "s0", "f0", "w0", etc.
    mirror_type: str                                   # "plane", "line", or "point"
    plane_origin: Optional[Tuple[float, float, float]] = None    # For plane mirror
    plane_normal: Optional[Tuple[float, float, float]] = None    # For plane mirror  
    line_point: Optional[Tuple[float, float, float]] = None      # For line mirror
    line_direction: Optional[Tuple[float, float, float]] = None  # For line mirror
    point: Optional[Tuple[float, float, float]] = None           # For point mirror
    copy_original: bool = True                         # Keep original + create copy, or just transform
    
    def __post_init__(self):
        if self.mirror_type not in ["plane", "line", "point"]:
            raise ValueError("mirror_type must be 'plane', 'line', or 'point'")
        
        if self.mirror_type == "plane":
            if self.plane_origin is None or self.plane_normal is None:
                raise ValueError("plane_origin and plane_normal must be specified for plane mirror")
        elif self.mirror_type == "line":
            if self.line_point is None or self.line_direction is None:
                raise ValueError("line_point and line_direction must be specified for line mirror")
        elif self.mirror_type == "point":
            if self.point is None:
                raise ValueError("point must be specified for point mirror")


@dataclass
class Transform:
    target: str                                        # What to transform: "s0", "f0", "w0", etc.
    operation: str                                     # "translate", "rotate", or "combined"
    
    # Translation parameters
    translation_type: Optional[str] = None            # "vector", "point_to_point", "distance_direction"
    translation_vector: Optional[Tuple[float, float, float]] = None
    from_point: Optional[Tuple[float, float, float]] = None
    to_point: Optional[Tuple[float, float, float]] = None
    distance: Optional[float] = None
    direction: Optional[Tuple[float, float, float]] = None
    
    # Rotation parameters
    rotation_type: Optional[str] = None               # "axis", "center_2d", "coordinate_axis"
    rotation_angle: Optional[float] = None            # Rotation angle in degrees
    rotation_axis_point: Optional[Tuple[float, float, float]] = None
    rotation_axis_direction: Optional[Tuple[float, float, float]] = None
    rotation_center: Optional[Tuple[float, float, float]] = None  # For 2D rotation
    rotation_plane_normal: Optional[Tuple[float, float, float]] = None  # For 2D rotation
    coordinate_axis: Optional[str] = None             # "x", "y", "z" for coordinate axis rotation
    
    # Combined transformation (for "combined" operation)
    transforms: Optional[List[dict]] = None           # List of transform dictionaries
    
    # General parameters
    copy_original: bool = True                        # Keep original + create copy, or just transform
    
    def __post_init__(self):
        if self.operation not in ["translate", "rotate", "combined"]:
            raise ValueError("operation must be 'translate', 'rotate', or 'combined'")
        
        if self.operation == "translate":
            self._validate_translation()
        elif self.operation == "rotate":
            self._validate_rotation()
        elif self.operation == "combined":
            self._validate_combined()
    
    def _validate_translation(self):
        if self.translation_type is None:
            raise ValueError("translation_type must be specified for translate operation")
        
        if self.translation_type not in ["vector", "point_to_point", "distance_direction"]:
            raise ValueError("translation_type must be 'vector', 'point_to_point', or 'distance_direction'")
        
        if self.translation_type == "vector":
            if self.translation_vector is None:
                raise ValueError("translation_vector must be specified for vector translation")
            if len(self.translation_vector) != 3:
                raise ValueError("translation_vector must be a 3D vector (x, y, z)")
        
        elif self.translation_type == "point_to_point":
            if self.from_point is None or self.to_point is None:
                raise ValueError("from_point and to_point must be specified for point_to_point translation")
            if len(self.from_point) != 3 or len(self.to_point) != 3:
                raise ValueError("from_point and to_point must be 3D points (x, y, z)")
        
        elif self.translation_type == "distance_direction":
            if self.distance is None or self.direction is None:
                raise ValueError("distance and direction must be specified for distance_direction translation")
            if self.distance <= 0:
                raise ValueError("distance must be positive")
            if len(self.direction) != 3:
                raise ValueError("direction must be a 3D vector (x, y, z)")
            # Check if direction is not zero vector
            if all(abs(d) < 1e-10 for d in self.direction):
                raise ValueError("direction vector cannot be zero")
    
    def _validate_rotation(self):
        if self.rotation_type is None:
            raise ValueError("rotation_type must be specified for rotate operation")
        
        if self.rotation_type not in ["axis", "center_2d", "coordinate_axis"]:
            raise ValueError("rotation_type must be 'axis', 'center_2d', or 'coordinate_axis'")
        
        if self.rotation_angle is None:
            raise ValueError("rotation_angle must be specified for rotate operation")
        
        if self.rotation_type == "axis":
            if self.rotation_axis_point is None or self.rotation_axis_direction is None:
                raise ValueError("rotation_axis_point and rotation_axis_direction must be specified for axis rotation")
            if len(self.rotation_axis_point) != 3 or len(self.rotation_axis_direction) != 3:
                raise ValueError("rotation_axis_point and rotation_axis_direction must be 3D vectors")
            # Check if axis direction is not zero vector
            if all(abs(d) < 1e-10 for d in self.rotation_axis_direction):
                raise ValueError("rotation_axis_direction cannot be zero")
        
        elif self.rotation_type == "center_2d":
            if self.rotation_center is None or self.rotation_plane_normal is None:
                raise ValueError("rotation_center and rotation_plane_normal must be specified for center_2d rotation")
            if len(self.rotation_center) != 3 or len(self.rotation_plane_normal) != 3:
                raise ValueError("rotation_center and rotation_plane_normal must be 3D vectors")
            # Check if plane normal is not zero vector
            if all(abs(n) < 1e-10 for n in self.rotation_plane_normal):
                raise ValueError("rotation_plane_normal cannot be zero")
        
        elif self.rotation_type == "coordinate_axis":
            if self.coordinate_axis is None:
                raise ValueError("coordinate_axis must be specified for coordinate_axis rotation")
            if self.coordinate_axis not in ["x", "y", "z"]:
                raise ValueError("coordinate_axis must be 'x', 'y', or 'z'")
    
    def _validate_combined(self):
        if self.transforms is None:
            raise ValueError("transforms list must be specified for combined operation")
        if not self.transforms:
            raise ValueError("transforms list cannot be empty for combined operation")
        
        for i, transform in enumerate(self.transforms):
            if not isinstance(transform, dict):
                raise ValueError(f"transforms[{i}] must be a dictionary")
            
            if "type" not in transform:
                raise ValueError(f"transforms[{i}] must have a 'type' field")
            
            transform_type = transform["type"]
            if transform_type not in ["translate", "rotate"]:
                raise ValueError(f"transforms[{i}] type must be 'translate' or 'rotate'")
            
            if transform_type == "translate":
                self._validate_combined_translation(transform, i)
            elif transform_type == "rotate":
                self._validate_combined_rotation(transform, i)
    
    def _validate_combined_translation(self, transform, index):
        if "method" not in transform:
            raise ValueError(f"transforms[{index}] translate must have a 'method' field")
        
        method = transform["method"]
        if method not in ["vector", "point_to_point", "distance_direction"]:
            raise ValueError(f"transforms[{index}] translate method must be 'vector', 'point_to_point', or 'distance_direction'")
        
        if method == "vector":
            if "vector" not in transform:
                raise ValueError(f"transforms[{index}] vector translate must have a 'vector' field")
            vector = transform["vector"]
            if not isinstance(vector, (list, tuple)) or len(vector) != 3:
                raise ValueError(f"transforms[{index}] vector must be a 3D vector")
        
        elif method == "point_to_point":
            if "from_point" not in transform or "to_point" not in transform:
                raise ValueError(f"transforms[{index}] point_to_point translate must have 'from_point' and 'to_point' fields")
            from_point = transform["from_point"]
            to_point = transform["to_point"]
            if (not isinstance(from_point, (list, tuple)) or len(from_point) != 3 or
                not isinstance(to_point, (list, tuple)) or len(to_point) != 3):
                raise ValueError(f"transforms[{index}] from_point and to_point must be 3D points")
        
        elif method == "distance_direction":
            if "distance" not in transform or "direction" not in transform:
                raise ValueError(f"transforms[{index}] distance_direction translate must have 'distance' and 'direction' fields")
            distance = transform["distance"]
            direction = transform["direction"]
            if not isinstance(distance, (int, float)) or distance <= 0:
                raise ValueError(f"transforms[{index}] distance must be a positive number")
            if not isinstance(direction, (list, tuple)) or len(direction) != 3:
                raise ValueError(f"transforms[{index}] direction must be a 3D vector")
            if all(abs(d) < 1e-10 for d in direction):
                raise ValueError(f"transforms[{index}] direction vector cannot be zero")
    
    def _validate_combined_rotation(self, transform, index):
        if "method" not in transform:
            raise ValueError(f"transforms[{index}] rotate must have a 'method' field")
        if "angle" not in transform:
            raise ValueError(f"transforms[{index}] rotate must have an 'angle' field")
        
        method = transform["method"]
        if method not in ["axis", "center_2d", "coordinate_axis"]:
            raise ValueError(f"transforms[{index}] rotate method must be 'axis', 'center_2d', or 'coordinate_axis'")
        
        angle = transform["angle"]
        if not isinstance(angle, (int, float)):
            raise ValueError(f"transforms[{index}] angle must be a number")
        
        if method == "axis":
            if "axis_point" not in transform or "axis_direction" not in transform:
                raise ValueError(f"transforms[{index}] axis rotate must have 'axis_point' and 'axis_direction' fields")
            axis_point = transform["axis_point"]
            axis_direction = transform["axis_direction"]
            if (not isinstance(axis_point, (list, tuple)) or len(axis_point) != 3 or
                not isinstance(axis_direction, (list, tuple)) or len(axis_direction) != 3):
                raise ValueError(f"transforms[{index}] axis_point and axis_direction must be 3D vectors")
            if all(abs(d) < 1e-10 for d in axis_direction):
                raise ValueError(f"transforms[{index}] axis_direction cannot be zero")
        
        elif method == "center_2d":
            if "center" not in transform or "plane_normal" not in transform:
                raise ValueError(f"transforms[{index}] center_2d rotate must have 'center' and 'plane_normal' fields")
            center = transform["center"]
            plane_normal = transform["plane_normal"]
            if (not isinstance(center, (list, tuple)) or len(center) != 3 or
                not isinstance(plane_normal, (list, tuple)) or len(plane_normal) != 3):
                raise ValueError(f"transforms[{index}] center and plane_normal must be 3D vectors")
            if all(abs(n) < 1e-10 for n in plane_normal):
                raise ValueError(f"transforms[{index}] plane_normal cannot be zero")
        
        elif method == "coordinate_axis":
            if "axis" not in transform:
                raise ValueError(f"transforms[{index}] coordinate_axis rotate must have an 'axis' field")
            axis = transform["axis"]
            if axis not in ["x", "y", "z"]:
                raise ValueError(f"transforms[{index}] coordinate axis must be 'x', 'y', or 'z'")


@dataclass
class LinearPattern:
    target: str                                        # What to pattern: "s0", "f0", "w0", etc.
    direction: Tuple[float, float, float]              # Direction vector for the pattern
    count: int                                         # Number of instances (including original)
    spacing: float                                     # Distance between instances
    include_original: bool = True                      # Whether to keep the original
    
    def __post_init__(self):
        if self.count < 1:
            raise ValueError("count must be at least 1")
        if self.spacing <= 0:
            raise ValueError("spacing must be positive")
        if len(self.direction) != 3:
            raise ValueError("direction must be a 3D vector (x, y, z)")
        # Check if direction is not zero vector
        if all(abs(d) < 1e-10 for d in self.direction):
            raise ValueError("direction vector cannot be zero")


@dataclass  
class CircularPattern:
    target: str                                        # What to pattern: "s0", "f0", "w0", etc.
    center_point: Tuple[float, float, float]           # Center point of rotation
    count: int                                         # Number of instances (including original)
    angle: float                                       # Total angle to span (in degrees)
    axis: str = "z"                                    # Rotation axis: "x", "y", "z" or custom direction
    axis_direction: Optional[Tuple[float, float, float]] = None  # Custom axis direction (if axis not x/y/z)
    include_original: bool = True                      # Whether to keep the original
    
    def __post_init__(self):
        if self.count < 1:
            raise ValueError("count must be at least 1")
        if self.axis not in ["x", "y", "z"] and self.axis_direction is None:
            raise ValueError("axis_direction must be specified when axis is not 'x', 'y', or 'z'")
        if self.axis_direction is not None:
            if len(self.axis_direction) != 3:
                raise ValueError("axis_direction must be a 3D vector (x, y, z)")
            # Check if axis direction is not zero vector
            if all(abs(d) < 1e-10 for d in self.axis_direction):
                raise ValueError("axis_direction cannot be zero")
        if len(self.center_point) != 3:
            raise ValueError("center_point must be a 3D point (x, y, z)")

