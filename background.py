"""
tameiki/background.py — 背景処理
素材の読み込み・9:16トリミング・Ken Burns
"""
import math
from PIL import Image
from config import W, H
from easing import ease_organic, random_jitter, clamp


def prepare_bg(path):
    """
    背景画像を読み込み、9:16にトリミング・リサイズ。
    縦長・横長・正方形いずれでも中央基準で安全に処理。
    """
    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    target_ratio = H / W   # 1.777...
    current_ratio = ih / iw

    if current_ratio > target_ratio:
        # 縦長すぎ → 上下クロップ（中央基準）
        new_h = int(iw * target_ratio)
        top   = (ih - new_h) // 2
        img   = img.crop((0, top, iw, top + new_h))
    elif current_ratio < target_ratio:
        # 横長すぎ → 左右クロップ（中央基準）
        new_w = int(ih / target_ratio)
        left  = (iw - new_w) // 2
        img   = img.crop((left, 0, left + new_w, ih))

    # 最小サイズチェック
    cw, ch = img.size
    if cw < W * 0.5 or ch < H * 0.5:
        print(f"警告: 素材が小さすぎます ({cw}x{ch}) → 引き伸ばして使用します")

    return img.resize((W, H), Image.LANCZOS)


def ken_burns(base_img, fi, total_frames, seed=0):
    """
    Ken Burnsエフェクト（ゆっくりズームイン）。
    ズーム量・パン方向にランダムな揺らぎを加えて有機的に。
    毎回違う動きになるが、同じseedなら同じ動き。
    """
    from config import KB_ZOOM_BASE, KB_ZOOM_JITTER, KB_PAN_JITTER

    t = fi / total_frames

    # ズーム量にランダム揺らぎ
    zoom_amount = KB_ZOOM_BASE + random_jitter(seed, KB_ZOOM_JITTER, seed=1)
    zoom = 1.0 + ease_organic(t, seed=seed) * zoom_amount

    nw = int(W / zoom)
    nh = int(H / zoom)

    # パン方向のランダム揺らぎ
    pan_y = random_jitter(seed, KB_PAN_JITTER, seed=2)
    py    = int((1 - t) * (20 + pan_y))

    left = (W - nw) // 2
    top  = max(0, min(py + (H - nh) // 2, H - nh))

    return base_img.crop((left, top, left + nw, top + nh)).resize(
        (W, H), Image.LANCZOS
    )
