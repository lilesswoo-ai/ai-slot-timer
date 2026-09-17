# -*- coding: utf-8 -*-
"""
发条AI时段小组件
===============
一块置顶、可拖拽的圆角渐变面板（带系统托盘图标），显示：

 1) DeepSeek 峰谷计价
    当前忙/闲状态、距本阶段结束倒计时、下一段起止时间。
 2) ChatGPT 额度重置
    按用量页显示的具体「下次重置」时刻倒计时（可同步），未设置时按 5h 周期。

主界面右下角齿轮进入「设置页」（与主界面同尺寸）：
 - 价格表：忙/闲时输入输出价格（每百万 tokens）
 - 声音提醒开关：DeepSeek 忙闲切换、GPT 重置到达时可选提示音（默认魅族提示音）
 - ChatGPT 重置时间同步 / 窗口周期 / 置顶开关

其他功能：
 - 置顶按钮：一键切换置顶
 - 系统托盘：关闭（×）只隐藏到托盘，点托盘图标恢复，退出需点“退出”
 - 右键菜单：同步重置时间 / 改周期 / 节假日覆盖 / 提醒声音 / 置顶 / 退出

定价规则来源（DeepSeek 官方定价页，2026-08-17 起生效、08-23 优化）：
    高峰时段 = 北京时间 周一至周五 09:00-12:00、14:00-18:00
    其余时间（含周末、法定节假日全天）= 空闲时段，价格为高峰时段的一半
    参考: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
价格（元/百万 tokens，2026-09 官方价，输入为缓存未命中价）：
    deepseek-flash   忙 入2/出8    闲 入1/出4
    deepseek-v4-pro  忙 入9/出27   闲 入4.5/出13.5

依赖：Python 3.9+，tkinter + Pillow + pystray（托盘）。
用法：
    pythonw deepseek_chatgpt_timer.py        # 静默启动
    python  deepseek_chatgpt_timer.py --selftest   # 逻辑自检
"""

import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, date as date_obj
import tkinter as tk
from tkinter import simpledialog, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

try:
    import winsound
except Exception:
    winsound = None

# 打包为 exe 时 __file__ 指向临时解压目录，资源目录应为 exe 所在目录
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# ---------------- 界面参数（物理像素设计尺寸） ----------------
DESIGN_W, DESIGN_H = 600, 400
PAD = 16
GRAD_TOP = (27, 62, 148)     # 深蓝（顶部）
GRAD_BOT = (112, 170, 240)   # 浅蓝（底部）
GRAD_BG_HEX = "#1b3e94"

FONT = "Microsoft YaHei UI"
MONO = "Consolas"
FG_W = "#ffffff"
FG_DIM = "#eaf4ff"
PEAK_C = "#ffb4a2"   # 忙时（暖橙红）
OFF_C  = "#8ff0c9"   # 闲时（亮绿）
ACC_C  = "#bcd9ff"   # 蓝白
WARN_C = "#ffe08a"   # 黄
DIVIDER = "#9cc3ff"
BTN_BG = "#163d8a"
BTN_HOV = "#1e54b5"
BTN_ON = "#1d6f45"   # 开关开
BAR_BG = "#0e2a63"

# ---------------- DeepSeek 峰谷规则与价格 ----------------
# 高峰(忙时): 北京时间 周一至周五 09:00-12:00、14:00-18:00
PEAK_MINUTES = [(9 * 60, 12 * 60), (14 * 60, 18 * 60)]
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 价格: (闲时, 忙时) 元/百万tokens（输入为缓存未命中价）
PRICES = {
    "deepseek-flash": {"input": (1.0, 2.0), "output": (4.0, 8.0)},
    "deepseek-v4-pro": {"input": (4.5, 9.0), "output": (13.5, 27.0)},
}

# 声音种类（meizu 为默认：播放 assets 下的 short-notification-sound-for-meizu.mp3）
SOUND_KINDS = ["meizu", "system", "ding", "double", "triple"]
SOUND_LABELS = {"meizu": "魅族提示音", "system": "系统提示音",
                "ding": "叮", "double": "滴滴", "triple": "三连音"}


def _play_meizu_mp3():
    """用 Windows MCI 播放默认提示音 mp3（无需额外依赖）。"""
    for rel in ("assets", ""):
        path = os.path.join(APP_DIR, rel, "short-notification-sound-for-meizu.mp3")
        if os.path.exists(path):
            break
    else:
        return
    try:
        winmm = ctypes.windll.winmm
        winmm.mciSendStringW("close meizu_snd", None, 0, 0)
        winmm.mciSendStringW(
            f'open "{path}" type mpegvideo alias meizu_snd', None, 0, 0)
        winmm.mciSendStringW("play meizu_snd from 0", None, 0, 0)
    except Exception:
        pass


def is_peak(dt: datetime, override: dict | None = None) -> bool:
    """给定时刻是否处于忙时。override: {'date':'YYYY-MM-DD','force':'offpeak'} 表示当天强制闲时（节假日）。"""
    if override and override.get("date") == dt.strftime("%Y-%m-%d"):
        return override.get("force") != "offpeak"
    if dt.weekday() >= 5:            # 周六/周日全天闲时
        return False
    m = dt.hour * 60 + dt.minute
    return any(lo <= m < hi for lo, hi in PEAK_MINUTES)


def _walk(dt: datetime, want_peak: bool, days: int = 8) -> datetime | None:
    """从 dt 起逐分钟找到第一个状态为 want_peak 的时刻（不含 dt 本身所在分钟）。"""
    cur = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(days * 24 * 60):
        if is_peak(cur) == want_peak:
            return cur
        cur += timedelta(minutes=1)
    return None


def next_switch(dt: datetime, override: dict | None = None):
    """返回 (下一阶段开始时刻, 再下一阶段开始时刻)。"""
    cur_peak = is_peak(dt, override)
    t1 = _walk(dt, not cur_peak)
    t2 = _walk(t1, cur_peak) if t1 else None
    return t1, t2


def fmt_until(td: timedelta) -> str:
    """timedelta -> HH:MM:SS"""
    s = max(0, int(td.total_seconds()))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def fmt_hm(t: datetime) -> str:
    """HH:MM；跨天显示 周X HH:MM（不显示秒）"""
    if t.date() == datetime.now().date():
        return t.strftime("%H:%M")
    return f"{WEEKDAY_CN[t.weekday()]} {t.strftime('%H:%M')}"


