# -*- coding: utf-8 -*-
"""生成 28x28 白色圆底品牌图标徽章（供小组件使用）"""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")


def round_badge(icon_path, out_path, size=28, pad=4):
    icon = Image.open(icon_path).convert("RGBA")
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    d.ellipse((0, 0, size - 1, size - 1), fill=(255, 255, 255, 255))
    icon = icon.resize((size - pad * 2, size - pad * 2), Image.LANCZOS)
    bg.alpha_composite(icon, (pad, pad))
    bg.save(out_path)
    print("saved", out_path, bg.size)


round_badge(os.path.join(ASSETS, "deepseek_3.ico"),
            os.path.join(ASSETS, "deepseek_icon.png"))
round_badge(os.path.join(ASSETS, "chatgpt_3.ico"),
            os.path.join(ASSETS, "chatgpt_icon.png"))
