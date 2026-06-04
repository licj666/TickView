"""生成 TickView 应用图标: 深色圆角底 + 上扬走势线, 导出 icon.png / icon.ico / icon.icns.

仅在需要重做图标时运行: python assets/make_icon.py
依赖 Pillow (pip install pillow), 与程序运行/打包无关。
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

BG_TOP = (32, 38, 46)       # 圆角底渐变上
BG_BOTTOM = (20, 23, 28)    # 渐变下
LINE = (46, 196, 126)       # 走势线(上扬绿)
FILL = (46, 196, 126, 70)   # 走势线下方半透明填充
DOT = (235, 240, 238)       # 末端圆点


def _gradient(size, top, bottom):
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=radius, fill=255)
    return mask


def render(size):
    """在 4x 超采样画布上绘制后缩放, 得到平滑边缘的 size×size RGBA 图。"""
    ss = 4
    S = size * ss
    base = _gradient(S, BG_TOP, BG_BOTTOM)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(base, (0, 0), _rounded_mask(S, int(S * 0.22)))

    draw = ImageDraw.Draw(icon)
    pts01 = [(0.15, 0.66), (0.33, 0.52), (0.50, 0.605),
             (0.68, 0.37), (0.85, 0.235)]
    pts = [(x * S, y * S) for x, y in pts01]

    # 走势线下方填充(到基线)
    baseline = 0.82 * S
    poly = pts + [(pts[-1][0], baseline), (pts[0][0], baseline)]
    fill_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(fill_layer).polygon(poly, fill=FILL)
    icon = Image.alpha_composite(icon, fill_layer)
    draw = ImageDraw.Draw(icon)

    # 折线(粗、圆角拐点用圆点补齐)
    w = int(S * 0.045)
    draw.line(pts, fill=LINE, width=w, joint="curve")
    for x, y in pts:
        r = w / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=LINE)

    # 末端箭头(指向右上)
    ex, ey = pts[-1]
    a = S * 0.085
    draw.polygon([(ex + a * 0.55, ey - a * 0.55),
                  (ex - a * 0.30, ey - a * 0.62),
                  (ex + a * 0.62, ey + a * 0.28)], fill=LINE)
    # 末端圆点
    r = S * 0.032
    draw.ellipse((ex - r, ey - r, ex + r, ey + r), fill=DOT)

    return icon.resize((size, size), Image.LANCZOS)


def main():
    master = render(1024)
    master.save(os.path.join(HERE, "icon.png"))

    ico_sizes = [16, 32, 48, 64, 128, 256]
    master.save(os.path.join(HERE, "icon.ico"),
                format="ICO", sizes=[(s, s) for s in ico_sizes])

    # ICNS 需要方图, Pillow 会自动切出各档尺寸
    master.save(os.path.join(HERE, "icon.icns"), format="ICNS")
    print("已生成: icon.png / icon.ico / icon.icns ->", HERE)


if __name__ == "__main__":
    main()
