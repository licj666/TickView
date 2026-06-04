#!/usr/bin/env bash
# TickView macOS 打包脚本: 在装有 Python 3.9+ 的 Mac 上运行,
# 产出 dist/TickView.app (无 Dock 图标的悬浮小工具)。
# 用法: chmod +x build_mac.sh && ./build_mac.sh
set -e
cd "$(dirname "$0")"

# 优先用 python3, 回退到 python
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

"$PY" -m pip install --upgrade pyinstaller -r requirements.txt
"$PY" -m PyInstaller --noconfirm TickView.spec

echo
echo "打包完成: dist/TickView.app"
echo "首次运行若提示「无法验证开发者」, 在 访达 里右键点按 App 选「打开」,"
echo "或到 系统设置 > 隐私与安全性 中点「仍要打开」。"
