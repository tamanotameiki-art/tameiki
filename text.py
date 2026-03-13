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


# ===== レイアウト計算 =====
def calc_layout(lines):
    """
    行数・文字数からフォントサイズ・字間・行間を自動計算。
    横幅は画面の3/4を積極的に使用。詩を大きく見せることを優先。
    """
    num_lines  = len(lines)
    max_chars  = max(len(l) for l in lines)

    # 安全エリア（縦は余裕を持たせ・横は3/4まで使う）
    usable_h = H * (SAFE_BOTTOM - SAFE_TOP) * 0.90
    usable_w = W * (SAFE_RIGHT  - SAFE_LEFT) * 0.75

    # 文字サイズ（文字数が多いほど小さく）
    base_size = max(34, min(56, int(560 / max(max_chars, 6))))

    # 字間（文字サイズの1.30倍）
    char_gap = int(base_size * 1.30)

    # 行間（行数が少ないほど広く：詩的な余白）
    line_gap_ratio = max(2.2, min(3.2, 7.5 / max(num_lines, 1)))
    line_gap = int(base_size * line_gap_ratio)

    # 全体サイズチェック → はみ出すなら縮小
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

    # 特例チェック：それでも収まらない場合は特例レイアウト
    total_h_final = (max_chars - 1) * char_gap + base_size
    total_w_final = (num_lines  - 1) * line_gap + base_size
    use_extended = total_h_final > H * 0.85 or total_w_final > W * 0.75

    return base_size, char_gap, line_gap, use_extended


def build_char_timings(lines, fps=FPS):
    """
    各文字の出現タイミングを計算。
    行間ポーズは LINE_PAUSE_SEC を使用。
    """
    timings = []
    cursor  = 0
    line_starts = []

    for li, line in enumerate(lines):
        line_starts.append(cursor)
        last_char_end = (len(line) - 1) * int(CHAR_INTERVAL * fps)
        fade_half     = int(CHAR_FADEIN_SEC * fps * 0.5)
        if li < len(LINE_PAUSE_SEC):
            pause = int(LINE_PAUSE_SEC[li] * fps)
        else:
            pause = int(LINE_PAUSE_SEC[-1] * fps)
        cursor += last_char_end + fade_half + pause

    for li, line in enumerate(lines):
        for ci, ch in enumerate(line):
            start = line_starts[li] + ci * int(CHAR_INTERVAL * fps)
            timings.append((li, ci, ch, start))

    return timings


def get_char_position(li, ci, ch, sx, sy, char_gap, line_gap, font_size, seed=0):
    """
    縦書きでの文字座標を返す。
    句読点・延ばし棒は適切に処理。
    わずかな揺らぎを加えて「手で書いた感」を出す。
    """
    x = sx - li * line_gap
    y = sy + ci * char_gap

    # 句読点オフセット
    if ch in PUNCT_OFFSET:
        dx_ratio, dy_ratio = PUNCT_OFFSET[ch]
        x += int(font_size * dx_ratio)
        y += int(font_size * dy_ratio)

    # わずかな揺らぎ（0.5px程度・気づかないくらい）
    jitter_x = random_jitter(li * 100 + ci + seed, 0.5, seed=22)
    jitter_y = random_jitter(li * 100 + ci + seed, 0.5, seed=33)
    x += int(jitter_x)
    y += int(jitter_y)

    return x, y


def should_rotate(ch):
    """延ばし棒・ダッシュ系は縦書きで回転が必要"""
    return ch in ROTATE_CHARS


def draw_char_rotated(layer, ch, x, y, font, color, alpha):
    """延ばし棒などを90度回転して描画"""
    tmp = Image.new("RGBA", (font.size + 10, font.size + 10), (0, 0, 0, 0))
    td  = ImageDraw.Draw(tmp)
    td.text((0, 0), ch, font=font, fill=(*color, int(alpha * 255)))
    rotated = tmp.rotate(90, expand=True)
    layer.paste(rotated, (x, y), rotated)


