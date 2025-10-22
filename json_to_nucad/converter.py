"""
Main converter class that orchestrates all feature converters
"""
from typing import Dict, Any, List
from .core.unit_converter import UnitConverter
from .core.geometry_tracker import GeometryTracker
from .converters.sketch_converter import SketchConverter
from .converters.extrude_converter import ExtrudeConverter


class ModularJSONToNuCADConverter:
    """Main converter that delegates to feature-specific converters"""
    
    def __init__(self):
        # Core utilities
        self.unit_converter = UnitConverter()
        self.geometry_tracker = GeometryTracker()
        
        # Registry of feature converters
        self.converters = {
            'newsketch': SketchConverter(self.unit_converter, self.geometry_tracker),
            'extrude': ExtrudeConverter(self.unit_converter, self.geometry_tracker),
            # 'revolve': RevolveConverter(self.unit_converter, self.geometry_tracker),
            # 'fillet': FilletConverter(self.unit_converter, self.geometry_tracker),
            # ... etc; FILL THIS OUT AS WE ADD CONVERTERS ...
        }
    
    def convert_feature(self, feature_name: str, feature_data: Dict[str, Any]) -> List:
        """Convert a single feature to nuCAD actions"""
        feature_type = feature_data.get('type', '').lower()
        
        print(f"Converting feature {feature_name}: {feature_type}")
        
        converter = self.converters.get(feature_type)
        if converter:
            try:
                return converter.convert(feature_data)
            except Exception as e:
                print(f"Error converting {feature_type}: {e}")
                return []
        else:
            print(f"Warning: No converter for feature type: {feature_type}")
            return []
    
    def convert_json_to_actions(self, json_data: Dict[str, Any]) -> List:
        """Convert entire JSON data to list of nuCAD actions"""
        all_actions = []
        
        # Reset geometry tracker for new conversion
        self.geometry_tracker.reset()
        
        # Build feature timeline for proper face reference calculation
        self.geometry_tracker.build_feature_timeline(json_data)
        
        # Process features in order
        for feature_name, feature_data in json_data.items():
            if feature_name.startswith("feature "):
                # Set current feature context for geometry tracker
                self.geometry_tracker.set_current_feature(feature_name)
                
                actions = self.convert_feature(feature_name, feature_data)
                all_actions.extend(actions)
        
        return all_actions
    
    def get_conversion_stats(self) -> Dict[str, Any]:
        """Get statistics about the conversion process"""
        return {
            "faces_created": self.geometry_tracker.face_counter,
            "solids_created": self.geometry_tracker.solid_counter,
            "operations": len(self.geometry_tracker.solid_operations),
            "supported_features": list(self.converters.keys()),
            "operation_history": self.geometry_tracker.solid_operations
        }