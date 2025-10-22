import os
import time
import math
from typing import Sequence
import imageio
from PIL import Image

from OCC.Display.SimpleGui import init_display
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeSphere
from OCC.Core.gp import gp_Pnt, gp_Ax1
from OCC.Core.Quantity import (
                        Quantity_Color, 
                        Quantity_NOC_BLACK, 
                        Quantity_NOC_WHITE, 
                        Quantity_NOC_BLUE1,
                        Quantity_NOC_LIGHTBLUE
                    )   
from .actions import (
    AddSketch, AddLine, AddArc, AddCircle, AddEllipse, 
    AddSpline, AddBezier, 
    CloseProfile, MakeFace, Extrude, Fillet, Revolve
    )
from .geometry.sketch_operations import _to_global_3d


# ----------------------------------------------------------------------
# util: accept (x,y) or (x,y,z) and return xyz
# ----------------------------------------------------------------------
def _as_xyz(pt: Sequence[float]) -> tuple[float, float, float]:          
    if len(pt) == 3:
        return tuple(pt)
    if len(pt) == 2:
        return pt[0], pt[1], 0.0
    raise ValueError("Point must be length-2 or length-3")


def _rot_z(vec: Sequence[float], deg: float) -> tuple[float, float, float]:
    """Rotate a 3D vector about Z by deg degrees (Z component unchanged)."""
    x, y = vec[0], vec[1]
    z = vec[2] if len(vec) > 2 else 0.0
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c, z)



