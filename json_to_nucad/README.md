# JSON-to-nuCAD Converter

**Converts OnShape FeatureScript JSON to nuCAD action sequences**

This module parses CAD feature data exported from OnShape and converts it to executable nuCAD actions, enabling programmatic reconstruction of CAD models.

---

## Overview

The converter translates OnShape's FeatureScript JSON format into nuCAD's action-based API, handling:
- **Sketches** (lines, arcs, circles, splines, constraints)
- **Extrusions** (with complex profiles and operations)
- **Face References** (sophisticated topology-aware face selection)

---

## Key Features

### 🎯 Topology-Aware Face References (NEW - Oct 2025)

**Problem:** CAD operations often reference faces on solids (e.g., "sketch on the top face of this extrusion"). Traditional approaches hard-coded assumptions like "donuts always have caps at indices :2 and :3", which broke for variations.

**Solution:** Geometric analysis system that classifies profiles and predicts face indices:

```python
# OLD (Brittle):
if num_circles >= 2:
    return "s0:3"  # ASSUMES donut topology

# NEW (Robust):
topology = analyzer.analyze_profile_topology(entities, primitives)
# Returns: type="annulus", cap_faces=[2,3], confidence=0.95
```

**Supported Topologies:**
- **Annulus** (concentric circles → donut/ring)
- **Multi-Hole** (separate circles → disk with holes)
- **Simple** (single loop → rectangle, polygon, circle)
- **Complex** (overlapping/tangent → runtime discovery needed)

See [`docs/TOPOLOGY_ANALYSIS_MIGRATION.md`](../docs/TOPOLOGY_ANALYSIS_MIGRATION.md) for details.

---

## Architecture

```
json_to_nucad/
├── __main__.py              # CLI entry point
├── converter.py             # Main converter orchestration
├── main.py                  # High-level conversion API
├── core/
│   ├── base_converter.py    # Base class for feature converters
│   ├── geometry_tracker.py  # Face/solid/edge reference tracking
│   ├── topology_analyzer.py # NEW: Geometric profile analysis
│   └── face_validator.py    # NEW: Runtime validation framework
├── converters/
│   ├── sketch_converter.py  # Sketch → AddSketch + primitives
│   ├── extrude_converter.py # Extrude → Extrude actions
│   └── ...                  # Other feature converters
└── utils/
    ├── unit_converter.py    # Unit conversion (inches, mm, etc.)
    └── ...
```

---

## Usage

### Basic Conversion

```python
from json_to_nucad.main import convert_json_to_nucad

# Convert JSON file to nuCAD actions
actions = convert_json_to_nucad("path/to/features.json")

# Execute in nuCAD
from nuCAD.env.rl_env import create_training_env

env = create_training_env()
env.reset()

for action in actions:
    env.step(action)

env.export(type="stl", filename="model")
```

### CLI Usage

```bash
# Convert JSON to nuCAD Python script
python -m json_to_nucad input.json output.py

# Convert and execute
python output.py
```

---

## Testing

### Unit Tests

```bash
# Test topology analysis (17 tests)
python3 -m pytest tests/test_topology_analyzer.py -v

# Test integration (4 tests)
python3 -m pytest tests/test_face_reference_integration.py -v

# All tests
python3 -m pytest tests/ -v
```

### Test Coverage

- ✅ Donut/annulus profiles
- ✅ Multi-hole disks
- ✅ Simple rectangles/polygons
- ✅ Complex overlapping geometry
- ✅ Confidence-based fallback
- ✅ Edge cases (empty, malformed data)

---

## Examples

### Example 1: Donut Extrusion

**Input JSON:**
```json
{
  "feature 1": {
    "type": "newSketch",
    "primitives": {
      "outer": {"type": "skCircle", "geometry": {"center": [0, 0], "radius": 0.05}},
      "inner": {"type": "skCircle", "geometry": {"center": [0, 0], "radius": 0.03}}
    }
  },
  "feature 2": {
    "type": "extrude",
    "parameters": {
      "entities": [[["sketch1", "newSketch"], ["outer", "skCircle"], ["inner", "skCircle"]]],
      "depth": {"value": 1, "unit": "in"}
    }
  }
}
```

**Output Actions:**
```python
[
    AddSketch(origin=(0,0,0), normal=(0,0,1)),
    StartLoop(),
    AddCircle(center=(0, 0), radius=50.0),  # Converted to mm
    CloseProfile(),
    MakeFace(),
    StartLoop(),
    AddCircle(center=(0, 0), radius=30.0),
    CloseProfile(),
    MakeFace(operation='cut'),
    Extrude(height=25.4, faces=['f1'])  # Creates annulus solid
]
```

**Topology Analysis Output:**
```
Topology analysis for extrude1:
  Type: annulus
  Cap faces: [2, 3]
  Confidence: 0.95
  Metadata: {'num_circles': 2, 'outer_radius': 0.05, 'inner_radius': 0.03}
```

---

## Configuration

### Custom Tolerance

```python
from json_to_nucad.core.topology_analyzer import TopologyAnalyzer

# Default tolerance: 0.001 (1 micrometer)
analyzer = TopologyAnalyzer()

# Strict tolerance for high-precision models
analyzer = TopologyAnalyzer(tolerance=0.000001)

# Loose tolerance for approximate geometry
analyzer = TopologyAnalyzer(tolerance=0.01)
```

### Logging

```python
import logging

# Enable debug logging for topology analysis
logging.basicConfig(level=logging.DEBUG)

# Topology decisions will be printed during conversion
```

---

## Known Limitations

1. **No runtime discovery yet** - Framework exists but not integrated
2. **Empirical face indices** - Cap positions (e.g., [2, 3] for annulus) are observed, not calculated
3. **2D analysis only** - Doesn't account for 3D extrusion effects
4. **Limited operation support** - No loft, sweep, revolve, shell operations

See [Future Improvements](../docs/TOPOLOGY_ANALYSIS_MIGRATION.md#planned-improvements) in migration guide.

---

## Contributing

### Adding New Geometry Support

When encountering new failure cases:

**❌ DON'T add shape-specific counters:**
```python
if num_hexagons >= 1:
    return "s0:5"  # Hard-coded!
```

**✅ DO add geometric tests:**
```python
def _are_polygons_nested(self, polygons):
    """Check if polygons are nested (one inside another)"""
    # Implement geometric containment test
    ...
```

See [Developer Guidelines](../docs/TOPOLOGY_ANALYSIS_MIGRATION.md#developer-guidelines) for details.

---

## References

- **Migration Guide:** [`docs/TOPOLOGY_ANALYSIS_MIGRATION.md`](../docs/TOPOLOGY_ANALYSIS_MIGRATION.md)
- **Copilot Instructions:** [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
- **nuCAD Documentation:** [Main README](../README.md)

---

## Changelog

### v1.0 (October 22, 2025)

**Major Changes:**
- ✨ Added topology analysis system
- ✨ Added confidence-based face reference selection
- ✨ Added runtime validation framework
- 🧪 Added 21 comprehensive tests
- 📚 Added migration guide and documentation
- ♻️ Refactored geometry tracker to use analysis
- 🐛 Fixed entities flattening edge case
- ⚡ Improved robustness for complex profiles

**Breaking Changes:** None (fully backward compatible)

---

**Maintained by:** AI Development Team  
**Last Updated:** October 22, 2025