# ===== 出現演出 =====
def appear_mist(layer, d, ch, x, y, font, color, alpha):
    """霧の中から現れる：ぼかし→焦点が合う"""
    if alpha < 0.7:
        blur_r = (1 - alpha / 0.7) * 5
        bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bl)
        if should_rotate(ch):
            draw_char_rotated(bl, ch, x, y, font, color, 1.0)
        else:
            bd.text((x, y), ch, font=font, fill=(*color, 255))
        bl = bl.filter(ImageFilter.GaussianBlur(radius=blur_r))
        r2, g2, b2, a2 = bl.split()
        a2 = a2.point(lambda v: int(v * alpha))
        bl = Image.merge("RGBA", (r2, g2, b2, a2))
        return Image.alpha_composite(layer, bl)
    else:
        d.text((x, y), ch, font=font, fill=(*color, int(alpha * 255)))
        return layer


def appear_rise(layer, d, ch, x, y, font, color, alpha):
    """下から浮かび上がる：Y方向にオフセット"""
    rise_offset = int((1 - ease_out(alpha)) * 18)
    actual_y = y + rise_offset
    a = int(ease_out(alpha) * 255)
    if should_rotate(ch):
        draw_char_rotated(layer, ch, x, actual_y, font, color, ease_out(alpha))
    else:
        d.text((x, actual_y), ch, font=font, fill=(*color, a))
    return layer


def appear_dissolve(layer, d, ch, x, y, font, color, alpha):
    """滲みながら現れる：ブラーが強め・ゆっくり"""
    blur_r = (1 - alpha) * 8
    if blur_r > 0.2:
        bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bl)
        if should_rotate(ch):
            draw_char_rotated(bl, ch, x, y, font, color, 1.0)
        else:
            bd.text((x, y), ch, font=font, fill=(*color, 255))
        bl = bl.filter(ImageFilter.GaussianBlur(radius=blur_r))
        r2, g2, b2, a2 = bl.split()
        a2 = a2.point(lambda v: int(v * alpha))
        bl = Image.merge("RGBA", (r2, g2, b2, a2))
        return Image.alpha_composite(layer, bl)
    else:
        d.text((x, y), ch, font=font, fill=(*color, int(alpha * 255)))
        return layer


# ===== メイン描画 =====
def draw_text_layer(lines, elapsed_frames, font, appear_pattern="mist",
                    bg_arr=None, fps=FPS, seed=0):
    """
    縦書きテキストレイヤーを生成。
    elapsed_frames: テキスト表示開始からのフレーム数
    appear_pattern: "mist" | "rise" | "dissolve"
    bg_arr: 背景画像配列（グロー色の参照用）
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    font_size = font.size
    _, char_gap, line_gap, use_extended = calc_layout(lines)

    num_lines = len(lines)
    max_chars = max(len(l) for l in lines)

    total_w = (num_lines - 1) * line_gap + font_size
    total_h = (max_chars - 1) * char_gap + font_size

    # 中央配置（わずかに詩的な上方向オフセット）
    sx = W // 2 + total_w // 2 - font_size // 2
    sy = H // 2 - total_h // 2 + 30

    # 特例：安全エリアを超える場合は画面中央に強制配置
    if use_extended:
        sx = min(sx, int(W * SAFE_RIGHT) - font_size)
        sy = max(sy, int(H * SAFE_TOP))

    timings   = build_char_timings(lines, fps)
    fadein_fr = int(CHAR_FADEIN_SEC * fps)

    for (li, ci, ch, delay) in timings:
        ch = VERTICAL_GLYPH_MAP.get(ch, ch)
        e = elapsed_frames - delay
        if e <= 0:
            continue

        raw_alpha = clamp(e / fadein_fr)
        alpha     = ease_organic(raw_alpha, seed=li * 10 + ci)
        if alpha <= 0:
            continue

        x, y = get_char_position(
            li, ci, ch, sx, sy, char_gap, line_gap, font_size, seed
        )

        if appear_pattern == "rise":
            layer = appear_rise(layer, d, ch, x, y, font, C_TEXT, alpha)
        elif appear_pattern == "dissolve":
            layer = appear_dissolve(layer, d, ch, x, y, font, C_TEXT, alpha)
        else:
            layer = appear_mist(layer, d, ch, x, y, font, C_TEXT, alpha)
            d = ImageDraw.Draw(layer)

    return layer


def get_appear_pattern(emotion_tags):
    """感情タグから出現パターンを決定"""
    for tag in emotion_tags:
        if tag in TEXT_APPEAR_PATTERNS:
            return TEXT_APPEAR_PATTERNS[tag]
    return TEXT_APPEAR_PATTERNS["default"]
