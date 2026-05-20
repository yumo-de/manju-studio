"""
Video effects and transitions for Manju Studio.

Defines ffmpeg filter descriptions for common video transitions.
"""

# Transition filter descriptions for use with ffmpeg xfade or custom overlay logic.
# Each entry is a dict with:
#   - name: display name
#   - ffmpeg_xfade: the transition name for ffmpeg's xfade filter
#   - description: brief explanation
TRANSITIONS = {
    "fade": {
        "name": "Fade",
        "ffmpeg_xfade": "fade",
        "description": "Crossfade — first clip fades out as second fades in",
    },
    "fadeblack": {
        "name": "Fade to Black",
        "ffmpeg_xfade": "fadeblack",
        "description": "Fade through black between clips",
    },
    "fadewhite": {
        "name": "Fade to White",
        "ffmpeg_xfade": "fadewhite",
        "description": "Fade through white between clips",
    },
    "wipeleft": {
        "name": "Wipe Left",
        "ffmpeg_xfade": "wipeleft",
        "description": "Wipe transition from right to left",
    },
    "wiperight": {
        "name": "Wipe Right",
        "ffmpeg_xfade": "wiperight",
        "description": "Wipe transition from left to right",
    },
    "wipeup": {
        "name": "Wipe Up",
        "ffmpeg_xfade": "wipeup",
        "description": "Wipe transition from bottom to top",
    },
    "wipedown": {
        "name": "Wipe Down",
        "ffmpeg_xfade": "wipedown",
        "description": "Wipe transition from top to bottom",
    },
    "slideleft": {
        "name": "Slide Left",
        "ffmpeg_xfade": "slideleft",
        "description": "Second clip slides in from the right",
    },
    "slideright": {
        "name": "Slide Right",
        "ffmpeg_xfade": "slideright",
        "description": "Second clip slides in from the left",
    },
    "circleopen": {
        "name": "Circle Open",
        "ffmpeg_xfade": "circleopen",
        "description": "Expanding circle reveals second clip",
    },
    "circleclose": {
        "name": "Circle Close",
        "ffmpeg_xfade": "circleclose",
        "description": "Contracting circle hides first clip",
    },
    "pixelize": {
        "name": "Pixelize",
        "ffmpeg_xfade": "pixelize",
        "description": "Pixelation dissolve between clips",
    },
    "dissolve": {
        "name": "Dissolve",
        "ffmpeg_xfade": "dissolve",
        "description": "Soft dissolve between clips",
    },
    "radial": {
        "name": "Radial",
        "ffmpeg_xfade": "radial",
        "description": "Radial wipe from center",
    },
    "hrect": {
        "name": "Horizontal Rectangle",
        "ffmpeg_xfade": "hrect",
        "description": "Horizontal rectangle transition",
    },
    "vrect": {
        "name": "Vertical Rectangle",
        "ffmpeg_xfade": "vrect",
        "description": "Vertical rectangle transition",
    },
}


def validate_transition(name: str) -> bool:
    """Check if a transition name is supported."""
    return name in TRANSITIONS
