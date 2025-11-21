"""
Unit conversion utilities with 1000x scaling for distance units
"""
from typing import Dict


class UnitConverter:
    """Handles all unit conversions and the critical 1000x scaling for nuCAD"""
    
    def __init__(self):
        self.unit_conversions = {
            "in": 0.0254,      # inches to meters
            "inch": 0.0254,
            "mm": 0.001,       # millimeters to meters
            "cm": 0.01,        # centimeters to meters
            "m": 1.0,          # meters
            "ft": 0.3048,      # feet to meters
            "deg": 1.0,        # degrees (no conversion needed)
            "degree": 1.0
        }
    
    def convert_distance(self, value: float, unit: str = "in") -> float:
        """Convert distance units to meters and scale by 1000 for nuCAD compatibility."""
        converted_value = value * self.unit_conversions.get(unit.lower(), 1.0)
        # Scale by 1000 for all units except angles
        if unit.lower() not in ["deg", "degree"]:
            converted_value *= 1000
        return round(converted_value, 2)
    
    def convert_angle(self, value: float, unit: str = "deg") -> float:
        """Convert angle units - no scaling applied."""
        return round(value * self.unit_conversions.get(unit.lower(), 1.0), 2)
    
    def parse_parameter_value(self, param) -> float:
        """Extract numeric value from parameter dictionary or raw value."""
        if isinstance(param, dict):
            raw_value = param.get("value", 0)
            # Handle fraction strings like "(15/32)" or "15/32"
            if isinstance(raw_value, str) and '/' in raw_value:
                raw_value = raw_value.strip('()')
                try:
                    numerator, denominator = raw_value.split('/')
                    value = float(numerator) / float(denominator)
                except (ValueError, ZeroDivisionError):
                    value = 0.0
            else:
                value = float(raw_value)
            unit = param.get("unit", "")
            return self.convert_distance(value, unit)
        elif isinstance(param, (int, float)):
            # Scale raw numbers by 1000 (assume they are distances)
            return round(float(param) * 1000, 2)
        elif isinstance(param, str):
            # Handle string expressions like "2.94 * inch"
            try:
                if "*" in param:
                    parts = param.strip().split("*")
                    if len(parts) == 2:
                        value = float(parts[0].strip())
                        unit = parts[1].strip()
                        return self.convert_distance(value, unit)
                return round(float(param) * 1000, 2)
            except (ValueError, IndexError):
                return 0.0
        return 0.0