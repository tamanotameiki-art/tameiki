"""
tameiki/background.py — 背景処理
素材の読み込み・9:16トリミング・Ken Burns
動画ファイル（.mp4等）はffmpegで全フレームを事前展開して使用
"""
import os
import subprocess
from PIL import Image
from config import W, H
from easing import ease_organic, random_jitter, clamp


def is_video_file(path):
    """動画ファイルかどうか判定"""
    return os.path.splitext(path)[1].lower() in (".mp4", ".mov", ".avi", ".m4v", ".webm")


def get_video_duration(video_path):
    """動画の長さ（秒）を取得"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except Exception:
        return 10.0


def extract_video_frames(video_path, frames_dir, total_frames, fps):
    """
    動画から必要フレーム数分を均等に抽出してJPEGとして保存。
    動画が短い場合はループして補完。
    """
    os.makedirs(frames_dir, exist_ok=True)

    duration    = get_video_duration(video_path)
    video_total = int(duration * fps)

    print(f"動画フレーム展開中: {duration:.1f}秒 → {total_frames}枚必要", flush=True)

    for fi in range(total_frames):
        out_path = f"{frames_dir}/bg_{fi:05d}.jpg"
        if os.path.exists(out_path):
            continue
        # 動画が短い場合はループ
        video_fi = fi % max(video_total, 1)
        t = video_fi / fps
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{t:.4f}",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "3",
            out_path
        ]
        subprocess.run(cmd, capture_output=True)

    print(f"動画フレーム展開完了", flush=True)
    return frames_dir


def load_video_frame(frames_dir, fi):
    """展開済み動画フレームを読み込む"""
    path = f"{frames_dir}/bg_{fi:05d}.jpg"
    img  = Image.open(path).convert("RGB")
    return crop_and_resize(img)


def prepare_bg(path):
    """
    静止画背景を読み込み、9:16にトリミング・リサイズ。
    動画の場合は中間フレームを1枚抽出（フォールバック用）。
    """
    if is_video_file(path):
        frame_path = path + "_frame.jpg"
        if not os.path.exists(frame_path):
            duration = get_video_duration(path)
            t = duration / 3.0
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(t),
                "-i", path,
                "-vframes", "1",
                "-q:v", "2",
                frame_path
            ]
            subprocess.run(cmd, capture_output=True)
            print(f"動画からフレーム抽出（フォールバック）: {t:.1f}秒地点", flush=True)
        path = frame_path

    img = Image.open(path).convert("RGB")
    return crop_and_resize(img)


def crop_and_resize(img):
    """9:16にクロップしてリサイズ"""
    iw, ih        = img.size
    target_ratio  = H / W
    current_ratio = ih / iw

    if current_ratio > target_ratio:
        new_h = int(iw * target_ratio)
        top   = (ih - new_h) // 2
        img   = img.crop((0, top, iw, top + new_h))
    elif current_ratio < target_ratio:
        new_w = int(ih / target_ratio)
        left  = (iw - new_w) // 2
        img   = img.crop((left, 0, left + new_w, ih))

    cw, ch = img.size
    if cw < W * 0.5 or ch < H * 0.5:
        print(f"警告: 素材が小さすぎます ({cw}x{ch}) → 引き伸ばして使用します")

    return img.resize((W, H), Image.LANCZOS)


def ken_burns(base_img, fi, total_frames, seed=0):
    """
    Ken Burnsエフェクト（ゆっくりズームイン）。
    静止画背景にのみ使用。動画背景はそのままフレームを使う。
    """
    from config import KB_ZOOM_BASE, KB_ZOOM_JITTER, KB_PAN_JITTER
    t = fi / total_frames

    zoom_amount = KB_ZOOM_BASE + random_jitter(seed, KB_ZOOM_JITTER, seed=1)
    zoom = 1.0 + ease_organic(t, seed=seed) * zoom_amount
    nw = int(W / zoom)
    nh = int(H / zoom)

    pan_y = random_jitter(seed, KB_PAN_JITTER, seed=2)
    py    = int((1 - t) * (20 + pan_y))
    left  = (W - nw) // 2
    top   = max(0, min(py + (H - nh) // 2, H - nh))

    return base_img.crop((left, top, left + nw, top + nh)).resize(
        (W, H), Image.LANCZOS
    )
