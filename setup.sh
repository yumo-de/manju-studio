#!/bin/bash
# 漫剧系统 - 一键初始化脚本
set -e

echo "🚀 漫剧工作室 - 初始化..."

# 1. 检查 Python
echo "[1/4] 检查 Python..."
python3 --version || { echo "需要 Python 3.11+"; exit 1; }

# 2. 安装依赖
echo "[2/4] 安装依赖..."
pip install -e ".[dev]" --break-system-packages

# 3. 复制 .env
echo "[3/4] 设置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   请编辑 .env 填入 API Key:"
    echo "   - DEEPSEEK_API_KEY (必填，已注册)"
    echo "   - TONGYI_API_KEY (选填，0成本方案，每天免费50张)"
fi

# 4. 下载免费 BGM
echo "[4/4] 准备 BGM 素材库..."
mkdir -p data/bgm_library/{epic,tense,gentle,comic,action}
echo "   BGM 目录已创建：data/bgm_library/"
echo "   请从 https://freepd.com/ 下载免费音乐放入对应目录"

echo ""
echo "✅ 初始化完成！"
echo "运行: cd manju-studio && python3 app.py"
echo "浏览器打开: http://localhost:7860"
