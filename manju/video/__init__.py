"""Video module — compositing, effects, and subtitle support."""

from .compositor import VideoCompositor
from .effects import TRANSITIONS, validate_transition

__all__ = [
    "VideoCompositor",
    "TRANSITIONS",
    "validate_transition",
]