class nuCADRenderer:
    def label_faces_and_edges(self, solid_id, env):
        """
        Label all faces and edges of the given solid in the viewer.
        Usage: renderer.label_faces_and_edges('s0', env)
        """
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.BRepGProp import brepgprop
        from OCC.Core.gp import gp_Pnt
        face_ids = list(env.list_faces(solid_id))
        edge_ids = list(env.list_edges(solid_id))
        for i, fid in enumerate(face_ids):
            face_shape = env.list_faces(solid_id)[fid].shape
            props = GProp_GProps()
            brepgprop.SurfaceProperties(face_shape, props)
            c = props.CentreOfMass()
            self.display.DisplayMessage(gp_Pnt(c.X(), c.Y(), c.Z()), f"F{i}")
        for i, eid in enumerate(edge_ids):
            edge_shape = env.list_edges(solid_id)[eid].shape
            props = GProp_GProps()
            brepgprop.LinearProperties(edge_shape, props)
            c = props.CentreOfMass()
            self.display.DisplayMessage(gp_Pnt(c.X(), c.Y(), c.Z()), f"E{i}")
    
    def __init__(self, render_setting=None):
        self.display, self.start_display, _, _ = init_display()

        # Default settings (isometric view)
        default_setting = {
            # Isometric projection direction and a proper orthogonal up vector
            "proj":  (1, 1, 1),
            "up":    (-1, 1, 0),
            "at":    (0, 0, 0),
            "eye":   (3, 3, 3),
            "scale": 100.0,
            "delay": 0.25,
            # Slight yaw to the right by default (negative yaw = right/clockwise when looking from +Z)
            "yaw_deg": 40.0,
            "background_color": "white",  # New option for background color
            # Transparency settings for different geometry types
            "solid_transparency": 0.1,  # Transparency for solids (0.0 = opaque, 1.0 = fully transparent)
            "face_transparency": 0.2,   # Transparency for faces
            "edge_transparency": 0.0,   # Transparency for edges (usually kept opaque)
            "wire_transparency": 0.0,   # Transparency for wires (usually kept opaque)
            # Rendering visibility controls
            "show_solids": True,
            "show_faces": True,
            "show_edges": True,
            "show_wires": True,
            "show_points": False,
            "show_action_points": False,  # Points from the last action
        }
        
        # Merge user settings with defaults
        if render_setting:
            setting = {**default_setting, **render_setting}
        else:
            setting = default_setting

        # Store visibility settings
        self.show_solids = setting["show_solids"]
        self.show_faces = setting["show_faces"]
        self.show_edges = setting["show_edges"]
        self.show_wires = setting["show_wires"]
        self.show_points = setting["show_points"]
        self.show_action_points = setting["show_action_points"]
        
        # Store transparency settings
        self.solid_transparency = setting["solid_transparency"]
        self.face_transparency = setting["face_transparency"]
        self.edge_transparency = setting["edge_transparency"]
        self.wire_transparency = setting["wire_transparency"]

        v = self.display.View
        # Apply optional yaw rotation around Z to proj and up
        yaw = float(setting.get("yaw_deg", 0.0) or 0.0)
        proj_vec = _rot_z(setting["proj"], yaw) if abs(yaw) > 1e-9 else setting["proj"]
        up_vec = _rot_z(setting["up"], yaw) if abs(yaw) > 1e-9 else setting["up"]
        # Store for later adjustments
        self._proj = proj_vec
        self._up = up_vec
        v.SetProj(*proj_vec)
        v.SetUp(*up_vec)
        v.SetAt(*setting["at"])
        v.SetEye(*setting["eye"])
        v.SetScale(setting["scale"]) 
        
        # Set background color or transparency
        bg_color = setting.get("background_color", "white")
        if bg_color.lower() == "transparent":
            # Try multiple methods for transparent background
            try:
                # Method 1: Disable background completely
                v.SetBackgroundImage(None)
                
                # Method 2: Set background style to none
                from OCC.Core.Aspect import Aspect_FM_NONE
                v.SetBgImageStyle(Aspect_FM_NONE)
                
                # Method 3: Try to make background "invisible" 
                # Use a neutral light gray that works well with most desktop backgrounds
                from OCC.Core.Quantity import Quantity_TOC_RGB
                neutral_gray = Quantity_Color(0.94, 0.94, 0.94, Quantity_TOC_RGB)
                v.SetBgGradientColors(neutral_gray, neutral_gray, False)
                
                print("[INFO] Transparent background enabled (light gray fallback for compatibility)")
                    
            except Exception as e:
                # Fallback: Use light neutral gray
                print(f"[INFO] Using fallback background for transparency. Details: {e}")
                from OCC.Core.Quantity import Quantity_TOC_RGB
                fallback_gray = Quantity_Color(0.92, 0.92, 0.92, Quantity_TOC_RGB)
                v.SetBgGradientColors(fallback_gray, fallback_gray, False)
        elif bg_color.lower() == "white":
            # Set pure white background with multiple methods to ensure it sticks
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_WHITE), 
                Quantity_Color(Quantity_NOC_WHITE),
                False  # No gradient, just solid white
            )
            
            # Additional method: Set background color directly
            try:
                v.SetBackgroundColor(Quantity_Color(Quantity_NOC_WHITE))
            except:
                pass
                
            # Additional method: Disable any background image
            try:
                v.SetBackgroundImage(None)
            except:
                pass
                
            # Additional method: Set background style to solid color
            try:
                from OCC.Core.Aspect import Aspect_FM_CENTERED
                v.SetBgImageStyle(Aspect_FM_CENTERED)
            except:
                pass
        
        elif bg_color.lower() == "black":
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_BLACK), 
                Quantity_Color(Quantity_NOC_BLACK),
                False
            )
            print("[INFO] BLACK background set")
        elif bg_color.lower() == "blue":
            from OCC.Core.Quantity import Quantity_NOC_LIGHTBLUE
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_LIGHTBLUE), 
                Quantity_Color(Quantity_NOC_LIGHTBLUE),
                False
            )
            print("[INFO] BLUE background set")
        else:
            # Default to white for unknown colors
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_WHITE), 
                Quantity_Color(Quantity_NOC_WHITE),
                False
            )
            print(f"[INFO] Unknown background '{bg_color}', defaulting to WHITE")

        self.delay = setting["delay"]
        self._ais_objects: list[AIS_Shape] = []
        self._all_shapes = []

        # Store background color setting for enforcement during render
        self.background_color = bg_color

        self.frame_dir = "frames"
        os.makedirs(self.frame_dir, exist_ok=True)
        self.frame_count = 0

        # AIS object tracking for selection
        self.id_to_ais = {}  # Maps entity IDs to AIS objects
        self.ais_hash_to_id = {}  # Maps AIS handle hashes to entity IDs
        self._selection_callbacks = []  # List of selection callback functions
        self._selection_manager = None  # Reference to the selection manager for bidirectional selection
        
        # Coordinate axes tracking
        self._coordinate_axes = []  # Track coordinate axes AIS objects for removal
        
        # Setup mouse selection callback
        self._setup_selection_callback()

    def set_isometric_view(self):
        """Switch the current view to a standard isometric orientation."""
        try:
            v = self.display.View
            v.SetProj(1.0, 1.0, 1.0)
            v.SetUp(-1.0, 1.0, 0.0)
            self._proj = (1.0, 1.0, 1.0)
            self._up = (-1.0, 1.0, 0.0)
            v.SetAt(0.0, 0.0, 0.0)
            # Keep current eye distance if available; else use a reasonable default
            try:
                # Some OCC builds support Eye() getter; if not, just set a default
                ex, ey, ez = 3.0, 3.0, 3.0
                v.SetEye(ex, ey, ez)
            except Exception:
                v.SetEye(3.0, 3.0, 3.0)
            # Optionally maintain scale
            # v.FitAll()  # Uncomment if you prefer auto-fit after switching
        except Exception:
            pass

    def rotate_yaw(self, deg: float):
        """Rotate current view around world Z by deg degrees; positive is CCW, negative is to the right."""
        try:
            self._proj = _rot_z(self._proj, deg)
            self._up = _rot_z(self._up, deg)
            v = self.display.View
            v.SetProj(*self._proj)
            v.SetUp(*self._up)
        except Exception:
            pass

    def nudge_right(self, deg: float = 10.0):
        """Convenience: rotate a small amount towards the right (clockwise viewed from +Z)."""
        self.rotate_yaw(-abs(deg))

    def _setup_selection_callback(self):
        """Setup mouse selection callback for the 3D viewer"""
        try:
            # Enable selection mode for the context
            ctx = self.display.Context
            
            # Ensure selection is enabled
            try:
                # For modern OCC versions
                ctx.SetSelectionSensitivity(True)
                ctx.SetPickingStrategy(0)  # Enable picking
                
                # Activate different selection modes
                # Mode 0: whole shape, Mode 1: edges, Mode 2: faces
                for mode in [0, 1, 2]:
                    try:
                        ctx.SetSelectionModeActive(mode, True)
                    except:
                        pass
                        
            except Exception:
                # Try legacy approach
                try:
                    ctx.OpenLocalContext()
                    from OCC.Core.AIS import AIS_Shape
                    ctx.ActivateStandardMode(AIS_Shape.GetType())
                    # Activate selection modes
                    ctx.ActivateStandardMode(0)  # Shape selection
                    ctx.ActivateStandardMode(1)  # Edge selection  
                    ctx.ActivateStandardMode(2)  # Face selection
                except Exception:
                    pass
                    
            # Make sure the viewer allows selection
            try:
                view = self.display.View
                view.SetComputedMode(False)
            except:
                pass
        
        except Exception:
            pass
        
        # Register the selection callback - this is crucial for mouse interaction
        if hasattr(self.display, 'register_select_callback'):
            self.display.register_select_callback(self._on_mouse_select)
        
        # Always patch display for better selection support
        self._patch_display_for_selection()

    def _patch_display_for_selection(self):
        """Add selection callback support to the display object"""
        # Store original mouse button handlers if they exist
        original_select = getattr(self.display, '_select_callback', None)
        
        def patched_select_callback():
            # Call original callback if it exists
            if original_select:
                try:
                    original_select()
                except Exception:
                    pass
            # Call our callbacks
            self._on_mouse_select()
        
        # Replace the callback
        self.display._select_callback = patched_select_callback
        
        # Try to hook into the Qt widget's mouse events more directly
        try:
            # For Qt-based displays
            if hasattr(self.display, '_display') and hasattr(self.display._display, 'mousePressEvent'):
                original_mouse_press = self.display._display.mousePressEvent
                original_mouse_release = self.display._display.mouseReleaseEvent
                
                def patched_mouse_press(event):
                    # Call original handler first
                    try:
                        original_mouse_press(event)
                    except Exception:
                        pass
                
                def patched_mouse_release(event):
                    # Call original handler first
                    try:
                        original_mouse_release(event)
                    except Exception:
                        pass
                    # Then check for selection after mouse release (this is when selection happens)
                    if event.button() == 1:  # Left mouse button
                        # Small delay to ensure selection is processed
                        try:
                            from PySide6.QtCore import QTimer
                            QTimer.singleShot(50, self._on_mouse_select)  # 50ms delay
                        except:
                            try:
                                from PyQt5.QtCore import QTimer
                                QTimer.singleShot(50, self._on_mouse_select)  # 50ms delay
                            except:
                                # Fallback: call immediately
                                self._on_mouse_select()
                
                self.display._display.mousePressEvent = patched_mouse_press
                self.display._display.mouseReleaseEvent = patched_mouse_release
                
        except Exception:
            pass

    def register_select_callback(self, callback):
        """Register a callback function to be called when objects are selected in the 3D viewer"""
        if callback not in self._selection_callbacks:
            self._selection_callbacks.append(callback)

    def set_selection_manager(self, selection_manager):
        """Set the selection manager for bidirectional selection"""
        self._selection_manager = selection_manager

    def _on_mouse_select(self, selected_shapes=None, x=None, y=None):
        """Handle mouse selection events in the 3D viewer"""
        try:
            # Get currently selected objects from the context
            ctx = self.display.Context
            selected_ids = []
            
            # If we have selected_shapes passed from the callback, use those
            if selected_shapes:
                for shape in selected_shapes:
                    # Find the corresponding AIS object for this shape
                    for entity_id, ais_obj in self.id_to_ais.items():
                        try:
                            if hasattr(ais_obj, 'Shape') and ais_obj.Shape().IsEqual(shape):
                                selected_ids.append(entity_id)
                                break
                        except Exception:
                            continue
            else:
                # Fallback: iterate through selected objects in context
                ctx.InitSelected()
                while ctx.MoreSelected():
                    try:
                        selected_obj = ctx.SelectedInteractive()
                        # Look up the entity ID for this AIS object
                        ais_hash = hash(selected_obj.GetHandle())
                        entity_id = self.ais_hash_to_id.get(ais_hash)
                        if entity_id:
                            selected_ids.append(entity_id)
                    except Exception:
                        pass
                    ctx.NextSelected()
            
            # If we have a selection manager and selected IDs, update the selection
            if self._selection_manager and selected_ids:
                for entity_id in selected_ids:
                    # For faces, use force highlight to ensure proper pink highlighting
                    if entity_id.startswith('f') or 'f' in entity_id:
                        # Check if it's currently selected - if so, deselect it
                        if entity_id in self._selection_manager._selected_ids:
                            self._selection_manager.deselect_id(entity_id)
                        else:
                            self._selection_manager.force_highlight_id(entity_id)
                    else:
                        # For edges and other entities, use normal selection
                        self._selection_manager.select_id(entity_id)
            
            # Call all registered callbacks with the selected IDs
            for callback in self._selection_callbacks:
                try:
                    callback(selected_ids)
                except Exception:
                    pass
                    
        except Exception:
            pass

    def _register_ais_object(self, ais_shape, entity_id):
        """Register an AIS shape with an entity ID for selection tracking"""
        self.id_to_ais[entity_id] = ais_shape
        try:
            ais_hash = hash(ais_shape.GetHandle())
            self.ais_hash_to_id[ais_hash] = entity_id
        except Exception:
            pass

    def _enforce_background_color(self):
        """Enforce the background color setting - call during render to prevent reversion."""
        v = self.display.View
        bg_color = self.background_color
        
        if bg_color.lower() == "transparent":
            # Transparent background
            try:
                v.SetBackgroundImage(None)
                from OCC.Core.Aspect import Aspect_FM_NONE
                v.SetBgImageStyle(Aspect_FM_NONE)
                from OCC.Core.Quantity import Quantity_TOC_RGB
                neutral_gray = Quantity_Color(0.94, 0.94, 0.94, Quantity_TOC_RGB)
                v.SetBgGradientColors(neutral_gray, neutral_gray, False)
            except Exception as e:
                print(f"[DEBUG] Error enforcing transparent background: {e}")
                
        elif bg_color.lower() == "white":
            # Pure white background - multiple enforcement methods
            try:
                v.SetBgGradientColors(
                    Quantity_Color(Quantity_NOC_WHITE), 
                    Quantity_Color(Quantity_NOC_WHITE),
                    False
                )
                v.SetBackgroundColor(Quantity_Color(Quantity_NOC_WHITE))
                v.SetBackgroundImage(None)
                from OCC.Core.Aspect import Aspect_FM_CENTERED
                v.SetBgImageStyle(Aspect_FM_CENTERED)
            except Exception as e:
                print(f"[DEBUG] Error enforcing white background: {e}")
                
        elif bg_color.lower() == "black":
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_BLACK), 
                Quantity_Color(Quantity_NOC_BLACK),
                False
            )
        elif bg_color.lower() == "blue":
            from OCC.Core.Quantity import Quantity_NOC_LIGHTBLUE
            v.SetBgGradientColors(
                Quantity_Color(Quantity_NOC_LIGHTBLUE), 
                Quantity_Color(Quantity_NOC_LIGHTBLUE),
                False
            )

    def display_coordinate_axes(self, length=100.0, thickness=2.0):
        """Display coordinate axes at the origin with X=red, Y=green, Z=blue"""
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Vec
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCC.Core.gp import gp_Trsf
        from OCC.Core.Quantity import Quantity_NOC_RED, Quantity_NOC_GREEN, Quantity_NOC_BLUE
        
        # Clear any existing axes first
        self.hide_coordinate_axes()
        
        # Create origin point
        origin = gp_Pnt(0, 0, 0)
        
        # X-axis (red) - cylinder along X direction
        x_axis = BRepPrimAPI_MakeCylinder(thickness/2, length).Shape()
        x_transform = gp_Trsf()
        x_transform.SetRotation(gp_Ax1(origin, gp_Dir(0, 1, 0)), math.pi/2)
        x_axis_transformed = BRepBuilderAPI_Transform(x_axis, x_transform).Shape()
        x_ais = AIS_Shape(x_axis_transformed)
        x_ais.SetColor(Quantity_Color(Quantity_NOC_RED))
        self.display.Context.Display(x_ais, True)
        
        # Y-axis (green) - cylinder along Y direction
        y_axis = BRepPrimAPI_MakeCylinder(thickness/2, length).Shape()
        y_transform = gp_Trsf()
        y_transform.SetRotation(gp_Ax1(origin, gp_Dir(1, 0, 0)), -math.pi/2)
        y_axis_transformed = BRepBuilderAPI_Transform(y_axis, y_transform).Shape()
        y_ais = AIS_Shape(y_axis_transformed)
        y_ais.SetColor(Quantity_Color(Quantity_NOC_GREEN))
        self.display.Context.Display(y_ais, True)
        
        # Z-axis (blue) - cylinder already pointing up
        z_axis = BRepPrimAPI_MakeCylinder(thickness/2, length).Shape()
        z_ais = AIS_Shape(z_axis)
        z_ais.SetColor(Quantity_Color(Quantity_NOC_BLUE))
        self.display.Context.Display(z_ais, True)
        
        # Store references for later removal
        self._coordinate_axes.extend([x_ais, y_ais, z_ais])
        
        # Redraw to show the axes
        self.display.View.Redraw()

    def hide_coordinate_axes(self):
        """Hide coordinate axes"""
        if hasattr(self, '_coordinate_axes') and self._coordinate_axes:
            for axis_ais in self._coordinate_axes:
                try:
                    self.display.Context.Erase(axis_ais, True)
                except Exception:
                    pass  # Ignore errors if already removed
            self._coordinate_axes.clear()
            self.display.View.Redraw()

    # ------------------------------------------------------------------
    # camera helpers
    # ------------------------------------------------------------------
    def center_camera_on(self, shape):
        box = Bnd_Box()
        brepbndlib_Add(shape, box)
        xmi, ymi, zmi, xma, yma, zma = box.Get()
        cx, cy, cz = (xmi + xma) / 2, (ymi + yma) / 2, (zmi + zma) / 2
        v = self.display.View
        v.SetAt(cx, cy, cz)
        v.SetEye(cx + 3, cy - 3, cz + 3)

    # ------------------------------------------------------------------
    # primitive drawing
    # ------------------------------------------------------------------
    def _display_filled_sphere(self, pt, radius=0.05):
        x, y, z = _to_global_3d(*pt) if len(pt) == 2 else pt
        sph   = BRepPrimAPI_MakeSphere(gp_Pnt(x, y, z), radius).Shape()
        ais   = AIS_Shape(sph)
        ctx   = self.display.Context
        ctx.SetColor(ais, Quantity_Color(Quantity_NOC_BLACK), False)
        ctx.Display(ais, False)
        self._ais_objects.append(ais)


    def capture_frame(self):
        img_path = os.path.join(self.frame_dir, f"frame_{self.frame_count:04d}.png")
        self.display.View.Dump(img_path)
        self.frame_count += 1

    # ------------------------------------------------------------------
    # main entry
    # ------------------------------------------------------------------
    def render(self, current_shape, last_action, state, active_sketch):
        
        # Enforce background color at the start of each render
        self._enforce_background_color()

        if current_shape is None:
            self.capture_frame()
            return

        ctx       = self.display.Context
        ais_shape = AIS_Shape(current_shape)

        # --------------------------------------------------------------
        # highlight logic depending on last_action
        # --------------------------------------------------------------
        
        if isinstance(last_action, AddLine):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            self._display_filled_sphere(last_action.starsave_vt)
            self._display_filled_sphere(last_action.end)

        elif isinstance(last_action, AddArc):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            for pt in last_action.points:
                self._display_filled_sphere(pt)

        elif isinstance(last_action, AddCircle):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            self._display_filled_sphere(last_action.center)

        elif isinstance(last_action, AddEllipse):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            self._display_filled_sphere(last_action.center)


        elif isinstance(last_action, AddSpline):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            for pt in last_action.points:
                self._display_filled_sphere(pt)


        elif isinstance(last_action, AddBezier):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
            ctx.SetWidth(ais_shape, 3.0, True)
            for pt in last_action.control_points:
                self._display_filled_sphere(pt)


        if isinstance(last_action, CloseProfile):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLUE1), False)
            ctx.SetWidth(ais_shape, 3.0, True)

            last_wid = state.sketches[active_sketch["id"]]["wires"][-1]
            edge_ids = state.wires[last_wid]["edges"]
            for eid in edge_ids:
                edge = state.edges[eid]
                self._display_filled_sphere(edge["start"])
                self._display_filled_sphere(edge["end"])

        elif isinstance(last_action, MakeFace):
            ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLUE1), False)
            ctx.SetDisplayMode(ais_shape, 0, False)
            ctx.SetTransparency(ais_shape, 0.75, False)

            # Get exact wire and edge info
            fid = next(reversed(state.faces))
            edge_ids = state.faces[fid]["edges"]
            for eid in edge_ids:
                edge = state.edges[eid]
                if "start" in edge:
                    self._display_filled_sphere(edge["start"])
                if "end" in edge:
                    self._display_filled_sphere(edge["end"])


        elif isinstance(last_action, Fillet):
            self.clear()

        elif isinstance(last_action, Revolve):
            self.clear()


        ais_shape.SetPolygonOffsets(True)
        ais_shape.SetPolygonOffsets(1, 1.0)


        ctx.Display(ais_shape, False)
        self._ais_objects.append(ais_shape)
        self._all_shapes.append(current_shape)

        # auto-center camera after the first solid is made              # 🆕 optional tweak
        # self.center_camera_on(current_shape)
        self.center_camera_on_all_shapes()

        # if isinstance(last_action, (MakeFace, Extrude)):
        #     self.center_camera_on(current_shape)

        # Enforce background color before redraw (prevents reversion)
        self._enforce_background_color()
        
        self.display.View.Redraw()
        time.sleep(self.delay)

        self.capture_frame()

    def center_camera_on_all_shapes(self):
        if not self._all_shapes:
            return
        bbox = Bnd_Box()
        for shape in self._all_shapes:
            brepbndlib_Add(shape, bbox)
        self.display.FitAll()

    def save_video(self, output_path="demo.gif", fps=5, hold_last_frame=5):
        frame_paths = sorted([
            os.path.join(self.frame_dir, f) for f in os.listdir(self.frame_dir)
            if f.endswith(".png")
        ])
        images = [Image.open(f) for f in frame_paths]

        # Repeat the last frame
        if images:
            last_frame = images[-1]
            images.extend([last_frame.copy()] * hold_last_frame)

        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            duration=int(1000 / fps),
            loop=0
        )
        print(f"[INFO] Saved animation to {output_path}")

        # Clean up frames after GIF creation
        for f in frame_paths:
            try:
                os.remove(f)
            except Exception as e:
                print(f"[WARNING] Could not delete frame {f}: {e}")

    # ------------------------------------------------------------------
    # convenience
    # ------------------------------------------------------------------
    def clear(self):                                                      # 🆕 remove old AIS shapes
        for ais in self._ais_objects:
            self.display.Context.Remove(ais, False)
        self._ais_objects.clear()
        self.display.View.Redraw()

    def show_final_shape(self):
        self.start_display()

    def render_all_solids(self, state, last_action):
        """Render all solids in the state, not just the current shape"""
        
        # Enforce background color
        self._enforce_background_color()
        
        # Clear previous displays
        self.clear()
        
        ctx = self.display.Context
        
        # Display all solids with different colors
        from OCC.Core.Quantity import Quantity_TOC_RGB
        colors = [
            Quantity_Color(Quantity_NOC_BLUE1),
            Quantity_Color(0.0, 0.8, 0.0, Quantity_TOC_RGB),  # Green
            Quantity_Color(0.8, 0.0, 0.0, Quantity_TOC_RGB),  # Red
            Quantity_Color(0.8, 0.8, 0.0, Quantity_TOC_RGB),  # Yellow
            Quantity_Color(0.8, 0.0, 0.8, Quantity_TOC_RGB),  # Magenta
            Quantity_Color(0.0, 0.8, 0.8, Quantity_TOC_RGB),  # Cyan
            Quantity_Color(0.5, 0.5, 0.5, Quantity_TOC_RGB),  # Gray
            Quantity_Color(1.0, 0.5, 0.0, Quantity_TOC_RGB),  # Orange
        ]
        
        # Render each solid with a different color
        for i, solid in enumerate(state.solids):
            ais_shape = AIS_Shape(solid.shape)
            
            # Use different colors for different solids
            color = colors[i % len(colors)]
            ctx.SetColor(ais_shape, color, False)
            
            # Make shapes semi-transparent so we can see overlaps
            ctx.SetTransparency(ais_shape, 0.3, False)
            
            # Set display mode to shaded
            ctx.SetDisplayMode(ais_shape, 1, False)  # 1 = shaded mode
            
            ctx.Display(ais_shape, False)
            self._ais_objects.append(ais_shape)
            self._all_shapes.append(solid.shape)
        
        # Center camera on all shapes
        self.center_camera_on_all_shapes()
        
        # Enforce background color before redraw
        self._enforce_background_color()
        
        self.display.View.Redraw()
        time.sleep(self.delay)
        
        self.capture_frame()
        

    def render_active_geometry(self, active_geometry, last_action):
        """Render all active geometry (solids, faces, edges, wires) - not replaced by newer versions"""
        
        # Enforce background color
        self._enforce_background_color()
        
        # Clear previous displays
        self.clear()
        
        ctx = self.display.Context
                
        # Special handling: If we want to show faces but not solids, 
        # we need to extract faces from solids
        if self.show_faces and not self.show_solids:
            self._render_faces_from_solids(active_geometry, ctx)
        
        # Render each active geometry item with appropriate styling
        for i, geometry in enumerate(active_geometry):
            if not hasattr(geometry, 'id'):
                continue
                
            # Check visibility settings for each geometry type
            if geometry.id.startswith('s') and not self.show_solids:
                continue
            elif geometry.id.startswith('f') and not self.show_faces:
                continue
            elif geometry.id.startswith('e') and not self.show_edges:
                continue
            elif geometry.id.startswith('w') and not self.show_wires:
                continue
            
            ais_shape = AIS_Shape(geometry.shape)
            
            # Set different styles for different geometry types
            if geometry.id.startswith('s'):  # Solid
                # Solids use default solid rendering with configurable transparency
                ctx.SetTransparency(ais_shape, self.solid_transparency, False)
            elif geometry.id.startswith('f'):  # Face
                # All faces are rendered in light gray with configurable transparency
                from OCC.Core.Quantity import Quantity_NOC_LIGHTGRAY
                ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_LIGHTGRAY), False)
                ctx.SetTransparency(ais_shape, self.face_transparency, False)
                
            elif geometry.id.startswith('e'):  # Edge
                # Edges are thicker black lines with configurable transparency
                ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLACK), False)
                ctx.SetWidth(ais_shape, 2.0, True)
                if self.edge_transparency > 0:
                    ctx.SetTransparency(ais_shape, self.edge_transparency, False)
                
                # Also show points (vertices) for edges - extract from actual geometry
                if self.show_points:
                    self._display_vertices_from_shape(geometry.shape)
                    
            elif geometry.id.startswith('w'):  # Wire
                # Wires are blue lines (sketch elements) with configurable transparency
                ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_BLUE1), False)
                ctx.SetWidth(ais_shape, 1.5, True)
                if self.wire_transparency > 0:
                    ctx.SetTransparency(ais_shape, self.wire_transparency, False)
                
                # Also show points (vertices) for wires - extract from actual geometry
                if self.show_points:
                    self._display_vertices_from_shape(geometry.shape)
            
            # Display the geometry
            ctx.Display(ais_shape, False)
            self._ais_objects.append(ais_shape)
            
            # Activate selection modes for this object
            try:
                if geometry.id.startswith('f'):  # Face
                    # For faces, prioritize face selection mode
                    ctx.SetSelectionModeActive(ais_shape, 2, True)  # Face selection (primary)
                    ctx.SetSelectionModeActive(ais_shape, 0, True)  # Whole shape selection (secondary)
                elif geometry.id.startswith('e'):  # Edge  
                    ctx.SetSelectionModeActive(ais_shape, 1, True)  # Edge selection (primary)
                    ctx.SetSelectionModeActive(ais_shape, 0, True)  # Whole shape selection (secondary)
                else:
                    ctx.SetSelectionModeActive(ais_shape, 0, True)  # Default: whole shape selection
            except Exception:
                pass
            
            # Register the AIS object with its entity ID for selection
            self._register_ais_object(ais_shape, geometry.id)
        
        # Highlight the last action if appropriate (show points for action-specific context)
        if last_action and self.show_action_points:
            
            # For sketch actions, show the action points only if we're currently in a sketch
            # (i.e., if there are active edges/wires but no solids yet)
            show_action_points = len(active_geometry) > 0 and all(
                hasattr(g, 'id') and (g.id.startswith('e') or g.id.startswith('w') or g.id.startswith('f'))
                for g in active_geometry
            )
            
            if show_action_points:
                # Show points for sketch actions
                if isinstance(last_action, AddLine):
                    self._display_filled_sphere(last_action.start)
                    self._display_filled_sphere(last_action.end)
                elif isinstance(last_action, AddArc):
                    for pt in last_action.points:
                        self._display_filled_sphere(pt)
                elif isinstance(last_action, AddCircle):
                    self._display_filled_sphere(last_action.center)
                elif isinstance(last_action, AddEllipse):
                    self._display_filled_sphere(last_action.center)
                elif isinstance(last_action, AddSpline):
                    for pt in last_action.points:
                        self._display_filled_sphere(pt)
                elif isinstance(last_action, AddBezier):
                    for pt in last_action.control_points:
                        self._display_filled_sphere(pt)
        
        # Update the display
        self.display.View.Redraw()
        
        # Activate selection modes for all displayed objects
        self._activate_all_selection_modes()
        
        # Add delay for step-by-step visualization
        time.sleep(self.delay)
        
        # Capture the frame
        self.capture_frame()

    def _display_vertices_from_shape(self, shape):
        """Extract and display vertices from a TopoDS_Shape"""
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_VERTEX
        from OCC.Core.TopoDS import topods
        from OCC.Core.BRep import BRep_Tool
        
        # Explore the shape to find all vertices
        exp = TopExp_Explorer(shape, TopAbs_VERTEX)
        vertices_seen = set()  # To avoid duplicate vertices
        
        while exp.More():
            vertex = topods.Vertex(exp.Current())
            point = BRep_Tool.Pnt(vertex)
            vertex_coords = (round(point.X(), 6), round(point.Y(), 6), round(point.Z(), 6))
            
            # Only display each unique vertex once
            if vertex_coords not in vertices_seen:
                vertices_seen.add(vertex_coords)
                self._display_filled_sphere(vertex_coords, radius=0.05)
            
            exp.Next()

    def set_visibility(self, show_solids=None, show_faces=None, show_edges=None, 
                      show_wires=None, show_points=None, show_action_points=None, 
                      solid_transparency=None, face_transparency=None, 
                      edge_transparency=None, wire_transparency=None):
        """
        Update visibility settings for different geometry types
        
        Args:
            show_solids: Show/hide solid objects
            show_faces: Show/hide face objects
            show_edges: Show/hide edge objects
            show_wires: Show/hide wire objects (sketch paths)
            show_points: Show/hide vertices/points from geometry
            show_action_points: Show/hide points from the last action
            solid_transparency: Transparency for solids (0.0 = opaque, 1.0 = fully transparent)
            face_transparency: Transparency for faces (0.0 = opaque, 1.0 = fully transparent)
            edge_transparency: Transparency for edges (0.0 = opaque, 1.0 = fully transparent)
            wire_transparency: Transparency for wires (0.0 = opaque, 1.0 = fully transparent)
        """
        if show_solids is not None:
            self.show_solids = show_solids
        if show_faces is not None:
            self.show_faces = show_faces
        if show_edges is not None:
            self.show_edges = show_edges
        if show_wires is not None:
            self.show_wires = show_wires
        if show_points is not None:
            self.show_points = show_points
        if show_action_points is not None:
            self.show_action_points = show_action_points
        if solid_transparency is not None:
            self.solid_transparency = solid_transparency
        if face_transparency is not None:
            self.face_transparency = face_transparency
        if edge_transparency is not None:
            self.edge_transparency = edge_transparency
        if wire_transparency is not None:
            self.wire_transparency = wire_transparency

    def get_visibility(self):
        """Get current visibility settings"""
        return {
            "show_solids": self.show_solids,
            "show_faces": self.show_faces,
            "show_edges": self.show_edges,
            "show_wires": self.show_wires,
            "show_points": self.show_points,
            "show_action_points": self.show_action_points,
            "solid_transparency": self.solid_transparency,
            "face_transparency": self.face_transparency,
            "edge_transparency": self.edge_transparency,
            "wire_transparency": self.wire_transparency,
        }

    def show_only_solids(self):
        """Show only solid objects, hide everything else"""
        self.set_visibility(show_solids=True, show_faces=False, show_edges=False, 
                           show_wires=False, show_points=False, show_action_points=False)

    def show_only_sketches(self):
        """Show only sketch elements (edges, wires, points), hide solids and faces"""
        self.set_visibility(show_solids=False, show_faces=False, show_edges=True, 
                           show_wires=True, show_points=True, show_action_points=True)

    def show_everything(self):
        """Show all geometry types"""
        self.set_visibility(show_solids=True, show_faces=True, show_edges=True, 
                           show_wires=True, show_points=True, show_action_points=True)

    def hide_everything(self):
        """Hide all geometry types"""
        self.set_visibility(show_solids=False, show_faces=False, show_edges=False, 
                           show_wires=False, show_points=False, show_action_points=False)

    def _render_faces_from_solids(self, active_geometry, ctx):
        """
        Render individual faces from solids when show_faces=True and show_solids=False
        This allows viewing the faces of solids without showing the solid itself
        """
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_FACE
        
        # Find all solids in active geometry
        solids = [geom for geom in active_geometry if hasattr(geom, 'id') and geom.id.startswith('s')]
        
        # Extract and render faces from each solid
        for solid in solids:
            
            # Explore all faces in the solid
            exp = TopExp_Explorer(solid.shape, TopAbs_FACE)
            face_count = 0
            
            while exp.More():
                face_shape = exp.Current()
                
                # Create AIS object for this face
                ais_shape = AIS_Shape(face_shape)
                
                # Generate face ID in the same format as used in the solid's faces list
                # Face IDs follow the pattern: {solid_id}f{index}
                face_id = f"{solid.id}f{face_count}"
                
                # Register this AIS object with its face ID for selection
                self._register_ais_object(ais_shape, face_id)
                
                # All faces are rendered in light gray with configurable transparency
                from OCC.Core.Quantity import Quantity_NOC_LIGHTGRAY
                ctx.SetColor(ais_shape, Quantity_Color(Quantity_NOC_LIGHTGRAY), False)
                ctx.SetTransparency(ais_shape, self.face_transparency, False)
                
                # Display the face
                ctx.Display(ais_shape, False)
                
                # Activate face selection mode for this object
                try:
                    # For faces from solids, prioritize face selection mode
                    ctx.SetSelectionModeActive(ais_shape, 2, True)  # Face selection (primary)
                    ctx.SetSelectionModeActive(ais_shape, 0, True)  # Whole shape selection (secondary)
                    # Do not activate edge selection mode to avoid conflicts
                except Exception:
                    pass
                
                self._ais_objects.append(ais_shape)
                
                face_count += 1
                exp.Next()

    def _activate_all_selection_modes(self):
        """Activate selection modes for all currently displayed objects"""
        try:
            ctx = self.display.Context
            
            # Activate selection for all AIS objects we're tracking
            for entity_id, ais_obj in self.id_to_ais.items():
                try:
                    # For faces, prioritize face selection mode over edge selection
                    if entity_id.startswith('f') or 'f' in entity_id:  # Face
                        # Activate face selection mode with higher priority
                        ctx.SetSelectionModeActive(ais_obj, 2, True)  # Face selection (primary)
                        ctx.SetSelectionModeActive(ais_obj, 0, True)  # Whole shape selection (secondary)
                        # Don't activate edge mode for faces to avoid conflicts
                    elif entity_id.startswith('e') or 'e' in entity_id:  # Edge
                        ctx.SetSelectionModeActive(ais_obj, 1, True)  # Edge selection (primary)
                        ctx.SetSelectionModeActive(ais_obj, 0, True)  # Whole shape selection (secondary)
                    elif entity_id.startswith('w') or 'w' in entity_id:  # Wire
                        ctx.SetSelectionModeActive(ais_obj, 1, True)  # Edge selection for wires
                        ctx.SetSelectionModeActive(ais_obj, 0, True)  # Whole shape selection
                    else:
                        # Default: whole shape selection
                        ctx.SetSelectionModeActive(ais_obj, 0, True)
                        
                except Exception:
                    continue
                    
        except Exception:
            pass