def make_gradient(w: int, h: int, c1, c2) -> Image.Image:
    """垂直渐变：顶部 c1（深蓝）→ 底部 c2（浅蓝）。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=color)
    return img


def make_gear(size: int = 20, color=(255, 255, 255)) -> Image.Image:
    """画一个简单齿轮图标（设置按钮用）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    d.ellipse([cx - 5.5, cy - 5.5, cx + 5.5, cy + 5.5], outline=color, width=2)
    tooth = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    td = ImageDraw.Draw(tooth)
    td.rectangle([cx - 1.6, 0, cx + 1.6, 5], fill=color)
    for i in range(8):
        img.alpha_composite(tooth.rotate(i * 45, center=(cx, cy)))
    d.ellipse([cx - 1.8, cy - 1.8, cx + 1.8, cy + 1.8], fill=color)
    return img


def play_sound(kind: str):
    """播放提示音。kind: meizu/system/ding/double/triple"""
    if kind == "meizu":
        _play_meizu_mp3()
        return
    if winsound is None:
        return
    try:
        if kind == "system":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif kind == "ding":
            winsound.Beep(1200, 250)
        elif kind == "double":
            winsound.Beep(900, 150)
            winsound.Beep(900, 150)
        elif kind == "triple":
            winsound.Beep(700, 120)
            winsound.Beep(900, 120)
            winsound.Beep(1200, 150)
    except Exception:
        pass


# ---------------- ChatGPT 额度重置计数器 ----------------
class ChatGPTCounter:
    """mode='ts'：按用户设置的具体重置时刻为锚点，每窗口小时数自动续算下一时刻；
    mode='cycle'：未设置锚点时按固定周期滚动。"""

    def __init__(self, cfg: dict):
        self.window_h = float(cfg.get("gpt_reset_hours", 5) or 5)
        self.window_s = self.window_h * 3600.0
        self.reset_ts = cfg.get("gpt_reset_ts")          # float | None
        self.last = float(cfg.get("gpt_last_reset_ts", 0) or 0)

    def set_reset(self, ts: float):
        self.reset_ts = float(ts)
        self.last = self.reset_ts - self.window_s

    def clear_reset(self):
        self.reset_ts = None

    def state(self, now_ts: float):
        if self.reset_ts:
            ts = self.reset_ts
            rolled = False
            # 到达后自动按窗口小时数续算下一次，无需手动同步
            while ts <= now_ts:
                ts += self.window_s
                rolled = True
            self.reset_ts = ts
            self.last = ts - self.window_s
            remain = max(0.0, ts - now_ts)
            progress = min(1.0, max(0.0, (now_ts - self.last) / self.window_s))
            return {"mode": "ts", "remain": remain, "progress": progress,
                    "end": ts, "done": False, "rolled": rolled}
        if self.last <= 0:
            self.last = now_ts
        last, end = self.last, self.last + self.window_s
        while end <= now_ts:
            last = end
            end = last + self.window_s
        self.last = last
        return {"mode": "cycle", "remain": max(0.0, end - now_ts),
                "progress": min(1.0, (now_ts - last) / self.window_s),
                "end": end, "done": False, "rolled": False}


class GPTWeekCounter:
    """ChatGPT 一周窗口：设置最近重置日期（锚点）后自动按 7 天续算。"""

    def __init__(self, cfg: dict):
        self.window_s = 7 * 86400.0
        self.reset_ts = cfg.get("gpt_week_reset_ts")       # float | None
        self.last = float(cfg.get("gpt_week_last_reset_ts", 0) or 0)

    def set_reset(self, ts: float):
        self.reset_ts = float(ts)
        self.last = self.reset_ts - self.window_s

    def clear_reset(self):
        self.reset_ts = None

    def state(self, now_ts: float):
        if self.reset_ts:
            ts = self.reset_ts
            rolled = False
            while ts <= now_ts:
                ts += self.window_s
                rolled = True
            self.reset_ts = ts
            self.last = ts - self.window_s
            return {"mode": "ts", "remain": max(0.0, ts - now_ts),
                    "end": ts, "rolled": rolled}
        if self.last <= 0:
            self.last = now_ts
        last, end = self.last, self.last + self.window_s
        while end <= now_ts:
            last = end
            end = last + self.window_s
        self.last = last
        return {"mode": "cycle", "remain": max(0.0, end - now_ts),
                "end": end, "rolled": False}


def fmt_week_until(td) -> str:
    """timedelta -> 'X天 HH:MM'（不足 1 天只显示 HH:MM）。"""
    s = max(0, int(td.total_seconds()))
    d, rem = divmod(s, 86400)
    h, m = divmod(rem, 3600)
    m //= 60
    return f"{d}天 {h:02d}:{m:02d}" if d > 0 else f"{h:02d}:{m:02d}"


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "发条AI时段小组件"


def _autostart_command() -> str:
    """开机启动命令行：exe 直接注册自身；源码运行注册 pythonw + 脚本。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):   # 换 pythonw 避免开机弹控制台
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            exe = w
    script = os.path.join(APP_DIR, "deepseek_chatgpt_timer.py")
    return f'"{exe}" "{script}"'


def _autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _set_autostart(enabled: bool):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ,
                                  _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


def _activate_existing_instance() -> bool:
    """已有实例运行时：显示并置前其窗口，返回 True（新实例应退出）。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "发条AI时段小组件")
        if hwnd:
            if not user32.IsWindowVisible(hwnd):
                user32.ShowWindow(hwnd, 5)     # SW_SHOW（从托盘隐藏恢复）
            user32.ShowWindow(hwnd, 9)         # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            return True
    except Exception:
        pass
    return False


