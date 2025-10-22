from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Set, Any, List

try:
    from OCC.Core.AIS import AIS_Shape  # type: ignore
except Exception:  # pragma: no cover
    AIS_Shape = object  # type: ignore

try:  # OCC may fail in headless
    from OCC.Core.AIS import AIS_InteractiveObject  # type: ignore
    from OCC.Core.Quantity import (
        Quantity_Color,
        Quantity_NOC_RED,
        Quantity_NOC_BLACK,
        Quantity_TOC_RGB,
    )  # type: ignore
except Exception:  # pragma: no cover
    AIS_InteractiveObject = object  # type: ignore
    Quantity_Color = lambda *a, **k: None  # type: ignore
    Quantity_NOC_RED = Quantity_NOC_BLACK = 0  # type: ignore
    Quantity_TOC_RGB = None  # type: ignore

@dataclass
class _SavedStyle:
    color: Optional[Any] = None
    width: Optional[float] = None

@dataclass
class SelectionManager:
    display: any
    on_select_id: Callable[[str], None]
    multi_select: bool = False
    _saved_styles: Dict[str, _SavedStyle] = field(default_factory=dict)
    _selected_ids: Set[str] = field(default_factory=set)
    on_selection_changed_set: Optional[Callable[[List[str]], None]] = None
    highlight_rgb: tuple[float, float, float] = (0.95, 0.15, 0.95)
    highlight_width: float = 4.0
    # New: use black for edges for better visibility
    highlight_rgb_edges: tuple[float, float, float] = (0.0, 0.0, 0.0)
    entity_registry: Any | None = None
    renderer: Any | None = None
    # Track AIS instances we created lazily so we can erase them on deselect
    _owned_ais: Set[str] = field(default_factory=set)
    # Track highlight overlays we created for faces
    _highlight_overlays: Dict[str, Any] = field(default_factory=dict)
    def __post_init__(self):
        if hasattr(self.display, 'register_select_callback'):
            try:
                self.display.register_select_callback(self._on_occ_select)
            except Exception:
                pass
    def refresh_from_renderer(self, renderer) -> None:
        self._id_to_ais = getattr(renderer, 'id_to_ais', {})
        self._ais_hash_to_id = getattr(renderer, 'ais_hash_to_id', {})
        self.renderer = renderer
    def _equivalent_ids(self, rid: str) -> List[str]:
        eq: List[str] = []
        reg = self.entity_registry
        if reg and hasattr(reg, 'find_equivalent_ids'):
            try:
                eq = reg.find_equivalent_ids(rid)
            except Exception:
                eq = []
        return [e for e in eq if e != rid]
    def _ensure_many_ais(self, ids: List[str]):
        for eid in ids:
            self._ensure_ais(eid)
    def select_id(self, rid: str) -> bool:
        # Determine the group (rid + equivalents)
        group = [rid] + self._equivalent_ids(rid)
        for gid in group:
            self._ensure_ais(gid)
        if not hasattr(self, '_id_to_ais'):
            return False
        changed = False
        if self.multi_select:
            # Toggle off if any in the group is currently selected
            any_selected = any(g in self._selected_ids for g in group)
            if any_selected:
                for gid in group:
                    if gid in self._selected_ids:
                        self._restore_style(gid)
                        self._selected_ids.remove(gid)
                        changed = True
            else:
                for gid in group:
                    if gid not in self._selected_ids:
                        ais = self._id_to_ais.get(gid)
                        if not ais:
                            continue
                        self._apply_highlight(gid, ais)
                        self._selected_ids.add(gid)
                        changed = True
        else:
            # Single-select: if any of the group is selected, deselect all; else select the group exclusively
            group_set = set(group)
            if self._selected_ids & group_set:
                # Deselect
                for gid in list(self._selected_ids & group_set):
                    self._restore_style(gid)
                    self._selected_ids.remove(gid)
                    changed = True
            else:
                # Select this group exclusively
                if self._selected_ids:
                    self.clear_selection()
                for gid in group:
                    ais = self._id_to_ais.get(gid)
                    if not ais:
                        continue
                    self._apply_highlight(gid, ais)
                    self._selected_ids.add(gid)
                    changed = True
        # Emit callbacks for the base rid
        if changed and self.on_select_id:
            try:
                self.on_select_id(rid)
            except Exception:
                pass
        if changed:
            # Force viewer to update after style changes
            try:
                self.display.Context.UpdateCurrentViewer()
            except Exception:
                pass
            self._emit_set_change()
        return True
    def deselect_id(self, rid: str) -> bool:
        group = [rid] + self._equivalent_ids(rid)
        changed = False
        for gid in group:
            if gid in self._selected_ids:
                self._restore_style(gid)
                self._selected_ids.remove(gid)
                # Clear OCC selection/highlight state
                self._unselect_in_context(gid)
                # If AIS was created by us, erase to avoid lingering overlay
                self._erase_owned_ais_if_any(gid)
                changed = True
        if changed:
            try:
                self.display.Context.UpdateCurrentViewer()
            except Exception:
                pass
            self._emit_set_change()
        return changed
    def clear_selection(self):
        if not self._selected_ids:
            return
        for rid in list(self._selected_ids):
            self._restore_style(rid)
            self._unselect_in_context(rid)
            # Erase owned AIS if any
            self._erase_owned_ais_if_any(rid)
        self._selected_ids.clear()
        try:
            self.display.Context.UpdateCurrentViewer()
        except Exception:
            pass
        self._emit_set_change()
    def get_selected_ids(self):
        return list(self._selected_ids)
    def _on_occ_select(self, *args, **kwargs):
        ctx = self.display.Context
        try:
            selected = []
            ctx.InitSelected()
            while ctx.MoreSelected():
                ais = ctx.SelectedInteractive()
                selected.append(ais)
                ctx.NextSelected()
        except Exception:
            return
        if not selected:
            return
        # Deduplicate AIS objects
        unique = []
        seen = set()
        for ais in selected:
            try:
                h = ais.GetHandle()
            except Exception:
                h = id(ais)
            if h in seen:
                continue
            seen.add(h)
            unique.append(ais)
        selected = unique
        changed = False
        if self.multi_select:
            for ais in selected:
                rid = self._lookup_id(ais)
                if not rid:
                    continue
                group = [rid] + self._equivalent_ids(rid)
                any_selected = any(g in self._selected_ids for g in group)
                if any_selected:
                    for gid in list(group):
                        if gid in self._selected_ids:
                            self._restore_style(gid)
                            self._selected_ids.remove(gid)
                            self._unselect_in_context(gid)
                            self._erase_owned_ais_if_any(gid)
                            changed = True
                else:
                    for gid in group:
                        self._ensure_ais(gid)
                        ais_g = self._id_to_ais.get(gid) if hasattr(self, '_id_to_ais') else None
                        if not ais_g:
                            continue
                        if gid not in self._selected_ids:
                            self._apply_highlight(gid, ais_g)
                            self._selected_ids.add(gid)
                            changed = True
                    if self.on_select_id:
                        try:
                            self.on_select_id(rid)
                        except Exception:
                            pass
        else:
            ais = selected[-1]
            rid = self._lookup_id(ais)
            if rid:
                group = [rid] + self._equivalent_ids(rid)
                group_set = set(group)
                if self._selected_ids & group_set:
                    # Toggle off
                    for gid in list(self._selected_ids & group_set):
                        self._restore_style(gid)
                        self._selected_ids.remove(gid)
                        self._unselect_in_context(gid)
                        self._erase_owned_ais_if_any(gid)
                        changed = True
                else:
                    # Select this group exclusively
                    self.clear_selection()
                    for gid in group:
                        self._ensure_ais(gid)
                        ais_g = self._id_to_ais.get(gid)
                        if not ais_g:
                            continue
                        self._apply_highlight(gid, ais_g)
                        self._selected_ids.add(gid)
                        changed = True
                if self.on_select_id:
                    try:
                        self.on_select_id(rid)
                    except Exception:
                        pass
        if changed:
            # Update viewer after toggling off/on
            try:
                self.display.Context.UpdateCurrentViewer()
            except Exception:
                pass
            self._emit_set_change()
    def _get_entity_type(self, rid: str) -> Optional[str]:
        """Return entity type using registry when available; fallback to id heuristics."""
        reg = self.entity_registry
        if reg is not None:
            try:
                rec = reg.get(rid)
                if rec is not None:
                    return getattr(rec, 'type', None)
            except Exception:
                pass
        # Heuristic: id prefixes
        rl = rid.lower()
        if rl.startswith('e') or (rl.startswith('s') and 'e' in rl and 'f' not in rl):
            return 'edge'
        if rl.startswith('f') or (rl.startswith('s') and 'f' in rl):
            return 'face'
        if rl.startswith('w'):
            return 'wire'
        if rl.startswith('s'):
            return 'solid'
        return None
    def _apply_highlight(self, rid: str, ais):
        ctx = self.display.Context
        if rid not in self._saved_styles:
            try:
                try:
                    cur_color = ctx.Color(ais) if hasattr(ctx, 'Color') else None
                except Exception:
                    cur_color = None
                saved_width = None
                self._saved_styles[rid] = _SavedStyle(color=cur_color, width=saved_width)
            except Exception:
                self._saved_styles[rid] = _SavedStyle()
        # Decide highlight approach based on entity type
        try:
            etype = self._get_entity_type(rid)
            
            if etype == 'face':
                # For faces, create a separate highlight overlay instead of modifying the original
                self._create_face_highlight_overlay(rid, ais)
            elif etype == 'wire':
                # For wires, also create a separate highlight overlay for consistency
                self._create_wire_highlight_overlay(rid, ais)
            else:
                # For edges, use the traditional color/width approach
                if etype == 'edge':
                    r, g, b = self.highlight_rgb_edges
                else:
                    r, g, b = self.highlight_rgb
                    
                if 'Quantity_TOC_RGB' in globals() and Quantity_TOC_RGB is not None:
                    qcol = Quantity_Color(r, g, b, Quantity_TOC_RGB)
                else:
                    qcol = Quantity_Color(Quantity_NOC_BLACK if etype == 'edge' else Quantity_NOC_RED)
                    
                ctx.SetColor(ais, qcol, False)
                if etype == 'edge':
                    ctx.SetWidth(ais, self.highlight_width, True)
        except Exception:
            pass
        ctx.UpdateCurrentViewer()
    def _restore_style(self, rid: str):
        # Remove highlight overlay for faces
        if rid in self._highlight_overlays:
            try:
                overlay_ais = self._highlight_overlays[rid]
                self.display.Context.Erase(overlay_ais, False)
                del self._highlight_overlays[rid]
            except Exception:
                pass
        
        # For edges/wires, restore original style
        if not hasattr(self, '_id_to_ais'):
            return
        ais = self._id_to_ais.get(rid)
        if not ais:
            return
        ctx = self.display.Context
        saved = self._saved_styles.get(rid)
        
        # Only restore style for edges (faces and wires use overlays)
        etype = self._get_entity_type(rid)
        if etype == 'edge':
            try:
                if saved and saved.color is not None:
                    ctx.SetColor(ais, saved.color, False)
                else:
                    # Force back to neutral if original not known
                    ctx.SetColor(ais, Quantity_Color(Quantity_NOC_BLACK), False)
                if saved and saved.width is not None:
                    ctx.SetWidth(ais, saved.width, True)
                else:
                    ctx.SetWidth(ais, 1.0, True)
            except Exception:
                pass
    def _lookup_id(self, ais) -> Optional[str]:
        if not hasattr(self, '_ais_hash_to_id'):
            return None
        try:
            h = hash(ais.GetHandle())
        except Exception:
            return None
        return self._ais_hash_to_id.get(h)
    def _emit_set_change(self):
        if self.on_selection_changed_set:
            try:
                self.on_selection_changed_set(self.get_selected_ids())
            except Exception:
                pass
    def select_exclusive(self, rid: str) -> bool:
        if not hasattr(self, '_id_to_ais'):
            return False
        group = [rid] + self._equivalent_ids(rid)
        # Ensure AIS for all
        for gid in group:
            self._ensure_ais(gid)
        # If already exactly the group, do nothing
        if self._selected_ids == set(group):
            return True
        self.clear_selection()
        changed = False
        for gid in group:
            ais = self._id_to_ais.get(gid)
            if not ais:
                continue
            self._apply_highlight(gid, ais)
            self._selected_ids.add(gid)
            changed = True
        if changed and self.on_select_id:
            try:
                self.on_select_id(rid)
            except Exception:
                pass
        if changed:
            self._emit_set_change()
        return True
    def _ensure_ais(self, rid: str):
        if not hasattr(self, '_id_to_ais'):
            return False
        if rid in self._id_to_ais:
            return True
        if not self.entity_registry:
            return False
        try:
            shape = self.entity_registry.get_shape(rid)
        except Exception:
            shape = None
        if shape is None:
            return False
        try:
            ais = AIS_Shape(shape)
        except Exception:
            return False
        ctx = self.display.Context
        try:
            ctx.Display(ais, False)
        except Exception:
            pass
        if self.renderer and hasattr(self.renderer, '_register_entity'):
            try:
                self.renderer._register_entity(rid, ais)  # type: ignore
            except Exception:
                pass
        self._id_to_ais[rid] = ais
        try:
            self._ais_hash_to_id[hash(ais.GetHandle())] = rid
        except Exception:
            pass
        # Mark as owned so we can erase if deselected
        self._owned_ais.add(rid)
        return True
    def _erase_owned_ais_if_any(self, rid: str):
        if rid not in getattr(self, '_owned_ais', set()):
            return
        ais = self._id_to_ais.get(rid)
        if not ais:
            self._owned_ais.discard(rid)
            return
        ctx = self.display.Context
        try:
            ctx.Erase(ais, False)
        except Exception:
            pass
        # Remove mappings
        try:
            h = hash(ais.GetHandle())
            if hasattr(self, '_ais_hash_to_id') and h in self._ais_hash_to_id:
                del self._ais_hash_to_id[h]
        except Exception:
            pass
        if rid in self._id_to_ais:
            del self._id_to_ais[rid]
        self._owned_ais.discard(rid)
    def _unselect_in_context(self, rid: str):
        # Try to remove OCC selection/highlight for the AIS of this id
        if not hasattr(self, '_id_to_ais'):
            return
        ais = self._id_to_ais.get(rid)
        if not ais:
            return
        ctx = self.display.Context
        try:
            if hasattr(ctx, 'AddOrRemoveSelected'):
                try:
                    ctx.AddOrRemoveSelected(ais, False)
                except Exception:
                    pass
            if hasattr(ctx, 'Unhilight'):
                try:
                    try:
                        ctx.Unhilight(ais, True)
                    except TypeError:
                        ctx.Unhilight(ais)
                except Exception:
                    pass
            # Extra safety: clear any lingering green selection overlay (affects viewer selection, not our magenta)
            if hasattr(ctx, 'UnhilightSelected'):
                try:
                    ctx.UnhilightSelected(True)
                except Exception:
                    pass
        except Exception:
            pass
    def _create_face_highlight_overlay(self, rid: str, original_ais):
        """Create a separate highlight overlay for faces"""
        try:
            # Get the shape from the entity registry
            if not self.entity_registry:
                return
            shape = self.entity_registry.get_shape(rid)
            if shape is None:
                return
                
            # Create a new AIS object for the highlight overlay
            highlight_ais = AIS_Shape(shape)
            
            # Set highlight color and transparency
            r, g, b = self.highlight_rgb
            if 'Quantity_TOC_RGB' in globals() and Quantity_TOC_RGB is not None:
                qcol = Quantity_Color(r, g, b, Quantity_TOC_RGB)
            else:
                qcol = Quantity_Color(Quantity_NOC_RED)
            
            ctx = self.display.Context
            ctx.SetColor(highlight_ais, qcol, False)
            ctx.SetTransparency(highlight_ais, 0.2, False)  # Semi-transparent highlight
            
            # Display the highlight overlay
            ctx.Display(highlight_ais, False)
            
            # Store the overlay so we can remove it later
            self._highlight_overlays[rid] = highlight_ais
            
        except Exception as e:
            # If overlay creation fails, fallback to traditional highlighting
            print(f"Failed to create face highlight overlay for {rid}: {e}")
            etype = self._get_entity_type(rid)
            if etype == 'face':
                r, g, b = self.highlight_rgb
                if 'Quantity_TOC_RGB' in globals() and Quantity_TOC_RGB is not None:
                    qcol = Quantity_Color(r, g, b, Quantity_TOC_RGB)
                else:
                    qcol = Quantity_Color(Quantity_NOC_RED)
                ctx = self.display.Context
                ctx.SetColor(original_ais, qcol, False)
    def _create_wire_highlight_overlay(self, rid: str, original_ais):
        """Create a separate highlight overlay for wires"""
        try:
            # Get the shape from the entity registry
            if not self.entity_registry:
                return
            shape = self.entity_registry.get_shape(rid)
            if shape is None:
                return
                
            # Create a new AIS object for the highlight overlay
            highlight_ais = AIS_Shape(shape)
            
            # Set highlight color (black for wires to match edges)
            r, g, b = self.highlight_rgb_edges
            if 'Quantity_TOC_RGB' in globals() and Quantity_TOC_RGB is not None:
                qcol = Quantity_Color(r, g, b, Quantity_TOC_RGB)
            else:
                qcol = Quantity_Color(Quantity_NOC_BLACK)
            
            ctx = self.display.Context
            ctx.SetColor(highlight_ais, qcol, False)
            ctx.SetWidth(highlight_ais, self.highlight_width, True)  # Thicker for highlighting
            
            # Display the highlight overlay
            ctx.Display(highlight_ais, False)
            
            # Store the overlay so we can remove it later
            self._highlight_overlays[rid] = highlight_ais
            
        except Exception as e:
            # If overlay creation fails, fallback to traditional highlighting
            print(f"Failed to create wire highlight overlay for {rid}: {e}")
            etype = self._get_entity_type(rid)
            if etype == 'wire':
                r, g, b = self.highlight_rgb_edges
                if 'Quantity_TOC_RGB' in globals() and Quantity_TOC_RGB is not None:
                    qcol = Quantity_Color(r, g, b, Quantity_TOC_RGB)
                else:
                    qcol = Quantity_Color(Quantity_NOC_BLACK)
                ctx = self.display.Context
                ctx.SetColor(original_ais, qcol, False)
                ctx.SetWidth(original_ais, self.highlight_width, True)

__all__ = ['SelectionManager']
