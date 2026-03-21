"""
tameiki/filters.py — フィルター処理エンジン
全20種のフィルターと映像エフェクトを管理
"""
import math
import numpy as np
from PIL import Image, ImageFilter
from config import W, H, FILTERS
from easing import random_jitter, clamp


# ===== ビネット =====
_vignette_cache = {}

def make_vignette(strength=190, seed=0):
    key = (strength, seed)
    if key in _vignette_cache:
        return _vignette_cache[key]
    cx = W / 2 + random_jitter(seed, 12, seed=1)
    cy = H / 2 + random_jitter(seed, 20, seed=2)
    rx = W / 2 * (0.93 + random_jitter(seed, 0.04, seed=3))
    ry = H / 2 * (0.91 + random_jitter(seed, 0.04, seed=4))
    xs = (np.arange(W, dtype=np.float32) - cx) / rx
    ys = (np.arange(H, dtype=np.float32) - cy) / ry
    xx, yy = np.meshgrid(xs, ys)
    d   = np.sqrt(xx * xx + yy * yy)
    arr = np.clip((d - 0.40) / 0.85, 0.0, 1.0)
    result = (arr * strength).astype(np.uint8)
    _vignette_cache[key] = result
    return result


def apply_vignette(img_arr, strength=190, dark=(8, 5, 3), seed=0):
    h, w = img_arr.shape[:2]
    cx = w / 2 + random_jitter(seed, 12, seed=1)
    cy = h / 2 + random_jitter(seed, 20, seed=2)
    rx = w / 2 * (0.93 + random_jitter(seed, 0.04, seed=3))
    ry = h / 2 * (0.91 + random_jitter(seed, 0.04, seed=4))
    xs = (np.arange(w, dtype=np.float32) - cx) / rx
    ys = (np.arange(h, dtype=np.float32) - cy) / ry
    xx, yy = np.meshgrid(xs, ys)
    d   = np.sqrt(xx * xx + yy * yy)
    arr = np.clip((d - 0.40) / 0.85, 0.0, 1.0)
    vign = (arr * strength).astype(np.uint8)
    v = vign[:, :, np.newaxis] / 255.0
    dark_arr = np.array(dark, dtype=np.float32)
    result = img_arr * (1 - v) + dark_arr * v
    return np.clip(result, 0, 255).astype(np.uint8)


# ===== カラーグレーディング =====
def apply_color_matrix(arr, matrix, contrast=1.0, lift=0.0):
    f = arr.astype(np.float32) / 255.0
    if matrix is not None:
        f[:, :, 0] = np.clip(f[:, :, 0] * matrix["R"][0] + matrix["R"][1], 0, 1)
        f[:, :, 1] = np.clip(f[:, :, 1] * matrix["G"][0] + matrix["G"][1], 0, 1)
        f[:, :, 2] = np.clip(f[:, :, 2] * matrix["B"][0] + matrix["B"][1], 0, 1)
    if contrast != 1.0:
        f = np.clip((f - 0.5) * contrast + 0.5, 0, 1)
    if lift > 0:
        f = np.clip(f * (1 - lift) + lift, 0, 1)
    return (f * 255).astype(np.uint8)


def apply_monochrome(arr, contrast=1.15):
    f = arr.astype(np.float32) / 255.0
    gray = f[:, :, 0] * 0.299 + f[:, :, 1] * 0.587 + f[:, :, 2] * 0.114
    gray = np.clip((gray - 0.5) * contrast + 0.5, 0, 1)
    result = np.stack([gray, gray, gray], axis=2)
    return (result * 255).astype(np.uint8)


# ===== フィルム粒子 =====
def apply_grain(arr, strength=14, fi=0):
    actual_strength = strength * (1.0 + random_jitter(fi, 0.15, seed=99))
    rng = np.random.RandomState(fi % 97 + int(actual_strength))
    noise = rng.randint(
        -int(actual_strength), int(actual_strength) + 1,
        arr.shape, dtype=np.int16
    )
    return np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# ===== クロマティックアベレーション =====
