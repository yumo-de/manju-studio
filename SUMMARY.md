# Manju Studio — 漫剧生成系统

> **版本:** v0.1.0 (MVP)
> **描述:** From story to video — 输入主题，AI 自动生成完整漫剧视频

## 一、项目概述

Manju Studio 是一个**全自动漫剧生成系统**，用户只需输入一个故事主题，系统通过 AI 流水线自动完成：
1. 故事大纲创作
2. 剧本编写
3. 分镜头设计
4. 角色立绘 + 关键帧图片生成
5. 角色配音生成
6. 最终视频合成（带 Ken Burns 动效、转场、字幕）

### 核心理念
- **接近零成本落地**：使用 DeepSeek API（极低价 LLM）+ 通义万相（每日 50 张免费额度）+ Edge-TTS（免费）
- **一人工作室**：无需团队、无需专业设备，一个人即可量产漫剧内容
- **Gradio 网页界面**：开箱即用，浏览器操作

## 二、当前项目结构

```
manju-studio/
├── app.py                      # Gradio Web 界面入口
├── pipeline.py                 # 核心 Pipeline 编排器（6步流水线）
├── config.yaml                 # 全局配置（LLM/Image/TTS/Video）
├── pyproject.toml              # Python 项目依赖
├── setup.sh                    # 一键安装脚本
├── .env.example                # API Key 模板
│
├── manju/                      # 核心模块
│   ├── config.py               # 配置加载器（支持 ${ENV} 替换）
│   │
│   ├── llm/                    # LLM 客户端
│   │   ├── llm_client.py       # DeepSeek API 封装（chat/chat_json/流式）
│   │   └── prompt_templates.py # 所有 LLM 提示词模板
│   │
│   ├── story_engine/           # 故事引擎（3个子模块）
│   │   ├── expander.py         # 主题 → 故事大纲（角色/幕/世界观）
│   │   ├── scriptwriter.py     # 大纲 → 剧本场景（对话+动作）
│   │   └── shot_generator.py   # 剧本 → 分镜头列表（Shot）
│   │
│   ├── schemas/                # 数据模型（Pydantic）
│   │   ├── story.py            # Story/Character/Shot/Camera/Storyboard
│   │   └── project.py          # Project
│   │
│   ├── visual/                 # 视觉生成
│   │   ├── tongyi_client.py    # 通义万相 API 客户端（异步轮询）
│   │   └── prompt_gen.py       # 英文绘画 Prompt 生成器
│   │
│   ├── tts/                    # 语音合成
│   │   └── engine.py           # Edge-TTS 引擎（8种中文声线）
│   │
│   └── video/                  # 视频合成
│       ├── compositor.py       # ffmpeg 封装（图片→片段→拼接→音频→字幕）
│       └── effects.py          # 16种转场效果定义
│
├── data/projects/              # 运行输出目录
├── scripts/download_bgm.sh     # BGM 下载脚本
└── tests/                      # 测试（4个测试文件）
    ├── test_story_engine.py
    ├── test_tts.py
    ├── test_visual.py
    └── test_video.py
```

## 三、MVP 技术栈与成本分析

| 组件 | 技术选型 | 成本 |
|------|----------|------|
| LLM | DeepSeek Chat API | ~¥0.5/百万 token，极低 |
| 图像生成 | 通义万相 Wanx v1 | 每日 50 张免费 |
| 语音合成 | Edge-TTS | 完全免费 |
| 视频合成 | ffmpeg | 免费 |
| Web 界面 | Gradio | 免费 |
| 部署 | 本地/任意云服务器 | 自定 |

## 四、MVP 流水线流程

```
用户输入主题
    │
    ▼
[1/6] 故事扩展器 (StoryExpander)
    ├─ 调用 DeepSeek → 生成完整故事大纲
    └─ 角色、世界观、幕结构、旁白风格
    │
    ▼
[2/6] 剧本编写器 (ScriptWriter)
    ├─ 调用 DeepSeek → 生成结构化剧本
    └─ 场景列表（地点、时间、氛围、对话、动作、转场）
    │
    ▼
[3/6] 分镜头生成器 (ShotGenerator)
    ├─ 调用 DeepSeek → 逐场景拆解镜头
    └─ 每个镜头含 camera/description/prompt/dialogue/BGM 情感
    │
    ▼
[4/6] 图像生成 (TongyiImageClient + PromptGenerator)
    ├─ 角色立绘（前3角色）
    ├─ 关键帧（前5个镜头）
    └─ 中英文风格组合 Prompt
    │
    ▼
[5/6] 配音生成 (TTSEngine)
    ├─ Edge-TTS 并发生成
    └─ 根据角色声线匹配音色
    │
    ▼
[6/6] 视频合成 (VideoCompositor)
    ├─ 图片 → 视频片段（Ken Burns 动效）
    ├─ 片段拼接（支持转场）
    ├─ 叠加配音（角色对话）
    └─ 烧录字幕（SRT）
    │
    ▼
最终视频输出 (final.mp4)
```

## 五、当前 MVP 优势

- **架构清晰**：模块化设计，6 步流水线松耦合
- **成本极低**：全部使用免费/低价 API
- **一键生成**：从主题到最终视频全自动
- **中文友好**：完整支持中文故事、中文配音、中文字幕
- **可扩展**：每个模块都可以独立替换（如 LLM 可换 GPT/Qwen，图像可换 SD/FLUX）

## 六、当前 MVP 已知局限

1. **图像生成限制**：只生成立绘（3角色）+ 关键帧（5镜头），非全量
2. **视频时长**：预览性质，约 30-90 秒
3. **无用户系统**：没有用户登录、项目管理
4. **无 BGM 支持**：BGM 目录存在但未集成到流水线
5. **单一 LLM 供应商**：只支持 DeepSeek
6. **无缓存机制**：每次完全重新生成
7. **无并行加速**：串行流水线，长故事耗时较大
8. **无视频风格化**：图片→视频仅 Ken Burns，无动画/转场多样化
9. **TTS 仅 Edge-TTS**：中文声线有限（8种）
10. **无错误重试机制**：LLM JSON 解析失败或 API 超时缺乏弹性
