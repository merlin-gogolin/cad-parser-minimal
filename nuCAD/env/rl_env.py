"""
RL-optimized CAD environment with memory management.
Addresses memory leaks identified in profiling.
"""

from typing import Optional, Dict, Any, Tuple
import gc
import weakref
from nuCAD.env.base_env import nuCADEnv


class RLCADEnv(nuCADEnv):
    """
    RL-optimized CAD environment with aggressive memory management.
    
    Key optimizations:
    1. Lazy visualization (only when explicitly needed)
    2. Aggressive garbage collection
    3. State cleanup between episodes
    4. Memory usage tracking
    5. Configurable memory limits
    """
    
    def __init__(self, 
                 memory_limit_mb: int = 50,
                 auto_gc: bool = True,
                 lazy_viz: bool = True,
                 render_setting: Optional[Dict] = None):
        """
        Initialize RL-optimized CAD environment.
        
        Args:
            memory_limit_mb: Maximum memory usage before forcing cleanup
            auto_gc: Whether to automatically run garbage collection
            lazy_viz: Whether to defer visualization until needed
            render_setting: Renderer settings (only used if viz requested)
        """
        self.memory_limit_mb = memory_limit_mb
        self.auto_gc = auto_gc
        self.lazy_viz = lazy_viz
        self._render_setting = render_setting
        self._renderer_created = False
        
        # Initialize parent without visualization
        super().__init__(viz=False, render_setting=None)
        
        # Track instances for cleanup
        self._instance_id = id(self)
        RLCADEnv._register_instance(self)
    
    # Class-level instance tracking
    _instances = weakref.WeakSet()
    
    @classmethod
    def _register_instance(cls, instance):
        """Register instance for global cleanup tracking."""
        cls._instances.add(instance)
    
    @classmethod
    def cleanup_all_instances(cls):
        """Clean up all instances - useful for training loops."""
        instances = list(cls._instances)  # Copy to avoid modification during iteration
        for instance in instances:
            try:
                instance._force_cleanup()
            except:
                pass  # Instance might already be deleted
        gc.collect()
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    def _check_memory_limit(self):
        """Check if memory limit is exceeded and force cleanup if needed."""
        if self.memory_limit_mb <= 0:
            return
            
        current_memory = self._get_memory_usage()
        if current_memory > self.memory_limit_mb:
            self._force_cleanup()
            
            # If still over limit after cleanup, run global cleanup
            if self._get_memory_usage() > self.memory_limit_mb:
                self.cleanup_all_instances()
    
    def _force_cleanup(self):
        """Force cleanup of current state while preserving essential data."""
        # Clear current shape references but keep essential state
        self.current_shape = None
        self.current_solid_id = None
        
        # Clear wire edges and loops but keep essential tracking
        self.current_wire_edges = []
        self.last_face_wire_index = 0
        
        # Force garbage collection
        if self.auto_gc:
            gc.collect()
    
    def _light_cleanup(self):
        """Light cleanup that preserves state but frees memory."""
        # Only run garbage collection
        if self.auto_gc:
            gc.collect()
    
    def reset(self):
        """Reset environment with light cleanup."""
        # Light cleanup before reset (preserve state structure)
        self._light_cleanup()
        
        # Call parent reset
        result = super().reset()
        
        # Run GC after reset if enabled
        if self.auto_gc:
            gc.collect()
        
        return result
    
    def step(self, action):
        """Step with memory monitoring."""
        # Check memory before action
        self._check_memory_limit()
        
        # Execute action
        result = super().step(action)
        
        # Run GC periodically if enabled
        if self.auto_gc and hasattr(self, '_step_count'):
            self._step_count = getattr(self, '_step_count', 0) + 1
            if self._step_count % 10 == 0:  # Every 10 steps
                gc.collect()
        
        return result
    
    def render(self, export_video=False, video_path=None):
        """Lazy render - only create renderer when actually needed."""
        if not self._renderer_created and self.lazy_viz:
            # Create renderer on first render call
            from nuCAD.env.renderer import nuCADRenderer
            self.renderer = nuCADRenderer(self._render_setting)
            self._renderer_created = True
            self.viz = True
        
        if hasattr(self, 'renderer'):
            return super().render(export_video, video_path)
        else:
            # No-op if no renderer
            return None
    
    def close(self):
        """Close environment with proper cleanup."""
        # Only do light cleanup to avoid breaking state
        self._light_cleanup()
        
        # Clean up renderer if created
        if hasattr(self, 'renderer') and self.renderer:
            try:
                # Attempt to close renderer cleanly
                del self.renderer
            except:
                pass
        
        # Final GC
        if self.auto_gc:
            gc.collect()
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get detailed memory information."""
        return {
            'current_memory_mb': self._get_memory_usage(),
            'memory_limit_mb': self.memory_limit_mb,
            'renderer_created': self._renderer_created,
            'auto_gc_enabled': self.auto_gc,
            'num_solids': len(self.state.solids) if hasattr(self, 'state') else 0,
            'num_faces': len(self.state.faces) if hasattr(self, 'state') else 0,
            'num_edges': len(self.state.edges) if hasattr(self, 'state') else 0,
        }
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except:
            pass


class ParallelRLCADEnv:
    """
    Wrapper for running multiple RL environments in parallel with memory management.
    """
    
    def __init__(self, num_envs: int = 4, memory_limit_per_env: int = 25):
        """
        Initialize parallel environments.
        
        Args:
            num_envs: Number of parallel environments
            memory_limit_per_env: Memory limit per environment in MB
        """
        self.num_envs = num_envs
        self.envs = []
        
        for i in range(num_envs):
            env = RLCADEnv(
                memory_limit_mb=memory_limit_per_env,
                auto_gc=True,
                lazy_viz=True
            )
            self.envs.append(env)
    
    def reset_all(self):
        """Reset all environments."""
        return [env.reset() for env in self.envs]
    
    def step_all(self, actions):
        """Step all environments with given actions."""
        assert len(actions) == self.num_envs
        return [env.step(action) for env, action in zip(self.envs, actions)]
    
    def get_total_memory_usage(self) -> float:
        """Get total memory usage across all environments."""
        return sum(env._get_memory_usage() for env in self.envs)
    
    def cleanup_all(self):
        """Clean up all environments."""
        for env in self.envs:
            env.close()
        RLCADEnv.cleanup_all_instances()
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.cleanup_all()
        except:
            pass


# Factory functions for common RL use cases
def create_training_env(memory_limit_mb: int = 50) -> RLCADEnv:
    """Create environment optimized for RL training."""
    return RLCADEnv(
        memory_limit_mb=memory_limit_mb,
        auto_gc=True,
        lazy_viz=True
    )


def create_evaluation_env(memory_limit_mb: int = 100, enable_viz: bool = False) -> RLCADEnv:
    """Create environment optimized for RL evaluation."""
    env = RLCADEnv(
        memory_limit_mb=memory_limit_mb,
        auto_gc=True,
        lazy_viz=not enable_viz
    )
    
    if enable_viz:
        # Force renderer creation for evaluation
        env.render()
    
    return env


def create_parallel_training_envs(num_envs: int = 4, memory_limit_mb: int = 50) -> ParallelRLCADEnv:
    """Create multiple environments for parallel RL training."""
    return ParallelRLCADEnv(
        num_envs=num_envs,
        memory_limit_per_env=memory_limit_mb // num_envs
    )
