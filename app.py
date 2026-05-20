"""
Manju Studio — 漫剧生成工作室 (Pipeline 可视化版)

全流程节点可视化，每步状态一目了然。
"""

from __future__ import annotations

import json
from pathlib import Path

import gradio as gr

from pipeline import ManjuPipeline
from manju.schemas.story import Story, Shot as ShotModel
from manju.tts.engine import TTSEngine

pipeline = ManjuPipeline()

# ── 步骤定义 ──
STEPS = [
    {"id": 1, "icon": "📖", "name": "故事大纲", "key": "story"},
    {"id": 2, "icon": "📜", "name": "剧本", "key": "script"},
    {"id": 3, "icon": "🎥", "name": "分镜头", "key": "storyboard"},
    {"id": 4, "icon": "🖼️", "name": "图片生成", "key": "images"},
    {"id": 5, "icon": "🎤", "name": "配音生成", "key": "audio"},
    {"id": 6, "icon": "🎬", "name": "合成视频", "key": "video"},
]

STATUS_ICONS = {"pending": "⏳", "active": "▶️", "done": "✅", "failed": "❌", "skipped": "⭕"}
STATUS_COLORS = {"pending": "#9ca3af", "active": "#3b82f6", "done": "#22c55e", "failed": "#ef4444", "skipped": "#f59e0b"}


def build_pipeline_html(current_step: int, statuses: dict[int, str]) -> str:
    """生成全流程节点可视化 HTML。"""
    cols = []
    for i, step in enumerate(STEPS):
        sid = step["id"]
        icon = step["icon"]
        name = step["name"]
        st = statuses.get(sid, "pending")
        s_icon = STATUS_ICONS[st]
        color = STATUS_COLORS[st]
        is_current = sid == current_step
        is_last = i == len(STEPS) - 1

        active_class = "pulse-glow" if is_current else ""
        box_shadow = "0 0 12px rgba(59,130,246,0.5)" if is_current else "none"
        transform = "scale(1.08)" if is_current else "none"
        border_w = "3px" if is_current else "2px"
        bg = "white" if st in ("done", "active") else "#f3f4f6"
        min_w = "110px" if is_current else "90px"
        fs = "14px" if is_current else "12px"
        icon_fs = "24px" if is_current else "20px"
        fw = "700" if is_current else "600"

        col = f"""<div style="text-align:center; flex:{'1.3' if is_current else '1'}">
          <div class="step-node {active_class}" style="background:{bg}; border:{border_w} solid {color}; border-radius:12px; padding:8px 6px; margin:0 2px; box-shadow:{box_shadow}; transform:{transform}; transition:all 0.3s ease; min-width:{min_w}; font-size:{fs};">
            <div style="font-size:{icon_fs}">{icon}</div>
            <div style="font-weight:{fw}; margin:2px 0; color:#1f2937">{name[:4]}</div>
            <div style="font-size:11px; color:{color}">{s_icon} {st}</div>
          </div>
          {'' if is_last else f'<div style="flex:1; height:2px; background:{color if st=="done" else "#e5e7eb"}; margin:0 -2px;"></div>'}
        </div>"""
        cols.append(col)

    return f"""<style>
      @keyframes pulseGlow {{
        0% {{ box-shadow: 0 0 5px rgba(59,130,246,0.3); }}
        50% {{ box-shadow: 0 0 18px rgba(59,130,246,0.6); }}
        100% {{ box-shadow: 0 0 5px rgba(59,130,246,0.3); }}
      }}
      .pulse-glow {{ animation: pulseGlow 2s infinite; }}
      .step-node:hover {{ transform: scale(1.05) !important; }}
    </style>
    <div style="display:flex; align-items:center; gap:0; padding:16px 8px; background:#f9fafb; border-radius:16px;">
      {''.join(cols)}
    </div>"""


def read_json(path: str) -> dict | list | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# =========================================================================
# UI 构建
# =========================================================================

CSS = """
footer { display: none !important; }
.gradio-container { max-width: 1200px !important; margin: auto; }
"""

