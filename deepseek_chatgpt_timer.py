# -*- coding: utf-8 -*-
"""
发条AI时段小组件
===============
一块置顶、可拖拽的圆角渐变面板（带系统托盘图标），多页面轮播显示：

 1) DeepSeek 峰谷计价
    当前忙/闲状态、距本阶段结束倒计时、下一段起止时间。
 2) ChatGPT 额度重置
    按用量页显示的具体「下次重置」时刻倒计时（可同步），未设置时按 5h 周期。
 3) 订阅到期提醒（多页面）
    内置「即梦 / Running Hub / 豆包免费 / WorkBuddy 积分」预设 + 自定义订阅；
    订阅分两种：按月续费日（每月 N 日续费）与固定日期到期（YYYY-MM-DD），倒计时剩余天数；
    订阅多了自动增加页面；默认每 60 秒自动切换到下一页（可点标题栏 ◀ 页码 ▶ 手动切）；
    到期前 N 天（默认 3，可调）文字变红，每 3 秒红/浅红交替闪烁提醒。
 4) ChatGPT 每月续费到期提醒
    按「每月 N 日」（默认 5 日，设置页可改）倒计时续费，到期前 N 天同样红字闪烁提醒。

设置页已改为「网页形式」：主界面右下角齿轮（或右键 → 打开设置）会打开
本机内置网页（http://127.0.0.1:<端口>/），在浏览器大页面里管理全部设置：
订阅管理、轮播间隔、提醒天数、声音、DeepSeek API Key、ChatGPT 窗口周期等。

定价规则来源（DeepSeek 官方定价页，2026-08-17 起生效、08-23 优化）：
    高峰时段 = 北京时间 周一至周五 09:00-12:00、14:00-18:00
    其余时间（含周末、法定节假日全天）= 空闲时段，价格为高峰时段的一半
    参考: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
价格（元/百万 tokens，2026-09 官方价，输入为缓存未命中价）：
    deepseek-flash   忙 入2/出8    闲 入1/出4
    deepseek-v4-pro  忙 入9/出27   闲 入4.5/出13.5

依赖：Python 3.9+，tkinter + Pillow + pystray（托盘）。
用法：
    pythonw deepseek_chatgpt_timer.py            # 静默启动
    python  deepseek_chatgpt_timer.py --selftest # 逻辑自检
    python  deepseek_chatgpt_timer.py --preview [输出目录]  # 逐页截图（验证用）
"""

import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import webbrowser
from ctypes import wintypes
from datetime import datetime, timedelta, date as date_obj
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import tkinter as tk
from tkinter import font as tkfont
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
DESIGN_W, DESIGN_H = 600, 400   # 设计稿尺寸（内部布局坐标基准）
PAD = 16
UI_SCALE = 0.75                   # 宽度/字号缩放系数（1.0=原尺寸）
UI_SCALE_H = 0.9                  # 高度缩放系数（可单独调高，当前=360 高）
GRAD_TOP = (27, 62, 148)     # 深蓝（顶部）
GRAD_BOT = (112, 170, 240)   # 浅蓝（底部）
GRAD_BG_HEX = "#1b3e94"

FONT = "Microsoft YaHei"        # 全部文字统一微软雅黑
MONO = FONT                     # 数字/时段也使用微软雅黑（与正文一致）
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

# ---------------- 订阅到期提醒参数 ----------------
SUB_PRESETS = [                      # 内置订阅预设（可改续费日/到期日/停用/删除）
    {"name": "即梦", "renew_day": 1, "color": "#7ec8ff"},
    {"name": "Running Hub", "renew_day": 1, "color": "#ffb4a2"},
    {"name": "豆包免费", "expire_date": "2026-09-25", "color": "#7fd8a0"},
    {"name": "WorkBuddy 积分", "expire_date": "2026-09-26", "color": "#c9a6ff"},
]
SUB_PER_PAGE = 4                     # 每页最多显示几个订阅
DEFAULT_WARN_DAYS = 3                # 到期前 N 天红字提醒（默认 3，可调）
DEFAULT_ROTATE_SECONDS = 60          # 页面轮播间隔（默认 60 秒，可调）
FLASH_SECONDS = 3.0                  # 红字闪烁：每 3 秒红/浅红交替
WARN_RED = "#ff5252"                 # 提醒红
WARN_RED_LIGHT = "#ffd0cc"           # 提醒浅红（闪烁另一相）
CARD_BG = "#1a3f8f"                  # 订阅卡片底
CARD_OUT = "#2f5fb5"                 # 订阅卡片描边
LOGO_SIZE = 34                       # 订阅卡片左侧自动 LOGO 圆直径（设计坐标）

# ---------------- API 订阅额度模板（官方真实接口） ----------------
# balance_url 非空 → 支持「API Key 一键查询」；为空 → 该平台无 API Key 直查余额接口
# （余额查询需 AK/SK 签名或登录控制台），条目仍可显示手动登记的余额。
API_TEMPLATES = [
    {"id": "siliconflow", "name": "硅基流动 SiliconFlow", "color": "#4db8ff",
     "api_url": "https://api.siliconflow.cn/v1",
     "balance_url": "https://api.siliconflow.cn/v1/user/info",
     "console_url": "https://cloud.siliconflow.cn/account/balance",
     "tip": "一键查询总余额（赠送+充值）"},
    {"id": "minimax", "name": "MiniMax（mimo）", "color": "#5eead4",
     "api_url": "https://api.minimaxi.com/v1",
     "balance_url": "https://www.minimaxi.com/v1/token_plan/remains",
     "console_url": "https://platform.minimaxi.com",
     "tip": "一键查询 Token Plan 订阅剩余额度"},
    {"id": "deepseek", "name": "DeepSeek", "color": "#7ec8ff",
     "api_url": "https://api.deepseek.com",
     "balance_url": "https://api.deepseek.com/user/balance",
     "console_url": "https://platform.deepseek.com",
     "tip": "一键查询账户余额（与主界面一致）"},
    {"id": "zhipu", "name": "智谱 GLM", "color": "#ffb4a2",
     "api_url": "https://open.bigmodel.cn/api/paas/v4",
     "balance_url": "", "console_url": "https://open.bigmodel.cn/console",
     "tip": "无公开余额接口，请登录控制台查看"},
    {"id": "moonshot", "name": "月之暗面 Kimi", "color": "#c9a6ff",
     "api_url": "https://api.moonshot.cn/v1",
     "balance_url": "", "console_url": "https://platform.moonshot.cn/console",
     "tip": "无公开余额接口，请登录控制台查看"},
    {"id": "volcengine", "name": "火山引擎（方舟）", "color": "#ffd166",
     "api_url": "https://ark.cn-beijing.volces.com/api/v3",
     "balance_url": "", "console_url": "https://console.volcengine.com/ark",
     "tip": "余额需 AccessKey（AK/SK）签名，请登录控制台查看"},
    {"id": "aliyun", "name": "阿里云百炼", "color": "#a8d8ff",
     "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "balance_url": "", "console_url": "https://bailian.console.aliyun.com",
     "tip": "余额需 AccessKey（AK/SK）签名，请登录控制台查看"},
    {"id": "tencent", "name": "腾讯云大模型", "color": "#a5e6a5",
     "api_url": "https://api.hunyuan.cloud.tencent.com/v1",
     "balance_url": "", "console_url": "https://console.cloud.tencent.com/expense",
     "tip": "余额需 SecretId/SecretKey 签名，请登录控制台查看"},
    {"id": "custom", "name": "自定义", "color": "#cfd8dc",
     "api_url": "", "balance_url": "", "console_url": "",
     "tip": "自定义 API 地址（Key 仅记录，需手动登记余额）"},
]


def api_tpl_by_id(tid):
    for t in API_TEMPLATES:
        if t["id"] == tid:
            return t
    return None


