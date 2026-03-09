#!/usr/bin/env python3
"""
tameiki/generate.py — メイン動画生成エンジン
全モジュールを統合して20秒の縦型動画を生成する
動画素材の場合はフレームを順番に使用（Ken Burnsはスキップ）
"""
import os
import sys
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    W, H, FPS, FONT_PATH, FONT_IDX,
    C_MIST, C_TEXT, C_DARK,
    INTRO_DUR, TEXT_DELAY, ENDING_START, TOTAL_SEC,
    CHAR_FADEIN_SEC,
)
from easing import ease_io, ease_out, ease_organic, clamp, random_jitter
from filters import apply_filter
from background import (
    prepare_bg, ken_burns,
    is_video_file, extract_video_frames, load_video_frame, crop_and_resize
)
from text import draw_text_layer, calc_layout, get_appear_pattern
from ending import draw_ending, get_ending_pattern


def generate(
    text,
    bg_path,
    filter_name    = "写ルンです",
    emotion_tags   = None,
    output_path    = "/mnt/user-data/outputs/tameiki_v4.mp4",
    frames_dir     = "/home/claude/tameiki_frames",
    total_sec      = TOTAL_SEC,
    seed           = 42,
):
    if emotion_tags is None:
        emotion_tags = []

    total_frames = int(FPS * total_sec)
    lines        = text.split("\n")

    # ===== フォント =====
    font_size, char_gap, line_gap, use_extended = calc_layout(lines)
    font_main = ImageFont.truetype(FONT_PATH, font_size, index=FONT_IDX)
    font_end  = ImageFont.truetype(FONT_PATH, 40,        index=FONT_IDX)

    # ===== タイムライン =====
    T_INTRO_END  = int(INTRO_DUR    * FPS)
    T_TEXT_START = int(TEXT_DELAY   * FPS)
    T_END_START  = int(ENDING_START * FPS)
    T_FADEIN     = int(CHAR_FADEIN_SEC * FPS)

    # ===== 出現パターン =====
    appear_pattern = get_appear_pattern(emotion_tags)
    ending_pattern = get_ending_pattern(emotion_tags)

    print(f"{'='*50}")
    print(f"テキスト　: {repr(text[:30])}...")
    print(f"フィルター: {filter_name}")
    print(f"感情タグ　: {emotion_tags}")
    print(f"出現演出　: {appear_pattern} / エンディング: {ending_pattern}")
    print(f"レイアウト: size={font_size}px char_gap={char_gap}px line_gap={line_gap}px")
    print(f"総フレーム: {total_frames}枚 ({total_sec}秒)")
    print(f"{'='*50}")

    # ===== 背景準備 =====
    print("背景準備中...")
    use_video  = is_video_file(bg_path)
    bg_frames_dir = frames_dir + "_bg"

    if use_video:
        # 動画：全フレームを事前展開
        extract_video_frames(bg_path, bg_frames_dir, total_frames, FPS)
        base_bg = None  # 動画の場合はフレームごとに読み込む
    else:
        # 静止画：1枚読み込んでKen Burns
        base_bg = prepare_bg(bg_path)

    # ===== フレーム生成 =====
    os.makedirs(frames_dir, exist_ok=True)

    print("フレーム生成中...")
    for fi in range(total_frames):
        if fi % FPS == 0:
            print(f"  {fi // FPS}s / {int(total_sec)}s")

        # --- 背景 ---
        if use_video:
            bg = load_video_frame(bg_frames_dir, fi)
        else:
            bg = ken_burns(base_bg, fi, total_frames, seed=seed)

        # --- フィルター適用 ---
        frame = apply_filter(bg, filter_name, fi)
        frame = frame.convert("RGBA")

        # --- 冒頭滲み演出（0〜INTRO_DUR秒） ---
        if fi < T_INTRO_END:
            p      = fi / T_INTRO_END
            blur_r = (1 - ease_io(p)) * 14
            if blur_r > 0.3:
                frame = frame.filter(ImageFilter.GaussianBlur(radius=blur_r))
            mist_a = int((1 - ease_io(p)) * 255)
            mist   = Image.new("RGBA", (W, H), (*C_MIST, mist_a))
            frame  = Image.alpha_composite(frame, mist)

        # --- テキスト描画 ---
        if T_TEXT_START <= fi < T_END_START:
            elapsed   = fi - T_TEXT_START
            # 動画の場合はフレームそのままをbg_arrに使う
            bg_arr    = np.array(bg)
            txt_layer = draw_text_layer(
                lines, elapsed, font_main,
                appear_pattern=appear_pattern,
                bg_arr=bg_arr,
                fps=FPS,
                seed=seed,
            )
            frame = Image.alpha_composite(frame, txt_layer)

        # --- エンディング ---
        if fi >= T_END_START:
            ep    = (fi - T_END_START) / (total_frames - T_END_START)
            frame = draw_ending(frame, ep, font_end, emotion_tags)

        # --- 保存 ---
        frame.convert("RGB").save(f"{frames_dir}/f{fi:05d}.png")

    # ===== 動画合成 =====
    print("動画合成中...")
    cmd = (
        f"ffmpeg -y -framerate {FPS} -i {frames_dir}/f%05d.png "
        f"-c:v libx264 -preset fast -crf 17 "
        f"-pix_fmt yuv420p "
        f"-vf scale={W}:{H} "
        f"{output_path} 2>&1 | tail -5"
    )
    ret = os.system(cmd)
    shutil.rmtree(frames_dir, ignore_errors=True)
    if use_video:
        shutil.rmtree(bg_frames_dir, ignore_errors=True)

    if ret == 0:
        print(f"\n完了: {output_path}")
    else:
        print(f"\nエラー: {ret}")

    return ret == 0


# ===== 単体実行 =====
if __name__ == "__main__":
    generate(
        text         = "心のとばりが降りて、\n自分と向き合えたら、\n春が還ってくる",
        bg_path      = "/mnt/user-data/uploads/IMG_8424.jpeg",
        filter_name  = "写ルンです",
        emotion_tags = ["哀愁", "希望"],
        output_path  = "/mnt/user-data/outputs/tameiki_v4.mp4",
        seed         = 42,
    )
