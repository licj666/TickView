# TickView

> 桌面极简看盘小工具：在屏幕角落用一根迷你悬浮条实时显示 A 股 / ETF / 指数的最新价与涨跌幅，支持价格预警。
> 设计目标 —— **小、静、稳**：不弹窗、不出声、不打扰。

跨平台支持 **Windows / macOS / Linux**，纯 Python + Tkinter，无需账号、无需 API key。

---

## 功能介绍

- **迷你悬浮条**：无边框、可置顶、半透明，停在屏幕角落不挡事。
- **只显示关键信息**：每行 `最新价 涨跌幅`，**红涨绿跌**（A 股习惯）。
- **股票 / 基金 / ETF / 指数**：A 股主板·创业板·科创板·北交所，沪深 ETF/LOF/基金，以及上证指数等指数。
  价格小数位自动适配 —— 股票 2 位，基金/ETF 3 位（如卫星 ETF `159206`）。
- **点行看当日高低**：单击某行，在悬浮条下方弹出该标的**当日最高/最低**价。
- **两种显示模式**：单行轮播（多只自动切换，可滚轮手动切）/ 纵向列表（全部一次看到）。
- **价格预警**：每只可设上限/下限，越界时该行背景静默闪烁（无声、无系统弹窗）；
  点击确认后安静，价格回到区间再越界会再次提醒。
- **三源容灾**：腾讯 / 新浪 / 东财 自动切换，断网时整体变灰并静默重试。
- **配置自动保存**：股票列表、顺序、预警价、窗口位置、透明度等都存本地 JSON。

---

## 悬浮条操作（各平台通用）

启动后屏幕角落出现一根悬浮条，鼠标操作如下：

| 操作 | 行为 |
|---|---|
| **拖动** | 移动悬浮条，位置自动记忆 |
| **单击某行** | 在悬浮条下方弹出当日**最高/最低**价（常驻，再次点该行收起）；同时确认并消除该行预警闪烁 |
| **双击** | 收起成屏幕原位的 6×6 小点；点小点恢复 |
| **滚轮** | 轮播模式下手动切换上/下一只 |
| **右键** | 在窗口正下方弹出菜单：设置 / 切换显示模式 / 隐藏 / 退出 |

> macOS 上右键如无反应，请用 **Control + 点按**（副键在部分系统识别为 `Button-2`，程序已一并兼容）。

### 设置窗（右键 → 设置）

- **股票**：输入框填代码后「添加」；选中后可「删除选中」；**在列表里按住条目上下拖动可调整显示顺序**；
  点输入框后面的 **`?`** 查看完整的代码规则。
  - 6 位代码自动识别市场：`600519`（沪股）、`000001`/`300750`（深股）、`510300`（沪 ETF）、`159206`（深 ETF）、`830799`（北交所）。
  - 也可手动加前缀强制指定：`sh600519`。
  - **指数需带前缀**（沪市指数与深股数字会冲突）：上证指数 `sh000001`（也可输通达信代码 `1A0001`）、深证成指 `sz399001`、创业板指 `sz399006`、沪深300 `sh000300`。
- **预警价**：选中某只，填上限/下限（留空=不预警），点「应用」（须为正数、上限 > 下限）。
- **显示**：透明度滑块、单行轮播 / 纵向列表、轮播间隔、是否始终置顶。

### 配置文件位置

| 平台 | 路径 |
|---|---|
| Windows | `%APPDATA%\TickView\config.json` |
| macOS | `~/Library/Application Support/TickView/config.json` |
| Linux | `~/.config/TickView/config.json` |

同目录还有运行日志 `tickview.log`（自动滚动，最多约 1MB）。

---

## 按平台：安装、运行与打包

三平台都需要 **Python 3.9+**。运行依赖只有一个 `requests`（图形界面用 Python 自带的 tkinter）。
打包统一从同一份 `TickView.spec` 构建；**PyInstaller 产物不跨平台**，需在目标系统上各自打包。

### 🪟 Windows

**直接运行（源码）**

```bat
pip install -r requirements.txt
python main.py
```

