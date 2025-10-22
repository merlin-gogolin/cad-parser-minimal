from __future__ import annotations
from typing import List, Optional, Callable, Dict

_QT_BINDING = None
try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QApplication, QTreeWidget, QTreeWidgetItem
    from PySide6.QtCore import Qt
    _QT_BINDING = 'PySide6'
except Exception:
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication, QTreeWidget, QTreeWidgetItem
        from PyQt5.QtCore import Qt
        _QT_BINDING = 'PyQt5'
    except Exception:
        _QT_BINDING = None

_QT_AVAILABLE = _QT_BINDING is not None

def ensure_qt_app():
    if not _QT_AVAILABLE:
        return None
    app = QApplication.instance()
    if app is None:
        import os
        if 'DISPLAY' not in os.environ and 'QT_QPA_PLATFORM' not in os.environ:
            os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        try:
            app = QApplication([])
        except Exception as e:
            print(f"[WARN] Could not start Qt app: {e}")
            return None
    return app

if _QT_AVAILABLE:
    class EntityListPanel(QWidget):
        CATEGORY_ORDER = ["Solids", "Faces", "Edges", "Wires", "Other"]
        PREFIX_TO_CAT = {'s': 'Solids', 'f': 'Faces', 'e': 'Edges', 'w': 'Wires'}
        def __init__(self, renderer, selection_manager, parent=None, on_selection_changed: Optional[Callable[[str], None]] = None, state_provider: Optional[Callable[[], object]] = None):
            ensure_qt_app()
            super().__init__(parent)
            self.setWindowTitle(f"CAD Entities ({_QT_BINDING})")
            self._renderer = renderer
            self._sel_mgr = selection_manager
            if hasattr(self._sel_mgr, 'multi_select'):
                self._sel_mgr.multi_select = True
            self._on_selection_changed = on_selection_changed
            if hasattr(self._sel_mgr, 'on_selection_changed_set'):
                self._sel_mgr.on_selection_changed_set = self.on_selection_set_change
            self._state_provider = state_provider
            self._tree = QTreeWidget()
            self._tree.setHeaderHidden(True)
            self._tree.setSelectionMode(QTreeWidget.ExtendedSelection)
            self._tree.setAlternatingRowColors(True)
            self._tree.itemClicked.connect(self._on_item_clicked)
            try:
                self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)  # type: ignore
            except Exception:
                pass
            lay = QVBoxLayout(self)
            lay.setContentsMargins(6, 6, 6, 6)
            lay.setSpacing(4)
            lay.addWidget(self._tree)
            self.setMinimumSize(300, 600)
            self.resize(340, 720)
            self.setStyleSheet("""
                QWidget { background: #1e1f24; color: #d5d9e0; font-family: 'Segoe UI', 'Helvetica', Arial; font-size: 11pt; }
                QTreeWidget { border: 1px solid #2c313c; background: #23272e; alternate-background-color: #28313a; }
                QTreeWidget::item { height: 22px; }
                QTreeWidget::item:selected { background: #2d6cdf; color: #ffffff; }
                QTreeWidget::item:hover { background: #304050; }
            """)
            self._cat_items: Dict[str, QTreeWidgetItem] = {}
            # Support multiple visual items for the same ID (appearing in both flat and hierarchical views)
            self._id_items: Dict[str, List[QTreeWidgetItem]] = {}
            self._build_category_roots()
        def _build_category_roots(self):
            self._tree.clear()
            self._cat_items.clear()
            for cat in self.CATEGORY_ORDER:
                root = QTreeWidgetItem([f"{cat} (0)"])
                root.setData(0, Qt.UserRole, cat)
                root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
                font = root.font(0)
                font.setPointSize(font.pointSize() + 1)
                font.setBold(True)
                root.setFont(0, font)
                self._tree.addTopLevelItem(root)
                # Don't auto-expand category roots - let user expand as needed
                # root.setExpanded(True)
                self._cat_items[cat] = root
            self._id_items.clear()
        def _category_for_id(self, rid: str) -> str:
            # Per-solid entities (s0f1, s0e10, etc.) should go under Solids category only
            if rid.startswith('s'):
                return 'Solids'
            # Standalone entities (f0, e0, w0) go to their respective categories
            return self.PREFIX_TO_CAT.get(rid[:1], 'Other')
        def _add_id_item(self, parent: QTreeWidgetItem, rid: str) -> QTreeWidgetItem:
            child = QTreeWidgetItem([rid])
            parent.addChild(child)
            self._id_items.setdefault(rid, []).append(child)
            return child
        def refresh_ids(self, ids: List[str]):
            reg_ids = ids
            reg = None
            if hasattr(self._sel_mgr, 'entity_registry') and self._sel_mgr.entity_registry:
                try:
                    reg = self._sel_mgr.entity_registry
                    reg_ids = [rec.id for rec in reg.records()]
                except Exception:
                    pass
            self._build_category_roots()
            # Flat groups
            grouped: Dict[str, List[str]] = {c: [] for c in self.CATEGORY_ORDER}
            for rid in reg_ids:
                cat = self._category_for_id(rid)
                grouped.setdefault(cat, []).append(rid)
            # Build hierarchical Solids -> Faces -> Edges using state if available
            state = self._state_provider() if callable(self._state_provider) else None
            solids_from_state = getattr(state, 'solids', None) if state is not None else None
            for cat, items in grouped.items():
                parent = self._cat_items.get(cat)
                if not parent:
                    continue
                if cat == 'Solids':
                    if solids_from_state is not None:
                        solids_list = list(solids_from_state)
                        if not solids_list:
                            placeholder = QTreeWidgetItem(["(empty)"])
                            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
                            parent.addChild(placeholder)
                        else:
                            for solid in solids_list:
                                sid = getattr(solid, 'id', None)
                                if not sid:
                                    continue
                                solid_item = self._add_id_item(parent, sid)
                                # Faces under solid
                                faces = getattr(solid, 'faces', []) or []
                                if faces:
                                    for face in faces:
                                        fid = getattr(face, 'id', None)
                                        if not fid:
                                            continue
                                        face_item = self._add_id_item(solid_item, fid)
                                        # Edges under face
                                        fedges = getattr(face, 'edges', []) or []
                                        if fedges:
                                            for edge in fedges:
                                                eid = getattr(edge, 'id', None)
                                                if not eid:
                                                    continue
                                                self._add_id_item(face_item, eid)
                                        else:
                                            ph = QTreeWidgetItem(["(none)"])
                                            ph.setFlags(ph.flags() & ~Qt.ItemIsSelectable)
                                            face_item.addChild(ph)
                                else:
                                    ph = QTreeWidgetItem(["(none)"])
                                    ph.setFlags(ph.flags() & ~Qt.ItemIsSelectable)
                                    solid_item.addChild(ph)
                                # Don't auto-expand solid items
                                # solid_item.setExpanded(True)
                    else:
                        # Fallback: show only solids from flat ids
                        solids = [rid for rid in items if 'f' not in rid[1:] and 'e' not in rid[1:]]
                        if not solids:
                            placeholder = QTreeWidgetItem(["(empty)"])
                            placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
                            parent.addChild(placeholder)
                        else:
                            for sid in sorted(solids):
                                self._add_id_item(parent, sid)
                else:
                    # Flat categories remain
                    if not items:
                        placeholder = QTreeWidgetItem(["(empty)"])
                        placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
                        parent.addChild(placeholder)
                    else:
                        for rid in items:
                            self._add_id_item(parent, rid)
                base_name = parent.data(0, Qt.UserRole)
                # Count solids accurately from state if available
                if cat == 'Solids':
                    count = len(solids_from_state) if solids_from_state is not None else len([rid for rid in grouped.get('Solids', []) if 'f' not in rid[1:] and 'e' not in rid[1:]])
                else:
                    count = len(items)
                parent.setText(0, f"{base_name} ({count})")
            self._apply_visual_selection_state()
            # Don't expand all items by default - let user expand as needed
            # self._tree.expandAll()
        def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
            rid = item.text(0)
            if rid in self.CATEGORY_ORDER or rid in ("Faces", "Edges", "(empty)", "(none)"):
                return
            self._sel_mgr.select_id(rid)
            if self._on_selection_changed: self._on_selection_changed(rid)
            self._apply_visual_selection_state()
        def _on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
            rid = item.text(0)
            if rid in self.CATEGORY_ORDER or rid in ("Faces", "Edges", "(empty)", "(none)"):
                return
            if hasattr(self._sel_mgr, 'deselect_id'):
                self._sel_mgr.deselect_id(rid)
            self._apply_visual_selection_state()
        def on_external_selection(self, rid: str):
            self._apply_visual_selection_state()
        def on_selection_set_change(self, selected_ids: List[str]):
            self._apply_visual_selection_state()
        def _apply_visual_selection_state(self):
            sel_ids = set(self._sel_mgr.get_selected_ids()) if hasattr(self._sel_mgr, 'get_selected_ids') else set()
            self._tree.clearSelection()
            for rid, items in self._id_items.items():
                for item in items:
                    font = item.font(0)
                    if rid in sel_ids:
                        font.setBold(True)
                        item.setFont(0, font)
                        item.setSelected(True)
                    else:
                        font.setBold(False)
                        item.setFont(0, font)
                        item.setSelected(False)
else:
    class EntityListPanel:  # fallback stub
        def __init__(self, *a, **k):
            print('[WARN] No Qt binding available; inspector disabled.')
        def refresh_ids(self, ids: List[str]):
            pass
        def on_external_selection(self, rid: str):
            pass

def create_inspector(renderer, selection_manager, show: bool = True) -> EntityListPanel:
    panel = EntityListPanel(renderer, selection_manager)
    if _QT_AVAILABLE and show:
        app = ensure_qt_app()
        try:
            panel.show()
        except Exception as e:
            print(f"[WARN] Could not show panel: {e}")
    return panel

__all__ = ['EntityListPanel', 'create_inspector', 'ensure_qt_app']
