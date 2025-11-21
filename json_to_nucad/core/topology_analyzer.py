"""
Topology analysis for face reference determination.

This module provides geometric analysis of sketch profiles to replace
hard-coded shape assumptions (especially donut detection).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import math


@dataclass
class TopologyInfo:
    """
    Geometric topology information for an extruded profile.
    
    Attributes:
        type: Topology classification
            - "simple": Single closed loop (rectangle, polygon)
            - "annulus": Concentric circles forming donut/ring
            - "multi_hole": Multiple non-overlapping holes in disk
            - "complex": Complex or indeterminate topology
        cap_faces: Indices of cap faces [bottom, top]
        swept_faces: Indices of swept side faces (from sketch edges)
        confidence: How confident we are in this classification (0.0-1.0)
        metadata: Additional information about the analysis
    """
    type: str
    cap_faces: Optional[List[int]]
    swept_faces: Optional[List[int]]
    confidence: float
    metadata: Dict[str, Any]


class TopologyAnalyzer:
    """
    Analyzes sketch profile geometry to determine expected face topology
    after extrusion, replacing hard-coded shape assumptions.
    """
    
    # Tolerance for geometric comparisons (in same units as primitives)
    POSITION_TOLERANCE = 0.001  # 1 micrometer for positions
    
    def __init__(self, tolerance: float = None):
        """
        Initialize analyzer.
        
        Args:
            tolerance: Optional custom tolerance for geometric comparisons
        """
        self.tolerance = tolerance or self.POSITION_TOLERANCE
    
    def analyze_profile_topology(
        self, 
        entities: List[List], 
        primitives: Dict[str, Any]
    ) -> TopologyInfo:
        """
        Analyze geometric relationships in sketch profile to determine topology.
        
        This is the main entry point that replaces the old `num_circles >= 2` check
        with actual geometric analysis.
        
        Args:
            entities: FeatureScript entity references 
                      [[sketch_id, 'newSketch'], [entity_id1, 'skCircle'], ...]
            primitives: Dictionary of primitive definitions with geometry
        
        Returns:
            TopologyInfo with classification and face indices
        
        Example:
            >>> entities = [['sketch1', 'newSketch'], ['c1', 'skCircle'], ['c2', 'skCircle']]
            >>> primitives = {
            ...     'c1': {'type': 'skCircle', 'geometry': {'center': [0, 0], 'radius': 0.05}},
            ...     'c2': {'type': 'skCircle', 'geometry': {'center': [0, 0], 'radius': 0.03}}
            ... }
            >>> info = analyzer.analyze_profile_topology(entities, primitives)
            >>> info.type
            'annulus'
            >>> info.cap_faces
            [2, 3]
        """
        # Extract primitive types and geometries
        circles = self._extract_circles(entities, primitives)
        lines = self._extract_lines(entities, primitives)
        arcs = self._extract_arcs(entities, primitives)
        
        metadata = {
            'num_circles': len(circles),
            'num_lines': len(lines),
            'num_arcs': len(arcs),
        }
        
        # Analyze circle configurations first (most common special case)
        if len(circles) >= 2:
            return self._analyze_multi_circle_profile(circles, metadata)
        
        # Single circle (cylinder)
        if len(circles) == 1 and not lines and not arcs:
            return TopologyInfo(
                type="simple",
                cap_faces=[1, 2],  # Bottom and top caps (index 0 is cylindrical surface)
                swept_faces=[0],   # Cylindrical surface
                confidence=0.95,
                metadata=metadata
            )
        
        # Polygon/mixed profile (lines and/or arcs)
        if lines or arcs:
            num_edges = len(lines) + len(arcs)
            # EMPIRICAL OBSERVATION: OpenCASCADE creates swept faces FIRST, then caps
            # For a pentagon: faces 0-4 are swept, faces 5-6 are caps
            return TopologyInfo(
                type="simple",
                cap_faces=[num_edges, num_edges + 1],  # Caps come AFTER swept faces
                swept_faces=list(range(0, num_edges)),  # Swept faces start at index 0
                confidence=0.9,
                metadata=metadata
            )
        
        # Fallback: unknown configuration
        return TopologyInfo(
            type="complex",
            cap_faces=None,  # Requires runtime discovery
            swept_faces=None,
            confidence=0.0,
            metadata=metadata
        )
    
    def _analyze_multi_circle_profile(
        self, 
        circles: List[Dict[str, Any]], 
        metadata: Dict[str, Any]
    ) -> TopologyInfo:
        """
        Analyze profiles with 2+ circles to determine if annulus, multi-hole, or complex.
        
        This replaces the old `if num_circles >= 2: return donut_indices` logic.
        """
        # Check if all circles are concentric (same center)
        if self._are_circles_concentric(circles):
            # Concentric circles → annulus/donut
            # Sort by radius to identify outer and inner
            sorted_circles = sorted(circles, key=lambda c: c['radius'], reverse=True)
            metadata['outer_radius'] = sorted_circles[0]['radius']
            metadata['inner_radius'] = sorted_circles[-1]['radius']
            metadata['num_rings'] = len(circles) - 1
            
            # For simple annulus (2 circles), we have empirically observed:
            # - Index 0: Outer cylindrical surface
            # - Index 1: Inner cylindrical surface  
            # - Index 2: Bottom cap (ring)
            # - Index 3: Top cap (ring)
            return TopologyInfo(
                type="annulus",
                cap_faces=[2, 3],
                swept_faces=[0, 1],  # Cylindrical surfaces
                confidence=0.95,
                metadata=metadata
            )
        
        # Check if circles are tangent (figure-8 or similar) - BEFORE non-overlapping check
        if self._are_circles_tangent(circles):
            metadata['configuration'] = 'tangent'
            return TopologyInfo(
                type="complex",
                cap_faces=None,  # Topology too complex, use runtime discovery
                swept_faces=None,
                confidence=0.3,
                metadata=metadata
            )
        
        # Check if circles don't overlap (separate holes in a disk)
        if self._are_circles_non_overlapping(circles):
            # Multiple separate holes
            # Each hole creates its own cylindrical surface
            # Caps are at indices 0 and 1, then cylindrical surfaces for each hole
            num_holes = len(circles)
            return TopologyInfo(
                type="multi_hole",
                cap_faces=[0, 1],
                swept_faces=list(range(2, 2 + num_holes)),
                confidence=0.85,
                metadata=metadata
            )
        
        # Overlapping but not concentric → complex case
        metadata['configuration'] = 'overlapping'
        return TopologyInfo(
            type="complex",
            cap_faces=None,
            swept_faces=None,
            confidence=0.2,
            metadata=metadata
        )
    
    def _extract_circles(
        self, 
        entities: List[List], 
        primitives: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract circle geometry from entities and primitives.
        
        Handles both raw JSON format (from OnShape) and processed format (from SketchConverter).
        
        Returns:
            List of dicts with {'id', 'center', 'radius'}
        """
        circles = []
        
        # Check if entities list only contains sketch reference (no primitive IDs)
        # This means "use ALL primitives from the sketch"
        has_primitive_refs = any(
            isinstance(e, list) and len(e) >= 2 and e[1] not in ['newSketch']
            for e in entities
        )
        
        if not has_primitive_refs:
            # No specific primitives listed → analyze ALL primitives
            entity_ids_to_check = list(primitives.keys())
        else:
            # Specific primitives listed → only analyze those
            entity_ids_to_check = [
                e[0] for e in entities 
                if isinstance(e, list) and len(e) >= 2 and e[1] != 'newSketch'
            ]
        
        for entity_id in entity_ids_to_check:
            primitive_data = primitives.get(entity_id, {})
            
            # Check if this is a circle
            prim_type = primitive_data.get('type', '')
            if prim_type not in ['skCircle', 'circle']:
                continue
            
            # Try to extract geometry - handle both raw and processed formats
            center = None
            radius = None
            
            # Format 1: Raw JSON with 'geometry' key
            if 'geometry' in primitive_data:
                geometry = primitive_data['geometry']
                center = geometry.get('center')
                radius = geometry.get('radius')
            
            # Format 2: Processed format with direct keys
            if center is None and 'center' in primitive_data:
                center = primitive_data['center']
            if radius is None and 'radius' in primitive_data:
                radius = primitive_data['radius']
            
            if center is not None and radius is not None:
                # Normalize center to list
                if isinstance(center, (list, tuple)) and len(center) >= 2:
                    center_point = [float(center[0]), float(center[1])]
                else:
                    continue
                
                circles.append({
                    'id': entity_id,
                    'center': center_point,
                    'radius': float(radius)
                })
        
        return circles
    
    def _extract_lines(
        self, 
        entities: List[List], 
        primitives: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract line geometry from entities. Handles both raw and processed formats."""
        lines = []
        
        # Check if entities list only contains sketch reference (no primitive IDs)
        has_primitive_refs = any(
            isinstance(e, list) and len(e) >= 2 and e[1] not in ['newSketch']
            for e in entities
        )
        
        if not has_primitive_refs:
            # No specific primitives listed → analyze ALL primitives
            entity_ids_to_check = list(primitives.keys())
        else:
            # Specific primitives listed → only analyze those
            entity_ids_to_check = [
                e[0] for e in entities 
                if isinstance(e, list) and len(e) >= 2 and e[1] != 'newSketch'
            ]
        
        for entity_id in entity_ids_to_check:
            primitive_data = primitives.get(entity_id, {})
            
            # Check if this is a line
            prim_type = primitive_data.get('type', '')
            if prim_type not in ['skLineSegment', 'skLine', 'line']:
                continue
            
            # Try to extract geometry - handle both raw and processed formats
            start = None
            end = None
            
            # Format 1: Raw JSON with 'geometry' key
            if 'geometry' in primitive_data:
                geometry = primitive_data['geometry']
                start = geometry.get('start')
                end = geometry.get('end')
            
            # Format 2: Processed format with direct keys
            if start is None and 'start' in primitive_data:
                start = primitive_data['start']
            if end is None and 'end' in primitive_data:
                end = primitive_data['end']
            
            if start and end:
                lines.append({
                    'id': entity_id,
                    'start': list(start),
                    'end': list(end)
                })
        
        return lines
    
    def _extract_arcs(
        self, 
        entities: List[List], 
        primitives: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract arc geometry from entities. Handles both raw and processed formats."""
        arcs = []
        
        # Check if entities list only contains sketch reference (no primitive IDs)
        has_primitive_refs = any(
            isinstance(e, list) and len(e) >= 2 and e[1] not in ['newSketch']
            for e in entities
        )
        
        if not has_primitive_refs:
            # No specific primitives listed → analyze ALL primitives
            entity_ids_to_check = list(primitives.keys())
        else:
            # Specific primitives listed → only analyze those
            entity_ids_to_check = [
                e[0] for e in entities 
                if isinstance(e, list) and len(e) >= 2 and e[1] != 'newSketch'
            ]
        
        for entity_id in entity_ids_to_check:
            primitive_data = primitives.get(entity_id, {})
            
            # Check if this is an arc
            prim_type = primitive_data.get('type', '')
            if prim_type not in ['skArc', 'arc']:
                continue
            
            # Try to extract geometry - handle both raw and processed formats
            center = None
            radius = None
            
            # Format 1: Raw JSON with 'geometry' key
            if 'geometry' in primitive_data:
                geometry = primitive_data['geometry']
                center = geometry.get('center')
                radius = geometry.get('radius')
            
            # Format 2: Processed format with direct keys
            if center is None and 'center' in primitive_data:
                center = primitive_data['center']
            if radius is None and 'radius' in primitive_data:
                radius = primitive_data['radius']
            
            if center and radius:
                arcs.append({
                    'id': entity_id,
                    'center': list(center),
                    'radius': float(radius)
                })
        
        return arcs
    
    def _are_circles_concentric(self, circles: List[Dict[str, Any]]) -> bool:
        """
        Check if all circles share the same center (within tolerance).
        
        This is the key test to distinguish annulus from multi-hole configurations.
        """
        if len(circles) < 2:
            return False
        
        # Use first circle's center as reference
        ref_center = circles[0]['center']
        
        for circle in circles[1:]:
            distance = self._distance_2d(ref_center, circle['center'])
            if distance > self.tolerance:
                return False
        
        return True
    
    def _are_circles_non_overlapping(self, circles: List[Dict[str, Any]]) -> bool:
        """
        Check if circles don't overlap (distance between centers > sum of radii).
        """
        for i, c1 in enumerate(circles):
            for c2 in circles[i+1:]:
                center_distance = self._distance_2d(c1['center'], c2['center'])
                sum_radii = c1['radius'] + c2['radius']
                
                # If centers are too close, circles overlap
                if center_distance < sum_radii - self.tolerance:
                    return False
        
        return True
    
    def _are_circles_tangent(self, circles: List[Dict[str, Any]]) -> bool:
        """
        Check if any pair of circles is tangent (touching at exactly one point).
        """
        for i, c1 in enumerate(circles):
            for c2 in circles[i+1:]:
                center_distance = self._distance_2d(c1['center'], c2['center'])
                
                # External tangency: distance = r1 + r2
                if abs(center_distance - (c1['radius'] + c2['radius'])) < self.tolerance:
                    return True
                
                # Internal tangency: distance = |r1 - r2|
                if abs(center_distance - abs(c1['radius'] - c2['radius'])) < self.tolerance:
                    return True
        
        return False
    
    def _distance_2d(self, p1: List[float], p2: List[float]) -> float:
        """Calculate Euclidean distance between two 2D points."""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