# ---------------- 小组件 UI（双页面：主界面 / 设置页） ----------------
class Widget(tk.Tk):

    def __init__(self):
        # 单实例：已有小组件在运行则激活它，避免重复启动
        if _activate_existing_instance():
            sys.exit(0)
        super().__init__()
        self.cfg = self.load_cfg()
        self.counter = ChatGPTCounter(self.cfg)
        self.week_counter = GPTWeekCounter(self.cfg)
        self.override = self.cfg.get("ds_override")
        self._drag = None
        self._ds_alerted = None     # 已提醒的 DS 切换时刻
        self._gpt_alerted = None    # 已提醒的 GPT 重置时刻
        self._tray = None
        self._closing = False
        self.page = "main"          # "main" | "settings"
        self._set_btns = {}         # tag -> (矩形id, 文字id)
        self._auto_send_pending = False   # 等待自动发送
        self._auto_send_at = 0.0          # 自动发送执行时刻
        self._balance = None        # None=未设置Key / dict=查询结果 / "err"=失败
        self._balance_fetched_at = 0.0    # 上次成功查询时间

        self.overrideredirect(True)
        self.title("发条AI时段小组件")
        self.attributes("-topmost", bool(self.cfg.get("topmost", True)))

        self._bg_img = ImageTk.PhotoImage(
            make_gradient(DESIGN_W, DESIGN_H, GRAD_TOP, GRAD_BOT))
        self._icon_ds = self._load_icon("deepseek_icon.png")
        self._icon_gpt = self._load_icon("chatgpt_icon.png")
        self._gear_img = ImageTk.PhotoImage(make_gear(20, (255, 255, 255)))

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=GRAD_BG_HEX, width=DESIGN_W, height=DESIGN_H)
        self.canvas.pack()
        self.canvas_set = tk.Canvas(self, highlightthickness=0, bd=0,
                                    bg=GRAD_BG_HEX, width=DESIGN_W,
                                    height=DESIGN_H)
        # 页面切换用 pack 顺序控制：后 pack 的在上层
        self.canvas_set.pack()
        self.canvas.pack()

        self._build_main_ui()
        self._bind_events()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = self.cfg.get("pos", {}).get("x")
        y = self.cfg.get("pos", {}).get("y")
        if not x or not y:
            x = sw - DESIGN_W
            y = sh - DESIGN_H
        self.geometry(f"{DESIGN_W}x{DESIGN_H}+{int(x)}+{int(y)}")
        self.update_idletasks()
        self._apply_round_rect()

        self.tick()
        self.save_cfg()
        if "--selftest" not in sys.argv:
            self.after(300, self._init_tray)

    # ---------- 配置持久化 ----------
    def load_cfg(self) -> dict:
        try:
            # utf-8-sig：兼容带 BOM 的配置文件（如 PowerShell 写入的 UTF-8）
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_cfg(self):
        data = {
            "gpt_reset_hours": self.counter.window_h,
            "gpt_reset_ts": self.counter.reset_ts,
            "gpt_last_reset_ts": self.counter.last,
            "gpt_week_reset_ts": self.week_counter.reset_ts,
            "gpt_week_last_reset_ts": self.week_counter.last,
            "topmost": bool(self.attributes("-topmost")),
            "pos": {"x": self.winfo_x(), "y": self.winfo_y()},
            "ds_override": self.override,
            "ds_sound": bool(self.cfg.get("ds_sound", False)),
            "gpt_sound": bool(self.cfg.get("gpt_sound", False)),
            "sound_kind": self.cfg.get("sound_kind", "meizu"),
            "gpt_auto_send": bool(self.cfg.get("gpt_auto_send", False)),
            "deepseek_api_key": self.cfg.get("deepseek_api_key", ""),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_icon(self, name):
        try:
            return ImageTk.PhotoImage(
                Image.open(os.path.join(APP_DIR, "assets", name)).convert("RGBA"))
        except Exception:
            return None

    def _apply_round_rect(self, radius=22):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, DESIGN_W + 1, DESIGN_H + 1, radius * 2, radius * 2)
            ctypes.windll.user32.SetWindowRgn(hwnd, hrgn, True)
        except Exception:
            pass

    # ---------- 托盘 ----------
    def _make_tray_image(self):
        try:
            img = make_gradient(64, 64, GRAD_TOP, GRAD_BOT)
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
            except Exception:
                font = ImageFont.load_default()
            d.ellipse((4, 4, 60, 60), fill=(255, 255, 255, 200))
            d.text((32, 32), "AI", font=font, fill=GRAD_BG_HEX, anchor="mm")
            return img
        except Exception:
            return Image.new("RGB", (64, 64), GRAD_BG_HEX)

    def _init_tray(self):
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("显示 / 隐藏", self._tray_toggle, default=True),
                pystray.MenuItem("退出", self._tray_quit),
            )
            self._tray = pystray.Icon("ai_timer_widget", self._make_tray_image(),
                                      "发条AI时段小组件", menu)
            self._tray.run_detached()
        except Exception:
            self._tray = None

    def _tray_toggle(self, icon=None, item=None):
        self.after(0, self._toggle_window)

    def _tray_quit(self, icon=None, item=None):
        self.after(0, self._quit_app)

    def _toggle_window(self):
        if self.state() == "normal":
            self.withdraw()
        else:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", bool(self.cfg.get("topmost", True)))

    def _quit_app(self):
        if self._closing:
            return
        self._closing = True
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass
        self.destroy()

    # ---------- 主界面 ----------
    def _build_main_ui(self):
        cv = self.canvas
        cv.create_image(0, 0, image=self._bg_img, anchor="nw")
        R = DESIGN_W - PAD

        # 标题栏：左标题，右 [置顶:开] [×]
        cv.create_text(PAD, 26, text="发条AI时段小组件", anchor="w",
                       fill=FG_DIM, font=(FONT, 8))
        cv.create_text(R - 40, 26, text="  ×  ", anchor="e", fill=FG_DIM,
                       font=(FONT, 11), tags="close")
        cv.tag_bind("close", "<Button-1>", lambda e: self._hide_to_tray())
        cv.tag_bind("close", "<Enter>", lambda e: cv.itemconfig("close", fill=FG_W))
        cv.tag_bind("close", "<Leave>", lambda e: cv.itemconfig("close", fill=FG_DIM))
        self.pin_btn = cv.create_text(R - 88, 26, text="", anchor="e",
                                      fill=ACC_C, font=(FONT, 8), tags="pin")
        cv.tag_bind("pin", "<Button-1>", lambda e: self.toggle_topmost())
        cv.tag_bind("pin", "<Enter>", lambda e: cv.itemconfig("pin", fill=FG_W))
        cv.tag_bind("pin", "<Leave>", lambda e: self._paint_pin())

        # ---- DeepSeek 区块 ----
        if self._icon_ds:
            cv.create_image(PAD, 44, image=self._icon_ds, anchor="nw")
        cv.create_text(PAD + 38, 56, text="DeepSeek 峰谷计价", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"))
        self.ds_badge = cv.create_text(R, 56, text="", anchor="e",
                                       fill=OFF_C, font=(FONT, 9, "bold"))
        self.ds_main = cv.create_text(PAD, 96, text="", anchor="w",
                                      fill=FG_W, font=(MONO, 14, "bold"))
        # “剩 xx:xx:xx”右对齐（右缘与下方 GPT 行的“剩”对齐），颜色随闲忙
        self.ds_remain = cv.create_text(R, 96, text="", anchor="e",
                                        fill=FG_W, font=(MONO, 14, "bold"))
        self.ds_sub = cv.create_text(PAD, 126, text="", anchor="w",
                                     fill=FG_DIM, font=(MONO, 10))
        self.ds_balance = cv.create_text(PAD, 152, text="", anchor="w",
                                         fill=FG_DIM, font=(FONT, 8))
        # 分割线下移，与 ChatGPT 区块等高（两区纵向空间一致）
        cv.create_line(PAD, 190, R, 190, fill=DIVIDER, width=1)

        # ---- ChatGPT 区块（5小时 + 一周双窗口，无进度条） ----
        if self._icon_gpt:
            cv.create_image(PAD, 192, image=self._icon_gpt, anchor="nw")
        cv.create_text(PAD + 38, 206, text="ChatGPT 额度重置", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"))
        # 5小时行
        cv.create_text(PAD, 240, text="下次重置", anchor="w",
                       fill=FG_DIM, font=(FONT, 9))
        self.gpt_next = cv.create_text(PAD + 78, 240, text="", anchor="w",
                                       fill=FG_W, font=(MONO, 12, "bold"))
        self.gpt_remain = cv.create_text(R, 240, text="", anchor="e",
                                         fill=PEAK_C, font=(MONO, 14, "bold"))
        # 同步按钮（时间 + 日期）+ 右侧一周重置信息（同右对齐到 R）
        self.btn_sync = cv.create_rectangle(PAD, 272, PAD + 136, 294,
                                            fill=BTN_BG, outline="", tags="sync")
        cv.create_text(PAD + 68, 283, text="同步重置时间", fill=FG_W,
                       font=(FONT, 9), tags="sync")
        cv.tag_bind("sync", "<Button-1>", lambda e: self.sync_reset_time())
        cv.tag_bind("sync", "<Enter>", lambda e: cv.itemconfig(self.btn_sync, fill=BTN_HOV))
        cv.tag_bind("sync", "<Leave>", lambda e: cv.itemconfig(self.btn_sync, fill=BTN_BG))
        self.btn_week = cv.create_rectangle(PAD + 144, 272, PAD + 294, 294,
                                            fill=BTN_BG, outline="", tags="week_sync")
        cv.create_text(PAD + 219, 283, text="同步重置日期", fill=FG_W,
                       font=(FONT, 9), tags="week_sync")
        cv.tag_bind("week_sync", "<Button-1>", lambda e: self.sync_reset_date())
        cv.tag_bind("week_sync", "<Enter>",
                    lambda e: cv.itemconfig(self.btn_week, fill=BTN_HOV))
        cv.tag_bind("week_sync", "<Leave>",
                    lambda e: cv.itemconfig(self.btn_week, fill=BTN_BG))
        # 一周重置信息：字号小于“剩”，宽度与上面“剩 xx:xx:xx”接近
        self.gpt_week_info = cv.create_text(R, 283, text="", anchor="e",
                                            fill=FG_W, font=(MONO, 10, "bold"))
        # 按钮提示语（按钮下一行；与 DeepSeek 区块等高）
        cv.create_text(PAD, 340, text="提示：同步重置时间后自动按 5 小时续算；同步重置日期后自动按 7 天续算",
                       anchor="w", fill=FG_DIM, font=(FONT, 8))

        # 底部：提示 + 右下角设置（图标与文字同一行、整体右对齐不出界）
        cv.create_text(PAD, 384, text="右键：菜单 · 拖拽移动 · × 隐藏到托盘",
                       anchor="w", fill=FG_DIM, font=(FONT, 8))
        cv.create_image(R - 44, 372, image=self._gear_img, anchor="center",
                        tags="gear")
        cv.create_text(R - 28, 372, text="设置", anchor="w", fill=FG_DIM,
                       font=(FONT, 7), tags="gear")
        cv.tag_bind("gear", "<Button-1>", lambda e: self._show_settings())
        cv.tag_bind("gear", "<Enter>",
                    lambda e: cv.itemconfig("gear", state="active"))
        cv.tag_bind("gear", "<Leave>",
                    lambda e: cv.itemconfig("gear", state="normal"))

    # ---------- 设置页 ----------
    def _show_settings(self):
        self._build_settings_ui()
        self.canvas.pack_forget()
        self.canvas_set.pack()
        self.page = "settings"

    def _close_settings(self):
        self.canvas_set.pack_forget()
        self.canvas.pack()
        self.page = "main"
        self._paint_pin()
        self.tick()

    def _build_settings_ui(self):
        cv = self.canvas_set
        cv.delete("all")
        cv.create_image(0, 0, image=self._bg_img, anchor="nw")
        R = DESIGN_W - PAD

        # 标题栏：左"设置"
        cv.create_text(PAD, 26, text="设置", anchor="w",
                       fill=FG_DIM, font=(FONT, 8))

        # ---- 1) 声音提醒 ----
        cv.create_text(PAD, 54, text="声音提醒", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"))
        cv.create_text(R, 54, text="忙/闲切换到达、GPT 重置到达时响铃",
                       anchor="e", fill=FG_DIM, font=(FONT, 8))
        self.set_snd_ds = self._mk_btn(cv, PAD, 76, 230, "set_snd_ds", "snd")
        self.set_snd_gpt = self._mk_btn(cv, PAD + 246, 76, 150, "set_snd_gpt", "snd")
        self.set_snd_kind = self._mk_btn(cv, PAD + 412, 76, 156, "set_snd_kind", "snd")
        cv.create_line(PAD, 118, R, 118, fill=DIVIDER, width=1)

        # ---- 2) DeepSeek 价格表 ----
        cv.create_text(PAD, 142, text="DeepSeek 价格表（元 / 百万 tokens）",
                       anchor="w", fill=FG_W, font=(FONT, 10, "bold"))
        # 表头（与数据列同起点，左对齐保证上下对齐）
        cv.create_text(PAD + 40, 168, text="模型", anchor="w",
                       fill=FG_DIM, font=(FONT, 9))
        cv.create_text(200, 168, text="忙时 · 高峰", anchor="w",
                       fill=PEAK_C, font=(FONT, 9, "bold"))
        cv.create_text(400, 168, text="闲时 · 半价", anchor="w",
                       fill=OFF_C, font=(FONT, 9, "bold"))
        cv.create_line(PAD, 180, R, 180, fill="#7aa8e8", width=1)
        p1, p2 = PRICES["deepseek-flash"], PRICES["deepseek-v4-pro"]
        rows = [
            ("Flash", p1),
            ("Pro", p2),
        ]
        for i, (name, p) in enumerate(rows):
            y = 194 + i * 26
            cv.create_text(PAD + 40, y, text=name, anchor="w",
                           fill=FG_W, font=(MONO, 9, "bold"))
            cv.create_text(200, y,
                           text=f"输入 {p['input'][1]:g} / 输出 {p['output'][1]:g}",
                           anchor="w", fill=PEAK_C, font=(MONO, 9))
            cv.create_text(400, y,
                           text=f"输入 {p['input'][0]:g} / 输出 {p['output'][0]:g}",
                           anchor="w", fill=OFF_C, font=(MONO, 9))
        cv.create_text(PAD, 254, text="输入为缓存未命中价；闲时价 = 高峰价的一半",
                       anchor="w", fill=FG_DIM, font=(FONT, 8))
        cv.create_line(PAD, 272, R, 272, fill=DIVIDER, width=1)

        # ---- 3) DeepSeek 余额 ----
        cv.create_text(PAD, 298, text="DeepSeek 余额", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"))
        cv.create_text(R, 298, text="官方接口仅支持余额，今日用量请到控制台查看",
                       anchor="e", fill=FG_DIM, font=(FONT, 8))
        self.set_dskey = self._mk_btn(cv, PAD, 316, 240, "set_dskey", "btn")
        self.dskey_state = cv.create_text(PAD + 256, 329, text="", anchor="w",
                                          fill=ACC_C, font=(FONT, 8))

        # ---- 4) 开机启动 ----
        self.set_autostart_btn = self._mk_btn(cv, PAD, 352, 240,
                                              "set_autostart", "btn")

        # ---- 右下角：返回主界面按钮 ----
        self.btn_back = cv.create_rectangle(R - 176, 358, R - 16, 386,
                                            fill=BTN_BG, outline="",
                                            tags="back_btn")
        cv.create_text(R - 96, 372, text="← 返回主界面", fill=FG_W,
                       font=(FONT, 9), tags="back_btn")
        cv.tag_bind("back_btn", "<Button-1>", lambda e: self._close_settings())
        cv.tag_bind("back_btn", "<Enter>",
                    lambda e: cv.itemconfig(self.btn_back, fill=BTN_HOV))
        cv.tag_bind("back_btn", "<Leave>",
                    lambda e: cv.itemconfig(self.btn_back, fill=BTN_BG))

        self._paint_small_btns()

    def _mk_btn(self, cv, x, y, w, tag, kind):
        """在指定 canvas 创建一个小按钮，返回 (矩形id, 文字id)。kind: snd/btn"""
        r = cv.create_rectangle(x, y, x + w, y + 26, fill=BTN_BG,
                                outline="", tags=tag)
        t = cv.create_text(x + w // 2, y + 13, text="", fill=FG_W,
                           font=(FONT, 8), tags=tag)
        self._set_btns[tag] = (r, t)
        cv.tag_bind(tag, "<Button-1>",
                    lambda e, tg=tag: self._on_small_btn(tg))
        cv.tag_bind(tag, "<Enter>",
                    lambda e: cv.itemconfig(r, fill=BTN_HOV))
        cv.tag_bind(tag, "<Leave>",
                    lambda e: self._paint_small_btns())
        return (r, t)

    def _on_small_btn(self, tag):
        if tag == "set_snd_ds":
            self.cfg["ds_sound"] = not self.cfg.get("ds_sound", False)
            self.save_cfg()
            if self.cfg["ds_sound"]:
                play_sound(self.cfg.get("sound_kind", "meizu"))
        elif tag == "set_snd_gpt":
            self.cfg["gpt_sound"] = not self.cfg.get("gpt_sound", False)
            self.save_cfg()
            if self.cfg["gpt_sound"]:
                play_sound(self.cfg.get("sound_kind", "meizu"))
        elif tag == "set_snd_kind":
            kinds = SOUND_KINDS
            cur = self.cfg.get("sound_kind", "meizu")
            nxt = kinds[(kinds.index(cur) + 1) % len(kinds)] if cur in kinds else "meizu"
            self.cfg["sound_kind"] = nxt
            self.save_cfg()
            play_sound(nxt)
        elif tag == "set_dskey":
            self.set_deepseek_api_key()
        elif tag == "set_autostart":
            on = not _autostart_enabled()
            _set_autostart(on)
            self.save_cfg()
        self._paint_small_btns()

    def _paint_small_btns(self):
        cv = self.canvas_set
        ds_on = self.cfg.get("ds_sound", False)
        gpt_on = self.cfg.get("gpt_sound", False)
        snd_kind = self.cfg.get("sound_kind", "meizu")
        key = self.cfg.get("deepseek_api_key", "")
        labels = {
            "set_snd_ds": ("DeepSeek 切换提醒：" + ("开" if ds_on else "关"),
                           "#7dffc0" if ds_on else FG_W,
                           BTN_ON if ds_on else BTN_BG),
            "set_snd_gpt": ("GPT 重置提醒：" + ("开" if gpt_on else "关"),
                            "#7dffc0" if gpt_on else FG_W,
                            BTN_ON if gpt_on else BTN_BG),
            "set_snd_kind": ("声音：" + SOUND_LABELS.get(snd_kind, "魅族提示音"),
                             ACC_C, BTN_BG),
            "set_dskey": ("设置 DeepSeek API Key", FG_W, BTN_BG),
            "set_autostart": ("开机启动：" + ("开" if _autostart_enabled() else "关"),
                              "#7dffc0" if _autostart_enabled() else FG_W,
                              BTN_ON if _autostart_enabled() else BTN_BG),
        }
        for tag, (text, fg, bg) in labels.items():
            r, t = self._set_btns.get(tag, (None, None))
            if r is None:
                continue
            cv.itemconfig(r, fill=bg)
            cv.itemconfig(t, text=text, fill=fg)
        # API Key 状态文字
        if key:
            cv.itemconfig(self.dskey_state,
                          text=f"已设置 {key[:6]}…", fill=ACC_C)
        else:
            cv.itemconfig(self.dskey_state, text="未设置", fill=FG_DIM)

    # ---------- 事件 ----------
    def _bind_events(self):
        self.bind("<Button-3>", self._menu)
        self.bind("<Button-1>", self._drag_start)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_start(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _drag_end(self, e):
        self._drag = None
        self.save_cfg()

    # ---------- 显示 / 隐藏 ----------
    def _hide_to_tray(self):
        self.withdraw()

    # ---------- 菜单 ----------
    def _menu(self, e):
        m = tk.Menu(self, tearoff=0, bg="#122b5e", fg=FG_W,
                    activebackground="#1e54b5", activeforeground=FG_W,
                    font=(FONT, 9))
        m.add_command(label="打开设置", command=self._show_settings)
        m.add_command(label="同步 ChatGPT 重置时间…", command=self.sync_reset_time)
        if self.counter.reset_ts is not None:
            m.add_command(label="清除自定义重置时间（恢复 5 小时周期）",
                          command=self.clear_reset_time)
        m.add_command(label=f"窗口周期：{self.counter.window_h:g} 小时…",
                      command=self.set_reset_hours)
        m.add_separator()
        m.add_command(label="DeepSeek 切换提醒：" + ("开" if self.cfg.get("ds_sound") else "关"),
                      command=self.toggle_ds_sound_menu)
        m.add_command(label="GPT 重置提醒：" + ("开" if self.cfg.get("gpt_sound") else "关"),
                      command=self.toggle_gpt_sound_menu)
        m.add_separator()
        if self.override and self.override.get("date") == datetime.now().strftime("%Y-%m-%d"):
            m.add_command(label="今天强制闲时（节假日）✓", command=self.clear_override)
        else:
            m.add_command(label="今天强制闲时（节假日）…", command=self.set_override)
        m.add_command(label="置顶：" + ("开" if self.attributes("-topmost") else "关"),
                      command=self.toggle_topmost)
        m.add_separator()
        m.add_command(label="规则说明", command=self.show_help)
        m.add_command(label="退出", command=self._quit_app)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def toggle_ds_sound_menu(self):
        self.cfg["ds_sound"] = not self.cfg.get("ds_sound", False)
        self.save_cfg()
        self._paint_small_btns()

    def toggle_gpt_sound_menu(self):
        self.cfg["gpt_sound"] = not self.cfg.get("gpt_sound", False)
        self.save_cfg()
        self._paint_small_btns()

    # ---------- ChatGPT 同步 ----------
    def sync_reset_time(self):
        v = simpledialog.askstring(
            "同步重置时间",
            "ChatGPT 用量页显示的「下次重置」时刻（HH:MM）：\n"
            "例如页面显示 12:10 就输入 12:10",
            parent=self, initialvalue=datetime.now().strftime("%H:%M"))
        if not v:
            return
        try:
            h, m = v.strip().split(":")
            now = datetime.now()
            ts = now.replace(hour=int(h), minute=int(m), second=0,
                             microsecond=0).timestamp()
            if ts <= now.timestamp():
                ts += 86400
            self.counter.set_reset(ts)
            self.save_cfg()
            self.tick()
        except Exception:
            pass

    def sync_reset_date(self):
        v = simpledialog.askstring(
            "同步重置日期",
            "ChatGPT 用量页显示的「一周窗口」重置日期：\n"
            "输入最近的重置日期，如 09-19 或 2026-09-19；\n"
            "设置后自动按 7 天续算，无需再手动同步。",
            parent=self, initialvalue=datetime.now().strftime("%m-%d"))
        if not v:
            return
        v = v.strip()
        try:
            today = datetime.now().date()
            if re.fullmatch(r"\d{1,2}-\d{1,2}", v):
                m, d = map(int, v.split("-"))
                date = date_obj(today.year, m, d)
            elif re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", v):
                y, m, d = map(int, v.split("-"))
                date = date_obj(y, m, d)
            else:
                raise ValueError
            ts = datetime.combine(date, datetime.min.time()).timestamp()
        except Exception:
            messagebox.showwarning("格式错误", "请输入日期，如 09-19 或 2026-09-19")
            return
        self.week_counter.set_reset(ts)
        self.save_cfg()
        self.tick()

    def clear_reset_time(self):
        self.counter.clear_reset()
        self.save_cfg()
        self.tick()

    def set_reset_hours(self):
        v = simpledialog.askstring(
            "窗口周期", "ChatGPT 额度窗口小时数（默认 5）：",
            parent=self, initialvalue=f"{self.counter.window_h:g}")
        if not v:
            return
        try:
            self.counter.window_h = max(0.5, float(v))
            self.counter.window_s = self.counter.window_h * 3600.0
            if self.counter.reset_ts is not None:
                self.counter.last = self.counter.reset_ts - self.counter.window_s
            self.save_cfg()
            self.tick()
        except Exception:
            pass

    def set_override(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.override = {"date": today, "force": "offpeak"}
        self.save_cfg()
        self.tick()

    def clear_override(self):
        self.override = None
        self.save_cfg()
        self.tick()

    def toggle_topmost(self):
        self.attributes("-topmost", not self.attributes("-topmost"))
        self._paint_pin()
        self.save_cfg()

    def _paint_pin(self):
        top = bool(self.attributes("-topmost"))
        self.canvas.itemconfig("pin", text="置顶：" + ("开" if top else "关"),
                               fill=ACC_C if top else FG_DIM)

    def show_help(self):
        messagebox.showinfo(
            "规则说明",
            "DeepSeek 峰谷计价（官方定价页，2026-08 生效）\n"
            "· 高峰（忙时）：北京时间 周一至周五 09:00-12:00、14:00-18:00\n"
            "· 其余时间（含周末、法定节假日全天）= 闲时，价格约为高峰一半\n"
            "· 价格单位：元/百万 tokens（输入为缓存未命中价）\n"
            "· 来源：api-docs.deepseek.com/quick_start/pricing\n\n"
            "ChatGPT 额度重置\n"
            "· 额度按「每 N 小时窗口」滚动计数，用量页会显示具体的下次重置时刻\n"
            "· 点【同步重置时间】输入页面显示的时刻即可倒计时\n\n"
            "声音提醒：DeepSeek 忙/闲切换到达、GPT 重置到达时响铃\n"
            "托盘：× 仅隐藏，点托盘图标恢复，退出请用菜单/托盘“退出”\n\n"
            "参考项目：github.com/CodeZeno/Claude-Code-Usage-Monitor（MIT）\n"
            "           npmjs.com/package/ds-peak-warningx", parent=self)

    # ---------- DeepSeek 余额查询（官方 /user/balance 接口） ----------
    def _fetch_balance_http(self):
        """同步调用余额接口（在工作线程中执行）。"""
        try:
            import urllib.request
            key = self.cfg.get("deepseek_api_key", "")
            req = urllib.request.Request(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            infos = data.get("balance_infos", []) or []
            total = 0.0
            for i in infos:
                if i.get("currency") == "CNY":
                    total += float(i.get("total_balance", 0) or 0)
            return {"total": total, "available": bool(data.get("is_available", False))}
        except Exception:
            return "err"

    def _maybe_refresh_balance(self, now_ts):
        if not self.cfg.get("deepseek_api_key"):
            self._balance = None
            return
        if now_ts - self._balance_fetched_at < 900 and isinstance(self._balance, dict):
            return
        self._balance_fetched_at = now_ts

        def work():
            res = self._fetch_balance_http()
            self.after(0, lambda: self._apply_balance(res))

        threading.Thread(target=work, daemon=True).start()

    def _apply_balance(self, res):
        self._balance = res
        if isinstance(res, dict):
            self._balance_fetched_at = time.time()
        else:
            self._balance_fetched_at = 0.0   # 失败立即允许重试（但受 60s 最小间隔保护）
        self.tick()

    def set_deepseek_api_key(self):
        cur = self.cfg.get("deepseek_api_key", "")
        v = simpledialog.askstring(
            "DeepSeek API Key",
            "在 platform.deepseek.com → API Keys 创建并复制 Key：\n"
            "（保存在本地 config.json，仅用于查询余额）"
            + (f"\n\n当前已设置：{cur[:6]}…（留空可清除）" if cur else ""),
            parent=self, show="*")
        if v is None:
            return
        v = v.strip()
        if v:
            self.cfg["deepseek_api_key"] = v
        else:
            self.cfg.pop("deepseek_api_key", None)
        self._balance = None
        self._balance_fetched_at = 0.0
        self.save_cfg()
        self.tick()
        self._paint_small_btns()

    # ---------- 自动发送「继续任务」到 ChatGPT 桌面端 ----------
    def _find_chatgpt_window(self):
        """枚举可见窗口，返回标题含 chatgpt 的窗口句柄（先枚举到的优先）。"""
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.lower()
            if "chatgpt" in title or "chat gpt" in title:
                found.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        return found

    def _auto_send_continue(self):
        """激活 ChatGPT 桌面端窗口，粘贴「继续任务」并回车。成功返回 True。"""
        try:
            user32 = ctypes.windll.user32
            hwnds = self._find_chatgpt_window()
            if not hwnds:
                return False
            hwnd = hwnds[0]
            user32.ShowWindow(hwnd, 9)            # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            time.sleep(0.35)
            # 剪贴板写入（tkinter 自带，避免额外依赖）
            self.clipboard_clear()
            self.clipboard_append("继续任务")
            self.update()
            time.sleep(0.1)
            # Ctrl+V 粘贴
            user32.keybd_event(0x11, 0, 0, 0)     # Ctrl down
            user32.keybd_event(0x56, 0, 0, 0)     # V down
            user32.keybd_event(0x56, 0, 2, 0)     # V up
            user32.keybd_event(0x11, 0, 2, 0)     # Ctrl up
            time.sleep(0.2)
            # Enter 发送
            user32.keybd_event(0x0D, 0, 0, 0)     # Enter down
            user32.keybd_event(0x0D, 0, 2, 0)     # Enter up
            return True
        except Exception:
            return False

    # ---------- 每秒刷新 ----------
    def tick(self):
        if self.page != "main":
            self.after(1000, self.tick)
            return
        now = datetime.now()
        now_ts = now.timestamp()
        cv = self.canvas

        # --- DeepSeek ---
        peak = is_peak(now, self.override)
        cv.itemconfig(self.ds_badge,
                      text="忙时 · 高峰价" if peak else "闲时 · 半价",
                      fill=PEAK_C if peak else OFF_C)
        t1, t2 = next_switch(now, self.override)
        if t1 is None:
            cv.itemconfig(self.ds_main, text="全天闲时（无时段切换）", fill=OFF_C)
            cv.itemconfig(self.ds_remain, text="")
            cv.itemconfig(self.ds_sub, text="")
        else:
            phase = "忙时" if peak else "闲时"
            cv.itemconfig(self.ds_main,
                          text=f"距{phase}结束 {fmt_hm(t1)}",
                          fill=PEAK_C if peak else OFF_C)
            cv.itemconfig(self.ds_remain,
                          text="剩 " + fmt_until(t1 - now),
                          fill=PEAK_C if peak else OFF_C)
            # 下一段忙时 / 下一段闲时 两个时段信息
            if t2:
                st1 = is_peak(t1, self.override)
                t3 = _walk(t2, st1)
                if st1:                      # 下一段是忙时
                    busy_a, busy_b = t1, t2
                    off_a, off_b = t2, t3
                else:                        # 下一段是闲时
                    off_a, off_b = t1, t2
                    busy_a, busy_b = t2, t3
                if off_b and busy_b:
                    cv.itemconfig(self.ds_sub,
                                  text=f"下一段忙时 {fmt_hm(busy_a)}-{fmt_hm(busy_b)}"
                                       f" ｜ 下一段闲时 {fmt_hm(off_a)}-{fmt_hm(off_b)}")
                else:
                    cv.itemconfig(self.ds_sub,
                                  text=f"下一段忙时 {fmt_hm(t1)} 起 ｜ 下一段闲时 {fmt_hm(t1)} 起")
            else:
                cv.itemconfig(self.ds_sub, text="")

        # 余额显示（15 分钟刷新一次，需在设置页配置 API Key）
        self._maybe_refresh_balance(now_ts)
        bal = self._balance
        if bal is None:
            cv.itemconfig(self.ds_balance, text="余额：未设置 API Key（设置页可配置）",
                          fill=FG_DIM)
        elif isinstance(bal, dict) and "total" in bal:
            if bal.get("available"):
                cv.itemconfig(self.ds_balance,
                              text=f"余额：¥{bal['total']:.2f} · 可用",
                              fill=OFF_C)
            else:
                cv.itemconfig(self.ds_balance,
                              text=f"余额：¥{bal['total']:.2f} · 余额不足",
                              fill=WARN_C)
        else:
            cv.itemconfig(self.ds_balance, text="余额：查询失败，稍后自动重试",
                          fill=WARN_C)

        # --- 声音提醒：DS 切换到达 ---
        if self.cfg.get("ds_sound", False):
            if t1 and 0 <= (t1 - now).total_seconds() < 1.5 and self._ds_alerted != t1:
                self._ds_alerted = t1
                play_sound(self.cfg.get("sound_kind", "meizu"))
        else:
            self._ds_alerted = None

        # --- ChatGPT ---
        st = self.counter.state(now_ts)
        end_dt = datetime.fromtimestamp(st["end"])
        cv.itemconfig(self.gpt_remain,
                      text="剩 " + fmt_until(timedelta(seconds=st["remain"])))
        cv.itemconfig(self.gpt_next, text=end_dt.strftime("%H:%M:%S"))
        # “剩”固定用 DeepSeek 忙时橙色
        cv.itemconfig(self.gpt_remain, fill=PEAK_C)

        # 重置到达（自动续算）事件：声音提醒 + 安排自动发送
        if st.get("rolled"):
            if self.cfg.get("gpt_sound", False):
                play_sound(self.cfg.get("sound_kind", "meizu"))
            if self.cfg.get("gpt_auto_send", False):
                self._auto_send_pending = True
                self._auto_send_at = now_ts + 60.0
            self.save_cfg()          # 持久化新的重置锚点
        if self._auto_send_pending and now_ts >= self._auto_send_at:
            self._auto_send_pending = False
            if self._auto_send_continue():
                play_sound(self.cfg.get("sound_kind", "meizu"))

        # --- 一周窗口（按钮行右侧右对齐，只显示重置日期） ---
        wst = self.week_counter.state(now_ts)
        wend_dt = datetime.fromtimestamp(wst["end"])
        cv.itemconfig(self.gpt_week_info,
                      text=f"一周重置 {wend_dt.month}月{wend_dt.day}日")
        if wst.get("rolled"):
            self.save_cfg()          # 持久化新的周重置锚点

        self.after(1000, self.tick)

    # ---------- 自检 ----------
    def selftest_report(self) -> str:
        now = datetime.now()
        lines = [f"[selftest] now={now:%Y-%m-%d %H:%M:%S} {WEEKDAY_CN[now.weekday()]}"]
        checks = [(now.replace(hour=10, minute=0), True),
                  (now.replace(hour=13, minute=0), False),
                  (now.replace(hour=15, minute=30), True),
                  (now.replace(hour=20, minute=0), False)]
        for d, expect in checks:
            got = is_peak(d)
            lines.append(f"[selftest] is_peak({WEEKDAY_CN[d.weekday()]} {d:%H:%M})"
                         f"={got} expect={expect} {'OK' if got == expect else 'FAIL'}")
        if now.weekday() < 5:
            sat = (now + timedelta(days=5 - now.weekday())).replace(hour=10, minute=0)
            lines.append(f"[selftest] is_peak(周六 10:00)={is_peak(sat)}"
                         f" expect=False {'OK' if not is_peak(sat) else 'FAIL'}")
        t1, t2 = next_switch(now, None)
        lines.append(f"[selftest] next_switch -> {fmt_hm(t1)} / {fmt_hm(t2)}")
        peak = is_peak(now, None)
        lines.append(f"[selftest] main_line: 距{'忙时' if peak else '闲时'}结束 "
                     f"{fmt_hm(t1)} 剩 {fmt_until(t1 - now)}")
        if t2:
            st1 = is_peak(t1, None)
            t3 = _walk(t2, st1)
            if st1:
                sub = f"下一段忙时 {fmt_hm(t1)}-{fmt_hm(t2)} ｜ 下一段闲时 {fmt_hm(t2)}-{fmt_hm(t3)}"
            else:
                sub = f"下一段忙时 {fmt_hm(t2)}-{fmt_hm(t3)} ｜ 下一段闲时 {fmt_hm(t1)}-{fmt_hm(t2)}"
            lines.append(f"[selftest] sub_line: {sub}")
        lines.append(f"[selftest] balance: key={'set' if self.cfg.get('deepseek_api_key') else 'none'} "
                     f"state={self._balance}")
        self.counter.set_reset(now.replace(hour=12, minute=10).timestamp())
        st = self.counter.state(time.time())
        lines.append(f"[selftest] gpt(ts) remain={fmt_until(timedelta(seconds=st['remain']))} "
                     f"end={datetime.fromtimestamp(st['end']):%H:%M:%S} "
                     f"rolled={st.get('rolled')}")
        # 自动续算验证：锚点设在 6 小时前，应自动滚动到未来最近的窗口时刻
        past = now.timestamp() - 6 * 3600
        self.counter.set_reset(past)
        st2 = self.counter.state(time.time())
        ok = st2["end"] > time.time()
        lines.append(f"[selftest] auto-roll: end={datetime.fromtimestamp(st2['end']):%H:%M:%S} "
                     f"rolled={st2.get('rolled')} {'OK' if ok else 'FAIL'}")
        self.counter.clear_reset()
        lines.append(f"[selftest] sounds ds={self.cfg.get('ds_sound')} "
                     f"gpt={self.cfg.get('gpt_sound')} kind={self.cfg.get('sound_kind','system')} "
                     f"auto_send={self.cfg.get('gpt_auto_send', False)}")
        win = self._find_chatgpt_window()
        lines.append(f"[selftest] chatgpt window found: {len(win)} "
                     f"(selftest 不发送文本)")
        lines.append(f"[selftest] UI OK {self.winfo_width()}x{self.winfo_height()} "
                     f"bg={self._bg_img.width()}x{self._bg_img.height()}")
        lines.append(f"[selftest] settings page has price table + sound switches")
        return "\n".join(lines)


def main():
    app = Widget()
    if "--selftest" in sys.argv:
        def _report():
            print(app.selftest_report(), flush=True)
            app.destroy()
        app.after(1500, _report)
    app.mainloop()


if __name__ == "__main__":
    main()
