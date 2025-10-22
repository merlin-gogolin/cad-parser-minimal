#!/usr/bin/env python3
"""
Test to demonstrate the coordinate system issue with sketch planes.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'nucad_test'))

from nuCAD.env.geometry.sketch_operations import begin_sketch, _to_global_3d

def test_coordinate_transformation():
    """Test how coordinates are transformed for a sketch with normal (1,0,0)"""
    
    print("Testing sketch with normal (1,0,0)")
    begin_sketch(origin=(0, 0, 0), normal=(1, 0, 0))
    
    # Test point (0, 10) in sketch coordinates
    sketch_point = (0, 10)
    global_point = _to_global_3d(*sketch_point)
    
    print(f"Sketch coordinates: {sketch_point}")
    print(f"Global coordinates: {global_point}")
    print(f"Expected: (0, 0, 10) or similar positive Y/Z")
    print(f"Actual Y coordinate: {global_point[1]}")
    print(f"Actual Z coordinate: {global_point[2]}")
    
    # The issue: when looking towards the plane with normal (1,0,0),
    # a point at (0,10) in sketch coordinates should appear ABOVE the origin
    # But if the global Y or Z coordinate is negative, it will appear BELOW
    
    if global_point[2] < 0:
        print("❌ ISSUE FOUND: Z coordinate is negative, circle will appear mirrored!")
    else:
        print("✅ Z coordinate is positive")
        
    if global_point[1] < 0:
        print("❌ ISSUE FOUND: Y coordinate is negative, circle will appear mirrored!")
    else:
        print("✅ Y coordinate is positive")

if __name__ == "__main__":
    test_coordinate_transformation()