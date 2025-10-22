from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterable, Any

try:
    from OCC.Core.TopoDS import TopoDS_Shape  # type: ignore
except Exception:  # pragma: no cover
    from typing import Any as TopoDS_Shape  # type: ignore

@dataclass
class EntityRecord:
    id: str
    type: str  # solid|face|edge|wire|sketch
    shape: TopoDS_Shape
    key: Optional[int] = None  # stable shape key if available

@dataclass
class EntityRegistry:
    _records: Dict[str, EntityRecord] = field(default_factory=dict)
    version: int = 0
    def clear(self):
        self._records.clear()
    def _compute_shape_key(self, shape: Any) -> Optional[int]:
        try:
            # Use large prime modulus for OCCT HashCode
            if hasattr(shape, 'HashCode'):
                return int(shape.HashCode(2147483647))
        except Exception:
            pass
        return None
    def sync(self, state) -> None:
        self.clear()
        def _extract_shape(obj: Any):
            if obj is None:
                return None
            shape = getattr(obj, 'shape', None)
            if shape is None and isinstance(obj, dict):
                shape = obj.get('shape')
            return shape
        # Solids and nested per-solid entities
        for solid in getattr(state, 'solids', []):
            try:
                shape = _extract_shape(solid)
                if shape is not None:
                    self._records[solid.id] = EntityRecord(solid.id, 'solid', shape, self._compute_shape_key(shape))
            except Exception:
                pass
            # Per-solid faces and edges
            for face in getattr(solid, 'faces', []) or []:
                try:
                    fshape = _extract_shape(face)
                    if fshape is not None and getattr(face, 'id', None):
                        self._records[face.id] = EntityRecord(face.id, 'face', fshape, self._compute_shape_key(fshape))
                except Exception:
                    pass
                for edge in getattr(face, 'edges', []) or []:
                    try:
                        eshape = _extract_shape(edge)
                        if eshape is not None and getattr(edge, 'id', None) and edge.id not in self._records:
                            self._records[edge.id] = EntityRecord(edge.id, 'edge', eshape, self._compute_shape_key(eshape))
                    except Exception:
                        pass
        # Global registries
        for fid, fdata in getattr(state, 'faces', {}).items():
            shape = _extract_shape(fdata)
            if shape is not None:
                self._records[fid] = EntityRecord(fid, 'face', shape, self._compute_shape_key(shape))
        for wid, wdata in getattr(state, 'wires', {}).items():
            shape = _extract_shape(wdata)
            if shape is not None:
                self._records[wid] = EntityRecord(wid, 'wire', shape, self._compute_shape_key(shape))
        for eid, edata in getattr(state, 'edges', {}).items():
            shape = _extract_shape(edata)
            if shape is not None:
                self._records[eid] = EntityRecord(eid, 'edge', shape, self._compute_shape_key(shape))
        self.version += 1
    def list_ids(self, type_filter: Optional[str] = None) -> List[str]:
        if type_filter is None:
            return list(self._records.keys())
        return [rid for rid, rec in self._records.items() if rec.type == type_filter]
    def get(self, rid: str) -> Optional[EntityRecord]:
        return self._records.get(rid)
    def get_shape(self, rid: str):
        rec = self.get(rid)
        return rec.shape if rec else None
    def records(self) -> Iterable[EntityRecord]:
        return self._records.values()
    # Helper: find equivalent IDs (same shape) using hash key or IsEqual fallback
    def find_equivalent_ids(self, rid: str) -> List[str]:
        base = self.get(rid)
        if not base:
            return []
        eq: List[str] = []
        base_key = base.key
        base_shape = base.shape
        for other_id, other in self._records.items():
            if other_id == rid:
                continue
            try:
                if base_key is not None and other.key is not None and base_key == other.key:
                    eq.append(other_id)
                    continue
                if hasattr(base_shape, 'IsEqual') and base_shape.IsEqual(other.shape):
                    eq.append(other_id)
                    continue
                if other.shape is base_shape:
                    eq.append(other_id)
            except Exception:
                if other.shape is base_shape:
                    eq.append(other_id)
        return eq

__all__ = ['EntityRegistry', 'EntityRecord']
