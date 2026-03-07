"""
tameiki/ending.py — エンディング演出エンジン
感情タグ連動の3パターン + 後光エフェクト
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import W, H, C_DARK, C_GOLD, C_AMBER, C_WHITE, ENDING_PATTERNS
from easing import ease_out, ease_io, ease_organic, clamp


def get_ending_pattern(emotion_tags):
    """感情タグからエンディングパターンを決定"""
    for tag in emotion_tags:
        if tag in ENDING_PATTERNS:
            return ENDING_PATTERNS[tag]
    return ENDING_PATTERNS["default"]


def draw_halo(base, title, font, tx, ty, tp):
    """
    後光エフェクト（3層グロー）
    一瞬ピークを作り、その後落ち着いていく（フラッシュ感）
    """
    result = base.copy()

    # フラッシュ感：ピーク後に残光として落ち着く
    halo_peak = ease_out(min(tp * 2.5, 1.0)) * (1 - ease_io(max(tp - 0.4, 0) / 0.6))
    halo_peak = max(halo_peak, ease_out(min(tp, 1.0)) * 0.28)

    for radius, alpha_mul, color in [
        (55, 0.18, C_GOLD),    # 外輪：大きく広がるゴールド
        (30, 0.30, C_AMBER),   # 中輪：アンバー
        (14, 0.45, C_WHITE),   # 内輪：ほぼ白
    ]:
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hd   = ImageDraw.Draw(halo)
        hd.text((tx, ty), title, font=font, fill=(*color, 255))
        halo = halo.filter(ImageFilter.GaussianBlur(radius=radius))
        r2, g2, b2, a2 = halo.split()
        a2 = a2.point(lambda v: int(v * alpha_mul * halo_peak))
        halo = Image.merge("RGBA", (r2, g2, b2, a2))
        result = Image.alpha_composite(result, halo)

    # 文字マスク（内側に動画の色が透ける）
    mask = Image.new("L", (W, H), 0)
    md   = ImageDraw.Draw(mask)
    md.text((tx, ty), title, font=font, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.4))
    cutout = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cutout.paste(base, mask=mask)
    r2, g2, b2, a2 = cutout.split()
    a2 = a2.point(lambda v: int(v * 0.60 * tp))
    cutout = Image.merge("RGBA", (r2, g2, b2, a2))
    result = Image.alpha_composite(result, cutout)

    # テキスト本体（クリーム白）
    txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td  = ImageDraw.Draw(txt)
    td.text((tx, ty), title, font=font, fill=(255, 248, 232, int(235 * tp)))
    result = Image.alpha_composite(result, txt)

    # 輪郭グロー（文字の立体感）
    sg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sgd = ImageDraw.Draw(sg)
    sgd.text((tx, ty), title, font=font, fill=(255, 255, 255, int(160 * tp)))
    sg = sg.filter(ImageFilter.GaussianBlur(radius=2.5))
    result = Image.alpha_composite(result, sg)

    return result


def draw_ending(frame_rgba, ep, font, emotion_tags=None, last_sound_alpha=0.0):
    """
    エンディング描画。ep = 0.0〜1.0
    emotion_tags: 感情タグリスト
    last_sound_alpha: ハーモニクスの残響（最後だけ音が残る演出用）
    """
    if emotion_tags is None:
        emotion_tags = []

    pattern = get_ending_pattern(emotion_tags)
    result  = frame_rgba.copy()

    title = "たまのためいき。"
    bbox  = font.getbbox(title)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (W - tw) // 2
    ty = (H - th) // 2

    # ===== white_flash（希望・温かい） =====
    if pattern == "white_flash":
        # 前半：映像がわずかに明るくなる（夜明け感）
        if ep < 0.25:
            bright_t = ease_io(ep / 0.25)
            bright = Image.new("RGBA", (W, H), (255, 248, 230, int(bright_t * 30)))
            result = Image.alpha_composite(result, bright)

        # 暗転（白から）
        dark_a = int(ease_io(min(ep * 1.6, 1.0)) * 200)
        dark   = Image.new("RGBA", (W, H), (*C_DARK, dark_a))
        result = Image.alpha_composite(result, dark)

        # タイトル表示フェーズ
        TEXT_END = 0.75
        if 0.25 < ep <= TEXT_END:
            tp = ease_out((ep - 0.25) / 0.50)
            result = draw_halo(result, title, font, tx, ty, tp)
        elif ep > TEXT_END:
            # 白く飛んで消える
            flash_t = (ep - TEXT_END) / (1.0 - TEXT_END)
            white_a = int(ease_io(flash_t) * 255)
            white   = Image.new("RGBA", (W, H), (255, 252, 240, white_a))
            result  = Image.alpha_composite(result, white)

    # ===== mist_fade（哀愁・孤独） =====
    elif pattern == "mist_fade":
        # 映像がわずかにブレる（記憶が揺らぐ感覚）
        if ep < 0.15:
            blur_r = ep / 0.15 * 2.5
            result = result.filter(ImageFilter.GaussianBlur(radius=blur_r))

        # 霧が漂うような暗転
        dark_a = int(ease_io(min(ep * 1.5, 1.0)) * 215)
        dark   = Image.new("RGBA", (W, H), (*C_DARK, dark_a))
        result = Image.alpha_composite(result, dark)

        # タイトル表示
        TEXT_END = 0.78
        if 0.28 < ep <= TEXT_END:
            tp = ease_out((ep - 0.28) / 0.50)
            result = draw_halo(result, title, font, tx, ty, tp)
        elif ep > TEXT_END:
            # 霧に溶けるように消える（ゆっくり）
            mist_t  = (ep - TEXT_END) / (1.0 - TEXT_END)
            mist_a  = int(ease_organic(mist_t) * 255)
            mist    = Image.new("RGBA", (W, H), (*C_DARK, mist_a))
            result  = Image.alpha_composite(result, mist)

    # ===== slow_dark（静謐・空虚） =====
    elif pattern == "slow_dark":
        # 何も起こらずゆっくり暗転
        dark_a = int(ease_io(min(ep * 1.4, 1.0)) * 210)
        dark   = Image.new("RGBA", (W, H), (*C_DARK, dark_a))
        result = Image.alpha_composite(result, dark)

        # タイトル表示
        TEXT_END = 0.80
        if 0.30 < ep <= TEXT_END:
            tp = ease_organic((ep - 0.30) / 0.50)
            result = draw_halo(result, title, font, tx, ty, tp)
        elif ep > TEXT_END:
            blackout_a = int(ease_io((ep - TEXT_END) / (1.0 - TEXT_END)) * 255)
            blackout   = Image.new("RGBA", (W, H), (0, 0, 0, blackout_a))
            result     = Image.alpha_composite(result, blackout)

    # ===== dark_flash（デフォルト） =====
    else:
        dark_a = int(ease_io(min(ep * 1.7, 1.0)) * 218)
        dark   = Image.new("RGBA", (W, H), (*C_DARK, dark_a))
        result = Image.alpha_composite(result, dark)

        TEXT_END = 0.78
        if 0.28 < ep <= TEXT_END:
            tp = ease_out((ep - 0.28) / 0.50)
            result = draw_halo(result, title, font, tx, ty, tp)
        elif ep > TEXT_END:
            flash_t    = (ep - TEXT_END) / (1.0 - TEXT_END)
            blackout_a = int(ease_io(flash_t) * 255)
            blackout   = Image.new("RGBA", (W, H), (0, 0, 0, blackout_a))
            result     = Image.alpha_composite(result, blackout)

    return result
