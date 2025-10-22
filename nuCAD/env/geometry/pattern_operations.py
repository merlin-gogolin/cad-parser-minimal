"""
Pattern operations module for nuCAD.

This module provides all pattern operations including:
- Linear pattern operations
- Circular pattern operations
"""

from typing import Tuple, List, Dict, Optional

# Geometry primitives
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Trsf

# Shape types
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Compound
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform

import math


def linear_pattern(shape: TopoDS_Shape, direction: Tuple[float, float, float], 
                   count: int, spacing: float, include_original: bool = True) -> TopoDS_Shape:
    """
    Create a linear pattern of shapes.
    
    Args:
        shape: The shape to pattern
        direction: Direction vector for the pattern
        count: Number of instances in the pattern
        spacing: Distance between pattern instances
        include_original: Whether to include the original shape
        
    Returns:
        Compound shape containing all pattern instances
    """
    if count < 1:
        raise ValueError("Count must be at least 1")
    
    # Normalize direction
    direction_vec = gp_Vec(*direction)
    direction_vec.Normalize()
    
    # Create compound to hold all instances
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    
    # Add original shape if requested
    if include_original:
        builder.Add(compound, shape)
    
    # Create pattern instances
    # If include_original=True, we need (count-1) additional instances
    # If include_original=False, we need count instances
    instances_to_create = (count - 1) if include_original else count
    start_index = 1 if include_original else 0
    
    for i in range(start_index, instances_to_create + start_index):
        # Calculate translation for this instance
        translation = direction_vec * (spacing * i)
        
        # Create transformation
        transform = gp_Trsf()
        transform.SetTranslation(translation)
        
        # Apply transformation
        transformer = BRepBuilderAPI_Transform(shape, transform)
        transformed_shape = transformer.Shape()
        
        # Add to compound
        builder.Add(compound, transformed_shape)
    
    return compound


def apply_linear_pattern(shape: TopoDS_Shape, direction: Tuple[float, float, float], 
                        count: int, spacing: float, include_original: bool = True) -> TopoDS_Shape:
    """
    Apply linear pattern operation.
    
    Args:
        shape: The shape to pattern
        direction: Direction vector for the pattern
        count: Number of instances in the pattern
        spacing: Distance between pattern instances
        include_original: Whether to include the original shape
        
    Returns:
        Compound shape containing all pattern instances
    """
    return linear_pattern(shape, direction, count, spacing, include_original)


def circular_pattern(shape: TopoDS_Shape, center_point: Tuple[float, float, float],
                     axis_direction: Tuple[float, float, float], angle: float, 
                     count: int, include_original: bool = True) -> TopoDS_Shape:
    """
    Create a circular pattern of shapes.
    
    Args:
        shape: The shape to pattern
        center_point: Center point of the circular pattern
        axis_direction: Axis direction for rotation
        angle: Total angle to distribute pattern over (in radians)
        count: Number of instances in the pattern
        
    Returns:
        Compound shape containing all pattern instances
    """
    if count < 1:
        raise ValueError("Count must be at least 1")
    
    # Create rotation axis
    center = gp_Pnt(*center_point)
    axis_dir = gp_Dir(*axis_direction)
    axis = gp_Ax1(center, axis_dir)
    
    # Create compound to hold all instances
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    # Add original shape if requested
    if include_original:
        builder.Add(compound, shape)

    # Determine spacing strategy
    full_circle = abs(angle - 2 * math.pi) < 1e-9
    if count < 1:
        return compound

    # Divisor: for full circle use count to avoid 2π overlap, else use (count-1)
    divisor = count if full_circle else (count - 1 if count > 1 else 1)

    # Start index: if original is included, skip i=0 to avoid duplicate at 0°
    start_idx = 0 if not include_original else (1 if count > 1 else 0)

    # Number of instances to generate in loop
    end_idx = count  # exclusive upper bound

    # Create pattern instances
    for i in range(start_idx, end_idx):
        rotation_angle = (angle * i) / divisor if divisor != 0 else 0.0

        # Create transformation
        transform = gp_Trsf()
        transform.SetRotation(axis, rotation_angle)

        # Apply transformation
        transformer = BRepBuilderAPI_Transform(shape, transform)
        transformed_shape = transformer.Shape()

        # Add to compound
        builder.Add(compound, transformed_shape)
    
    return compound


def apply_circular_pattern(shape: TopoDS_Shape, center_point: Tuple[float, float, float],
                          axis_direction: Tuple[float, float, float], angle: float, 
                          count: int, include_original: bool = True) -> TopoDS_Shape:
    """
    Apply circular pattern operation.
    
    Args:
        shape: The shape to pattern
        center_point: Center point of the circular pattern
        axis_direction: Axis direction for rotation
    angle: Total angle to distribute pattern over (in radians)
    count: Number of instances in the pattern
    include_original: Whether to include the original at 0°
        
    Returns:
        Compound shape containing all pattern instances
    """
    return circular_pattern(shape, center_point, axis_direction, angle, count, include_original)


def polar_pattern(shape: TopoDS_Shape, center_point: Tuple[float, float, float],
                  axis_direction: Tuple[float, float, float], count: int) -> TopoDS_Shape:
    """
    Create a polar pattern (full 360 degree circular pattern).
    
    Args:
        shape: The shape to pattern
        center_point: Center point of the polar pattern
        axis_direction: Axis direction for rotation
        count: Number of instances in the pattern
        
    Returns:
        Compound shape containing all pattern instances
    """
    full_circle = 2 * math.pi
    return circular_pattern(shape, center_point, axis_direction, full_circle, count, include_original=True)