def _find_number(obj, depth=0):
    """递归在 API 返回体中找第一个可作额度展示的数字（容错解析各家返回结构）。"""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        for k in ("remaining", "quota_remaining", "quota", "total_balance",
                  "balance", "total", "remain", "left", "credits", "tokens"):
            v = obj.get(k)
            if isinstance(v, (int, float)) and v >= 0:
                return v
            if isinstance(v, str):
                t = v.replace(",", "").strip()
                if t.replace(".", "", 1).isdigit():
                    return float(t)
        for k, v in obj.items():
            kl = str(k).lower()
            if any(x in kl for x in ("code", "err", "msg", "status", "ret",
                                     "request", "time", "version", "reqid")):
                continue
            r = _find_number(v, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            r = _find_number(v, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, (int, float)) and obj >= 0:
        return obj
    return None

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


def fmt_range(a: datetime, b: datetime) -> str:
    """起止区间：同日省略结束周几（周五 09:00-12:00）；跨天两端带周几（18:00-周五 09:00）"""
    if a.date() == b.date():
        return f"{fmt_hm(a)}-{b.strftime('%H:%M')}"
    return f"{fmt_hm(a)}-{fmt_hm(b)}"


def make_gradient(w: int, h: int, c1, c2) -> Image.Image:
    """垂直渐变：顶部 c1（深蓝）→ 底部 c2（浅蓝）。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=color)
    return img


# ---------------- Win32 托盘图标（Shell_NotifyIcon，无第三方依赖） ----------------
_WM_TRAYICON = 0x0400 + 20
_WM_COMMAND = 0x0111
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONUP = 0x0205
_NIM_ADD = 0x00000000
_NIM_DELETE = 0x00000002
_NIF_MESSAGE = 0x00000001
_NIF_ICON = 0x00000002
_NIF_TIP = 0x00000004
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x00000010
_MF_STRING = 0x00000000
_TPM_RIGHTBUTTON = 0x0002
_CMD_SHOW = 1
_CMD_QUIT = 2


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class WinTray:
    """纯 Win32 系统托盘图标：左键单击切换窗口显示/隐藏，右键菜单含「显示 / 隐藏」「退出」。"""

    _WNDCLASS = "TkAiTrayWnd2026"

    def __init__(self, app):
        self._app = app
        self._hwnd = None
        self._hicon = None
        self._tid = None
        self._alive = True
        self._wndproc = None

    def _wnd_proc(self, hwnd, msg, wp, lp):
        if msg == _WM_TRAYICON:
            ev = lp & 0xFFFF
            if ev == _WM_LBUTTONUP:
                self._app._tray_request("toggle")
            elif ev == _WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == _WM_COMMAND:
            cmd = wp & 0xFFFF
            if cmd == _CMD_SHOW:
                self._app._tray_request("toggle")
            elif cmd == _CMD_QUIT:
                self._app._tray_request("quit")
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _show_menu(self):
        try:
            u32 = ctypes.windll.user32
            h = u32.CreatePopupMenu()
            u32.AppendMenuW(h, _MF_STRING, _CMD_SHOW, "显示 / 隐藏")
            u32.AppendMenuW(h, _MF_STRING, _CMD_QUIT, "退出")
            pt = wintypes.POINT()
            u32.GetCursorPos(ctypes.byref(pt))
            u32.SetForegroundWindow(self._hwnd)
            u32.TrackPopupMenu(h, _TPM_RIGHTBUTTON,
                               pt.x, pt.y, 0, self._hwnd, None)
            u32.DestroyMenu(h)
        except Exception:
            pass

    def _load_icon(self):
        for p in (os.path.join(APP_DIR, "app.ico"),
                  os.path.join(APP_DIR, "assets", "deepseek_3.ico")):
            if os.path.exists(p):
                try:
                    h = ctypes.windll.user32.LoadImageW(
                        None, p, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
                    if h:
                        return h
                except Exception:
                    pass
        try:
            tmp = os.path.join(tempfile.gettempdir(), "ai_timer_tray.ico")
            img = make_gradient(64, 64, GRAD_TOP, GRAD_BOT)
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 34)
            except Exception:
                font = ImageFont.load_default()
            d.ellipse((2, 2, 62, 62), fill=(255, 255, 255, 255))
            d.text((32, 32), "AI", font=font, fill=GRAD_BG_HEX, anchor="mm")
            img.save(tmp, format="ICO", sizes=[(32, 32), (64, 64)])
            return ctypes.windll.user32.LoadImageW(
                None, tmp, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
        except Exception:
            return None

    def _create(self):
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hinst = k32.GetModuleHandleW(None)
        WNDPROC = ctypes.WINFUNCTYPE(wintypes.LONG, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)
        self._wndproc = WNDPROC(self._wnd_proc)

        class _WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wc = _WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self._WNDCLASS
        u32.RegisterClassW(ctypes.byref(wc))   # 已注册会失败，可忽略
        self._hwnd = u32.CreateWindowExW(0, self._WNDCLASS, "AiTray", 0,
                                         0, 0, 0, 0, None, None, hinst, None)
        if not self._hwnd:
            raise RuntimeError("CreateWindowExW failed")
        self._hicon = self._load_icon()
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _WM_TRAYICON
        nid.hIcon = self._hicon
        nid.szTip = "发条AI时段小组件"
        if not u32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid)):
            raise RuntimeError("Shell_NotifyIconW failed")

    def _run(self):
        try:
            self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
            self._create()
            msg = wintypes.MSG()
            u32 = ctypes.windll.user32
            while self._alive:
                r = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            try:
                self._destroy()
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _destroy(self):
        try:
            u32 = ctypes.windll.user32
            if self._hwnd:
                nid = _NOTIFYICONDATAW()
                nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
                nid.hWnd = self._hwnd
                nid.uID = 1
                u32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
                u32.DestroyWindow(self._hwnd)
                self._hwnd = None
            if self._hicon:
                u32.DestroyIcon(self._hicon)
                self._hicon = None
        except Exception:
            pass

    def remove(self):
        self._alive = False
        try:
            if self._tid:
                ctypes.windll.user32.PostThreadMessageW(
                    self._tid, 0x0012, 0, 0)   # WM_QUIT
        except Exception:
            pass


def _logo_fg(hexcolor: str) -> str:
    """订阅徽标文字颜色：浅色底用深色字，深色底用白字。"""
    try:
        r = int(hexcolor[1:3], 16)
        g = int(hexcolor[3:5], 16)
        b = int(hexcolor[5:7], 16)
        return "#12213a" if (r * 299 + g * 587 + b * 114) / 1000 > 160 else "#ffffff"
    except Exception:
        return "#ffffff"


def make_logo_img(text: str, hexcolor: str, size: int) -> Image.Image:
    """生成正圆形订阅徽标（RGBA）：品牌色圆 + 白色/深色首字符。
    size 为最终物理像素直径；用 PIL 预渲染可避免 canvas 非等比缩放把圆压扁。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=hexcolor)
    fg = _logo_fg(hexcolor)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", max(8, int(size * 0.52)))
    except Exception:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", max(8, int(size * 0.52)))
        except Exception:
            font = ImageFont.load_default()
    d.text((size / 2, size / 2), text, font=font, fill=fg, anchor="mm")
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


# ---------------- 订阅到期倒计时（按月续费日 / 固定日期到期） ----------------
def month_days(y: int, m: int) -> int:
    """该月天数。"""
    if m == 12:
        return (date_obj(y + 1, 1, 1) - date_obj(y, 12, 1)).days
    return (date_obj(y, m + 1, 1) - date_obj(y, m, 1)).days


def next_renew_date(renew_day: int, today: date_obj) -> date_obj:
    """最近一次（含今天）的续费日；续费日大于当月天数时截断到月末。"""
    renew_day = max(1, min(31, int(renew_day)))
    y, m = today.year, today.month
    for _ in range(2):
        d = min(renew_day, month_days(y, m))
        dt = date_obj(y, m, d)
        if dt >= today:
            return dt
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return date_obj(y, m, 1)


def sub_status(s: dict, today: date_obj):
    """返回 (剩余天数, 下一个关键日期)。天数<0 表示已过期。
    按月订阅（renew_day）算到下一个续费日；固定日期订阅（expire_date）算到到期日。"""
    ed = s.get("expire_date")
    if ed:
        try:
            d = datetime.strptime(str(ed).strip(), "%Y-%m-%d").date()
        except Exception:
            d = today
        return (d - today).days, d
    renew_day = int(s.get("renew_day") or 1)
    nxt = next_renew_date(renew_day, today)
    return (nxt - today).days, nxt


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


