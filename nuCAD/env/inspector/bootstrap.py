"""Bootstrap helpers to enable the inspector in one line.

Usage:
    from nuCAD.env.inspector import enable_cad_inspector
    enable_cad_inspector(env)  # patches env.step to auto-sync & refresh

Returned tuple: (registry, selection_manager, panel)
"""
from __future__ import annotations
from typing import Tuple
from .inspector_registry import EntityRegistry
from .selection_manager import SelectionManager
from .inspector_panel import create_inspector, ensure_qt_app


def enable_cad_inspector(env, *, multi_select: bool = True, show: bool = True, auto_refresh: bool = True):
    """Enable the inspector subsystem for an environment in one call.

    Parameters
    ----------
    env : nuCADEnv
        The environment instance (must have env.renderer.display when viz=True).
    multi_select : bool
        Allow multi-selection toggling in the panel/viewer.
    show : bool
        Show the Qt panel (no-op if Qt unavailable).
    auto_refresh : bool
        If True, wraps env.step so registry + panel sync automatically.

    Returns
    -------
    (EntityRegistry, SelectionManager, EntityListPanel | stub)
    """
    if not getattr(env, 'viz', False):
        raise RuntimeError('Inspector requires env.viz=True (viewer active).')

    registry = EntityRegistry()
    ensure_qt_app()
    sel = SelectionManager(env.renderer.display, on_select_id=lambda rid: None, multi_select=multi_select)
    sel.entity_registry = registry
    sel.renderer = env.renderer
    
    # Connect the renderer to the selection manager for bidirectional selection
    if hasattr(env.renderer, 'set_selection_manager'):
        env.renderer.set_selection_manager(sel)
    
    # Connect selection manager's AIS tracking to the renderer's tracking
    if hasattr(env.renderer, 'id_to_ais') and hasattr(env.renderer, 'ais_hash_to_id'):
        sel._id_to_ais = env.renderer.id_to_ais
        sel._ais_hash_to_id = env.renderer.ais_hash_to_id
    
    # Pass state provider so panel can build hierarchy directly from env.state
    state_provider = lambda: getattr(env, 'state', None)
    panel = create_inspector(env.renderer, sel, show=show)
    try:
        # If panel supports state provider, set it
        if hasattr(panel, '_state_provider'):
            panel._state_provider = state_provider
    except Exception:
        pass

    # Bind cross-callback for visual sync
    if panel is not None:
        sel.on_select_id = getattr(panel, 'on_external_selection', lambda rid: None)

    # Attach to env for convenience
    env.entity_registry = registry
    env.selection_manager = sel
    env.inspector_panel = panel

    if auto_refresh:
        orig_step = env.step
        def wrapped_step(action):
            result = orig_step(action)
            try:
                registry.sync(env.state)
                sel.refresh_from_renderer(env.renderer)
                if panel:
                    panel.refresh_ids([])
            except Exception:
                pass
            return result
        # Avoid double-wrapping
        if getattr(env.step, '__name__', '') != 'wrapped_step':
            env.step = wrapped_step  # type: ignore

    # Initial sync after env.reset() should be done by user OR call here if state exists
    try:
        if getattr(env, 'state', None):
            registry.sync(env.state)
            sel.refresh_from_renderer(env.renderer)
            if panel:
                panel.refresh_ids([])
    except Exception:
        pass

    return registry, sel, panel

__all__ = ['enable_cad_inspector']
