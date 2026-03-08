"""
tameiki/filters.py — フィルター処理エンジン
全14種のフィルターと映像エフェクトを管理
"""
import math
import numpy as np
from PIL import Image, ImageFilter
from config import W, H, FILTERS
from easing import random_jitter, clamp


# ===== ビネット（一度生成してキャッシュ） =====
_vignette_cache = {}


def make_vignette(strength=190, seed=0):
    """
    ビネット生成。seedで毎回微妙に形を変える（有機的な不完全さ）
    """
    key = (strength, seed)
    if key in _vignette_cache:
        return _vignette_cache[key]

    cx = W / 2 + random_jitter(seed, 12, seed=1)
    cy = H / 2 + random_jitter(seed, 20, seed=2)

    # 楕円ビネット（完全な円にしない・有機的に）
    rx = W / 2 * (0.93 + random_jitter(seed, 0.04, seed=3))
    ry = H / 2 * (0.91 + random_jitter(seed, 0.04, seed=4))

    # NumPyベクトル演算で高速化
    xs = (np.arange(W, dtype=np.float32) - cx) / rx
    ys = (np.arange(H, dtype=np.float32) - cy) / ry
    xx, yy = np.meshgrid(xs, ys)
    d   = np.sqrt(xx * xx + yy * yy)
    arr = np.clip((d - 0.40) / 0.85, 0.0, 1.0)

    result = (arr * strength).astype(np.uint8)
    _vignette_cache[key] = result
    return result


def apply_vignette(img_arr, strength=190, dark=(8, 5, 3), seed=0):
    """ビネットを画像配列に適用"""
    vign = make_vignette(strength, seed)
    v = vign[:, :, np.newaxis] / 255.0
    dark_arr = np.array(dark, dtype=np.float32)
    result = img_arr * (1 - v) + dark_arr * v
    return np.clip(result, 0, 255).astype(np.uint8)


# ===== カラーグレーディング =====
def apply_color_matrix(arr, matrix, contrast=1.0, lift=0.0):
    """
    カラーマトリクス適用
    matrix: {"R": (mul, add), "G": (mul, add), "B": (mul, add)}
    """
    f = arr.astype(np.float32) / 255.0

    if matrix is not None:
        f[:, :, 0] = np.clip(f[:, :, 0] * matrix["R"][0] + matrix["R"][1], 0, 1)
        f[:, :, 1] = np.clip(f[:, :, 1] * matrix["G"][0] + matrix["G"][1], 0, 1)
        f[:, :, 2] = np.clip(f[:, :, 2] * matrix["B"][0] + matrix["B"][1], 0, 1)

    # コントラスト
    if contrast != 1.0:
        f = np.clip((f - 0.5) * contrast + 0.5, 0, 1)

    # リフト（シャドウを持ち上げる）
    if lift > 0:
        f = np.clip(f * (1 - lift) + lift, 0, 1)

    return (f * 255).astype(np.uint8)


def apply_monochrome(arr, contrast=1.15):
    """モノクロ変換（サイレント映画フィルター）"""
    f = arr.astype(np.float32) / 255.0
    # 人間の視覚に合わせた重み
    gray = f[:, :, 0] * 0.299 + f[:, :, 1] * 0.587 + f[:, :, 2] * 0.114
    gray = np.clip((gray - 0.5) * contrast + 0.5, 0, 1)
    result = np.stack([gray, gray, gray], axis=2)
    return (result * 255).astype(np.uint8)


# ===== フィルム粒子 =====
def apply_grain(arr, strength=14, fi=0):
    """
    フィルム粒子。フレームごとに変わるが、シードで再現可能。
    強度も微妙にランダムに変える（有機的な不完全さ）
    """
    actual_strength = strength * (1.0 + random_jitter(fi, 0.15, seed=99))
    rng = np.random.RandomState(fi % 97 + int(actual_strength))
    noise = rng.randint(
        -int(actual_strength), int(actual_strength) + 1,
        arr.shape, dtype=np.int16
    )
    return np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# ===== クロマティックアベレーション =====
def apply_chroma_aberration(img, strength=1.5, fi=0):
    """
    RGB各チャンネルをわずかにズラす。
    レンズの収差・VHSの色ズレを再現。
    強度を毎回微妙に変える（有機的な揺らぎ）
    """
    if strength <= 0:
        return img

    arr = np.array(img)
    actual = strength * (1.0 + random_jitter(fi, 0.2, seed=77))
    shift = int(actual)
    if shift < 1:
        return img

    result = arr.copy()
    # Rチャンネルを右にずらす
    if shift > 0:
        result[:, shift:, 0] = arr[:, :-shift, 0]
        result[:, :shift, 0] = arr[:, 0:1, 0]
    # Bチャンネルを左にずらす
    if shift > 0:
        result[:, :-shift, 2] = arr[:, shift:, 2]
        result[:, -shift:, 2] = arr[:, -1:, 2]

    return Image.fromarray(result)


# ===== ブルーム（明るい部分の滲み） =====
def apply_bloom(img, strength=0.15, fi=0):
    """明るい部分の滲み。1/4縮小でぼかして拡大する高速版。"""
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


