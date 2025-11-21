"""
Face reference validation for nuCAD operations.

Provides runtime validation of face references to catch errors early
and enable runtime topology discovery.
"""

from typing import Optional, Tuple
import logging


class FaceReferenceValidator:
    """
    Validates face references before using them in nuCAD operations.
    
    This helps catch errors early when the converter generates incorrect
    face indices, and enables optional runtime topology discovery.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize validator.
        
        Args:
            logger: Optional logger for validation messages
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def validate_sketch_face(self, face_ref: str, env=None) -> Tuple[bool, str]:
        """
        Check if face reference is valid and suitable for sketching.
        
        For face-based sketching, the face must be:
        - Flat (planar)
        - Have defined normal vector
        - Be accessible in the current environment state
        
        Args:
            face_ref: Face reference string (e.g., "s0:3", "f2")
            env: Optional nuCAD environment for runtime checking
        
        Returns:
            Tuple of (is_valid, reason)
            - is_valid: True if face can be used for sketching
            - reason: Explanation of validation result
        
        Examples:
            >>> validator = FaceReferenceValidator()
            >>> is_valid, reason = validator.validate_sketch_face("s0:3")
            >>> if not is_valid:
            ...     print(f"Invalid face: {reason}")
        """
        # Basic format validation
        if not isinstance(face_ref, str):
            return False, "Face reference must be a string"
        
        # Sketch faces (f0, f1, ...) are always valid
        if face_ref.startswith('f') and face_ref[1:].isdigit():
            return True, "Sketch face reference is valid"
        
        # Solid face references (s0:1, s1:3, ...)
        if ':' in face_ref:
            parts = face_ref.split(':')
            if len(parts) != 2:
                return False, f"Invalid solid face format: {face_ref} (expected 's<id>:<index>')"
            
            solid_part, face_part = parts
            
            # Validate solid ID format
            if not solid_part.startswith('s') or not solid_part[1:].isdigit():
                return False, f"Invalid solid ID in {face_ref}"
            
            # Validate face index format
            if not face_part.isdigit():
                return False, f"Invalid face index in {face_ref}"
            
            # If we have a nuCAD environment, do runtime validation
            if env is not None:
                return self._validate_runtime(face_ref, env)
            
            # Without env, we can only do format validation
            return True, f"Format valid (runtime check not performed)"
        
        return False, f"Unrecognized face reference format: {face_ref}"
    
    def _validate_runtime(self, face_ref: str, env) -> Tuple[bool, str]:
        """
        Perform runtime validation by querying actual nuCAD environment.
        
        This is the ideal validation - checks actual geometry.
        """
        try:
            solid_id_str, face_idx_str = face_ref.split(':')
            solid_idx = int(solid_id_str[1:])  # Remove 's' prefix
            face_idx = int(face_idx_str)
            
            # Check if solid exists
            if not hasattr(env, 'state') or not hasattr(env.state, 'solids'):
                return True, "Cannot access environment state (assuming valid)"
            
            solids = env.state.solids
            
            if solid_idx >= len(solids):
                return False, f"Solid s{solid_idx} does not exist (only {len(solids)} solids in environment)"
            
            solid = solids[solid_idx]
            
            # Check if face index exists on this solid
            if not hasattr(solid, 'faces'):
                return True, "Cannot access solid faces (assuming valid)"
            
            faces = solid.faces
            
            if face_idx >= len(faces):
                return False, f"Face index {face_idx} does not exist on solid s{solid_idx} (only {len(faces)} faces)"
            
            face = faces[face_idx]
            
            # Check if face is planar (suitable for sketching)
            if hasattr(face, 'is_planar'):
                if not face.is_planar():
                    return False, f"Face {face_ref} is not planar (cannot sketch on curved surface)"
            elif hasattr(face, 'type'):
                if face.type not in ['PLANE', 'FLAT', 'PLANAR']:
                    self.logger.warning(f"Face {face_ref} has type '{face.type}' (may not be planar)")
            
            return True, f"Runtime validation passed for {face_ref}"
            
        except Exception as e:
            self.logger.warning(f"Runtime validation failed for {face_ref}: {e}")
            return True, f"Runtime validation error (assuming valid): {e}"
    
    def suggest_fallback_face(self, failed_ref: str, env=None) -> Optional[str]:
        """
        Suggest an alternative face reference when validation fails.
        
        This implements basic runtime discovery by scanning available faces
        to find a suitable alternative.
        
        Args:
            failed_ref: The face reference that failed validation
            env: nuCAD environment to search for alternatives
        
        Returns:
            Alternative face reference string, or None if no alternative found
        """
        if env is None:
            return None
        
        try:
            # Extract solid ID from failed reference
            if ':' not in failed_ref:
                return None
            
            solid_id_str, _ = failed_ref.split(':')
            solid_idx = int(solid_id_str[1:])
            
            if not hasattr(env, 'state') or not hasattr(env.state, 'solids'):
                return None
            
            solids = env.state.solids
            
            if solid_idx >= len(solids):
                return None
            
            solid = solids[solid_idx]
            
            if not hasattr(solid, 'faces'):
                return None
            
            faces = solid.faces
            
            # Find first planar face
            for idx, face in enumerate(faces):
                is_planar = False
                
                if hasattr(face, 'is_planar'):
                    is_planar = face.is_planar()
                elif hasattr(face, 'type'):
                    is_planar = face.type in ['PLANE', 'FLAT', 'PLANAR']
                
                if is_planar:
                    alternative = f"{solid_id_str}:{idx}"
                    self.logger.info(f"Suggesting fallback face {alternative} for failed {failed_ref}")
                    return alternative
            
        except Exception as e:
            self.logger.warning(f"Could not suggest fallback for {failed_ref}: {e}")
        
        return None


class RuntimeFaceDiscovery:
    """
    Runtime topology discovery by analyzing actual nuCAD solids.
    
    This is the ultimate solution - instead of predicting face indices,
    we query the actual created geometry.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def discover_cap_faces(self, solid_ref: str, env, side: str = "END") -> Optional[str]:
        """
        Discover cap faces by analyzing actual solid geometry at runtime.
        
        Cap faces are typically:
        - Planar (flat)
        - Have large area relative to swept faces
        - Have normal perpendicular to extrusion direction
        
        Args:
            solid_ref: Solid reference (e.g., "s0")
            env: nuCAD environment containing the solid
            side: "START" (bottom) or "END" (top)
        
        Returns:
            Face reference for the requested cap, or None if discovery fails
        """
        try:
            solid_idx = int(solid_ref[1:])  # Remove 's' prefix
            
            if not hasattr(env, 'state') or not hasattr(env.state, 'solids'):
                return None
            
            solids = env.state.solids
            
            if solid_idx >= len(solids):
                self.logger.error(f"Solid {solid_ref} does not exist")
                return None
            
            solid = solids[solid_idx]
            
            if not hasattr(solid, 'faces'):
                return None
            
            faces = solid.faces
            
            # Analyze faces to find caps
            planar_faces = []
            
            for idx, face in enumerate(faces):
                # Check if planar
                is_planar = False
                area = 0.0
                normal = None
                
                if hasattr(face, 'is_planar'):
                    is_planar = face.is_planar()
                elif hasattr(face, 'type'):
                    is_planar = face.type in ['PLANE', 'FLAT', 'PLANAR']
                
                if not is_planar:
                    continue
                
                # Get area if available
                if hasattr(face, 'area'):
                    area = face.area()
                elif hasattr(face, 'get_area'):
                    area = face.get_area()
                
                # Get normal if available
                if hasattr(face, 'normal'):
                    normal = face.normal()
                elif hasattr(face, 'get_normal'):
                    normal = face.get_normal()
                
                planar_faces.append({
                    'index': idx,
                    'area': area,
                    'normal': normal
                })
            
            if len(planar_faces) < 2:
                self.logger.warning(f"Found only {len(planar_faces)} planar faces on {solid_ref}, expected at least 2 caps")
                return None
            
            # Sort by area (caps typically larger than small side faces)
            planar_faces.sort(key=lambda f: f['area'], reverse=True)
            
            # Take top 2 as likely caps
            cap1, cap2 = planar_faces[0], planar_faces[1]
            
            # Determine which is START vs END based on normal direction
            # Assuming Z-up convention: negative normal = START, positive normal = END
            if cap1['normal'] and cap2['normal']:
                z1 = cap1['normal'][2] if len(cap1['normal']) > 2 else 0
                z2 = cap2['normal'][2] if len(cap2['normal']) > 2 else 0
                
                if side == "START":
                    chosen = cap1 if z1 < z2 else cap2
                else:  # END
                    chosen = cap1 if z1 > z2 else cap2
                
                face_ref = f"{solid_ref}:{chosen['index']}"
                self.logger.info(f"Discovered {side} cap face: {face_ref}")
                return face_ref
            
            # Fallback: just use first planar face
            face_ref = f"{solid_ref}:{cap1['index']}"
            self.logger.info(f"Discovered cap face (heuristic): {face_ref}")
            return face_ref
            
        except Exception as e:
            self.logger.error(f"Runtime cap discovery failed for {solid_ref}: {e}")
            return None
