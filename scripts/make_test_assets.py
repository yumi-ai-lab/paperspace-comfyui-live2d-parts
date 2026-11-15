#!/usr/bin/env python3
"""動作確認用の合成テスト画像を作る(著作物を含まない単純な図形)。

    python scripts/make_test_assets.py

test_assets/ に次の3枚を出力:
  live2d_test_image.png    透明背景のRGBA。顔の上に前髪が被っている簡易キャラ
  live2d_test_mask.png     白=描き直す範囲(前髪で隠れた額のあたり)
  live2d_test_standin.png  GPUなし合成テスト用の「生成結果の代役」(わざと別サイズ)
"""
import pathlib
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent.parent / "test_assets"
OUT.mkdir(exist_ok=True)
W, H = 1200, 1600

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((250, 150, 950, 950), fill=(92, 62, 48, 255))                      # 後ろ髪
d.rounded_rectangle((500, 900, 700, 1150), 40, fill=(247, 214, 196, 255))    # 首
d.rounded_rectangle((300, 1100, 900, 1600), 80, fill=(70, 110, 180, 255))    # 服
d.ellipse((350, 300, 850, 980), fill=(250, 222, 205, 255), outline=(60, 40, 35, 255), width=6)  # 顔
for cx in (480, 720):                                                        # 目
    d.ellipse((cx - 55, 610, cx + 55, 700), fill=(255, 255, 255, 255), outline=(40, 30, 30, 255), width=5)
    d.ellipse((cx - 28, 622, cx + 28, 692), fill=(60, 120, 170, 255))
d.arc((540, 780, 660, 850), 20, 160, fill=(150, 60, 60, 255), width=6)       # 口
d.pieslice((300, 180, 900, 760), 180, 360, fill=(110, 74, 56, 255), outline=(60, 40, 35, 255), width=6)  # 前髪
for x in (420, 540, 660, 780):
    d.polygon([(x - 70, 460), (x + 70, 460), (x, 600)], fill=(110, 74, 56, 255))
img.save(OUT / "live2d_test_image.png")

mask = Image.new("RGB", (W, H), (0, 0, 0))
ImageDraw.Draw(mask).rounded_rectangle((380, 330, 820, 600), 60, fill=(255, 255, 255))
mask.save(OUT / "live2d_test_mask.png")

standin = Image.new("RGB", (896, 1184), (255, 0, 255))
sd = ImageDraw.Draw(standin)
for y in range(0, 1184, 32):
    sd.line((0, y, 896, y), fill=(0, 255, 0), width=4)
standin.save(OUT / "live2d_test_standin.png")
print("wrote", sorted(p.name for p in OUT.glob("*.png")))
