"""
tameiki/text.py — 縦書きテキスト描画エンジン
句読点・延ばし棒・感情タグ連動の出現演出を管理
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import (
    W, H, FPS, FONT_PATH, FONT_IDX,
    C_TEXT, PUNCT_OFFSET, ROTATE_CHARS, VERTICAL_GLYPH_MAP,
    SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT,
    TEXT_APPEAR_PATTERNS, CHAR_FADEIN_SEC, CHAR_INTERVAL, LINE_PAUSE_SEC
)
from easing import ease_out, ease_io, ease_organic, clamp, random_jitter


# ===== 文字色の自動判定 =====
def get_text_color(bg_arr, sx, sy, total_w, total_h):
    """
    テキスト配置エリアの背景輝度を計算して文字色を返す。
    明るい背景 → #2a1a0e（深いこげ茶）
    暗い背景  → C_TEXT（cream）
    """
    if bg_arr is None:
        return C_TEXT
    pad = 20
    x1 = max(0, sx - total_w - pad)
    x2 = min(W, sx + pad)
    y1 = max(0, sy - pad)
    y2 = min(H, sy + total_h + pad)
    if x2 <= x1 or y2 <= y1:
        return C_TEXT
    region = bg_arr[y1:y2, x1:x2]
    if region.size == 0:
        return C_TEXT
    if region.ndim == 3 and region.shape[2] >= 3:
        luminance = (
            0.299 * region[:, :, 0].mean() +
            0.587 * region[:, :, 1].mean() +
            0.114 * region[:, :, 2].mean()
        )
    else:
        luminance = region.mean()
    if luminance > 140:
        return (42, 26, 14)
    else:
        return C_TEXT


# ===== レイアウト計算 =====
def calc_layout(lines):
    """
    行数・文字数からフォントサイズ・字間・行間を自動計算。
    横幅は画面の3/4を積極的に使用。詩を大きく見せることを優先。
    """
    num_lines  = len(lines)
    max_chars  = max(len(l) for l in lines)

    usable_h = H * (SAFE_BOTTOM - SAFE_TOP) * 0.90
    usable_w = W * (SAFE_RIGHT  - SAFE_LEFT) * 0.75

    base_size = max(34, min(56, int(560 / max(max_chars, 6))))
    char_gap  = int(base_size * 1.30)

    line_gap_ratio = max(2.2, min(3.2, 7.5 / max(num_lines, 1)))
    line_gap = int(base_size * line_gap_ratio)

    total_h = (max_chars - 1) * char_gap + base_size
    total_w = (num_lines  - 1) * line_gap + base_size

    if total_h > usable_h:
        scale     = usable_h / total_h
        base_size = max(28, int(base_size * scale))
        char_gap  = int(char_gap * scale)
        line_gap  = int(line_gap * scale)
        total_h   = (max_chars - 1) * char_gap + base_size
        total_w   = (num_lines  - 1) * line_gap + base_size

    if total_w > usable_w:
        scale    = usable_w / total_w
        line_gap = int(line_gap * scale)

    total_h_final = (max_chars - 1) * char_gap + base_size
    total_w_final = (num_lines  - 1) * line_gap + base_size
    use_extended  = total_h_final > H * 0.85 or total_w_final > W * 0.75

    return base_size, char_gap, line_gap, use_extended


def build_char_timings(lines, fps=FPS):
    """
    各文字の出現タイミングを計算。
    CHAR_FADEIN_SEC > CHAR_INTERVAL なので、前の文字がまだ滲んでいる間に
    次の文字が始まる → 複数文字が重なりながらゆっくり浮かび上がる。
    """
    timings     = []
    cursor      = 0
    line_starts = []

    interval_fr = int(CHAR_INTERVAL  * fps)
    fadein_fr   = int(CHAR_FADEIN_SEC * fps)

    for li, line in enumerate(lines):
        line_starts.append(cursor)
        last_char_start = (len(line) - 1) * interval_fr
        # 行間ポーズ：フェードインの1/3が終わった頃から次の行へ
        fade_partial = fadein_fr // 3
        if li < len(LINE_PAUSE_SEC):
            pause = int(LINE_PAUSE_SEC[li] * fps)
        else:
            pause = int(LINE_PAUSE_SEC[-1] * fps)
        cursor += last_char_start + fade_partial + pause

    for li, line in enumerate(lines):
        for ci, ch in enumerate(line):
            start = line_starts[li] + ci * interval_fr
            timings.append((li, ci, ch, start))

    return timings


def get_char_position(li, ci, ch, sx, sy, char_gap, line_gap, font_size, seed=0):
    """縦書きでの文字座標を返す。"""
    x = sx - li * line_gap
    y = sy + ci * char_gap
    if ch in PUNCT_OFFSET:
        dx_ratio, dy_ratio = PUNCT_OFFSET[ch]
        x += int(font_size * dx_ratio)
        y += int(font_size * dy_ratio)
    jitter_x = random_jitter(li * 100 + ci + seed, 0.5, seed=22)
    jitter_y = random_jitter(li * 100 + ci + seed, 0.5, seed=33)
    x += int(jitter_x)
    y += int(jitter_y)
    return x, y


def should_rotate(ch):
    return ch in ROTATE_CHARS


def draw_char_rotated(layer, ch, x, y, font, color, alpha):
    tmp = Image.new("RGBA", (font.size + 10, font.size + 10), (0, 0, 0, 0))
    td  = ImageDraw.Draw(tmp)
    td.text((0, 0), ch, font=font, fill=(*color, int(alpha * 255)))
    rotated = tmp.rotate(90, expand=True)
    layer.paste(rotated, (x, y), rotated)


# ===== 出現演出 =====

def _render_blurred_char(ch, x, y, font, color, blur_r, fade_alpha):
    """
    ぼかし付き文字をWxHのRGBAレイヤーに描いて返す内部ヘルパー。
    """
    bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bl)
    if should_rotate(ch):
        draw_char_rotated(bl, ch, x, y, font, color, 1.0)
    else:
        bd.text((x, y), ch, font=font, fill=(*color, 255))
    bl = bl.filter(ImageFilter.GaussianBlur(radius=blur_r))
    r2, g2, b2, a2 = bl.split()
    a2 = a2.point(lambda v: int(v * fade_alpha))
    return Image.merge("RGBA", (r2, g2, b2, a2))


def appear_phantom(layer, d, ch, x, y, font, color, alpha, seed=0):
    """
    霧の中からゆっくり浮かび上がる幻想的な滲み（メインエフェクト）。

    3段階で変化する：
      0.0〜0.4 : 強いぼかし＋低透明度（霧の奥にぼんやり存在する）
      0.4〜0.75: ぼかしが溶けながら透明度が上がる（じわぁと浮かび上がる）
      0.75〜1.0: ほぼ焦点が合う（完全には鮮明にならない・夢のような余韻）

    文字ごとに seed が異なるため、それぞれ微妙に違う速度で現れる。
    """
    organic_alpha = ease_organic(alpha, seed=seed)

    # ブラー半径：序盤は強く・0.75以降もわずかに残す（完全には消えない）
    if organic_alpha < 0.75:
        blur_r = (1.0 - organic_alpha / 0.75) ** 1.4 * 9.0
    else:
        blur_r = (1.0 - organic_alpha) * 2.5

    # 透明度：ゆっくり立ち上がる（序盤はうっすら）
    fade_alpha = organic_alpha ** 0.65

    if blur_r > 0.3:
        bl = _render_blurred_char(ch, x, y, font, color, blur_r, fade_alpha)
        return Image.alpha_composite(layer, bl)
    else:
        if should_rotate(ch):
            draw_char_rotated(layer, ch, x, y, font, color, fade_alpha)
        else:
            d.text((x, y), ch, font=font, fill=(*color, int(fade_alpha * 255)))
        return layer


def appear_mist(layer, d, ch, x, y, font, color, alpha):
    """後方互換エイリアス → appear_phantom に委譲"""
    return appear_phantom(layer, d, ch, x, y, font, color, alpha, seed=0)


def appear_rise(layer, d, ch, x, y, font, color, alpha):
    """
    霧ごと下から浮かび上がる。
    phantom の滲みに縦方向のゆっくりしたドリフトを加えた版。
    """
    organic_alpha = ease_organic(alpha, seed=0)
    # ドリフト量：序盤は下にずれており、徐々に正位置へ
    rise_offset = int((1.0 - organic_alpha ** 0.7) * 22)
    actual_y    = y + rise_offset

    if organic_alpha < 0.75:
        blur_r = (1.0 - organic_alpha / 0.75) ** 1.4 * 9.0
    else:
        blur_r = (1.0 - organic_alpha) * 2.5

    fade_alpha = organic_alpha ** 0.65

    if blur_r > 0.3:
        bl = _render_blurred_char(ch, x, actual_y, font, color, blur_r, fade_alpha)
        return Image.alpha_composite(layer, bl)
    else:
        if should_rotate(ch):
            draw_char_rotated(layer, ch, x, actual_y, font, color, fade_alpha)
        else:
            d.text((x, actual_y), ch, font=font, fill=(*color, int(fade_alpha * 255)))
        return layer


def appear_dissolve(layer, d, ch, x, y, font, color, alpha):
    """
    インクが紙に染みるように滲み広がりながら現れる。
    phantom より広いブラー半径・よりゆっくりした収束。
    """
    organic_alpha = ease_organic(alpha, seed=0)

    if organic_alpha < 0.8:
        blur_r = (1.0 - organic_alpha / 0.8) ** 1.2 * 13.0
    else:
        blur_r = (1.0 - organic_alpha) * 3.0

    fade_alpha = organic_alpha ** 0.55

    if blur_r > 0.3:
        bl = _render_blurred_char(ch, x, y, font, color, blur_r, fade_alpha)
        return Image.alpha_composite(layer, bl)
    else:
        if should_rotate(ch):
            draw_char_rotated(layer, ch, x, y, font, color, fade_alpha)
        else:
            d.text((x, y), ch, font=font, fill=(*color, int(fade_alpha * 255)))
        return layer


# ===== メイン描画 =====
def draw_text_layer(lines, elapsed_frames, font, appear_pattern="mist",
                    bg_arr=None, fps=FPS, seed=0):
    """
    縦書きテキストレイヤーを生成。
    elapsed_frames: テキスト表示開始からのフレーム数
    appear_pattern: "mist" | "rise" | "dissolve"
    bg_arr: 背景画像配列（輝度判定用）
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    font_size = font.size
    _, char_gap, line_gap, use_extended = calc_layout(lines)

    num_lines = len(lines)
    max_chars = max(len(l) for l in lines)

    total_w = (num_lines - 1) * line_gap + font_size
    total_h = (max_chars - 1) * char_gap + font_size

    sx = W // 2 + total_w // 2 - font_size // 2
    sy = H // 2 - total_h // 2 + 30

    if use_extended:
        sx = min(sx, int(W * SAFE_RIGHT) - font_size)
        sy = max(sy, int(H * SAFE_TOP))

    # 背景輝度から文字色を自動判定
    text_color = get_text_color(bg_arr, sx, sy, total_w, total_h)

    timings   = build_char_timings(lines, fps)
    fadein_fr = int(CHAR_FADEIN_SEC * fps)

    for (li, ci, ch, delay) in timings:
        ch = VERTICAL_GLYPH_MAP.get(ch, ch)
        e  = elapsed_frames - delay
        if e <= 0:
            continue

        raw_alpha = clamp(e / fadein_fr)
        if raw_alpha <= 0:
            continue

        x, y = get_char_position(
            li, ci, ch, sx, sy, char_gap, line_gap, font_size, seed
        )

        char_seed = li * 100 + ci + seed

        if appear_pattern == "rise":
            layer = appear_rise(layer, d, ch, x, y, font, text_color, raw_alpha)
        elif appear_pattern == "dissolve":
            layer = appear_dissolve(layer, d, ch, x, y, font, text_color, raw_alpha)
        else:
            layer = appear_phantom(layer, d, ch, x, y, font, text_color, raw_alpha, seed=char_seed)

        d = ImageDraw.Draw(layer)

    return layer


def get_appear_pattern(emotion_tags):
    """感情タグから出現パターンを決定"""
    for tag in emotion_tags:
        if tag in TEXT_APPEAR_PATTERNS:
            return TEXT_APPEAR_PATTERNS[tag]
    return TEXT_APPEAR_PATTERNS["default"]
