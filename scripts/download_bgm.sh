#!/bin/bash
# 从 FreePD / Pixabay 下载免费 BGM
# 功能：按情感分类下载到 data/bgm_library/
# 
# 用法：bash scripts/download_bgm.sh

BGM_DIR="data/bgm_library"
mkdir -p "$BGM_DIR"/{epic,tense,gentle,comic,action}

echo "请手动从以下网站下载免费 BGM 到对应目录："
echo ""
echo "  https://freepd.com/   - 全部 CC0 免版权"
echo "  https://pixabay.com/music/  - 免费商用"
echo ""
echo "目录结构："
echo "  $BGM_DIR/epic/     - 史诗/战斗音乐"
echo "  $BGM_DIR/tense/    - 悬疑/紧张音乐"
echo "  $BGM_DIR/gentle/   - 温馨/平静音乐"
echo "  $BGM_DIR/comic/    - 轻松/搞笑音乐"
echo "  $BGM_DIR/action/   - 快节奏/动作音乐"
