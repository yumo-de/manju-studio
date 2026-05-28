# Manju Studio — 项目当前状态报告

> 更新日期: 2026-05-28
> 版本: v0.3.0

---

## 一、完成的工作

### 基础设施
- [x] 依赖安装（Python 3.11 + 70 个包）
- [x] 项目可运行（Gradio 前端 http://localhost:7860）
- [x] 代码已推送 GitHub（SSH remote 已配）

### #1 LLM JSON 容错重试
- [x] `_repair_json()` — 自动修复 7 种 JSON 格式错误
- [x] `_safe_json_parse()` — 3 级递进修复策略
- [x] `chat_json()` 自动重试 — 最多 3 次，指数退避
- [x] HTTP 网络错误自动重试
- [x] Prompt 模板增强（JSON 严格格式要求）

### #2 全局异常处理
- [x] `StepResult` 类 — 每步状态追踪
- [x] 每一步独立 try/except — 单步失败不阻塞整体
- [x] 智能降级策略（剧本失败→从大纲提取、TTS 跳过→无声视频）
- [x] 自动生成 `pipeline_report.json`

### #3 BGM 集成
- [x] `BGMSelector` — 按 bgm_mood 自动匹配 BGM
- [x] 8 种情绪分类（epic/tense/gentle/comic/action/sad/mystery/happy）
- [x] 无 BGM 时自动下载默认音乐

### #4 全量图片生成
- [x] 移除角色立绘 `[:3]` 限制 → 所有角色
- [x] 移除关键帧 `[:5]` 限制 → 所有镜头
- [x] 每日 50 张免费额度保护

### #5 多线程并行优化
- [x] **分镜头多线程** — `ThreadPoolExecutor(4)` 并行处理场景
- [x] **图片多线程** — 角色立绘 + 关键帧同时生成
- [x] **按幕视频合成** — 每幕独立线程生成，最后拼接

### #6 一致性保障
- [x] 分镜头传递角色/世界观/画风上下文
- [x] 约束规则：同角色在不同场景中外貌一致
- [x] 图片 Prompt 基于统一角色描述生成

### #7 分步可视化前端
- [x] 全流程节点图（6步，带状态图标）
- [x] 每步：生成 → 预览 → 编辑 JSON → 确认 → 自动下一步
- [x] 图片画廊、音频播放器、视频播放器
- [x] 当前步骤高亮 + 状态实时更新

---

## 二、当前阶段：Phase 1 & 2 完成，Phase 3 待启动

```
Phase 1: MVP 巩固     ████████████████████ 100% ✅
Phase 2: 核心增强     ████████████████████ 100% ✅ ← 现在在这里
Phase 3: 专业升级     ░░░░░░░░░░░░░░░░░░░░   0%
Phase 4: 平台化       ░░░░░░░░░░░░░░░░░░░░   0%
```

---

## 三、流水线架构图（当前状态）

```
                    ┌─ 多线程并行(4线程) ─┐
                    ▼                     ▼
[1] 📖 故事大纲 → [2] 📜 剧本 → [3] 🎥 分镜头 → [4] 🖼️ 图片 ──→ [5] 🎤 配音 ──→ [6] 🎬 视频
                                                                                     │
                    ┌────────────────────────────────────────────────────────────────┘
                    ▼
             按幕多线程合成
             Act 1 ████████╗
             Act 2 ████████║ → 拼接 → 最终视频
             Act 3 ████████╝
```

---

## 四、后续任务（按优先级排序）

### Phase 2: 核心增强 (P1) — 已完成 ✅

```
优先级  任务                状态    说明
─────────────────────────────────────────────────────
P0      配置通义万相 Key     ✅     wan2.7-image-pro 已配
P1      多 LLM 供应商        ⬜     后续添加（独立，不阻塞其他任务）
P2      Image Provider 抽象   ⬜     后续添加
P3      缓存机制             ✅     ImageCache, SHA256 key, 自动淘汰
P4      RIFE 60fps 插帧      ✅     ffmpeg minterpolate, 可选 rife-ncnn-vulkan
P5      多转场自动编排        ✅     8种情绪→转场映射, 智能选择
P6      字幕样式定制          ✅     字体/颜色/描边/对齐 可配置
```

### Phase 3: 专业升级 (P2)

```
P7      CosyVoice 本地 TTS  8h       高拟真情感语音（免费）
P8      GPT-SoVITS 角色克隆  10h      克隆角色声音
P9      AI 音乐生成         6h       自动作曲
P10     统一画风策略         10h      SD LoRA/风格参考图
P11     用户/项目管理        6h       登录、历史记录
P12     多平台导出          4h       横版/竖版/方形
```

### Phase 4: 平台化 (P3)

```
P13     REST API            8h       OpenAPI 接口
P14     一键发布到B站/抖音   6h
P15     SaaS 化部署          10h
```

---

## 五、技术栈清单

|| 组件 | 当前选型 | 成本 | 可选替代 |
||------|---------|------|----------|
|| LLM | DeepSeek Chat | ~¥0.5/百万 token | Qwen, GLM, GPT, Claude |
|| 图像生成 | 通义万相 wan2.7-image-pro | 50张/天免费 | SD, FLUX, DALL-E |
|| 语音合成 | Edge-TTS | 免费 | CosyVoice, GPT-SoVITS |
|| 视频合成 | ffmpeg + minterpolate 插帧 | 免费 | rife-ncnn-vulkan |
|| 图片缓存 | ImageCache (本地) | 免费 | — |
|| 转场效果 | ffmpeg xfade (16种) | 免费 | — |
|| Web 界面 | Gradio 6.14 | 免费 | — |
|| 部署 | 本地 Linux (WSL) | 免费 | 云服务器 |

---

## 六、关键命令速查

```bash
# 启动前端
cd ~/Desktop/work_project/manju-studio
source .venv/bin/activate
python3 app.py
# → http://localhost:7860

# 命令行测试流水线
cd ~/Desktop/work_project/manju-studio
.venv/bin/python3 pipeline.py "你的故事主题"

# 推送到 GitHub
cd ~/Desktop/work_project/manju-studio
git push origin main

# SSH remote（已配）: git@github.com:yumo-de/manju-studio.git
```

|--|

## 七、已知问题

1. ~~**缺少图片 API Key** — 通义万相未配置，流水线到第4步自动跳过~~ ✅ 已配
2. **TTS 声线匹配不完善** — `voice_style` 是描述性文本（如"清脆、充满童真"），不是精确的声线名称，需要改进匹配逻辑（Phase 3 P7/P8 解决）
3. **单场景分镜头耗时** — 每个场景 5-10 秒 LLM 调用，25个场景约 2-4 分钟，后续可通过减少场景数优化
4. **GitHub 被墙** — 推送走 SSH（已配），拉取用 `gh-proxy.com` 镜像
5. **BGM 素材库为空** — `data/bgm_library/` 目录存在但无实际音频文件，下载脚本待完善
6. **Web UI 启动问题** — `app.py` 在某些环境可能因 GPU 版本问题卡住，需要调试
