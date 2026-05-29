# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Manju Studio is an automated comic-drama (漫剧) video generation system. Given a story theme, it runs a 6-step AI pipeline to produce a complete video: story outline → script → storyboard → image generation → TTS voiceover → video composition. Built on low-cost/free APIs (DeepSeek, Tongyi Wanxiang, Edge-TTS, ffmpeg) with a Gradio web UI.

## Commands

```bash
# Install (one-time)
cd manju-studio && bash setup.sh          # installs deps, creates .env, sets up BGM dirs

# Run web UI (Gradio on http://localhost:7860)
python3 app.py

# Run pipeline from CLI (one-shot, no UI)
python3 pipeline.py "你的故事主题"

# Tests (requires dev deps: pip install -e ".[dev]")
pytest                                     # run all tests
pytest tests/test_story_engine.py          # run a single test file
pytest tests/test_story_engine.py::TestShotCreation::test_camera_defaults  # single test
```

## Architecture

### Pipeline Flow (`pipeline.py`)

`ManjuPipeline.run(theme)` orchestrates 8 sequential steps with `StepResult` tracking per step. Each step catches exceptions independently — a failed step degrades gracefully rather than crashing the pipeline:

1. **StoryExpander** — theme → `Story` (characters, acts, worldview) via LLM
2. **ScriptWriter** — `Story` → scene list (location, time, dialogue, action) via LLM
3. **ShotGenerator** — scenes → `Storyboard` of `Shot` objects (camera, prompt, dialogue, bgm_mood) via LLM; uses `ThreadPoolExecutor(4)` to process scenes in parallel
4. **Image generation** — character portraits + keyframe images via Tongyi Wanxiang; multi-threaded (`ThreadPoolExecutor(3)`), respects 50-image daily free quota
5. **TTSEngine** — dialogue audio via Edge-TTS (concurrent generation, voice matched to character)
6. **BGM selection** — `BGMSelector` picks music by dominant `bgm_mood` from `data/bgm_library/`
7. **Video composition** — `VideoCompositor` (ffmpeg wrapper): images → clips with Ken Burns effects → concatenate with xfade transitions → add audio/BGM → burn subtitles. Supports per-act multi-threaded composition (`compose_video_by_acts`) or flat concatenation (`compose_video_flat`). Optional frame interpolation via `FrameInterpolator`.
8. **Output** — saves `pipeline_report.json` with step results

The Gradio UI (`app.py`) exposes the same pipeline as an interactive 6-step wizard where users can preview/edit JSON and confirm each step before proceeding.

### Core Modules (`manju/`)

- **`config.py`** — loads `config.yaml` with `${ENV_VAR}` substitution from `.env`
- **`llm/llm_client.py`** — `LLMClient` wraps DeepSeek API with `chat()`, `chat_json()`, `chat_stream()`. Includes `_repair_json()` (fixes 7 common LLM JSON issues) and exponential-backoff retry (up to 3 attempts)
- **`llm/prompt_templates.py`** — all LLM system/user prompt templates
- **`story_engine/`** — `expander.py`, `scriptwriter.py`, `shot_generator.py` — each wraps `LLMClient.chat_json()` with domain-specific prompts
- **`schemas/story.py`** — Pydantic v2 models: `Character`, `Act`, `Story`, `Camera`, `Shot`, `Storyboard`
- **`schemas/project.py`** — `Project` model for project-level state
- **`visual/tongyi_client.py`** — Tongyi Wanxiang async-polling image API client
- **`visual/prompt_gen.py`** — `PromptGenerator` builds English image prompts from `Shot` + genre style prefixes
- **`visual/cache.py`** — `ImageCache` with SHA256 key to avoid regenerating identical prompts
- **`tts/engine.py`** — `TTSEngine` wraps edge-tts with 8 Chinese voice styles, concurrent generation
- **`video/compositor.py`** — `VideoCompositor` wraps ffmpeg subprocess calls: `build_shot_clip()`, `concatenate_clips()`, `add_audio()`, `add_subtitles()`
- **`video/effects.py`** — `TRANSITIONS` dict (16 ffmpeg xfade transitions) + `pick_transition_between()` for mood-based auto-selection
- **`video/interpolator.py`** — `FrameInterpolator` for 24fps→60fps (ffmpeg `minterpolate` or external `rife-ncnn-vulkan`)

### Configuration

- `config.yaml` — LLM provider, image provider, video fps/resolution, subtitle styling, interpolation settings
- `.env` — API keys (`DEEPSEEK_API_KEY` required, `TONGYI_API_KEY` optional)
- Pipeline output goes to `data/projects/proj_YYYYMMDD_HHMMSS/` with subdirectories: `characters/`, `keyframes/`, `audio/`, `video/`

### Key Design Decisions

- **All LLM output goes through `chat_json()`** with auto-repair — never trust raw LLM JSON
- **Image generation is optional** — pipeline skips step 4 gracefully when `TONGYI_API_KEY` is missing (`_image_available` flag)
- **Video composition has two paths**: `compose_video_by_acts` (multi-threaded per act, when story has acts) vs `compose_video_flat` (sequential fallback)
- **Module-level `_VCOMP` compositor instance** in `pipeline.py` is shared; functions like `compose_video_by_acts` create their own local `VideoCompositor()` instances
- **Python 3.11+** required; uses `from __future__ import annotations` throughout