**打包成单文件 `TickView.exe`**

把整个项目目录拷到装有 Python 3.9+ 的机器，**双击 `build_win.bat`** 即可：

- 产物：`dist\TickView.exe`（单文件、无控制台窗口、约 12MB，双击即用）。
- 压缩：使用项目内置的 `upx\upx.exe`（已随项目附带）；若该文件不存在则跳过压缩照常打包。
- 打包后会自动刷新 Windows 图标缓存，使 exe 新图标立即显示。
- 若图标仍是旧的：那是资源管理器的路径缓存，复制一份 exe 或注销重登即可看到（不影响功能）。

### 🍎 macOS

**直接运行（源码）**

```bash
pip3 install -r requirements.txt
python3 main.py
```

**打包成 `TickView.app`**

```bash
chmod +x build_mac.sh
./build_mac.sh
```

- 产物：`dist/TickView.app`（设了 `LSUIElement`，**不在程序坞显示**，适合悬浮小工具）。
- macOS **不使用 UPX**（压缩后的二进制会被 Gatekeeper 拦截 / 在 Apple Silicon 上崩溃）。
- 首次运行若提示「无法验证开发者」：在访达里**右键点按 App → 打开**，或到
  **系统设置 → 隐私与安全性** 点「仍要打开」（未做代码签名的正常现象）。
- 右键菜单请用 **Control + 点按**。

### 🐧 Linux

**直接运行（源码）** —— 多数发行版的 tkinter 需单独安装：

```bash
sudo apt install python3-tk        # Debian/Ubuntu（Fedora: python3-tkinter；Arch: tk）
pip3 install -r requirements.txt
python3 main.py
```

**打包成单文件可执行 `TickView`**

```bash
chmod +x build_linux.sh
./build_linux.sh                   # 产物 dist/TickView，运行 ./dist/TickView
```

- UPX 可选：装了（在 `PATH` 中）会自动压缩，没装也能打包。
- 显示差异：半透明需系统开启**合成器**（compositor）；**Wayland** 下走 XWayland，
  个别桌面（如 GNOME Wayland）对“始终置顶”支持不稳定。

---

## 项目结构

```
TickView/
├── main.py          # 入口：组装模块、启动主循环与后台行情线程
├── quote.py         # 行情：多源容灾、代码规范化、价格小数位、当日高低、交易时段
├── config.py        # 配置：本地 JSON 读写、校验、损坏回退
├── ui.py            # 界面：悬浮条 + 设置窗 + 右键菜单 + 预警闪烁 + 高低气泡
├── requirements.txt # 仅 requests
├── TickView.spec    # PyInstaller 打包配置（三平台共用，按平台分支）
├── build_win.bat    # Windows 打包脚本
├── build_mac.sh     # macOS 打包脚本
├── build_linux.sh   # Linux 打包脚本
├── upx/             # 内置的 UPX 压缩器（Windows 打包用）
├── assets/          # 应用图标 icon.ico / icon.icns / icon.png 及生成脚本
├── README.md        # 本文件
└── DESIGN.md        # 设计与实现方案
```

> 应用图标已内置（exe/app 自动使用）。如需重做：编辑 `assets/make_icon.py` 后运行
> `pip install pillow && python assets/make_icon.py` 重新生成（Pillow 仅生成图标时用，打包/运行不依赖）。

实现细节与设计取舍见 [DESIGN.md](DESIGN.md)。

---

## 常见问题

- **盘后/周末看到的是收盘价吗？** 是。非交易时段每 60 秒刷新一次（交易时段 3 秒），仅用于显示收盘价。
- **价格一直是灰色？** 说明三个数据源都暂时取不到（多为网络问题），程序会静默重试，恢复后自动变回彩色。
- **窗口找不到了？** 可能双击收成了小点，找屏幕上一个深色小方块点一下即可恢复；或删除配置文件里的 `window_x/window_y` 重置位置。
- **想加黄金 / 港股 / 美股？** 当前仅支持 A 股 / 基金 ETF / 指数，其余暂不支持。
