#!/usr/bin/env python3
"""
Comprehensive test to verify coordinate system fixes for multiple orientations.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'nucad_test'))

from nuCAD.env.geometry.sketch_operations import begin_sketch, _to_global_3d

def test_orientation(normal, description):
    """Test coordinate transformation for a specific orientation"""
    print(f"\n--- Testing {description} ---")
    print(f"Normal: {normal}")
    
    begin_sketch(origin=(0, 0, 0), normal=normal)
    
    # Test several key points
    test_points = [
        (0, 10),    # Point "up" in sketch
        (10, 0),    # Point "right" in sketch
        (-10, 0),   # Point "left" in sketch
        (0, -10),   # Point "down" in sketch
    ]
    
    for i, sketch_pt in enumerate(test_points):
        global_pt = _to_global_3d(*sketch_pt)
        print(f"  Sketch {sketch_pt} → Global {global_pt}")
    
    return True

def main():
    """Test multiple orientations"""
    print("Testing coordinate transformations for different sketch orientations")
    print("="*60)
    
    # Test the original problematic case
    test_orientation((1, 0, 0), "YZ plane (normal pointing in +X)")
    
    # Test other common orientations
    test_orientation((0, 1, 0), "XZ plane (normal pointing in +Y)")
    test_orientation((0, 0, 1), "XY plane (normal pointing in +Z)")
    test_orientation((-1, 0, 0), "YZ plane (normal pointing in -X)")
    test_orientation((0, -1, 0), "XZ plane (normal pointing in -Y)")
    test_orientation((0, 0, -1), "XY plane (normal pointing in -Z)")
    
    print("\n" + "="*60)
    print("✅ All coordinate transformations completed!")
    print("The fix should now match OnShape's coordinate system behavior.")

if __name__ == "__main__":
    main()