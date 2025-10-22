"""
Base class for all feature converters
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from .unit_converter import UnitConverter
from .geometry_tracker import GeometryTracker


class BaseFeatureConverter(ABC):
    """Abstract base class for all feature converters"""
    
    def __init__(self, unit_converter: UnitConverter, geometry_tracker: GeometryTracker):
        self.unit_converter = unit_converter
        self.geometry_tracker = geometry_tracker
    
    @abstractmethod
    def convert(self, feature_data: Dict[str, Any]) -> List:
        """
        Convert a feature from JSON data to nuCAD actions.
        
        Args:
            feature_data: Dictionary containing feature information
            
        Returns:
            List of nuCAD actions
        """
        pass
    
    def get_feature_name(self, feature_data: Dict[str, Any]) -> str:
        """Extract feature name from feature data"""
        return feature_data.get("name", "Unknown")
    
    def get_feature_id(self, feature_data: Dict[str, Any]) -> str:
        """Extract feature ID from feature data"""
        return feature_data.get("id", "unknown")
    
    def get_parameters(self, feature_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from feature data"""
        return feature_data.get("parameters", {})
    
    def get_primitives(self, feature_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract primitives from feature data (for sketch features)"""
        return feature_data.get("primitives", {})