# ===== ハレーション（光源周辺の滲み） =====
def apply_halation(img, strength=0.12, fi=0):
    """フィルムの感光特性：暖色の滲み。1/4縮小で高速化。"""
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
    """夢のような柔らかさ。元画像とぼかした画像をブレンド。"""
    if strength <= 0:
        return img
    blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
    arr_orig = np.array(img).astype(np.float32)
    arr_blur = np.array(blurred).astype(np.float32)
    result = arr_orig * (1 - strength) + arr_blur * strength
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== 霞み（霧フィルター） =====
def apply_mist(img, strength=0.25):
    """霧がかかったような白みがかった霞み。"""
    if strength <= 0:
        return img
    arr = np.array(img).astype(np.float32)
    white = np.full_like(arr, 240.0)
    result = arr * (1 - strength) + white * strength
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


# ===== 退色処理 =====
def apply_fade(img, strength=0.2):
    """色褪せた感じ：彩度を下げて黄ばみを加える。"""
    if strength <= 0:
        return img
    arr = np.array(img).astype(np.float32)
    gray = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
    gray = gray[:, :, np.newaxis]
    desaturated = arr * (1 - strength) + gray * strength
    # 黄ばみ（Rを少し上げ、Bを下げる）
    desaturated[:, :, 0] = np.clip(desaturated[:, :, 0] + 8, 0, 255)
    desaturated[:, :, 2] = np.clip(desaturated[:, :, 2] - 12, 0, 255)
    return Image.fromarray(np.clip(desaturated, 0, 255).astype(np.uint8))


# ===== フィルムバーン（フィルムの焼け） =====
def apply_burn_edges(img, fi=0):
    """
    フィルムの端が焼けたような有機的な模様。
    毎回わずかに形が変わる。
    """
    arr = np.array(img).astype(np.float32)
    rng = np.random.RandomState(fi % 47)

    # 端に沿ってランダムな焼け模様
    for edge in ['top', 'bottom']:
        height = rng.randint(2, 8)
        opacity = rng.uniform(0.3, 0.7)
        warm = np.array([220, 140, 60], dtype=np.float32)

        if edge == 'top':
            region = arr[:height, :, :]
            region = region * (1 - opacity) + warm * opacity
            arr[:height, :, :] = region
        else:
            region = arr[-height:, :, :]
            region = region * (1 - opacity) + warm * opacity
            arr[-height:, :, :] = region

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ===== VHSスキャンライン =====
def apply_scanline(img, fi=0):
    """
    VHSの横線ノイズ。
    頻度低め・一瞬だけ・フレームによって位置が変わる。
    """
    import random
    rng = random.Random(fi * 13)

    # 30フレームに1回程度の確率で発生
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
    """
    テープの劣化による映像の乱れ。
    ごく稀に・一瞬だけ発生。
    """
    import random
    rng = random.Random(fi * 31)

    # 60フレームに1回程度
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


# ===== 揺らぎ（水の底フィルター） =====
def apply_ripple(img, fi=0, strength=2.0):
    """水面の揺らぎ：画像をわずかに波状に歪める。"""
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


# ===== フィルター統合適用 =====
def apply_filter(img, filter_name, fi=0):
    """
    指定フィルターを画像に適用する統合関数。
    全エフェクトをchainして返す。
    """
    if filter_name not in FILTERS:
        filter_name = "写ルンです"

    cfg = FILTERS[filter_name]
    arr = np.array(img)

    # 1. モノクロ変換（サイレント映画のみ）
    if cfg.get("monochrome"):
        arr = apply_monochrome(arr, cfg["contrast"])
        img = Image.fromarray(arr)
    else:
        # 2. カラーグレーディング
        arr = apply_color_matrix(
            arr,
            cfg["color_matrix"],
            cfg["contrast"],
            cfg["lift"]
        )
        img = Image.fromarray(arr)

    # 3. 退色処理
    if cfg.get("fade"):
        img = apply_fade(img, 0.22)

    # 4. 霞み
    if cfg.get("mist"):
        img = apply_mist(img, 0.20)

    # 5. 揺らぎ（水の底）
    if cfg.get("ripple"):
        img = apply_ripple(img, fi, strength=1.5)

    # 6. ソフトフォーカス
    if cfg.get("soft_focus"):
        img = apply_soft_focus(img, 0.25)

    # 7. フィルムバーン
    if cfg.get("burn_edges"):
        img = apply_burn_edges(img, fi)

    # 8. ブルーム
    img = apply_bloom(img, cfg.get("bloom", 0.0), fi)

    # 9. ハレーション
    img = apply_halation(img, cfg.get("halation", 0.0), fi)

    # 10. フィルム粒子
    arr = apply_grain(np.array(img), cfg.get("grain", 12), fi)
    img = Image.fromarray(arr)

    # 11. クロマティックアベレーション
    img = apply_chroma_aberration(img, cfg.get("chroma_aber", 0.0), fi)

    # 12. VHSエフェクト
    if cfg.get("scanline"):
        img = apply_scanline(img, fi)
    if cfg.get("gate_glitch"):
        img = apply_gate_glitch(img, fi)

    # 13. ビネット
    vign_strength = cfg.get("vignette", 190)
    # ビネット強度も毎回微妙にランダムに変える
    jitter = 1.0 + random_jitter(fi // 24, 0.08, seed=11)
    arr = apply_vignette(
        np.array(img),
        int(vign_strength * jitter),
        seed=fi // 120   # 5秒ごとに形が変わる
    )

    return Image.fromarray(arr)
