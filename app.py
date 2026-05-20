"""
Task 12: Gradio Web 界面
漫剧生成工作室 — 输入主题 → 点击生成 → 预览视频
"""
import threading
import time
from pathlib import Path

import gradio as gr

from pipeline import ManjuPipeline

pipeline = ManjuPipeline()


def generate_video(theme: str, progress=gr.Progress()):
    """在后台线程运行 Pipeline，返回视频路径、状态和故事预览。"""
    progress(0, desc="初始化...")
    result = {"video": None, "status": "", "story": "", "error": ""}

    def run():
        try:
            project_id = pipeline.run(theme)
            project_dir = pipeline.work_dir / project_id
            video_path = project_dir / "video" / "final.mp4"
            story_path = project_dir / "story.json"

            if video_path.exists():
                result["video"] = str(video_path)
            if story_path.exists():
                import json
                story_data = json.loads(story_path.read_text(encoding="utf-8"))
                title = story_data.get("title", "未命名")
                summary = story_data.get("plot_summary", "")
                characters = story_data.get("characters", [])
                char_list = "、".join(c.get("name", "") for c in characters[:3])
                result["story"] = (
                    f"**{title}**\n\n"
                    f"{summary}\n\n"
                    f"角色：{char_list}"
                )
            result["status"] = f"✅ 项目 {project_id} 完成!"
        except Exception as e:
            result["error"] = str(e)
            result["status"] = f"❌ 生成失败: {e}"

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    # 简单轮询（实时场景应改用消息队列）
    while thread.is_alive():
        time.sleep(0.5)

    if result["error"]:
        return None, result["status"], ""

    return result["video"], result["status"], result["story"]


# 构建界面
with gr.Blocks(
    title="漫剧工作室",
    theme=gr.themes.Soft(),
    css="""
        footer { display: none !important; }
        .gradio-container { max-width: 1200px !important; margin: auto; }
    """,
) as demo:
    gr.Markdown(
        """
    # 🎬 漫剧生成工作室

    **输入故事主题 → AI 自动生成完整的漫剧视频**
    """
    )

    with gr.Row():
        with gr.Column(scale=1):
            theme_input = gr.Textbox(
                label="📝 故事主题",
                placeholder="例如：一个武侠少年意外获得上古神剑，踏上江湖之路",
                lines=3,
            )
            generate_btn = gr.Button("🎬 生成漫剧", variant="primary", size="lg")

            gr.Markdown(
                """
                ---
                ### 💡 示例主题
                - 一个小女孩在森林里发现了一只会说话的兔子
                - 星际探险家发现了一颗神秘的未知星球
                - 古代剑客在月夜下与神秘对手对决
                """
            )

        with gr.Column(scale=2):
            video_output = gr.Video(label="🎥 生成的漫剧", height=480)

    with gr.Row():
        status = gr.Markdown("等待输入...")

    with gr.Row():
        story_preview = gr.Markdown(label="📖 故事预览")

    generate_btn.click(
        fn=generate_video,
        inputs=theme_input,
        outputs=[video_output, status, story_preview],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
