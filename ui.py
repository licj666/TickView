"""界面模块: 悬浮条主窗、右键菜单、设置窗与预警闪烁."""
import logging
import queue
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import config
import quote

log = logging.getLogger(__name__)

COLOR_BG = "#1f1f1f"
COLOR_UP = "#ff5252"        # A 股习惯: 红涨
COLOR_DOWN = "#26c281"      # 绿跌
COLOR_FLAT = "#c8c8c8"
COLOR_STALE = "#787878"     # 网络异常时整体变灰
FLASH_COLORS = ("#5a1f1f", "#4a3a10")  # 预警闪烁交替背景色
if sys.platform == "win32":
    FONT_FAMILY = "Consolas"
elif sys.platform == "darwin":
    FONT_FAMILY = "Menlo"
else:
    FONT_FAMILY = "monospace"
FONT = (FONT_FAMILY, 10)
ROW_WIDTH = 16              # 行宽(字符), 保证轮播切换时窗口尺寸稳定
DRAG_THRESHOLD = 5          # 像素, 区分点击与拖动
POLL_MS = 200               # 行情队列轮询周期
FLASH_MS = 500              # 闪烁半周期

_ADD_HELP = """直接输入 6 位代码, 自动识别市场:
  6 / 9 开头 → 沪市股票        例 600519、688981
  0 / 3 开头 → 深市股票        例 000001、300750
  5 开头     → 沪市基金 / ETF   例 510300
  1 开头     → 深市基金 / ETF   例 159206
  4 / 8 开头 → 北交所          例 830799

指数需带 sh / sz 前缀(沪市指数与深市股票数字会冲突):
  上证指数  sh000001  (也可直接输 1A0001)
  深证成指  sz399001
  创业板指  sz399006
  沪深300   sh000300
  上证50    sh000016

其他说明:
  · 也可手动加前缀强制指定市场, 如 sh600519。
  · 价格小数位自动适配: 股票 2 位, 基金 / ETF 3 位。
  · 点悬浮条某行可查看当日最高 / 最低价。

暂不支持: 黄金等上海黄金交易所现货、港股、美股。"""