# ---------------- 小组件 UI（多页面：主界面 + 订阅页；设置走网页） ----------------
class Widget(tk.Tk):

    def __init__(self):
        # 单实例：已有小组件在运行则激活它，避免重复启动（自检/预览模式跳过）
        if "--selftest" not in sys.argv and "--preview" not in sys.argv:
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
        self._auto_send_pending = False   # 等待自动发送
        self._auto_send_at = 0.0          # 自动发送执行时刻
        self._balance = None        # None=未设置Key / dict=查询结果 / "err"=失败
        self._balance_fetched_at = 0.0    # 上次成功查询时间

        # ---- 多页面状态 ----
        self.page_idx = 0                 # 当前页下标（0=主界面，1..=订阅页）
        self._page_count = 1              # 总页数
        self._indicator_ids = []          # （兼容保留）各页标题栏页码指示器 text id
        self._nav_prev = {}               # 各页标题栏「◀」三角 id
        self._nav_next = {}               # 各页标题栏「▶」三角 id
        self._nav_nums = {}               # 各页标题栏页码数字 id 列表（pg -> [ids]）
        self._sub_dynamic = []            # 订阅动态文本项（与启用的订阅对齐）
        self._api_dynamic = []            # API 额度卡动态文本项
        self._api_balance = {}            # tpl_id -> {text, fill, sub} 查询缓存
        self._api_balance_fetched_at = 0.0  # 上次 API 余额查询时间
        self._sub_pages = 0               # 订阅到期提醒页数（API 页从其后开始）
        self._zoom = 1.0                  # UI 缩放倍率（1.0 / 1.5）
        self._tray_q = []                 # 托盘事件队列（主线程 tick 消费）
        self._flash_on = False            # 红字闪烁相位
        self._last_switch = time.time()   # 上次切页时刻
        self._last_flash = time.time()    # 上次闪烁切换时刻

        # ---- 网页设置服务 ----
        self._httpd = None
        self._http_port = 0
        self._web_pending = []        # HTTP 线程投递的配置，由主线程 tick 统一应用

        self.overrideredirect(True)
        self.title("发条AI时段小组件")
        self.attributes("-topmost", bool(self.cfg.get("topmost", True)))

        self._icon_ds = self._load_icon("deepseek_icon.png")
        self._icon_gpt = self._load_icon("chatgpt_icon.png")
        _gear = make_gear(20, (255, 255, 255))
        if abs(UI_SCALE * self._zoom - 1.0) > 1e-9:
            _gear = _gear.resize(
                (max(1, int(20 * UI_SCALE * self._zoom)),
                 max(1, int(20 * UI_SCALE * self._zoom))),
                Image.LANCZOS)
        self._gear_img = ImageTk.PhotoImage(_gear)
        self._bg_img = None

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=GRAD_BG_HEX,
                                width=int(DESIGN_W * UI_SCALE * self._zoom),
                                height=int(DESIGN_H * UI_SCALE_H * self._zoom))
        self.canvas.pack()

        self.rebuild_pages()
        self._bind_events()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        pos = self.cfg.get("pos") or {}
        x = pos.get("x")
        y = pos.get("y")
        ww, wh = int(DESIGN_W * UI_SCALE * self._zoom), int(DESIGN_H * UI_SCALE_H * self._zoom)
        # 旧位置在新窗口尺寸下可能超出屏幕（越界则回到右下角）
        if not x or not y or x + ww > sw or y + wh > sh:
            x = sw - ww
            y = sh - wh
        self.geometry(f"{ww}x{wh}+{int(x)}+{int(y)}")
        self.update_idletasks()
        self._apply_round_rect()

        self.start_web_settings()
        self.tick()
        self.save_cfg()
        if "--selftest" not in sys.argv and "--preview" not in sys.argv:
            self.after(300, self._init_tray)

    # ---------- 配置持久化 ----------
    def load_cfg(self) -> dict:
        try:
            # utf-8-sig：兼容带 BOM 的配置文件（如 PowerShell 写入的 UTF-8）
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        # 订阅：首次运行自动内置「即梦 / Running Hub / 豆包免费 / WorkBuddy 积分」预设
        subs = cfg.get("subscriptions")
        if not isinstance(subs, list):
            subs = []
            for p in SUB_PRESETS:
                item = {"name": p["name"], "enabled": True, "color": p["color"]}
                if p.get("expire_date"):
                    item["expire_date"] = p["expire_date"]
                else:
                    item["renew_day"] = p.get("renew_day", 1)
                subs.append(item)
            cfg["subscriptions"] = subs
        else:
            for s in subs:
                if not isinstance(s, dict):
                    continue
                s["enabled"] = bool(s.get("enabled", True))
                name = str(s.get("name", "订阅")).strip()[:20] or "订阅"
                if name == "季梦":               # 旧版预设名迁移
                    name = "即梦"
                s["name"] = name
                s["color"] = str(s.get("color", "#7ec8ff"))
                ed = s.get("expire_date")
                if ed:
                    try:
                        datetime.strptime(str(ed).strip(), "%Y-%m-%d")
                        s["expire_date"] = str(ed).strip()
                    except Exception:
                        s.pop("expire_date", None)
                        ed = None
                if not ed:
                    try:
                        s["renew_day"] = max(1, min(31, int(s.get("renew_day", 1) or 1)))
                    except Exception:
                        s["renew_day"] = 1
                    s.pop("expire_date", None)
        cfg.setdefault("sub_warn_days", DEFAULT_WARN_DAYS)
        cfg.setdefault("rotate_seconds", DEFAULT_ROTATE_SECONDS)
        cfg.setdefault("topmost", True)
        cfg.setdefault("gpt_renew_day", 5)   # ChatGPT 每月续费日（默认下月 5 号）
        return cfg

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
            "rotate_seconds": int(self.cfg.get("rotate_seconds", DEFAULT_ROTATE_SECONDS)),
            "sub_warn_days": int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS)),
            "gpt_renew_day": int(self.cfg.get("gpt_renew_day", 5) or 5),
            "subscriptions": self.cfg.get("subscriptions", []),
            "api_subs": self.cfg.get("api_subs", []),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_icon(self, name):
        try:
            img = Image.open(os.path.join(APP_DIR, "assets", name)).convert("RGBA")
            if abs(UI_SCALE * self._zoom - 1.0) > 1e-9:
                img = img.resize(
                    (max(1, int(img.width * UI_SCALE * self._zoom)),
                     max(1, int(img.height * UI_SCALE * self._zoom))), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _apply_round_rect(self, radius=22):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, int(DESIGN_W * UI_SCALE * self._zoom) + 1,
                int(DESIGN_H * UI_SCALE_H * self._zoom) + 1,
                int(radius * 2 * UI_SCALE * self._zoom),
                int(radius * 2 * UI_SCALE * self._zoom))
            ctypes.windll.user32.SetWindowRgn(hwnd, hrgn, True)
        except Exception:
            pass

    # ---------- 托盘（Win32 Shell_NotifyIcon，见模块级 WinTray 类） ----------
    def _init_tray(self):
        try:
            self._tray = WinTray(self)
            self._tray.start()
        except Exception:
            self._tray = None

    def _tray_request(self, action):
        """托盘线程回调：把动作放进队列，由主线程 tick 执行（tkinter 只能在主线程操作）。"""
        try:
            self._tray_q.append(action)
        except Exception:
            pass

    def _drain_tray(self):
        while self._tray_q:
            a = self._tray_q.pop(0)
            if a == "toggle":
                self._toggle_window()
            elif a == "quit":
                self._quit_app()

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
                self._tray.remove()
        except Exception:
            pass
        try:
            if self._httpd:
                self._httpd.shutdown()
        except Exception:
            pass
        self.destroy()

    # ---------- 多页面构建 / 切换 ----------
    def _enabled_subs(self):
        return [s for s in self.cfg.get("subscriptions", [])
                if isinstance(s, dict) and s.get("enabled", True)]

    def _enabled_api_subs(self):
        return [s for s in self.cfg.get("api_subs", [])
                if isinstance(s, dict) and s.get("enabled", True)]

    def rebuild_pages(self):
        """重建全部页面（启动时 / 设置变化后）。"""
        cv = self.canvas
        cv.delete("all")
        self._pin_bg_off = self._pill(66, 20, (255, 255, 255), 38)
        self._pin_bg_on = self._pill(66, 20, (188, 217, 255), 88)
        self._pin_bg_hover = self._pill(66, 20, (255, 255, 255), 88)
        self._zoom_bg_off = self._pill(38, 20, (255, 255, 255), 38)
        self._zoom_bg_on = self._pill(38, 20, (188, 217, 255), 88)
        self._zoom_bg_hover = self._pill(38, 20, (255, 255, 255), 88)
        self._bg_img = ImageTk.PhotoImage(
            make_gradient(int(DESIGN_W * UI_SCALE * self._zoom),
                          int(DESIGN_H * UI_SCALE_H * self._zoom),
                          GRAD_TOP, GRAD_BOT))
        cv.create_image(0, 0, image=self._bg_img, anchor="nw", tags="bg")

        self._indicator_ids = []
        self._nav_prev = {}
        self._nav_next = {}
        self._nav_nums = {}
        self._sub_dynamic = []
        self._logo_imgs = []              # 订阅徽标位图引用（防 GC）
        self._build_main_page()
        subs = self._enabled_subs()
        sub_pages = (len(subs) + SUB_PER_PAGE - 1) // SUB_PER_PAGE if subs else 0
        self._sub_pages = sub_pages
        self._build_sub_pages(subs, sub_pages)
        apis = self._enabled_api_subs()
        api_pages = (len(apis) + SUB_PER_PAGE - 1) // SUB_PER_PAGE if apis else 0
        self._build_api_pages(apis, api_pages)
        self._page_count = 1 + sub_pages + api_pages
        if self.page_idx >= self._page_count:
            self.page_idx = 0
        self._last_switch = time.time()
        self._build_page_nav()
        self._bind_page_events()
        self.show_page(self.page_idx)
        self._paint_pin()
        self._scale_ui()

    def _pill(self, w_d, h_d, color, alpha):
        """生成半透明圆角胶囊按钮底图（按有效缩放换算实际像素）。"""
        w = max(2, int(w_d * UI_SCALE * self._zoom))
        h = max(2, int(h_d * UI_SCALE * self._zoom))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=max(2, h // 2),
                            fill=color + (alpha,))
        return ImageTk.PhotoImage(img)

    def _scale_ui(self):
        """把整界面按缩放系数变换；scale 不改文字字号/图片尺寸，字号按宽度系数单独缩放。"""
        SX, SY = UI_SCALE, UI_SCALE_H
        if abs(SX - 1.0) < 1e-9 and abs(SY - 1.0) < 1e-9:
            return
        cv = self.canvas
        cv.scale("all", 0, 0, SX, SY)
        for item in cv.find_all():
            try:
                t = cv.type(item)
            except Exception:
                continue
            if t == "text":
                try:
                    font = cv.itemcget(item, "font") or ""
                    m = re.search(r"(\d+(?:\.\d+)?)", font)
                    if m:
                        size = max(2, int(round(float(m.group(1)) * SX)))
                        cv.itemconfig(
                            item, font=re.sub(r"\d+(?:\.\d+)?", str(size), font, count=1))
                except Exception:
                    pass
            elif t in ("line", "rectangle", "oval", "polygon"):
                try:
                    w = cv.itemcget(item, "width")
                    if w and float(w) < 1:
                        cv.itemconfig(item, width=1)
                except Exception:
                    pass

    def show_page(self, idx):
        """显示第 idx 页（隐藏其它页）。"""
        self.page_idx = idx % max(1, self._page_count)
        cv = self.canvas
        for k in range(self._page_count):
            cv.itemconfig("pg%d" % k,
                          state="normal" if k == self.page_idx else "hidden")
        self._paint_page_indicator()
        self._paint_current()

    def next_page(self):
        if self._page_count <= 1:
            return
        self.show_page((self.page_idx + 1) % self._page_count)

    def prev_page(self):
        if self._page_count <= 1:
            return
        self.show_page((self.page_idx - 1) % self._page_count)

    def _on_page_num(self, e):
        """点击页码数字直接跳页。"""
        try:
            items = self.canvas.find_withtag("current")
            if not items:
                return
            self.show_page(int(self.canvas.itemcget(items[0], "text")) - 1)
        except Exception:
            pass

    def _build_page_nav(self):
        """每页标题栏画 ◀ 页码1..N ▶：左/右实心三角 + 中间全部页码数字（当前页高亮）。"""
        cv = self.canvas
        R = DESIGN_W - PAD
        y = 26
        num_w = 13
        tri_w = 12
        total_w = tri_w + self._page_count * num_w + tri_w
        # 导航组在标题栏水平居中（置顶开关固定在右上角，不会重叠）
        x0 = (DESIGN_W - total_w) // 2
        for pg in range(self._page_count):
            tag0 = "pg%d" % pg
            self._nav_prev[pg] = cv.create_polygon(
                x0 + 10, y - 5, x0, y, x0 + 10, y + 5,
                fill=FG_DIM, outline="", tags=(tag0, "prev"))
            ids = []
            for i in range(self._page_count):
                nx = x0 + tri_w + i * num_w + num_w // 2
                ids.append(cv.create_text(
                    nx, y, text=str(i + 1), anchor="center",
                    fill=FG_DIM, font=(FONT, 9), tags=(tag0, "page_num")))
            self._nav_nums[pg] = ids
            x1 = x0 + total_w - tri_w
            self._nav_next[pg] = cv.create_polygon(
                x1, y - 5, x1 + 10, y, x1, y + 5,
                fill=FG_DIM, outline="", tags=(tag0, "next"))

    def _paint_page_indicator(self):
        """更新页码导航高亮：当前页亮蓝，其它页暗色（字号已在 _scale_ui 统一缩放，这里只改颜色）。"""
        cur = self.page_idx
        cv = self.canvas
        for ids in self._nav_nums.values():
            for i, tid in enumerate(ids):
                cv.itemconfig(tid, fill=ACC_C if i == cur else FG_DIM)

    # ---------- 主界面（第 0 页） ----------
    def _build_main_page(self):
        cv = self.canvas
        R = DESIGN_W - PAD
        PG0 = "pg0"

        # 标题栏：左标题，右 [◀ 页码 ▶] [置顶:开] [×]
        cv.create_text(PAD, 26, text="发条AI时段小组件", anchor="w",
                       fill=FG_DIM, font=(FONT, 8), tags=PG0)
        cv.create_text(R - 40, 26, text="  ×  ", anchor="e", fill=FG_DIM,
                       font=(FONT, 11), tags=(PG0, "close"))
        cv.create_image(R - 110, 26, image=self._pin_bg_off, anchor="center",
                        tags=(PG0, "pinbg"))
        self.pin_btn = cv.create_text(R - 88, 26, text="", anchor="e",
                                      fill=ACC_C, font=(FONT, 8), tags=(PG0, "pin"))
        cv.create_image(R - 187, 26, image=self._zoom_bg_off, anchor="center",
                        tags=(PG0, "zoombg"))
        cv.create_text(R - 174, 26, text="1×", anchor="e", fill=FG_DIM,
                       font=(FONT, 8), tags=(PG0, "zoom"))

        # ---- DeepSeek 区块 ----
        if self._icon_ds:
            cv.create_image(PAD, 44, image=self._icon_ds, anchor="nw", tags=PG0)
        cv.create_text(PAD + 38, 56, text="DeepSeek 峰谷计价", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"), tags=PG0)
        self.ds_badge = cv.create_text(R, 56, text="", anchor="e",
                                       fill=OFF_C, font=(FONT, 9, "bold"), tags=PG0)
        self.ds_main = cv.create_text(PAD, 96, text="", anchor="w",
                                      fill=FG_W, font=(MONO, 14, "bold"), tags=PG0)
        self.ds_remain = cv.create_text(R, 96, text="", anchor="e",
                                        fill=FG_W, font=(MONO, 14, "bold"), tags=PG0)
        self.ds_sub = cv.create_text(PAD, 126, text="", anchor="w",
                                     fill=FG_DIM, font=(MONO, 9), tags=PG0)
        self.ds_sub_r = cv.create_text(R, 126, text="", anchor="e",
                                       fill=FG_DIM, font=(MONO, 9), tags=PG0)
        self.ds_balance = cv.create_text(PAD, 152, text="", anchor="w",
                                         fill=FG_DIM, font=(FONT, 10, "bold"), tags=PG0)
        cv.create_line(PAD, 190, R, 190, fill=DIVIDER, width=1, tags=PG0)

        # ---- ChatGPT 区块（5小时 + 一周双窗口，无进度条） ----
        if self._icon_gpt:
            cv.create_image(PAD, 192, image=self._icon_gpt, anchor="nw", tags=PG0)
        cv.create_text(PAD + 38, 206, text="ChatGPT 额度重置", anchor="w",
                       fill=FG_W, font=(FONT, 10, "bold"), tags=PG0)
        cv.create_text(PAD, 240, text="下次重置", anchor="w",
                       fill=FG_DIM, font=(FONT, 9), tags=PG0)
        self.gpt_next = cv.create_text(PAD + 78, 240, text="", anchor="w",
                                       fill=FG_W, font=(MONO, 12, "bold"), tags=PG0)
        self.gpt_remain = cv.create_text(R, 240, text="", anchor="e",
                                         fill=PEAK_C, font=(MONO, 14, "bold"), tags=PG0)
        self.btn_sync = cv.create_rectangle(PAD, 272, PAD + 136, 294,
                                            fill=BTN_BG, outline="",
                                            tags=(PG0, "sync"))
        cv.create_text(PAD + 68, 283, text="同步重置时间", fill=FG_W,
                       font=(FONT, 9), tags=(PG0, "sync"))
        self.btn_week = cv.create_rectangle(PAD + 144, 272, PAD + 294, 294,
                                            fill=BTN_BG, outline="",
                                            tags=(PG0, "week_sync"))
        cv.create_text(PAD + 219, 283, text="同步重置日期", fill=FG_W,
                       font=(FONT, 9), tags=(PG0, "week_sync"))
        self.gpt_week_info = cv.create_text(R, 283, text="", anchor="e",
                                            fill=FG_W, font=(MONO, 10, "bold"),
                                            tags=PG0)
        self.gpt_sub = cv.create_text(R, 305, text="", anchor="e",
                                      fill=FG_DIM, font=(MONO, 9), tags=PG0)
        cv.create_text(PAD, 340,
                       text="提示：同步重置时间后自动按 5 小时续算；同步重置日期后自动按 7 天续算",
                       anchor="w", fill=FG_DIM, font=(FONT, 8), tags=PG0)

        # 底部：提示 + 右下角设置
        cv.create_text(PAD, 384, text="右键：菜单 · 拖拽移动 · × 隐藏到托盘",
                       anchor="w", fill=FG_DIM, font=(FONT, 8), tags=PG0)
        cv.create_image(R - 44, 378, image=self._gear_img, anchor="center",
                        tags=(PG0, "gear"))
        cv.create_text(R - 28, 378, text="设置", anchor="w", fill=FG_DIM,
                       font=(FONT, 7), tags=(PG0, "gear"))

    # ---------- 订阅页（第 1..N 页） ----------
    def _build_sub_pages(self, subs, sub_pages):
        cv = self.canvas
        R = DESIGN_W - PAD
        warn_days = int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS))
        for k in range(sub_pages):
            pg = k + 1
            tag0 = "pg%d" % pg
            cv.create_text(PAD, 26, text="订阅到期提醒", anchor="w",
                           fill=FG_DIM, font=(FONT, 8), tags=tag0)
            cv.create_image(R - 110, 26, image=self._pin_bg_off, anchor="center",
                            tags=(tag0, "pinbg"))
            cv.create_text(R - 88, 26, text="", anchor="e", fill=ACC_C,
                           font=(FONT, 8), tags=(tag0, "pin"))
            cv.create_image(R - 187, 26, image=self._zoom_bg_off, anchor="center",
                            tags=(tag0, "zoombg"))
            cv.create_text(R - 174, 26, text="1×", anchor="e", fill=FG_DIM,
                           font=(FONT, 8), tags=(tag0, "zoom"))
            cv.create_text(R - 40, 26, text="  ×  ", anchor="e", fill=FG_DIM,
                           font=(FONT, 11), tags=(tag0, "close"))
            cv.create_image(R - 44, 378, image=self._gear_img, anchor="center",
                            tags=(tag0, "gear"))
            cv.create_text(R - 28, 378, text="设置", anchor="w", fill=FG_DIM,
                           font=(FONT, 7), tags=(tag0, "gear"))
            cv.create_text(PAD, 384,
                           text=f"右键：菜单 · 到期前 {warn_days} 天红字提醒 · × 隐藏到托盘",
                           anchor="w", fill=FG_DIM, font=(FONT, 8), tags=tag0)

            for r in range(SUB_PER_PAGE):
                i = k * SUB_PER_PAGE + r
                if i >= len(subs):
                    break
                s = subs[i]
                y = 52 + r * 80
                cv.create_rectangle(PAD, y, R, y + 72, fill=CARD_BG,
                                    outline=CARD_OUT, tags=tag0)
                # 自动 LOGO：正圆形徽标（PIL 预渲染，避免非等比缩放压扁）
                logo_char = s["name"][0].upper()
                logo_img = ImageTk.PhotoImage(make_logo_img(
                    logo_char, s.get("color", ACC_C),
                    max(2, int(LOGO_SIZE * UI_SCALE * self._zoom))))
                self._logo_imgs.append(logo_img)
                cv.create_image(PAD + 12, y + (72 - LOGO_SIZE) // 2,
                                image=logo_img, anchor="nw", tags=tag0)
                tip = ("一次性到期" if s.get("expire_date")
                       else f"每月 {s.get('renew_day', 1)} 日续费")
                cv.create_text(PAD + 56, y + 24, text=s["name"], anchor="w",
                               fill=FG_W, font=(FONT, 13, "bold"), tags=tag0)
                cv.create_text(PAD + 56, y + 48, text=tip,
                               anchor="w", fill=FG_DIM, font=(FONT, 9), tags=tag0)
                big = cv.create_text(R - 20, y + 24, text="", anchor="e",
                                     fill=FG_W, font=(MONO, 15, "bold"), tags=tag0)
                sub = cv.create_text(R - 20, y + 50, text="", anchor="e",
                                     fill=FG_DIM, font=(FONT, 9), tags=tag0)
                self._sub_dynamic.append({"sub": s, "big": big, "subtext": sub})

    def _build_api_pages(self, apis, api_pages):
        """API 额度/订阅页：排在订阅到期提醒页之后（页序 0=主界面，1..订阅，其后=API）。"""
        cv = self.canvas
        R = DESIGN_W - PAD
        for k in range(api_pages):
            pg = self._sub_pages + k + 1
            tag0 = "pg%d" % pg
            cv.create_text(PAD, 26, text="API 额度 / 订阅", anchor="w",
                           fill=FG_DIM, font=(FONT, 8), tags=tag0)
            cv.create_image(R - 110, 26, image=self._pin_bg_off, anchor="center",
                            tags=(tag0, "pinbg"))
            cv.create_text(R - 88, 26, text="", anchor="e", fill=ACC_C,
                           font=(FONT, 8), tags=(tag0, "pin"))
            cv.create_image(R - 187, 26, image=self._zoom_bg_off, anchor="center",
                            tags=(tag0, "zoombg"))
            cv.create_text(R - 174, 26, text="1×", anchor="e", fill=FG_DIM,
                           font=(FONT, 8), tags=(tag0, "zoom"))
            cv.create_text(R - 40, 26, text="  ×  ", anchor="e", fill=FG_DIM,
                           font=(FONT, 11), tags=(tag0, "close"))
            cv.create_image(R - 44, 378, image=self._gear_img, anchor="center",
                            tags=(tag0, "gear"))
            cv.create_text(R - 28, 378, text="设置", anchor="w", fill=FG_DIM,
                           font=(FONT, 7), tags=(tag0, "gear"))
            cv.create_text(PAD, 384,
                           text="右键：菜单 · 自动查询余额 · 无查询接口的平台显示「控制台查看」",
                           anchor="w", fill=FG_DIM, font=(FONT, 8), tags=tag0)

            for r in range(SUB_PER_PAGE):
                i = k * SUB_PER_PAGE + r
                if i >= len(apis):
                    break
                s = apis[i]
                tpl = api_tpl_by_id(s.get("tpl", ""))
                name = s.get("name") or (tpl or {}).get("name", "API")
                color = (tpl or {}).get("color", "#7ec8ff")
                tip = (tpl or {}).get("tip", "")
                y = 52 + r * 80
                cv.create_rectangle(PAD, y, R, y + 72, fill=CARD_BG,
                                    outline=CARD_OUT, tags=tag0)
                logo_char = (name[0] if name else "A").upper()
                logo_img = ImageTk.PhotoImage(make_logo_img(
                    logo_char, color, max(2, int(LOGO_SIZE * UI_SCALE * self._zoom))))
                self._logo_imgs.append(logo_img)
                cv.create_image(PAD + 12, y + (72 - LOGO_SIZE) // 2,
                                image=logo_img, anchor="nw", tags=tag0)
                cv.create_text(PAD + 56, y + 24, text=name, anchor="w",
                               fill=FG_W, font=(FONT, 13, "bold"), tags=tag0)
                cv.create_text(PAD + 56, y + 48, text=tip or "自定义 API",
                               anchor="w", fill=FG_DIM, font=(FONT, 8), tags=tag0)
                big = cv.create_text(R - 20, y + 24, text="", anchor="e",
                                     fill=FG_W, font=(MONO, 15, "bold"), tags=tag0)
                subtext = cv.create_text(R - 20, y + 50, text="", anchor="e",
                                         fill=FG_DIM, font=(FONT, 9), tags=tag0)
                self._api_dynamic.append({"sub": s, "big": big, "subtext": subtext})


    # ---------- 页面事件绑定（删除重建后重新绑定） ----------
    def _bind_page_events(self):
        cv = self.canvas
        cv.tag_bind("close", "<Button-1>", lambda e: self._hide_to_tray())
        cv.tag_bind("pin", "<Button-1>", lambda e: self.toggle_topmost())
        cv.tag_bind("pin", "<Enter>", lambda e: self._paint_pin(True))
        cv.tag_bind("pin", "<Leave>", lambda e: self._paint_pin(False))
        cv.tag_bind("zoom", "<Button-1>", lambda e: self.toggle_zoom())
        cv.tag_bind("zoom", "<Enter>", lambda e: self._paint_zoom_btn(True))
        cv.tag_bind("zoom", "<Leave>", lambda e: self._paint_zoom_btn(False))
        cv.tag_bind("gear", "<Button-1>", lambda e: self.open_web_settings())
        cv.tag_bind("prev", "<Button-1>", lambda e: self.prev_page())
        cv.tag_bind("next", "<Button-1>", lambda e: self.next_page())
        cv.tag_bind("page_num", "<Button-1>", self._on_page_num)
        cv.tag_bind("sync", "<Button-1>", lambda e: self.sync_reset_time())
        cv.tag_bind("week_sync", "<Button-1>", lambda e: self.sync_reset_date())
        cv.tag_bind("close", "<Enter>", lambda e: cv.itemconfig("close", fill=FG_W))
        cv.tag_bind("close", "<Leave>", lambda e: cv.itemconfig("close", fill=FG_DIM))
        cv.tag_bind("pin", "<Enter>", lambda e: cv.itemconfig("pin", fill=FG_W))
        cv.tag_bind("pin", "<Leave>", lambda e: self._paint_pin())
        cv.tag_bind("gear", "<Enter>",
                    lambda e: cv.itemconfig("gear", state="active"))
        cv.tag_bind("gear", "<Leave>",
                    lambda e: cv.itemconfig("gear", state="normal"))
        cv.tag_bind("sync", "<Enter>",
                    lambda e: cv.itemconfig(self.btn_sync, fill=BTN_HOV))
        cv.tag_bind("sync", "<Leave>",
                    lambda e: cv.itemconfig(self.btn_sync, fill=BTN_BG))
        cv.tag_bind("week_sync", "<Enter>",
                    lambda e: cv.itemconfig(self.btn_week, fill=BTN_HOV))
        cv.tag_bind("week_sync", "<Leave>",
                    lambda e: cv.itemconfig(self.btn_week, fill=BTN_BG))

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
        m.add_command(label="打开设置（网页）", command=self.open_web_settings)
        m.add_command(label="下一页", command=self.next_page)
        m.add_separator()
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

    def toggle_gpt_sound_menu(self):
        self.cfg["gpt_sound"] = not self.cfg.get("gpt_sound", False)
        self.save_cfg()

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
        self.cfg["topmost"] = bool(self.attributes("-topmost"))
        self._paint_pin()
        self.save_cfg()

    def _paint_pin(self, hover=False):
        top = bool(self.attributes("-topmost"))
        self.canvas.itemconfig("pin", text="置顶：" + ("开" if top else "关"),
                               fill=ACC_C if top else FG_DIM)
        if hover and not top:
            self.canvas.itemconfig("pinbg", image=self._pin_bg_hover)
        else:
            self.canvas.itemconfig("pinbg",
                                   image=self._pin_bg_on if top else self._pin_bg_off)

    # ---------- UI 缩放（1× / 1.5×） ----------
    def toggle_zoom(self):
        self._zoom = 1.5 if abs(self._zoom - 1.0) < 1e-9 else 1.0
        self._apply_zoom()
        self.save_cfg()

    def _paint_zoom_btn(self, hover=False):
        big = abs(self._zoom - 1.0) > 1e-9
        self.canvas.itemconfig(
            "zoom", text=("1.5×" if big else "1×"),
            fill=ACC_C if big else FG_DIM)
        if hover and not big:
            self.canvas.itemconfig("zoombg", image=self._zoom_bg_hover)
        else:
            self.canvas.itemconfig("zoombg",
                                   image=self._zoom_bg_on if big else self._zoom_bg_off)

    def _apply_zoom(self):
        """按 self._zoom 重建窗口（基坐标重绘 + 整体缩放 + 位图按有效缩放生成）。"""
        z = self._zoom
        w = int(DESIGN_W * UI_SCALE * z)
        h = int(DESIGN_H * UI_SCALE_H * z)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = self.winfo_x(), self.winfo_y()
        if x + w > sw:
            x = max(0, sw - w)
        if y + h > sh:
            y = max(0, sh - h)
        self.canvas.configure(width=w, height=h)
        self.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        self.rebuild_pages()          # 基坐标重建（_scale_ui 已做基础缩放）
        if abs(z - 1.0) > 1e-9:
            cv = self.canvas
            cv.scale("all", 0, 0, z, z)
            for item in cv.find_all():
                try:
                    t = cv.type(item)
                except Exception:
                    continue
                if t == "text":
                    try:
                        font = cv.itemcget(item, "font") or ""
                        m = re.search(r"(\d+(?:\.\d+)?)", font)
                        if m:
                            size = max(2, int(round(float(m.group(1)) * z)))
                            cv.itemconfig(item, font=re.sub(
                                r"\d+(?:\.\d+)?", str(size), font, count=1))
                    except Exception:
                        pass
        self._apply_round_rect()
        self._paint_zoom_btn()
        self._paint_pin()

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
            "订阅到期提醒\n"
            "· 设置页（网页）可添加/编辑订阅：按月续费日（每月 N 日）或固定日期到期（YYYY-MM-DD）\n"
            "· 订阅多了自动增加页面，默认每 60 秒自动切换，也可点标题栏 ◀ 页码 ▶ 手动切\n"
            "· 到期前 N 天（默认 3）文字变红，每 3 秒红/浅红交替闪烁提醒\n"
            "· ChatGPT 每月续费日（默认每月 5 日）也按同样规则红字提醒，续费日在设置页可改\n\n"
            "声音提醒：DeepSeek 忙/闲切换到达、GPT 重置到达时响铃\n"
            "托盘：× 仅隐藏，点托盘图标恢复，退出请用菜单/托盘“退出”\n\n"
            "参考项目：github.com/CodeZeno/Claude-Code-Usage-Monitor（MIT）\n"
            "           npmjs.com/package/ds-peak-warningx", parent=self)

    # ---------- 网页设置（本地 HTTP 服务） ----------
    def start_web_settings(self):
        """启动 127.0.0.1 随机端口 HTTP 服务，提供设置网页与配置读写 API。"""

        class _Handler(BaseHTTPRequestHandler):
            app = None

            def log_message(self, *args):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:
                    pass

            def do_GET(self):
                path = urlsplit(self.path).path
                if path in ("/", "/index.html"):
                    html = self.app.settings_html()
                    self._send(200, html.encode("utf-8"),
                               "text/html; charset=utf-8")
                elif path == "/api/config":
                    body = json.dumps(self.app.web_config_snapshot(),
                                      ensure_ascii=False).encode("utf-8")
                    self._send(200, body)
                else:
                    self._send(404, b"not found")

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    if length <= 0 or length > 512 * 1024:
                        raise ValueError
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError
                except Exception:
                    self._send(400, b'{"ok":false,"err":"bad request"}')
                    return
                # 只投递队列，由主线程 tick 应用（tkinter 只能在主线程操作）
                try:
                    self.app.push_web_config(data)
                except Exception:
                    pass
                self._send(200, b'{"ok":true}')

        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            _Handler.app = self
            self._http_port = self._httpd.server_address[1]
            threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        except Exception:
            self._httpd = None
            self._http_port = 0

    def open_web_settings(self):
        if self._httpd is None or self._http_port <= 0:
            self.start_web_settings()
        if self._http_port <= 0:
            messagebox.showwarning("设置", "无法启动本地设置服务，请从源码目录检查环境。")
            return
        try:
            webbrowser.open(f"http://127.0.0.1:{self._http_port}/")
        except Exception:
            pass

    def settings_html(self):
        p = os.path.join(APP_DIR, "settings.html")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ("<!doctype html><meta charset='utf-8'>"
                    "<body style='background:#0e2a63;color:#fff;font-family:sans-serif;"
                    "padding:40px'><h1>设置页</h1>"
                    "<p>未找到 settings.html，请确认它与主程序在同一目录。</p></body>")

    def push_web_config(self, data: dict):
        """HTTP 线程投递配置到队列（主线程 tick 消费）。"""
        try:
            self._web_pending.append(data)
        except Exception:
            pass

    def _drain_web_config(self):
        """主线程消费队列中的网页配置。"""
        while self._web_pending:
            data = self._web_pending.pop(0)
            try:
                self.apply_web_config(data)
            except Exception:
                pass

    def web_config_snapshot(self) -> dict:
        # 注意：此方法在 HTTP 工作线程执行，禁止直接调用 tkinter（如 attributes），
        # 置顶状态从 self.cfg 读取（由主线程 toggle_topmost/apply_web_config 维护）。
        return {
            "topmost": bool(self.cfg.get("topmost", True)),
            "rotate_seconds": int(self.cfg.get("rotate_seconds", DEFAULT_ROTATE_SECONDS)),
            "sub_warn_days": int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS)),
            "ds_sound": bool(self.cfg.get("ds_sound", False)),
            "gpt_sound": bool(self.cfg.get("gpt_sound", False)),
            "sound_kind": self.cfg.get("sound_kind", "meizu"),
            "deepseek_api_key": self.cfg.get("deepseek_api_key", ""),
            "autostart": _autostart_enabled(),
            "gpt_reset_hours": self.counter.window_h,
            "gpt_auto_send": bool(self.cfg.get("gpt_auto_send", False)),
            "gpt_renew_day": int(self.cfg.get("gpt_renew_day", 5) or 5),
            "gpt_reset_ts": self.counter.reset_ts,
            "gpt_week_reset_ts": self.week_counter.reset_ts,
            "ds_override": self.override,
            "subscriptions": self.cfg.get("subscriptions", []),
            "price_table": PRICES,
            "peak_rule": ("高峰：北京时间 周一至周五 09:00-12:00、14:00-18:00；"
                          "其余时间（含周末/节假日）为闲时，价格约为高峰一半"),
            "presets": SUB_PRESETS,
            "sound_labels": SOUND_LABELS,
            "sounds": SOUND_KINDS,
            "api_templates": API_TEMPLATES,
            "api_subs": self.cfg.get("api_subs", []),
        }

    def apply_web_config(self, data: dict):
        """网页 POST 来的配置：校验并应用到运行中的小组件。"""
        if not isinstance(data, dict):
            return
        c = self.cfg
        # --- 通用 ---
        if "rotate_seconds" in data:
            try:
                c["rotate_seconds"] = max(10, min(3600, int(data["rotate_seconds"])))
            except Exception:
                pass
        if "sub_warn_days" in data:
            try:
                c["sub_warn_days"] = max(0, min(30, int(data["sub_warn_days"])))
            except Exception:
                pass
        if "topmost" in data:
            self.attributes("-topmost", bool(data["topmost"]))
            c["topmost"] = bool(data["topmost"])
        if "autostart" in data:
            _set_autostart(bool(data["autostart"]))
        # --- 声音 ---
        if "ds_sound" in data:
            c["ds_sound"] = bool(data["ds_sound"])
        if "gpt_sound" in data:
            c["gpt_sound"] = bool(data["gpt_sound"])
        if "sound_kind" in data and data["sound_kind"] in SOUND_KINDS:
            c["sound_kind"] = data["sound_kind"]
        if "gpt_auto_send" in data:
            c["gpt_auto_send"] = bool(data["gpt_auto_send"])
        if "gpt_renew_day" in data:
            try:
                c["gpt_renew_day"] = max(1, min(31, int(data["gpt_renew_day"])))
            except Exception:
                pass
        # --- ChatGPT 窗口周期 / 重置锚点 ---
        if "gpt_reset_hours" in data:
            try:
                self.counter.window_h = max(0.5, float(data["gpt_reset_hours"]))
                self.counter.window_s = self.counter.window_h * 3600.0
                if self.counter.reset_ts is not None:
                    self.counter.last = self.counter.reset_ts - self.counter.window_s
            except Exception:
                pass
        if "gpt_reset_ts" in data:
            if data["gpt_reset_ts"]:
                try:
                    self.counter.set_reset(float(data["gpt_reset_ts"]))
                except Exception:
                    pass
            else:
                self.counter.clear_reset()
        if "gpt_week_reset_ts" in data:
            if data["gpt_week_reset_ts"]:
                try:
                    self.week_counter.set_reset(float(data["gpt_week_reset_ts"]))
                except Exception:
                    pass
            else:
                self.week_counter.clear_reset()
        # --- 节假日覆盖 ---
        if "ds_override" in data:
            self.override = data["ds_override"] if isinstance(data["ds_override"], dict) else None
        # --- DeepSeek API Key ---
        if "deepseek_api_key" in data:
            key = str(data["deepseek_api_key"]).strip()
            if key:
                c["deepseek_api_key"] = key
            else:
                c.pop("deepseek_api_key", None)
            self._balance = None
            self._balance_fetched_at = 0.0
        # --- 订阅 ---
        if "subscriptions" in data and isinstance(data["subscriptions"], list):
            subs = []
            for s in data["subscriptions"]:
                if not isinstance(s, dict):
                    continue
                name = str(s.get("name", "")).strip()[:20] or "订阅"
                item = {"name": name,
                        "enabled": bool(s.get("enabled", True)),
                        "color": str(s.get("color", "#7ec8ff"))}
                ed = str(s.get("expire_date", "")).strip()
                if ed:
                    try:
                        datetime.strptime(ed, "%Y-%m-%d")
                        item["expire_date"] = ed
                    except Exception:
                        ed = ""
                if not ed:
                    try:
                        item["renew_day"] = max(1, min(31, int(s.get("renew_day", 1))))
                    except Exception:
                        item["renew_day"] = 1
                subs.append(item)
            c["subscriptions"] = subs
        # --- API 订阅 ---
        if "api_subs" in data and isinstance(data["api_subs"], list):
            tpl_ids = {t["id"] for t in API_TEMPLATES}
            apis = []
            for s in data["api_subs"]:
                if not isinstance(s, dict):
                    continue
                tpl = str(s.get("tpl", "")).strip()
                if tpl not in tpl_ids:
                    continue
                tpl_info = api_tpl_by_id(tpl)
                item = {"tpl": tpl,
                        "name": str(s.get("name", "")).strip()[:24]
                                or (tpl_info["name"] if tpl_info else "API"),
                        "enabled": bool(s.get("enabled", True)),
                        "key": str(s.get("key", "")).strip()}
                man = str(s.get("manual", "")).strip()
                if man.replace(".", "", 1).isdigit():
                    item["manual"] = man
                if s.get("id"):
                    item["id"] = str(s["id"])[:32]
                else:
                    item["id"] = "api_" + str(int(time.time() * 1000) + len(apis))
                apis.append(item)
            c["api_subs"] = apis
            self._api_balance = {}
            self._api_balance_fetched_at = 0.0

        self.save_cfg()
        self.rebuild_pages()      # 页面数量/内容可能变化
        self.tick()
        self._paint_pin()

    # ---------- API 订阅余额/额度查询（各平台官方接口） ----------
    def _fetch_api_balance_http(self, sub):
        """同步调用某平台额度接口（工作线程中执行）。返回 {text, fill, sub} 或 None。"""
        tpl = api_tpl_by_id(sub.get("tpl", ""))
        if not tpl or not tpl.get("balance_url"):
            return None
        key = str(sub.get("key", "")).strip()
        if not key:
            return {"text": "未填 Key", "fill": WARN_RED, "sub": "设置页可配置"}
        try:
            import urllib.request
            req = urllib.request.Request(
                tpl["balance_url"],
                headers={"Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            tid = tpl["id"]
            if tid == "siliconflow":
                d = data.get("data", {}) or {}
                total = float(d.get("totalBalance", 0) or 0)
                gift = d.get("balance", 0)
                chg = d.get("chargeBalance", 0)
                return {"text": f"¥{total:.2f}", "fill": OFF_C,
                        "sub": f"总余额（赠 {gift:g} / 充 {chg:g}）"}
            if tid == "deepseek":
                infos = data.get("balance_infos", []) or []
                total = 0.0
                for i in infos:
                    if i.get("currency") == "CNY":
                        total += float(i.get("total_balance", 0) or 0)
                ok = bool(data.get("is_available", False))
                return {"text": f"¥{total:.2f}", "fill": OFF_C,
                        "sub": "可用" if ok else "不可用"}
            if tid == "minimax":
                if isinstance(data, dict) and ("error" in data
                                               or data.get("code")
                                               or data.get("success") is False):
                    return {"text": "查询失败", "fill": WARN_RED,
                            "sub": "Key 无效或未授权"}
                n = _find_number(data)
                if n is not None:
                    return {"text": f"剩 {float(n):g}", "fill": OFF_C,
                            "sub": "Token Plan 订阅额度"}
                return {"text": "订阅有效", "fill": OFF_C,
                        "sub": "未返回额度数字"}
            # 其它平台通用：递归取第一个数值
            n = _find_number(data)
            if n is not None:
                return {"text": f"{float(n):g}", "fill": OFF_C,
                        "sub": tpl.get("name", "")}
            return {"text": "查询成功", "fill": FG_DIM, "sub": "未解析到额度"}
        except Exception:
            return {"text": "查询失败", "fill": WARN_RED,
                    "sub": "请检查 Key 或网络"}

    def _maybe_refresh_api_balances(self, now_ts):
        """每 15 分钟刷新一次 API 订阅额度（跳过手动登记余额的条目）。"""
        apis = [s for s in self._enabled_api_subs()
                if not str(s.get("manual", "")).strip()]
        if not apis:
            return
        if now_ts - self._api_balance_fetched_at < 900:
            return
        self._api_balance_fetched_at = now_ts

        def work():
            res = {}
            for s in apis:
                try:
                    r = self._fetch_api_balance_http(s)
                    if r:
                        res[s.get("id") or s.get("tpl") or "?"] = r
                except Exception:
                    pass
            self.after(0, lambda: self._apply_api_balances(res))

        threading.Thread(target=work, daemon=True).start()

    def _apply_api_balances(self, res):
        self._api_balance.update(res)
        self.tick()

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
    def _has_warn_sub(self) -> bool:
        """是否存在处于「到期前 N 天」提醒窗口内的订阅或 ChatGPT 续费（含已过期，需提醒处理）。"""
        warn_days = int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS))
        today = datetime.now().date()
        if any(sub_status(s, today)[0] <= warn_days
               for s in self._enabled_subs()):
            return True
        gd = int(self.cfg.get("gpt_renew_day", 5) or 5)
        return (next_renew_date(gd, today) - today).days <= warn_days

    def tick(self):
        now = time.time()
        # --- 应用网页设置（主线程） ---
        self._drain_web_config()
        # --- 托盘事件（左键切换 / 右键退出） ---
        self._drain_tray()
        self._maybe_refresh_api_balances(now)
        # --- 页面轮播：每隔 rotate_seconds 秒自动切到下一页 ---
        if (self._page_count > 1 and
                now - self._last_switch >= float(self.cfg.get("rotate_seconds",
                                                              DEFAULT_ROTATE_SECONDS))):
            self._last_switch = now
            self.next_page()
        # --- 红字闪烁：每 3 秒切换红/浅红 ---
        if self._has_warn_sub() and now - self._last_flash >= FLASH_SECONDS:
            self._flash_on = not self._flash_on
            self._last_flash = now
        self._paint_current()
        self.after(1000, self.tick)

    def _paint_current(self):
        if self.page_idx == 0:
            self._paint_main()
        elif self.page_idx <= self._sub_pages:
            self._paint_sub_page()
        else:
            self._paint_api_page()
        self._paint_page_indicator()

    def _paint_sub_page(self):
        today = datetime.now().date()
        warn_days = int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS))
        cv = self.canvas
        for it in self._sub_dynamic:
            s = it["sub"]
            days, nxt = sub_status(s, today)
            warn = days <= warn_days
            fill = (WARN_RED_LIGHT if self._flash_on else WARN_RED) if warn else FG_W
            if days > 0:
                text = f"剩 {days} 天"
            elif days == 0:
                text = "今天到期"
            else:
                text = "已到期"
            if s.get("expire_date"):
                subtext = f"到期日 {nxt.month}月{nxt.day}日"
            else:
                subtext = f"下次续费 {nxt.month}月{nxt.day}日"
            cv.itemconfig(it["big"], text=text, fill=fill)
            cv.itemconfig(it["subtext"], text=subtext)

    def _paint_api_page(self):
        cv = self.canvas
        for it in self._api_dynamic:
            s = it["sub"]
            manual = str(s.get("manual", "")).strip()
            if manual:
                cv.itemconfig(it["big"], text="¥" + manual, fill=OFF_C)
                cv.itemconfig(it["subtext"], text="手动登记余额", fill=FG_DIM)
                continue
            key_id = s.get("id") or s.get("tpl") or ""
            bal = self._api_balance.get(key_id)
            if bal and bal.get("text"):
                cv.itemconfig(it["big"], text=bal["text"],
                              fill=bal.get("fill", FG_W))
                cv.itemconfig(it["subtext"], text=bal.get("sub", ""), fill=FG_DIM)
            else:
                tpl = api_tpl_by_id(s.get("tpl", ""))
                if tpl and tpl.get("balance_url"):
                    cv.itemconfig(it["big"], text="查询中…", fill=FG_DIM)
                    cv.itemconfig(it["subtext"], text="每 15 分钟自动刷新", fill=FG_DIM)
                else:
                    cv.itemconfig(it["big"], text="控制台查看", fill=FG_DIM)
                    cv.itemconfig(it["subtext"],
                                  text="该平台无 API Key 直查接口", fill=FG_DIM)

    def _paint_main(self):
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
            cv.itemconfig(self.ds_sub_r, text="")
        else:
            phase = "忙时" if peak else "闲时"
            cv.itemconfig(self.ds_main,
                          text=f"距{phase}结束 {fmt_hm(t1)}",
                          fill=PEAK_C if peak else OFF_C)
            cv.itemconfig(self.ds_remain,
                          text="剩 " + fmt_until(t1 - now),
                          fill=PEAK_C if peak else OFF_C)
            # 下一段忙时（左）/ 下一段闲时（右对齐）两个时段信息
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
                                  text=f"下一段忙时 {fmt_range(busy_a, busy_b)}")
                    cv.itemconfig(self.ds_sub_r,
                                  text=f"下一段闲时 {fmt_range(off_a, off_b)}")
                else:
                    cv.itemconfig(self.ds_sub, text="")
                    cv.itemconfig(self.ds_sub_r, text="")
            else:
                cv.itemconfig(self.ds_sub, text="")
                cv.itemconfig(self.ds_sub_r, text="")

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

        # --- ChatGPT 每月续费倒计时（到期提醒，可红闪） ---
        gd = int(self.cfg.get("gpt_renew_day", 5) or 5)
        g_nxt = next_renew_date(gd, now.date())
        g_days = (g_nxt - now.date()).days
        warn_days = int(self.cfg.get("sub_warn_days", DEFAULT_WARN_DAYS))
        if g_days > warn_days:
            cv.itemconfig(self.gpt_sub, text=f"每月{gd}日续费 · 下次 {g_nxt.month}月{g_nxt.day}日",
                          fill=FG_DIM)
        elif g_days == 0:
            cv.itemconfig(self.gpt_sub, text="今天续费", fill=WARN_RED)
        else:
            cv.itemconfig(self.gpt_sub, text=f"续费提醒 剩 {g_days} 天",
                          fill=WARN_RED_LIGHT if self._flash_on else WARN_RED)

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
                sub = f"下一段忙时 {fmt_range(t1, t2)} ｜ 下一段闲时 {fmt_range(t2, t3)}"
            else:
                sub = f"下一段忙时 {fmt_range(t2, t3)} ｜ 下一段闲时 {fmt_range(t1, t2)}"
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

        # --- 订阅逻辑自检 ---
        d0 = date_obj.today()
        r1 = next_renew_date(1, d0)
        lines.append(f"[selftest] sub: renew_day=1 -> 下次 {r1:%Y-%m-%d} "
                     f"剩 {sub_status({'renew_day': 1}, d0)[0]} 天 (expect >=0) "
                     f"{'OK' if sub_status({'renew_day': 1}, d0)[0] >= 0 else 'FAIL'}")
        feb = date_obj(2026, 2, 10)
        got_clamp = next_renew_date(31, feb)
        ok_clamp = got_clamp == date_obj(2026, 2, 28)
        lines.append(f"[selftest] sub: 2月31日截断 -> {got_clamp:%Y-%m-%d} "
                     f"{'OK' if ok_clamp else 'FAIL'}")
        same = next_renew_date(10, date_obj(2026, 9, 10))
        lines.append(f"[selftest] sub: 续费日当天 -> {same:%Y-%m-%d} 剩 0 天 "
                     f"{'OK' if same == date_obj(2026, 9, 10) else 'FAIL'}")
        d_fix = date_obj(2026, 9, 22)
        d_fix_ok = sub_status({"expire_date": "2026-09-25"}, d_fix) == (3, date_obj(2026, 9, 25))
        lines.append(f"[selftest] sub: 固定日期 09-25 剩 {sub_status({'expire_date': '2026-09-25'}, d_fix)[0]} 天 "
                     f"(expect 3) {'OK' if d_fix_ok else 'FAIL'}")
        d_exp_ok = sub_status({"expire_date": "2026-09-20"}, d_fix)[0] == -2
        lines.append(f"[selftest] sub: 已过期 -> {sub_status({'expire_date': '2026-09-20'}, d_fix)[0]} 天 "
                     f"(expect -2) {'OK' if d_exp_ok else 'FAIL'}")
        n_subs = len(self._enabled_subs())
        n_pages = max(0, (n_subs + SUB_PER_PAGE - 1) // SUB_PER_PAGE)
        lines.append(f"[selftest] sub: 启用订阅 {n_subs} 个 -> 订阅页 {n_pages} 页 "
                     f"(总页数 {self._page_count})")
        gd = int(self.cfg.get("gpt_renew_day", 5) or 5)
        g_nxt = next_renew_date(gd, d0)
        lines.append(f"[selftest] gpt_renew: 每月 {gd} 日 -> 下次 {g_nxt:%Y-%m-%d} "
                     f"剩 {(g_nxt - d0).days} 天")
        lines.append(f"[selftest] nav: prev={len(self._nav_prev)} "
                     f"next={len(self._nav_next)} "
                     f"nums={sum(len(v) for v in self._nav_nums.values())} "
                     f"expect={self._page_count}")

        win = self._find_chatgpt_window()
        lines.append(f"[selftest] chatgpt window found: {len(win)} "
                     f"(selftest 不发送文本)")
        lines.append(f"[selftest] UI OK {self.winfo_width()}x{self.winfo_height()} "
                     f"bg={self._bg_img.width()}x{self._bg_img.height()}")
        lines.append(f"[selftest] web settings port={self._http_port} "
                     f"started={self._httpd is not None}")
        lines.append(f"[selftest] pages={self._page_count} current={self.page_idx} "
                     f"warn_days={self.cfg.get('sub_warn_days')} "
                     f"rotate={self.cfg.get('rotate_seconds')}s "
                     f"gpt_renew_day={self.cfg.get('gpt_renew_day', 5)}")
        return "\n".join(lines)

    # ---------- 预览截图（验证用） ----------
    def start_preview(self, outdir: str):
        try:
            os.makedirs(outdir, exist_ok=True)
        except Exception:
            pass
        self._preview_out = outdir
        self._preview_queue = list(range(self._page_count))
        # 预览截图：固定到屏幕左上角并置顶，避免被其它窗口遮挡
        self.geometry("+0+0")
        self.attributes("-topmost", True)
        self.update_idletasks()
        self.after(900, self._preview_capture)

    def _preview_capture(self):
        try:
            import PIL.ImageGrab as ImageGrab
            self.show_page(self.page_idx)
            self._paint_current()
            self.update_idletasks()
            self.update()
            x, y = self.winfo_rootx(), self.winfo_rooty()
            img = ImageGrab.grab(bbox=(int(x), int(y),
                                       int(x) + int(DESIGN_W * UI_SCALE * self._zoom),
                                       int(y) + int(DESIGN_H * UI_SCALE_H * self._zoom)))
            img.save(os.path.join(self._preview_out, f"page{self.page_idx}.png"))
            self._preview_queue.pop(0)
        except Exception as e:
            print("preview error:", e, flush=True)
            self.destroy()
            return
        if self._preview_queue:
            self.next_page()
            self.after(500, self._preview_capture)
        else:
            self.destroy()


def main():
    argv = sys.argv
    app = Widget()
    if "--selftest" in argv:
        def _report():
            print(app.selftest_report(), flush=True)
            app.destroy()
        app.after(1500, _report)
    elif "--preview" in argv:
        outdir = "preview"
        if len(argv) > argv.index("--preview") + 1:
            outdir = argv[argv.index("--preview") + 1]
        if "--zoom15" in argv:
            app._zoom = 1.5
            app._apply_zoom()
        app.start_preview(outdir)
    app.mainloop()


if __name__ == "__main__":
    main()
