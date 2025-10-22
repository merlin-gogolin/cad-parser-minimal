"""
Geometry module for nuCAD.

This module contains all geometry-related operations organized by operation type:
- sketch_operations: 2D sketch operations (lines, arcs, circles, splines, etc.)
- face_operations: Face creation, manipulation, and analysis
- edge_operations: Edge operations (fillet, chamfer)
- body_operations: Body/solid creation (extrude, revolve, loft, sweep)
- boolean_operations: Boolean operations (fuse/union, cut/subtract, intersect)
- transform_operations: Transform operations (shell, mirror, transform)
- pattern_operations: Pattern operations (linear pattern, circular pattern)
"""

# Import all sketch operations for backwards compatibility
from .sketch_operations import (
    begin_sketch, add_line, add_arc, add_circle, add_ellipse, add_spline, 
    add_bezier, close_profile, get_current_sketch_edges, clear_sketch_edges,
    get_current_plane, is_sketch_active
)

# Import all face operations
from .face_operations import (
    make_face_with_optional_cut
)

# Import all edge operations
from .edge_operations import (
    apply_fillet, apply_chamfer
)

# Import all body operations
from .body_operations import (
    extrude, extrude_all_faces, revolve, apply_revolve, loft, apply_loft, 
    sweep, apply_sweep
)

# Import all boolean operations
from .boolean_operations import (
    fuse, cut, intersect, boolean_op
)

# Import all transform operations
from .transform_operations import (
    shell, apply_shell, mirror_plane, apply_mirror_plane, mirror_line, 
    apply_mirror_line, mirror_point, apply_mirror_point, translate,
    apply_translation_vector, apply_translation_point_to_point, 
    apply_translation_distance_direction, rotate, apply_rotation_axis, 
    apply_rotation_center_2d, apply_combined_transform
)

# Import all pattern operations
from .pattern_operations import (
    linear_pattern, apply_linear_pattern, circular_pattern, 
    apply_circular_pattern, polar_pattern
)

# Import core geometry utilities
from .geometry_utils import (
    get_face_data, get_faces_from_references, get_shape_from_reference, create_compound_shape
)
