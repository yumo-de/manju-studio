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


# ── 情绪 → 转场映射 ────────────────────────────────────────────────────

MOOD_TRANSITION_MAP: dict[str, str] = {
    # 情绪 → 推荐转场
    "epic":    "fade",         # 史诗→淡入淡出
    "tense":   "wiperight",    # 紧张→快速向右划
    "gentle":  "dissolve",     # 轻柔→溶解
    "comic":   "slideleft",    # 搞笑→滑动左入
    "action":  "wipeleft",     # 动作→向左划
    "sad":     "fadeblack",    # 悲伤→淡黑
    "mystery": "circleopen",   # 神秘→圆形展开
    "happy":   "radial",       # 欢快→放射展开
}

DEFAULT_TRANSITION = "fade"  # 无情绪信息时的默认转场


def transition_for_mood(mood: str) -> str:
    """根据情绪返回推荐转场名称。"""
    return MOOD_TRANSITION_MAP.get(mood, DEFAULT_TRANSITION)


def pick_transition_between(
    prev_mood: str,
    next_mood: str,
    mood_change: str = "",
) -> str:
    """根据前后镜头的情绪变化挑选转场。

    Args:
        prev_mood: 前一个镜头的情绪。
        next_mood: 后一个镜头的情绪。
        mood_change: 如果是同场景内连续镜头，可以指定情绪变化幅度。

    Returns:
        转场名称。
    """
    if mood_change == "contrast":
        # 情绪反差大 → 节奏感强的转场
        return "pixelize"
    if mood_change == "escalate":
        # 情绪升级 → 淡入
        return "fade"
    if mood_change == "relax":
        # 情绪回落 → 溶解
        return "dissolve"

    # 根据下一个镜头的情绪选择转场
    base = transition_for_mood(next_mood)

    # 情绪不变 → 柔和转场
    if prev_mood == next_mood:
        return "dissolve" if prev_mood in ("gentle", "sad") else "fade"

    # 情绪变化剧烈程度
    intense_moods = {"epic", "action", "tense"}
    calm_moods = {"gentle", "sad", "mystery"}

    if prev_mood in intense_moods and next_mood in calm_moods:
        return "fadeblack"  # 激烈→平静：淡黑过渡
    if prev_mood in calm_moods and next_mood in intense_moods:
        return "fadewhite"  # 平静→激烈：淡白过渡

    return base
