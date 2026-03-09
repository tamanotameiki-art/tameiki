"""
tameiki/background.py — 背景処理
素材の読み込み・9:16トリミング・Ken Burns
動画ファイル（.mp4等）はffmpegで中間フレームを抽出してから使用
"""
import os
import math
import subprocess
from PIL import Image
from config import W, H
from easing import ease_organic, random_jitter, clamp


def prepare_bg(path):
    """
    背景素材を読み込み、9:16にトリミング・リサイズ。
    動画ファイルの場合はffmpegで中間フレームを抽出してから処理。
    縦長・横長・正方形いずれでも中央基準で安全に処理。
    """
    # 動画ファイルの場合はフレーム抽出
    if is_video_file(path):
        path = extract_frame_from_video(path)

    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    target_ratio  = H / W   # 1.777...
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


def is_video_file(path):
    """動画ファイルかどうか判定"""
    return os.path.splitext(path)[1].lower() in (".mp4", ".mov", ".avi", ".m4v", ".webm")


def extract_frame_from_video(video_path):
    """
    動画から中間フレームを1枚抽出してJPEGとして保存し、そのパスを返す。
    同じ動画なら同じフレームを使い回す（キャッシュ）。
    """
    frame_path = video_path + "_frame.jpg"
    if os.path.exists(frame_path):
        return frame_path

    # 動画の長さを取得
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        duration = float(r.stdout.strip())
    except Exception:
        duration = 10.0

    # 中間フレームを抽出（動画の1/3地点）
    t = duration / 3.0
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        frame_path
    ]
    subprocess.run(cmd, capture_output=True)
    print(f"動画からフレーム抽出: {t:.1f}秒地点 → {frame_path}", flush=True)
    return frame_path


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
    left  = (W - nw) // 2
    top   = max(0, min(py + (H - nh) // 2, H - nh))

    return base_img.crop((left, top, left + nw, top + nh)).resize(
        (W, H), Image.LANCZOS
    )
