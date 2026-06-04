#!/usr/bin/env bash
# TickView Linux 打包脚本: 在装有 Python 3.9+ 的 Linux 上运行,
# 产出 dist/TickView (单文件可执行)。
# 用法: chmod +x build_linux.sh && ./build_linux.sh
#
# 注意: PyInstaller 产物不跨平台 —— Linux 二进制只能在 Linux 上构建/运行。
set -e
cd "$(dirname "$0")"

# 优先用 python3, 回退到 python
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

# tkinter 在多数发行版需单独安装(非 pip 包), 缺失时给出提示
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "警告: 未检测到 tkinter, 程序无法运行。请先安装系统包:"
    echo "  Debian/Ubuntu: sudo apt install python3-tk"
    echo "  Fedora:        sudo dnf install python3-tkinter"
    echo "  Arch:          sudo pacman -S tk"
fi

# UPX 可选: 装了(在 PATH 中)会自动用于压缩, 没装也能正常打包
command -v upx >/dev/null 2>&1 || echo "提示: 未检测到 upx, 本次不压缩(可选 apt/dnf install upx)。"

"$PY" -m pip install --upgrade pyinstaller -r requirements.txt
"$PY" -m PyInstaller --noconfirm TickView.spec

echo
echo "打包完成: dist/TickView   (运行: ./dist/TickView)"
