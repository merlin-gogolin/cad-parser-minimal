"""Inspector & selection subsystem.

Public re-exports:
  - EntityRegistry / EntityRecord
  - SelectionManager
  - EntityListPanel, create_inspector, ensure_qt_app

The package is optional; core env logic does not depend on Qt.
"""

from .inspector_registry import EntityRegistry, EntityRecord
from .selection_manager import SelectionManager
from .inspector_panel import EntityListPanel, create_inspector, ensure_qt_app
from .bootstrap import enable_cad_inspector

__all__ = [
    'EntityRegistry', 'EntityRecord', 'SelectionManager',
    'EntityListPanel', 'create_inspector', 'ensure_qt_app',
    'enable_cad_inspector'
]