with gr.Blocks(title="漫剧工作室") as demo:
    # ── 状态变量 ──
    cur_step = gr.State(1)
    step_statuses = gr.State({s["id"]: "pending" for s in STEPS})
    proj_dir = gr.State("")

    gr.Markdown("# 🎬 漫剧生成工作室\n**全流程可视化 — 每步可预览、编辑、确认后再继续**")

    # ── Pipeline 节点图 ──
    pipeline_html = gr.HTML(build_pipeline_html(1, {s["id"]: "pending" for s in STEPS}))

    # ── 主题输入 ──
    with gr.Row():
        theme_input = gr.Textbox(label="故事主题", placeholder="例如：一个武侠少年意外获得上古神剑，踏上江湖之路", lines=2, scale=4)

    # ======== 步骤 1 ========
    with gr.Column(visible=True) as panel_1:
        gr.Markdown("### 📖 步骤 1：故事大纲")
        step1_btn = gr.Button("✨ 生成故事大纲", variant="primary", size="sm")
        step1_status = gr.Markdown("等待生成...")
        step1_preview = gr.Markdown(visible=False)
        step1_editor = gr.Textbox(label="编辑故事 JSON", lines=10, visible=False)
        step1_confirm = gr.Button("✅ 确认并下一步", variant="secondary", visible=False, size="sm")
        step1_msg = gr.Markdown(visible=False)

    # ======== 步骤 2 ========
    with gr.Column(visible=False) as panel_2:
        gr.Markdown("### 📜 步骤 2：剧本")
        step2_preview = gr.Markdown("等待生成...")
        step2_btn = gr.Button("✨ 生成剧本", variant="primary", size="sm")
        step2_status = gr.Markdown("")
        step2_editor = gr.Textbox(label="编辑剧本 JSON", lines=10, visible=False)
        step2_confirm = gr.Button("✅ 确认并下一步", variant="secondary", visible=False, size="sm")
        step2_msg = gr.Markdown(visible=False)

    # ======== 步骤 3 ========
    with gr.Column(visible=False) as panel_3:
        gr.Markdown("### 🎥 步骤 3：分镜头")
        step3_preview = gr.Markdown("等待生成...")
        step3_btn = gr.Button("✨ 生成全部分镜头", variant="primary", size="sm")
        step3_status = gr.Markdown("")
        step3_editor = gr.Textbox(label="编辑分镜头 JSON", lines=10, visible=False)
        step3_confirm = gr.Button("✅ 确认并下一步", variant="secondary", visible=False, size="sm")
        step3_msg = gr.Markdown(visible=False)

    # ======== 步骤 4 ========
    with gr.Column(visible=False) as panel_4:
        gr.Markdown("### 🖼️ 步骤 4：图片生成")
        step4_btn = gr.Button("✨ 生成图片", variant="primary", size="sm")
        step4_status = gr.Markdown("")
        step4_gallery = gr.Gallery(label="角色立绘 + 关键帧", columns=4, height=280, visible=False)
        step4_msg = gr.Markdown(visible=False)
        step4_next = gr.Button("➡️ 下一步（配音）", variant="secondary", visible=False, size="sm")

    # ======== 步骤 5 ========
    with gr.Column(visible=False) as panel_5:
        gr.Markdown("### 🎤 步骤 5：配音生成")
        step5_btn = gr.Button("✨ 生成配音", variant="primary", size="sm")
        step5_status = gr.Markdown("")
        step5_audio = gr.Audio(label="试听第一条配音", visible=False, type="filepath")
        step5_msg = gr.Markdown(visible=False)
        step5_next = gr.Button("➡️ 下一步（合成视频）", variant="secondary", visible=False, size="sm")

    # ======== 步骤 6 ========
    with gr.Column(visible=False) as panel_6:
        gr.Markdown("### 🎬 步骤 6：合成视频")
        step6_btn = gr.Button("🎬 合成最终视频", variant="primary", size="lg")
        step6_status = gr.Markdown("")
        step6_video = gr.Video(label="最终漫剧视频", height=400, visible=False)
        step6_msg = gr.Markdown(visible=False)

    gr.Markdown("""---
    ### 示例主题
    - 一个小女孩在森林里发现了一只会说话的兔子
    - 星际探险家发现了一颗神秘的未知星球
    - 古代剑客在月夜下与神秘对手对决""")


    # =====================================================================
    # 工具函数
    # =====================================================================

    def advance_step(cur: int, statuses: dict, proj: str, step_key: str, new_status: str = "done"):
        nxt = min(cur + 1, len(STEPS))
        statuses = dict(statuses)
        statuses[cur] = new_status
        statuses[nxt] = "active"
        html = build_pipeline_html(nxt, statuses)
        vis = [gr.update(visible=s["id"] == nxt) for s in STEPS]
        return (html, nxt, statuses, *vis)

    # =====================================================================
    # 步骤 1
    # =====================================================================

    def s1_gen(theme):
        if not theme.strip():
            return [gr.update(), gr.update(value="请输入故事主题"),
                    gr.update(), gr.update(), gr.update()]
        try:
            story = pipeline.expander.expand(theme)
            js = story.model_dump_json(indent=2, ensure_ascii=False)
            prev = f"📖 **{story.title}**（{story.genre}）\n\n{story.plot_summary[:200]}\n\n角色：{'、'.join(c.name for c in story.characters[:5])}"
            return [gr.update(value=js, visible=True),
                    gr.update(value=f"✅ 故事《{story.title}》生成成功！"),
                    gr.update(value=prev, visible=True),
                    gr.update(visible=True), gr.update()]
        except Exception as e:
            return [gr.update(), gr.update(value=f"❌ {e}"),
                    gr.update(), gr.update(), gr.update()]

    step1_btn.click(fn=s1_gen, inputs=[theme_input],
                    outputs=[step1_editor, step1_status, step1_preview, step1_confirm, step1_msg])

    def s1_confirm(js, cur, sts):
        from datetime import datetime, timezone
        data = json.loads(js)
        pid = datetime.now(timezone.utc).strftime("proj_%Y%m%d_%H%M%S")
        pd_ = str(pipeline.work_dir / pid)
        Path(pd_).mkdir(parents=True, exist_ok=True)
        write_json(f"{pd_}/story.json", data)
        story = Story(**data)
        prev = f"📖 **{story.title}**（{story.genre}）\n\n{story.plot_summary[:200]}"
        ret = advance_step(cur, sts, pd_, "story")
        return [pd_, gr.update(value=f"✅ 已确认 — {prev}"), gr.update(visible=True), *ret]

    step1_confirm.click(fn=s1_confirm, inputs=[step1_editor, cur_step, step_statuses],
                        outputs=[proj_dir, step1_msg, step1_preview,
                                 pipeline_html, cur_step, step_statuses,
                                 panel_1, panel_2, panel_3, panel_4, panel_5, panel_6])

    # =====================================================================
    # 步骤 2
    # =====================================================================

    def s2_gen(proj):
        if not proj:
            return [gr.update(), gr.update(value="请先完成步骤1"), gr.update(), gr.update()]
        try:
            sd = read_json(f"{proj}/story.json")
            story = Story(**sd)
            scenes = pipeline.scriptwriter.write(story)
            js = json.dumps(scenes, ensure_ascii=False, indent=2)
            write_json(f"{proj}/scenes.json", scenes)
            n = len(scenes)
            prev = f"🎬 共 **{n}** 个场景\n\n" + "\n".join(f"- 场景{sc.get('scene_id','?')}: {sc.get('location','?')} ({sc.get('time','?')})" for sc in scenes[:5])
            if n > 5:
                prev += f"\n- ... 还有 {n-5} 个场景"
            return [gr.update(value=js, visible=True),
                    gr.update(value=f"✅ 共 {n} 个场景"),
                    gr.update(value=prev), gr.update(visible=True)]
        except Exception as e:
            return [gr.update(), gr.update(value=f"❌ {e}"), gr.update(), gr.update()]

    step2_btn.click(fn=s2_gen, inputs=[proj_dir],
                    outputs=[step2_editor, step2_status, step2_preview, step2_confirm])

    def s2_confirm(proj, js, cur, sts):
        data = json.loads(js)
        write_json(f"{proj}/scenes.json", data)
        n = len(data)
        ret = advance_step(cur, sts, proj, "script")
        return [gr.update(value=f"✅ **{n}** 个场景已确认"), gr.update(visible=True), *ret]

    step2_confirm.click(fn=s2_confirm, inputs=[proj_dir, step2_editor, cur_step, step_statuses],
                        outputs=[step2_msg, step2_preview,
                                 pipeline_html, cur_step, step_statuses,
                                 panel_1, panel_2, panel_3, panel_4, panel_5, panel_6])

    # =====================================================================
    # 步骤 3
    # =====================================================================

    def s3_gen(proj):
        if not proj:
            return [gr.update(), gr.update(value="请先完成步骤1"), gr.update(), gr.update()]
        try:
            sd = read_json(f"{proj}/story.json")
            sc = read_json(f"{proj}/scenes.json")
            story = Story(**sd)
            sb = pipeline.shot_generator.generate(story, sc)
            js = sb.model_dump_json(indent=2, ensure_ascii=False)
            write_json(f"{proj}/storyboard.json", json.loads(js))
            shots = sb.shots
            dur = sum(s.duration for s in shots)
            prev = f"🎥 **{len(shots)}** 个镜头，约 **{dur}秒**\n\n" + "\n".join(f"- **#{s.shot_id}** [{s.camera.type}/{s.camera.move}] {s.description[:30]}..." for s in shots[:5])
            if len(shots) > 5:
                prev += f"\n- ... 还有 {len(shots)-5} 个镜头"
            return [gr.update(value=js, visible=True),
                    gr.update(value=f"✅ 共 {len(shots)} 个镜头，{dur}s"),
                    gr.update(value=prev), gr.update(visible=True)]
        except Exception as e:
            return [gr.update(), gr.update(value=f"❌ {e}"), gr.update(), gr.update()]

    step3_btn.click(fn=s3_gen, inputs=[proj_dir],
                    outputs=[step3_editor, step3_status, step3_preview, step3_confirm])

    def s3_confirm(proj, js, cur, sts):
        data = json.loads(js)
        write_json(f"{proj}/storyboard.json", data)
        shots = data.get("shots", [])
        dur = sum(s.get("duration", 5) for s in shots)
        ret = advance_step(cur, sts, proj, "storyboard")
        return [gr.update(value=f"✅ **{len(shots)}** 个镜头，**{dur}秒** 已确认"), gr.update(visible=True), *ret]

    step3_confirm.click(fn=s3_confirm, inputs=[proj_dir, step3_editor, cur_step, step_statuses],
                        outputs=[step3_msg, step3_preview,
                                 pipeline_html, cur_step, step_statuses,
                                 panel_1, panel_2, panel_3, panel_4, panel_5, panel_6])

    # =====================================================================
    # 步骤 4
    # =====================================================================

    def s4_gen(proj):
        if not proj:
            return [gr.update(), gr.update(value="请先完成前面的步骤")]
        if not pipeline._image_available:
            return [gr.update(), gr.update(value="⚠ 未配置通义万相 API Key，跳过图片生成")]
        try:
            sd = read_json(f"{proj}/story.json")
            sbd = read_json(f"{proj}/storyboard.json")
            story = Story(**sd)
            cd = Path(proj) / "characters"
            kd = Path(proj) / "keyframes"
            cd.mkdir(exist_ok=True)
            kd.mkdir(exist_ok=True)
            imgs = []
            for i, ch in enumerate(story.characters[:3]):
                sty = pipeline.prompt_gen.STYLE_PREFIX.get(story.genre, pipeline.prompt_gen.STYLE_PREFIX["仙侠"])["en"]
                pm = f"Portrait of {ch.name}, {ch.appearance}, {sty}, character portrait"
                try:
                    urls = pipeline.image_client.generate(pm, n=1)
                    if urls:
                        fp = cd / f"{ch.name}.png"
                        pipeline.image_client.download(urls[0], fp)
                        imgs.append(str(fp))
                except Exception:
                    pass
            for j, s in enumerate(sbd.get("shots", [])[:5]):
                shot = ShotModel(**s)
                pm = pipeline.prompt_gen.build_prompt(shot, story.genre)
                try:
                    urls = pipeline.image_client.generate(pm, n=1)
                    if urls:
                        fp = kd / f"shot_{s.get('shot_id',j):04d}.png"
                        pipeline.image_client.download(urls[0], fp)
                        imgs.append(str(fp))
                except Exception:
                    pass
            return [gr.update(value=imgs, visible=True),
                    gr.update(value=f"✅ 生成 {len(imgs)} 张图片")]
        except Exception as e:
            return [gr.update(), gr.update(value=f"❌ {e}")]

    step4_btn.click(fn=s4_gen, inputs=[proj_dir],
                    outputs=[step4_gallery, step4_status])

    def s4_next(cur, sts, proj):
        ns = "done" if pipeline._image_available else "skipped"
        ret = advance_step(cur, sts, proj, "images", ns)
        msg = "✅ 已确认" if pipeline._image_available else "⭕ 已跳过（无 API Key）"
        return [gr.update(value=msg), *ret]

    step4_next.click(fn=s4_next, inputs=[cur_step, step_statuses, proj_dir],
                     outputs=[step4_msg,
                              pipeline_html, cur_step, step_statuses,
                              panel_1, panel_2, panel_3, panel_4, panel_5, panel_6])

    # =====================================================================
    # 步骤 5
    # =====================================================================

    def s5_gen(proj):
        if not proj:
            return [gr.update(), gr.update(value="请先完成前面的步骤")]
        try:
            sd = read_json(f"{proj}/story.json")
            sbd = read_json(f"{proj}/storyboard.json")
            story = Story(**sd)
            ad = Path(proj) / "audio"
            ad.mkdir(exist_ok=True)
            tts = TTSEngine(output_dir=str(ad))
            chars_dict = {ch.name: {"voice_style": ch.voice_style, "gender": ch.gender} for ch in story.characters}
            shots = [ShotModel(**s) for s in sbd.get("shots", [])]
            paths = tts.generate_dialogue(shots, chars_dict)
            fp = str(paths[0]) if paths else ""
            return [gr.update(value=fp, visible=bool(fp)),
                    gr.update(value=f"✅ 生成 {len(paths)} 条配音")]
        except Exception as e:
            return [gr.update(), gr.update(value=f"⭕ 配音跳过（可继续）: {e}")]

    step5_btn.click(fn=s5_gen, inputs=[proj_dir],
                    outputs=[step5_audio, step5_status])

    def s5_next(cur, sts, proj):
        ret = advance_step(cur, sts, proj, "audio")
        return [gr.update(value="✅ 已确认"), *ret]

    step5_next.click(fn=s5_next, inputs=[cur_step, step_statuses, proj_dir],
                     outputs=[step5_msg,
                              pipeline_html, cur_step, step_statuses,
                              panel_1, panel_2, panel_3, panel_4, panel_5, panel_6])

    # =====================================================================
    # 步骤 6
    # =====================================================================

    def s6_gen(proj):
        if not proj:
            return [gr.update(), gr.update(value="请先完成前面的步骤")]
        try:
            pp = Path(proj)
            sbd = read_json(f"{proj}/storyboard.json")
            shots = [ShotModel(**s) for s in sbd.get("shots", [])]
            kd = pp / "keyframes"
            vd = pp / "video"
            vd.mkdir(exist_ok=True)

            clips, subs, ct = [], [], 0.0
            for s in shots:
                ip = kd / f"shot_{s.shot_id:04d}.png"
                if not ip.exists():
                    continue
                cp = pipeline.compositor.build_shot_clip(str(ip), float(s.duration), "zoom-in")
                clips.append(cp)
                if s.dialogue:
                    subs.append({"start": ct, "end": ct + s.duration,
                                 "text": f"{s.speaker+': ' if s.speaker else ''}{s.dialogue}"})
                ct += float(s.duration)
            if not clips:
                return [gr.update(), gr.update(value="没有可用的图片来合成视频")]

            rv = str(vd / "raw.mp4")
            pipeline.compositor.concatenate_clips(clips, rv)

            af = sorted((pp / "audio").glob("shot_*.mp3"))
            if af:
                try:
                    if len(af) > 1:
                        mx = str(vd / "audio_mixed.mp3")
                        ManjuPipeline._concat_audio([str(p) for p in af], mx)
                        src = mx
                    else:
                        src = str(af[0])
                    va = str(vd / "with_audio.mp4")
                    pipeline.compositor.add_audio(rv, src, va)
                    rv = va
                except Exception:
                    pass

            fv = str(vd / "final.mp4")
            if subs:
                pipeline.compositor.add_subtitles(rv, subs, fv)
            else:
                fv = rv

            return [gr.update(value=fv, visible=True),
                    gr.update(value=f"✅ 视频合成完成！{len(clips)} 个片段")]
        except Exception as e:
            return [gr.update(), gr.update(value=f"❌ 合成失败: {e}")]

    step6_btn.click(fn=s6_gen, inputs=[proj_dir],
                    outputs=[step6_video, step6_status])


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft(),
        css=CSS,
    )
