# -*- mode: python ; coding: utf-8 -*-
import os
import sys

_is_mac = sys.platform == "darwin"
_is_win = sys.platform == "win32"
# Windows 用 .ico, macOS 用 .icns; Linux 可执行文件不内嵌图标; 文件缺失则用默认
if _is_mac:
    _icon = os.path.join("assets", "icon.icns")
elif _is_win:
    _icon = os.path.join("assets", "icon.ico")
else:
    _icon = None
if _icon is not None and not os.path.exists(_icon):
    _icon = None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除本程序用不到、但 PyInstaller 默认会扫进来的标准库, 减小 PYZ 体积
    excludes=[
        'unittest', 'doctest', 'pydoc', 'pdb',
        'test', 'tkinter.test',
    ],
    noarchive=False,
    optimize=2,        # 去掉 docstring/assert 字节码
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TickView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not _is_mac,        # macOS 上 UPX 压缩的二进制会被 Gatekeeper 拦截/在 Apple Silicon 崩溃
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

if _is_mac:
    app = BUNDLE(
        exe,
        name="TickView.app",
        icon=_icon,
        bundle_identifier="com.tickview.app",
        info_plist={
            "LSUIElement": True,            # 作为后台代理: 不在程序坞/Dock 显示, 适合悬浮小工具
            "NSHighResolutionCapable": True,
        },
    )