class TickViewApp:
    """悬浮条应用. 行情数据由外部线程经 in_queue 送入, 本类只在 UI 线程操作."""

    def __init__(self, cfg, in_queue):
        self._cfg = cfg
        self._queue = in_queue
        self._quotes = {}           # code -> quote.Quote, 累计最新行情
        self._alerts = {}           # code -> {"upper_armed","lower_armed","active"}
        self._stale = False         # 最近一次拉取是否失败
        self._flash_on = False
        self._carousel_index = 0
        self._packed = None         # 当前已 pack 的行下标签名, 避免反复重排
        self._drag_start = None
        self._dragging = False
        self._dot = None            # 隐藏后的角落小点窗口
        self._hidden_pos = None
        self._settings_win = None
        self._tip = None            # 点击某行显示当日高/低的小气泡(再次点击收起)
        self._tip_label = None
        self._tip_code = None       # 当前气泡对应的股票代码, None=未显示
        self.on_config_changed = lambda: None  # 由 main 注入, 通知行情线程

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", cfg["always_on_top"])
        self.root.attributes("-alpha", cfg["opacity"])
        self.root.configure(bg=COLOR_BG)
        if sys.platform == "darwin":
            # 让无边框悬浮窗在所有桌面/全屏空间上方显示且不抢焦点
            try:
                self.root.tk.call("::tk::unsupported::MacWindowStyle", "style",
                                  self.root._w, "plain", "noActivates")
            except tk.TclError:
                pass
        self._place_window()

        self._frame = tk.Frame(self.root, bg=COLOR_BG)
        self._frame.pack()
        self._rows = []             # [(code 或 None, Label)]
        self._rebuild_rows()

        self._menu = self._build_menu()
        self._bind_window_events(self.root)

        self.root.after(POLL_MS, self._poll_queue)
        self.root.after(FLASH_MS, self._flash_tick)
        self._schedule_carousel()

    # ---------- 对外接口 ----------

    def run(self):
        self.root.mainloop()

    def subscribed_codes(self):
        """供行情线程读取当前订阅的代码列表."""
        return [s["code"] for s in self._cfg["stocks"]]

    # ---------- 窗口与行 ----------

    def _place_window(self):
        x, y = self._cfg["window_x"], self._cfg["window_y"]
        if x is None or y is None:
            x = max(0, self.root.winfo_screenwidth() - 240)
            y = 30 if sys.platform == "darwin" else 8   # 避开 macOS 顶部菜单栏
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _rebuild_rows(self):
        for _, label in self._rows:
            label.destroy()
        self._rows = []
        self._packed = None
        stocks = self._cfg["stocks"]
        if not stocks:
            label = self._make_row_label(" 右键菜单添加股票")
            self._rows.append((None, label))
        else:
            for stock in stocks:
                self._rows.append((stock["code"], self._make_row_label("")))
        if self._carousel_index >= len(self._rows):
            self._carousel_index = 0
        self._refresh_display()

    def _make_row_label(self, text):
        label = tk.Label(self._frame, text=text, font=FONT, bg=COLOR_BG,
                         fg=COLOR_FLAT, anchor="w", width=ROW_WIDTH, padx=6)
        self._bind_window_events(label)
        return label

    def _refresh_display(self):
        mode = self._cfg["mode"]
        visible = tuple(i for i in range(len(self._rows))
                        if mode == "list" or i == self._carousel_index)
        if visible != self._packed:
            self._hide_tip()    # 布局变化(轮播/模式切换/增删行)时收起高低气泡, 避免错位
            for _, label in self._rows:
                label.pack_forget()
            for i in visible:
                self._rows[i][1].pack(fill="x")
            self._packed = visible
        for code, label in self._rows:
            if code is None:
                continue
            label.configure(text=self._row_text(code), fg=self._row_fg(code),
                            bg=self._row_bg(code))

    def _row_text(self, code):
        q = self._quotes.get(code)
        if q is None:
            return f"{'--':>8} {'--':>6}"
        dec = quote.price_decimals(code)   # 股票 2 位, 基金/ETF 3 位
        return f"{q.price:>8.{dec}f} {q.pct:+6.2f}%"

    def _row_fg(self, code):
        if self._stale:
            return COLOR_STALE
        q = self._quotes.get(code)
        if q is None or q.pct == 0:
            return COLOR_FLAT
        return COLOR_UP if q.pct > 0 else COLOR_DOWN

    def _row_bg(self, code):
        st = self._alerts.get(code)
        if st is not None and st["active"]:
            return FLASH_COLORS[int(self._flash_on)]
        return COLOR_BG

    # ---------- 行情与预警 ----------

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "quotes":
                    self._stale = False
                    self._quotes.update(payload)
                    self._update_alerts(payload)
                elif kind == "error":
                    self._stale = True
        except queue.Empty:
            pass
        self._refresh_display()
        self.root.after(POLL_MS, self._poll_queue)

    def _update_alerts(self, quotes):
        new_alert_code = None
        for stock in self._cfg["stocks"]:
            code = stock["code"]
            q = quotes.get(code)
            if q is None:
                continue
            st = self._alerts.setdefault(
                code, {"upper_armed": True, "lower_armed": True, "active": False})
            upper, lower = stock["upper"], stock["lower"]
            # 价格回到区间内则重新武装, 再次越界可重复触发
            if upper is not None and q.price < upper:
                st["upper_armed"] = True
            if lower is not None and q.price > lower:
                st["lower_armed"] = True
            hit = ((upper is not None and st["upper_armed"] and q.price >= upper)
                   or (lower is not None and st["lower_armed"] and q.price <= lower))
            if hit and not st["active"]:
                st["active"] = True
                if new_alert_code is None:
                    new_alert_code = code
                log.info("价格预警触发: %s(%s) 现价 %.2f", q.name, code, q.price)
        # 轮播模式下跳到触发预警的股票(轮播本身在有预警时暂停)
        if new_alert_code is not None and self._cfg["mode"] == "carousel":
            for i, (code, _) in enumerate(self._rows):
                if code == new_alert_code:
                    self._carousel_index = i
                    break

    def _has_active_alert(self):
        return any(st["active"] for st in self._alerts.values())

    def _acknowledge(self, code):
        """点击该行确认预警: 熄灭闪烁, 并在价格回到区间内前不再重复触发."""
        st = self._alerts.get(code)
        if st is None or not st["active"]:
            return
        st["active"] = False
        q = self._quotes.get(code)
        stock = next((s for s in self._cfg["stocks"] if s["code"] == code), None)
        if q is not None and stock is not None:
            if stock["upper"] is not None and q.price >= stock["upper"]:
                st["upper_armed"] = False
            if stock["lower"] is not None and q.price <= stock["lower"]:
                st["lower_armed"] = False
        self._refresh_display()

    def _flash_tick(self):
        self._flash_on = not self._flash_on
        if self._has_active_alert():
            self._refresh_display()
        # 置顶模式下周期性重申, 防止被其他窗口抢走
        if self._cfg["always_on_top"]:
            self.root.attributes("-topmost", True)
        self.root.after(FLASH_MS, self._flash_tick)

    # ---------- 轮播 ----------

    def _schedule_carousel(self):
        interval = max(2, int(self._cfg["carousel_interval"])) * 1000
        self.root.after(interval, self._carousel_tick)

    def _carousel_tick(self):
        if (self._cfg["mode"] == "carousel" and len(self._rows) > 1
                and not self._has_active_alert()):
            self._carousel_index = (self._carousel_index + 1) % len(self._rows)
            self._refresh_display()
        self._schedule_carousel()

    def _on_wheel(self, event):
        """滚轮手动切换轮播. Windows 用 delta, Linux 用 Button-4/5."""
        if self._cfg["mode"] != "carousel" or len(self._rows) < 2:
            return
        backward = getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0
        step = -1 if backward else 1
        self._carousel_index = (self._carousel_index + step) % len(self._rows)
        self._refresh_display()

    # ---------- 拖动 / 点击 / 隐藏 ----------

    def _bind_window_events(self, widget):
        widget.bind("<ButtonPress-1>", self._on_press)
        widget.bind("<B1-Motion>", self._on_motion)
        widget.bind("<ButtonRelease-1>", self._on_release)
        widget.bind("<Double-Button-1>", self._on_double)
        widget.bind("<Button-3>", self._show_menu)
        if sys.platform == "darwin":
            # macOS 上副键(右键)常报为 Button-2, 另支持传统的 Control+点按
            widget.bind("<Button-2>", self._show_menu)
            widget.bind("<Control-Button-1>", self._show_menu)
        widget.bind("<MouseWheel>", self._on_wheel)
        widget.bind("<Button-4>", self._on_wheel)
        widget.bind("<Button-5>", self._on_wheel)

    def _on_press(self, event):
        self._drag_start = (event.x_root, event.y_root,
                            self.root.winfo_x(), self.root.winfo_y())
        self._dragging = False

    def _on_motion(self, event):
        if self._drag_start is None:
            return
        sx, sy, wx, wy = self._drag_start
        dx, dy = event.x_root - sx, event.y_root - sy
        if abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD:
            if not self._dragging:
                self._hide_tip()    # 开始拖动窗口, 收起气泡(否则位置会错)
            self._dragging = True
        if self._dragging:
            self.root.geometry(f"+{wx + dx}+{wy + dy}")

    def _on_release(self, event):
        if self._drag_start is None:
            return
        if self._dragging:
            self._cfg["window_x"] = self.root.winfo_x()
            self._cfg["window_y"] = self.root.winfo_y()
            config.save(self._cfg)
        else:
            # 普通点击: 确认所点行的预警, 并切换该行当日最高/最低气泡
            for code, label in self._rows:
                if label is event.widget and code is not None:
                    self._acknowledge(code)
                    self._toggle_high_low(code)
                    break
        self._drag_start = None
        self._dragging = False

    def _toggle_high_low(self, code):
        """点击切换: 已在显示同一只则收起, 否则显示该只当日最高/最低(常驻)."""
        if self._tip_code == code and self._tip is not None and self._tip.winfo_exists():
            self._hide_tip()
        else:
            self._show_high_low(code)

    def _show_high_low(self, code):
        """在整个悬浮条最下方弹出小气泡显示当日最高/最低, 常驻到再次点击/拖动/隐藏.
        统一贴在窗口底部(而非被点行下方), 多行时也不会被其他行遮挡."""
        q = self._quotes.get(code)
        if q is None:
            return
        dec = quote.price_decimals(code)
        hi = f"{q.high:.{dec}f}" if q.high > 0 else "--"
        lo = f"{q.low:.{dec}f}" if q.low > 0 else "--"
        if self._tip is None or not self._tip.winfo_exists():
            self._tip = tk.Toplevel(self.root)
            self._tip.overrideredirect(True)
            self._tip.attributes("-topmost", True)
            # 不设固定宽度, 让气泡按内容自适应(ETF 3 位小数也不会被截断)
            self._tip_label = tk.Label(self._tip, font=FONT, bg="#2b2f36",
                                       fg=COLOR_FLAT, padx=8, pady=3)
            self._tip_label.pack()
        self._tip_label.configure(text=f"高 {hi}  低 {lo}")
        self.root.update_idletasks()    # 取最新窗口尺寸, 贴到窗口正下方
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty() + self.root.winfo_height() + 2
        self._tip.geometry(f"+{x}+{y}")
        self._tip.deiconify()
        self._tip.lift()
        self._tip_code = code

    def _hide_tip(self):
        self._tip_code = None
        if self._tip is not None and self._tip.winfo_exists():
            self._tip.withdraw()

    def _on_double(self, _event):
        self._hide_to_dot()
        return "break"

    def _hide_to_dot(self):
        """双击隐藏: 主窗收起, 在原位置留一个 6x6 像素小点, 点击恢复."""
        if self._dot is not None:
            return
        self._hide_tip()
        self._hidden_pos = (self.root.winfo_x(), self.root.winfo_y())
        self.root.withdraw()
        dot = tk.Toplevel(self.root)
        dot.overrideredirect(True)
        dot.attributes("-topmost", True)
        dot.configure(bg="#3a3a3a")
        dot.geometry(f"6x6+{self._hidden_pos[0]}+{self._hidden_pos[1]}")
        dot.bind("<Button-1>", lambda e: self._restore())
        self._dot = dot

    def _restore(self):
        if self._dot is not None:
            self._dot.destroy()
            self._dot = None
        self.root.deiconify()
        # Windows 上 deiconify 可能丢失 overrideredirect/位置, 重申一次
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self._cfg["always_on_top"])
        if self._hidden_pos is not None:
            self.root.geometry(f"+{self._hidden_pos[0]}+{self._hidden_pos[1]}")

    # ---------- 菜单与设置 ----------

    def _build_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="设置", command=self._open_settings)
        menu.add_command(label="切换显示模式", command=self._toggle_mode)
        menu.add_command(label="隐藏", command=self._hide_to_dot)
        menu.add_separator()
        menu.add_command(label="退出", command=self._quit)
        return menu

    def _quit(self):
        # 同步收起菜单并隐藏窗口后立即销毁. 不能用 after_idle 延迟销毁:
        # Windows 上右键菜单会让事件循环停在等待输入, 延迟的销毁要等到
        # 下次点击才执行, 导致悬浮条迟迟不消失.
        self._menu.unpost()
        self.root.withdraw()           # 立即隐藏主窗(同步生效)
        if self._dot is not None:
            self._dot.withdraw()
        self.root.update_idletasks()   # 刷新被腾出的屏幕区域
        self.root.destroy()

    def _show_menu(self, _event):
        # 弹在整个窗口正下方左对齐, 避免被窗口本身挡住
        self.root.update_idletasks()
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty() + self.root.winfo_height()
        try:
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()

    def _toggle_mode(self):
        self._cfg["mode"] = "list" if self._cfg["mode"] == "carousel" else "carousel"
        config.save(self._cfg)
        self._refresh_display()

    def _after_config_change(self):
        """股票列表变更后: 持久化、重建行、通知行情线程立即拉一次."""
        config.save(self._cfg)
        self._rebuild_rows()
        self.on_config_changed()

    def _open_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        win = tk.Toplevel(self.root)
        self._settings_win = win
        win.title("TickView 设置")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.geometry(f"+{self.root.winfo_x()}+{self.root.winfo_y() + 40}")

        # --- 股票列表 ---
        frame_list = ttk.LabelFrame(win, text="股票")
        frame_list.pack(fill="x", padx=8, pady=4)
        listbox = tk.Listbox(frame_list, height=6, width=44, exportselection=False)
        listbox.pack(padx=4, pady=4)

        def fmt_stock(s):
            q = self._quotes.get(s["code"])
            name = q.name if q is not None else ""
            upper = s["upper"] if s["upper"] is not None else "-"
            lower = s["lower"] if s["lower"] is not None else "-"
            code = s["code"][2:]   # 去掉 sh/sz/bj 前缀, 只显示 6 位代码
            return f'{code}  {name}  上限:{upper}  下限:{lower}'

        def reload_list():
            listbox.delete(0, tk.END)
            for s in self._cfg["stocks"]:
                listbox.insert(tk.END, fmt_stock(s))

        reload_list()

        row_add = ttk.Frame(frame_list)
        row_add.pack(fill="x", padx=4, pady=(0, 4))
        entry_code = ttk.Entry(row_add, width=12)
        entry_code.pack(side="left")
        ttk.Button(row_add, text="?", width=2,
                   command=lambda: messagebox.showinfo("添加规则", _ADD_HELP, parent=win)
                   ).pack(side="left", padx=(2, 0))

        def add_stock():
            code = quote.normalize_code(entry_code.get())
            if code is None:
                messagebox.showwarning("TickView", "无法识别的股票代码", parent=win)
                return
            if any(s["code"] == code for s in self._cfg["stocks"]):
                return
            self._cfg["stocks"].append({"code": code, "upper": None, "lower": None})
            self._after_config_change()
            reload_list()
            entry_code.delete(0, tk.END)

        def remove_stock():
            sel = listbox.curselection()
            if not sel:
                return
            code = self._cfg["stocks"][sel[0]]["code"]
            del self._cfg["stocks"][sel[0]]
            self._alerts.pop(code, None)
            self._after_config_change()
            reload_list()

        # 在列表内按住直接上下拖动即可调整顺序
        drag = {"index": None, "moved": False}

        def on_drag_start(event):
            drag["index"] = listbox.nearest(event.y)
            drag["moved"] = False

        def on_drag_motion(event):
            i = drag["index"]
            if i is not None:
                j = listbox.nearest(event.y)
                stocks = self._cfg["stocks"]
                if 0 <= j < len(stocks) and j != i:
                    stocks.insert(j, stocks.pop(i))   # 拖到新位置, 其余条目顺移
                    reload_list()
                    listbox.selection_clear(0, tk.END)
                    listbox.selection_set(j)
                    drag["index"] = j
                    drag["moved"] = True
            return "break"   # 阻止 Listbox 默认的拖动多选

        def on_drag_release(_event):
            if drag["moved"]:
                config.save(self._cfg)
                self._rebuild_rows()   # 同步悬浮条顺序(订阅代码不变, 无需重新拉取)
            drag["index"] = None
            drag["moved"] = False

        listbox.bind("<Button-1>", on_drag_start, add="+")
        listbox.bind("<B1-Motion>", on_drag_motion)
        listbox.bind("<ButtonRelease-1>", on_drag_release)

        ttk.Button(row_add, text="添加", command=add_stock).pack(side="left", padx=4)
        ttk.Button(row_add, text="删除选中", command=remove_stock).pack(side="left")

        # --- 预警价 ---
        frame_alert = ttk.LabelFrame(win, text="预警价 (选中股票后填写, 留空为不预警)")
        frame_alert.pack(fill="x", padx=8, pady=4)
        row_alert = ttk.Frame(frame_alert)
        row_alert.pack(padx=4, pady=4)
        ttk.Label(row_alert, text="上限").pack(side="left")
        entry_upper = ttk.Entry(row_alert, width=9)
        entry_upper.pack(side="left", padx=(2, 8))
        ttk.Label(row_alert, text="下限").pack(side="left")
        entry_lower = ttk.Entry(row_alert, width=9)
        entry_lower.pack(side="left", padx=2)

        def on_select(_event):
            sel = listbox.curselection()
            if not sel:
                return
            s = self._cfg["stocks"][sel[0]]
            entry_upper.delete(0, tk.END)
            entry_lower.delete(0, tk.END)
            if s["upper"] is not None:
                entry_upper.insert(0, str(s["upper"]))
            if s["lower"] is not None:
                entry_lower.insert(0, str(s["lower"]))

        listbox.bind("<<ListboxSelect>>", on_select)

        def parse_price(text):
            """返回 (价格或 None, 是否合法). 空串视为不设预警."""
            text = text.strip()
            if not text:
                return None, True
            try:
                value = float(text)
            except ValueError:
                return None, False
            return (value, True) if value > 0 else (None, False)

        def apply_alert():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("TickView", "请先在列表中选中股票", parent=win)
                return
            upper, ok_upper = parse_price(entry_upper.get())
            lower, ok_lower = parse_price(entry_lower.get())
            if not ok_upper or not ok_lower:
                messagebox.showwarning("TickView", "预警价必须是正数", parent=win)
                return
            if upper is not None and lower is not None and upper <= lower:
                messagebox.showwarning("TickView", "上限必须大于下限", parent=win)
                return
            s = self._cfg["stocks"][sel[0]]
            s["upper"], s["lower"] = upper, lower
            self._alerts.pop(s["code"], None)  # 阈值变更, 重置预警状态
            config.save(self._cfg)
            reload_list()
            listbox.selection_set(sel[0])

        ttk.Button(row_alert, text="应用", command=apply_alert).pack(side="left", padx=8)

        # --- 显示 ---
        frame_disp = ttk.LabelFrame(win, text="显示")
        frame_disp.pack(fill="x", padx=8, pady=(4, 8))
        row_opacity = ttk.Frame(frame_disp)
        row_opacity.pack(padx=4, pady=4, fill="x")
        ttk.Label(row_opacity, text="透明度").pack(side="left")
        scale = ttk.Scale(row_opacity, from_=0.3, to=1.0, value=self._cfg["opacity"],
                          command=lambda v: self.root.attributes("-alpha", float(v)))
        scale.pack(side="left", fill="x", expand=True, padx=4)

        def save_opacity(_event):
            self._cfg["opacity"] = round(float(scale.get()), 2)
            config.save(self._cfg)

        scale.bind("<ButtonRelease-1>", save_opacity)

        row_mode = ttk.Frame(frame_disp)
        row_mode.pack(padx=4, pady=(0, 4), fill="x")
        mode_var = tk.StringVar(value=self._cfg["mode"])

        def set_mode():
            self._cfg["mode"] = mode_var.get()
            config.save(self._cfg)
            self._refresh_display()

        ttk.Radiobutton(row_mode, text="单行轮播", variable=mode_var,
                        value="carousel", command=set_mode).pack(side="left")
        ttk.Radiobutton(row_mode, text="纵向列表", variable=mode_var,
                        value="list", command=set_mode).pack(side="left", padx=8)
        ttk.Label(row_mode, text="轮播间隔(秒)").pack(side="left", padx=(12, 2))
        spin = ttk.Spinbox(row_mode, from_=2, to=60, width=4)
        spin.set(self._cfg["carousel_interval"])

        def set_interval():
            try:
                value = int(spin.get())
            except ValueError:
                return
            self._cfg["carousel_interval"] = min(60, max(2, value))
            config.save(self._cfg)

        spin.configure(command=set_interval)
        spin.bind("<FocusOut>", lambda e: set_interval())
        spin.pack(side="left")

        row_top = ttk.Frame(frame_disp)
        row_top.pack(padx=4, pady=(0, 4), fill="x")
        top_var = tk.BooleanVar(value=self._cfg["always_on_top"])

        def set_always_on_top():
            self._cfg["always_on_top"] = top_var.get()
            self.root.attributes("-topmost", top_var.get())
            config.save(self._cfg)

        ttk.Checkbutton(row_top, text="窗口始终置顶(最前显示)", variable=top_var,
                        command=set_always_on_top).pack(side="left")
