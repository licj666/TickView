@echo off
chcp 65001 >nul
REM TickView Windows 打包脚本: 在装有 Python 3.9+ 的 Windows 机器上运行,
REM 产出 dist\TickView.exe (单文件, 无控制台窗口, 用项目内 upx\ 压缩)
cd /d %~dp0

python -m pip install --upgrade pyinstaller -r requirements.txt || goto :error

REM 使用项目内置的 UPX 压缩(存在才启用)
set "UPX_ARG="
if exist "%~dp0upx\upx.exe" set "UPX_ARG=--upx-dir "%~dp0upx""

python -m PyInstaller --noconfirm %UPX_ARG% TickView.spec || goto :error

REM 刷新图标缓存并通知资源管理器重读, 让新 exe 图标立即显示
ie4uinit.exe -ClearIconCache >nul 2>nul
powershell -NoProfile -Command "Add-Type -Namespace Win -Name Shell -MemberDefinition '[System.Runtime.InteropServices.DllImport(\"shell32.dll\")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'; [Win.Shell]::SHChangeNotify(0x8000000,0,[System.IntPtr]::Zero,[System.IntPtr]::Zero)" >nul 2>nul

echo.
echo 打包完成: dist\TickView.exe
pause
exit /b 0

:error
echo.
echo 打包失败, 请检查上面的错误信息
pause
exit /b 1
