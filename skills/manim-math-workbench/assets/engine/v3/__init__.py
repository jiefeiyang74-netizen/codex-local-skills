"""Minimal offline engine surface for the distributable runner."""

from .audio_timing import analyse_alignment, apply_audio_timing, probe_audio
from .capabilities import CAPABILITY_VERSION
from .compiler import compile_storyboard
from .storyboard import (
    STORYBOARD_SYSTEM_PROMPT,
    StoryboardValidationError,
    build_storyboard_user_prompt,
    estimate_motion_seconds,
    normalize_storyboard,
    storyboard_timeline,
)

__all__ = [
    "CAPABILITY_VERSION",
    "STORYBOARD_SYSTEM_PROMPT",
    "StoryboardValidationError",
    "analyse_alignment",
    "apply_audio_timing",
    "build_storyboard_user_prompt",
    "compile_storyboard",
    "estimate_motion_seconds",
    "normalize_storyboard",
    "probe_audio",
    "storyboard_timeline",
]