def apply_chroma_aberration(img, strength=1.5, fi=0):
    if strength <= 0:
        return img
    arr = np.array(img)
    actual = strength * (1.0 + random_jitter(fi, 0.2, seed=77))
    shift = int(actual)
    if shift < 1:
        return img
    result = arr.copy()
    if shift > 0:
        result[:, shift:, 0] = arr[:, :-shift, 0]
        result[:, :shift, 0] = arr[:, 0:1, 0]
    if shift > 0:
        result[:, :-shift, 2] = arr[:, shift:, 2]
        result[:, -shift:, 2] = arr[:, -1:, 2]
    return Image.fromarray(result)


# ===== ブルーム =====
def apply_bloom(img, strength=0.15, fi=0):
    if strength <= 0:
        return img
    actual = strength * (1.0 + random_jitter(fi, 0.12, seed=55))
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    bright = np.clip(arr - 180, 0, 75) / 75.0
    small  = Image.fromarray((bright * 255).astype(np.uint8)).resize((w//4, h//4), Image.BILINEAR)
    blurred = small.filter(ImageFilter.GaussianBlur(radius=5)).resize((w, h), Image.BILINEAR)
    blur_arr = np.array(blurred).astype(np.float32) / 255.0
    return Image.fromarray(np.clip(arr + blur_arr * actual * 80, 0, 255).astype(np.uint8))


# ===== ハレーション =====
def apply_halation(img, strength=0.12, fi=0):
    if strength <= 0:
        return img
    actual = strength * (1.0 + random_jitter(fi, 0.15, seed=44))
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    bright_r = np.clip(arr[:, :, 0] - 160, 0, 95) / 95.0
    small    = Image.fromarray((bright_r * 255).astype(np.uint8)).resize((w//4, h//4), Image.BILINEAR)
    halo     = small.filter(ImageFilter.GaussianBlur(radius=8)).resize((w, h), Image.BILINEAR)
    halo_arr = np.array(halo).astype(np.float32) / 255.0
    result = arr.copy()
    result[:, :, 0] = np.clip(arr[:, :, 0] + halo_arr * actual * 60, 0, 255)
    result[:, :, 1] = np.clip(arr[:, :, 1] + halo_arr * actual * 25, 0, 255)
    result[:, :, 2] = np.clip(arr[:, :, 2] + halo_arr * actual * 5,  0, 255)
    return Image.fromarray(result.astype(np.uint8))


# ===== ソフトフォーカス =====
def apply_soft_focus(img, strength=0.3):
    if strength <= 0:
        return img
    blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
    arr_orig = np.array(img).astype(np.float32)
    arr_blur = np.array(blurred).astype(np.float32)
    result = arr_orig * (1 - strength) + arr_blur * strength
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== 霞み =====
def apply_mist(img, strength=0.25):
    if strength <= 0:
        return img
    arr = np.array(img).astype(np.float32)
    white = np.full_like(arr, 240.0)
    result = arr * (1 - strength) + white * strength
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== 退色処理 =====
def apply_fade(img, strength=0.2):
    if strength <= 0:
        return img
    arr = np.array(img).astype(np.float32)
    gray = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
    gray = gray[:, :, np.newaxis]
    desaturated = arr * (1 - strength) + gray * strength
    desaturated[:, :, 0] = np.clip(desaturated[:, :, 0] + 8, 0, 255)
    desaturated[:, :, 2] = np.clip(desaturated[:, :, 2] - 12, 0, 255)
    return Image.fromarray(np.clip(desaturated, 0, 255).astype(np.uint8))


# ===== フィルムバーン（端） =====
def apply_burn_edges(img, fi=0):
    arr = np.array(img).astype(np.float32)
    rng = np.random.RandomState(fi % 47)
    for edge in ['top', 'bottom']:
        height = rng.randint(2, 8)
        opacity = rng.uniform(0.3, 0.7)
        warm = np.array([220, 140, 60], dtype=np.float32)
        if edge == 'top':
            region = arr[:height, :, :]
            arr[:height, :, :] = region * (1 - opacity) + warm * opacity
        else:
            region = arr[-height:, :, :]
            arr[-height:, :, :] = region * (1 - opacity) + warm * opacity
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ===== フィルムバーン（内部有機焼け）★強化 =====
def apply_film_burn_organic(img, fi=0, strength=0.6):
    """
    フレーム内に有機的な焼け模様を生成。
    不均一な焦げ・溶け感を複数のランダムな楕円マスクで表現。
    """
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng = np.random.RandomState(fi % 61 + 7)

    # 焼けマスク（複数の楕円を重ねる）
    burn_mask = np.zeros((h, w), dtype=np.float32)
    num_spots = rng.randint(2, 5)
    for _ in range(num_spots):
        # 端寄りにランダムな焼けの中心
        cx = rng.choice([
            rng.randint(0, w // 4),
            rng.randint(w * 3 // 4, w)
        ])
        cy = rng.choice([
            rng.randint(0, h // 5),
            rng.randint(h * 4 // 5, h)
        ])
        rx = rng.randint(w // 6, w // 2)
        ry = rng.randint(h // 8, h // 3)

        xs = (np.arange(w, dtype=np.float32) - cx) / rx
        ys = (np.arange(h, dtype=np.float32) - cy) / ry
        xx, yy = np.meshgrid(xs, ys)
        d = np.sqrt(xx * xx + yy * yy)
        spot = np.clip(1.0 - d, 0, 1) ** 1.5
        burn_mask = np.maximum(burn_mask, spot)

    burn_mask = (burn_mask * strength * rng.uniform(0.5, 1.0))[:, :, np.newaxis]

    # 焼け色：橙〜赤褐色
    burn_color = np.array([
        rng.uniform(180, 230),
        rng.uniform(80, 130),
        rng.uniform(20, 60)
    ], dtype=np.float32)

    result = arr * (1 - burn_mask) + burn_color * burn_mask
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== VHSスキャンライン =====
def apply_scanline(img, fi=0):
    import random
    rng = random.Random(fi * 13)
    if rng.random() > 0.033:
        return img
    arr = np.array(img).astype(np.float32)
    y = rng.randint(0, H - 3)
    h = rng.randint(1, 3)
    brightness = rng.uniform(0.4, 0.9)
    arr[y:y + h, :, :] = arr[y:y + h, :, :] * brightness
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ===== VHSゲートグリッチ =====
def apply_gate_glitch(img, fi=0):
    import random
    rng = random.Random(fi * 31)
    if rng.random() > 0.017:
        return img
    arr = np.array(img)
    y = rng.randint(H // 4, H * 3 // 4)
    shift = rng.randint(3, 12)
    direction = rng.choice([-1, 1])
    h = rng.randint(2, 6)
    shifted = np.roll(arr[y:y + h, :, :], shift * direction, axis=1)
    arr[y:y + h, :, :] = shifted
    return Image.fromarray(arr)


# ===== VHS輝度ノイズ帯 ★新規 =====
def apply_vhs_noise_band(img, fi=0, strength=0.35):
    """
    テープ劣化の輝度ノイズ帯。横に走る明暗のムラ。
    常時・複数帯・フレームごとに位置が微妙に変わる。
    """
    import random
    rng = random.Random(fi * 7 + 3)
    arr = np.array(img).astype(np.float32)
    num_bands = rng.randint(1, 3)
    for _ in range(num_bands):
        y = rng.randint(0, H - 1)
        band_h = rng.randint(1, 4)
        bright = rng.uniform(1.0 - strength, 1.0 + strength * 0.5)
        y2 = min(y + band_h, H)
        arr[y:y2, :, :] = np.clip(arr[y:y2, :, :] * bright, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


# ===== VHSカラーブリード ★新規 =====
def apply_vhs_color_bleed(img, fi=0, strength=4):
    """
    VHSテープの色にじみ。
    輝度と色差を分離し、色差チャンネルだけ右方向にぼかしてにじませる。
    """
    arr = np.array(img).astype(np.float32)
    actual = int(strength * (1.0 + random_jitter(fi, 0.2, seed=88)))
    if actual < 1:
        return img

    # R・Gチャンネルを右方向に少しだけにじませる
    result = arr.copy()
    for ch, s in [(0, actual), (1, actual // 2)]:
        shifted = np.roll(arr[:, :, ch], s, axis=1)
        shifted[:, :s] = arr[:, 0:1, ch]
        result[:, :, ch] = arr[:, :, ch] * 0.7 + shifted * 0.3

    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== フリッカー ★新規 =====
def apply_flicker(arr, fi=0, strength=0.06):
    """
    映写機・古いフィルムの明滅。
    フレームごとに輝度を微妙にランダム変調。
    """
    import random
    rng = random.Random(fi * 17 + 5)
    # 低周波フリッカー（映写機のゆっくりした揺れ）
    slow = 1.0 + math.sin(fi * 0.15) * strength * 0.5
    # 高周波フリッカー（フィルムの傷・ごく稀に大きく跳ねる）
    fast = 1.0
    if rng.random() < 0.04:
        fast = rng.uniform(1.0 - strength * 3, 1.0 + strength * 2)
    else:
        fast = 1.0 + rng.uniform(-strength * 0.4, strength * 0.4)

    scale = slow * fast
    return np.clip(arr.astype(np.float32) * scale, 0, 255).astype(np.uint8)


# ===== 縦揺れ（映写機） ★新規 =====
def apply_vertical_jitter(img, fi=0):
    """
    映写機のフィルム送りのズレ。ごく稀に画面が縦にわずかにずれる。
    """
    import random
    rng = random.Random(fi * 23 + 11)
    # 約40フレームに1回
    if rng.random() > 0.025:
        return img
    shift = rng.randint(1, 4)
    arr = np.array(img)
    result = np.roll(arr, shift, axis=0)
    # ずれた端は元画像の端で埋める
    if shift > 0:
        result[:shift, :, :] = arr[0:1, :, :]
    return Image.fromarray(result)


# ===== フィルムパーフォレーション（送り穴）★新規 =====
def apply_film_perforation(img, fi=0):
    """
    映写機フィルムの送り穴の影。
    画面左端にごく薄く現れる長方形の影。
    """
    arr = np.array(img).astype(np.float32)
    rng_seed = fi // 12  # 約0.5秒ごとに変化
    import random
    rng = random.Random(rng_seed * 41)

    # 左端に2〜3個の送り穴影
    hole_h = rng.randint(18, 30)
    hole_w = 6
    num_holes = 2
    spacing = H // (num_holes + 1)
    offset = rng.randint(-spacing // 4, spacing // 4)

    opacity = 0.25 + random_jitter(fi, 0.08, seed=19) * 0.1

    for i in range(num_holes):
        y = spacing * (i + 1) + offset - hole_h // 2
        y = max(0, min(H - hole_h, y))
        arr[y:y + hole_h, :hole_w, :] = arr[y:y + hole_h, :hole_w, :] * (1 - opacity)

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ===== 光漏れ ★新規 =====
def apply_light_leak(img, fi=0, strength=0.55):
    """
    フィルムカメラの光漏れ。
    フレームの端（上・右・左のどれか）からオレンジ〜赤の光が染み込む。
    フレームごとに微妙に強度と位置が変わる有機的な揺らぎ。
    """
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng_seed = fi // 48  # 約2秒ごとに変化
    import random
    rng = random.Random(rng_seed * 53 + 7)

    # 光漏れの色（橙〜赤の間でランダム）
    leak_r = rng.uniform(220, 255)
    leak_g = rng.uniform(80, 160)
    leak_b = rng.uniform(10, 50)
    leak_color = np.array([leak_r, leak_g, leak_b], dtype=np.float32)

    # 光漏れの向き（上端・右端・左端のどれか）
    edge = rng.choice(['top', 'right', 'left'])
    actual = strength * (1.0 + random_jitter(fi, 0.18, seed=66))

    if edge == 'top':
        # 上端から染み込む
        fade_h = int(h * rng.uniform(0.15, 0.35))
        ys = np.linspace(1.0, 0.0, fade_h, dtype=np.float32) ** 1.8
        mask = ys[:, np.newaxis, np.newaxis] * actual
        arr[:fade_h, :, :] = arr[:fade_h, :, :] * (1 - mask) + leak_color * mask

    elif edge == 'right':
        # 右端から染み込む（位置を縦にランダムにずらす）
        fade_w = int(w * rng.uniform(0.12, 0.28))
        center_y = rng.randint(h // 4, h * 3 // 4)
        xs = np.linspace(0.0, 1.0, fade_w, dtype=np.float32) ** 1.8
        for yi in range(h):
            dist = abs(yi - center_y) / (h * 0.5)
            local_strength = actual * max(0, 1.0 - dist * 1.4)
            if local_strength <= 0:
                continue
            mask_1d = xs * local_strength
            for ch in range(3):
                col = arr[yi, -fade_w:, ch]
                arr[yi, -fade_w:, ch] = np.clip(
                    col * (1 - mask_1d) + leak_color[ch] * mask_1d, 0, 255
                )

    elif edge == 'left':
        fade_w = int(w * rng.uniform(0.10, 0.22))
        center_y = rng.randint(h // 4, h * 3 // 4)
        xs = np.linspace(1.0, 0.0, fade_w, dtype=np.float32) ** 1.8
        for yi in range(h):
            dist = abs(yi - center_y) / (h * 0.5)
            local_strength = actual * max(0, 1.0 - dist * 1.6)
            if local_strength <= 0:
                continue
            mask_1d = xs * local_strength
            for ch in range(3):
                col = arr[yi, :fade_w, ch]
                arr[yi, :fade_w, ch] = np.clip(
                    col * (1 - mask_1d) + leak_color[ch] * mask_1d, 0, 255
                )

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ===== 揺らぎ（水の底・海底） =====
def apply_ripple(img, fi=0, strength=2.0):
    arr = np.array(img)
    result = arr.copy()
    phase = fi * 0.08
    h, w = arr.shape[:2]
    for y in range(h):
        shift = int(math.sin(y * 0.03 + phase) * strength)
        if shift > 0:
            result[y, shift:, :] = arr[y, :-shift, :]
            result[y, :shift, :] = arr[y, 0:1, :]
        elif shift < 0:
            s = -shift
            result[y, :-s, :] = arr[y, s:, :]
            result[y, -s:, :] = arr[y, -1:, :]
    return Image.fromarray(result)


# ===== コースティクス風光斑（海底）★新規 =====
def apply_caustics(img, fi=0, strength=0.18):
    """
    水面から差し込む光の屈折模様（コースティクス）。
    サイン波の重ね合わせで有機的な光の網目を生成。
    """
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]

    xs = np.arange(w, dtype=np.float32) / w
    ys = np.arange(h, dtype=np.float32) / h
    xx, yy = np.meshgrid(xs, ys)

    t = fi * 0.04
    # 複数の波を重ね合わせて有機的な模様を作る
    wave = (
        np.sin(xx * 8.0 + t * 1.1) * 0.35 +
        np.sin(yy * 6.0 + t * 0.8) * 0.35 +
        np.sin((xx + yy) * 5.0 + t * 0.6) * 0.20 +
        np.sin((xx - yy) * 7.0 - t * 0.9) * 0.10
    )
    # 正規化して光の明るい部分だけを抽出
    wave = (wave + 1.0) / 2.0
    caustic = np.clip((wave - 0.55) / 0.45, 0, 1) ** 1.5

    # 上方向ほど強く（水面に近い）
    depth_fade = (1.0 - ys) ** 1.2
    caustic = caustic * depth_fade[:, np.newaxis]

    # 青白い光として加算
    light_color = np.array([160, 210, 255], dtype=np.float32)
    mask = caustic[:, :, np.newaxis] * strength

    result = np.clip(arr + light_color * mask * 60, 0, 255)
    return Image.fromarray(result.astype(np.uint8))


# ===== フィルター統合適用 =====
def apply_filter(img, filter_name, fi=0):
    """
    指定フィルターを画像に適用する統合関数。
    """
    if filter_name not in FILTERS:
        filter_name = "写ルンです"

    cfg = FILTERS[filter_name]
    arr = np.array(img)

    # 1. モノクロ変換
    if cfg.get("monochrome"):
        arr = apply_monochrome(arr, cfg["contrast"])
        img = Image.fromarray(arr)
    else:
        arr = apply_color_matrix(
            arr,
            cfg["color_matrix"],
            cfg["contrast"],
            cfg["lift"]
        )
        img = Image.fromarray(arr)

    # 2. 退色処理
    if cfg.get("fade"):
        img = apply_fade(img, 0.22)

    # 3. 霞み
    if cfg.get("mist"):
        img = apply_mist(img, 0.20)

    # 4. 揺らぎ（水の底・海底）
    if cfg.get("ripple"):
        ripple_strength = cfg.get("ripple_strength", 1.5)
        img = apply_ripple(img, fi, strength=ripple_strength)

    # 5. コースティクス（海底）
    if cfg.get("caustics"):
        img = apply_caustics(img, fi, strength=cfg.get("caustics_strength", 0.18))

    # 6. ソフトフォーカス
    if cfg.get("soft_focus"):
        img = apply_soft_focus(img, 0.25)

    # 7. フィルムバーン（端）
    if cfg.get("burn_edges"):
        img = apply_burn_edges(img, fi)

    # 8. フィルムバーン（内部有機焼け）
    if cfg.get("film_burn_organic"):
        img = apply_film_burn_organic(img, fi, strength=cfg.get("burn_strength", 0.6))

    # 9. 光漏れ
    if cfg.get("light_leak"):
        img = apply_light_leak(img, fi, strength=cfg.get("leak_strength", 0.55))

    # 10. ブルーム
    img = apply_bloom(img, cfg.get("bloom", 0.0), fi)

    # 11. ハレーション
    img = apply_halation(img, cfg.get("halation", 0.0), fi)

    # 12. フィルム粒子
    arr = apply_grain(np.array(img), cfg.get("grain", 12), fi)
    img = Image.fromarray(arr)

    # 13. フリッカー
    if cfg.get("flicker"):
        arr = apply_flicker(np.array(img), fi, strength=cfg.get("flicker_strength", 0.06))
        img = Image.fromarray(arr)

    # 14. クロマティックアベレーション
    img = apply_chroma_aberration(img, cfg.get("chroma_aber", 0.0), fi)

    # 15. VHSエフェクト
    if cfg.get("vhs_noise_band"):
        img = apply_vhs_noise_band(img, fi, strength=cfg.get("noise_band_strength", 0.35))
    if cfg.get("vhs_color_bleed"):
        img = apply_vhs_color_bleed(img, fi, strength=cfg.get("color_bleed_strength", 4))
    if cfg.get("scanline"):
        img = apply_scanline(img, fi)
    if cfg.get("gate_glitch"):
        img = apply_gate_glitch(img, fi)

    # 16. 縦揺れ・パーフォレーション（映写機）
    if cfg.get("vertical_jitter"):
        img = apply_vertical_jitter(img, fi)
    if cfg.get("perforation"):
        img = apply_film_perforation(img, fi)

    # 17. ビネット
    vign_strength = cfg.get("vignette", 190)
    jitter = 1.0 + random_jitter(fi // 24, 0.08, seed=11)
    arr = apply_vignette(
        np.array(img),
        int(vign_strength * jitter),
        seed=fi // 120
    )

    return Image.fromarray(arr)
