#!/usr/bin/env python3
"""
scripts/run_generate.py
動画生成を実行し、サムネイル抽出・BGM合成・環境音合成・Drive保存・URL取得を行う
"""
import os
import sys
import json
import random
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def wrap_poem(text, max_lines=5):
    """句読点・意味の切れ目で詩を自動改行（2〜5行）"""
    if "\n" in text:
        lines = text.split("\n")
        if 2 <= len(lines) <= max_lines:
            return lines

    segments = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。、…―！？":
            segments.append(buf)
            buf = ""
    if buf:
        segments.append(buf)

    if len(segments) <= 1:
        n = len(text)
        num_lines = min(max_lines, max(2, round(n / 10)))
        chunk = max(1, n // num_lines)
        segments = [text[i:i+chunk] for i in range(0, n, chunk)]

    total_chars = len(text)
    target_lines = min(max_lines, max(2, round(total_chars / 10)))

    while len(segments) > target_lines:
        min_len = float('inf')
        min_idx = 0
        for i in range(len(segments) - 1):
            combined = len(segments[i]) + len(segments[i+1])
            if combined < min_len:
                min_len = combined
                min_idx = i
        segments[min_idx] = segments[min_idx] + segments[min_idx+1]
        segments.pop(min_idx + 1)

    i = 0
    while i < len(segments):
        if len(segments[i].strip()) <= 2 and len(segments) > 2:
            if i == 0:
                segments[1] = segments[0] + segments[1]
                segments.pop(0)
            else:
                segments[i-1] = segments[i-1] + segments[i]
                segments.pop(i)
        else:
            i += 1

    return segments


def measure_rms_lufs(path):
    """ffmpegでRMS/LUFSを測定して返す（dB値）"""
    cmd = [
        "ffmpeg", "-i", path,
        "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    import re
    m = re.search(r'"input_i"\s*:\s*"([-\d.]+)"', r.stderr)
    if m:
        return float(m.group(1))
    return -14.0


def calc_volume_factor(measured_lufs, target_lufs):
    """測定値とターゲットの差からvolumeフィルターの倍率を計算"""
    diff = target_lufs - measured_lufs
    factor = 10 ** (diff / 20.0)
    return max(0.05, min(2.0, factor))


def main():
    selection  = json.loads(os.environ.get("SELECTION", "{}"))
    conditions = json.loads(os.environ.get("CONDITIONS", "{}"))

    poem        = selection.get("poem", "")
    video_id    = selection.get("video_id", "")
    filter_name = selection.get("filter_name", "写ルンです")
    emotion_tags_str = selection.get("emotion_tags", "")
    emotion_tags = [t.strip() for t in emotion_tags_str.split("・") if t.strip()]
    se_list     = selection.get("se_list", [])

    poem_lines   = wrap_poem(poem)
    poem_wrapped = "\n".join(poem_lines)
    poem_first_line = poem_lines[0]
    print(f"詩（改行後）:\n{poem_wrapped}", flush=True)

    bg_path = download_video_asset(video_id)

    output_path_silent = "/tmp/tameiki_silent.mp4"
    output_path        = "/tmp/tameiki_output.mp4"
    thumbnail_path     = "/tmp/tameiki_thumb.jpg"
    print(f"動画生成開始: {filter_name} / {emotion_tags}", flush=True)

    from generate import generate, calc_total_sec
    from config import FPS, TEXT_DELAY, CHAR_FADEIN_SEC

    actual_total_sec = calc_total_sec(poem_lines)

    success = generate(
        text         = poem_wrapped,
        bg_path      = bg_path,
        filter_name  = filter_name,
        emotion_tags = emotion_tags,
        output_path  = output_path_silent,
        frames_dir   = "/tmp/tameiki_frames",
        seed         = hash(poem + filter_name) % 10000,
        total_sec    = actual_total_sec,
    )
    if not success:
        print("動画生成失敗", flush=True)
        print("success=false")
        return

    creds_str      = os.environ.get("GOOGLE_CREDENTIALS", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    bgm_info = download_bgm(spreadsheet_id, creds_str, actual_total_sec)
    se_paths = download_se(spreadsheet_id, creds_str, se_list)

    merge_audio(output_path_silent, bgm_info["path"] if bgm_info else None,
                se_paths, output_path, video_duration=actual_total_sec)

    generate_thumbnail(bg_path, thumbnail_path, poem_first_line, filter_name)

    if bgm_info and bgm_info.get("row"):
        increment_bgm_use_count(spreadsheet_id, creds_str, bgm_info["row"], bgm_info["use_count"])

    print(f"success=true")
    print(f"video_path={output_path}")
    print(f"thumbnail_path={thumbnail_path}")
    print(f"video_url={output_path}")
    print(f"poem_first_line={poem_first_line}")
    print(f"poem_wrapped={poem_wrapped}")
    print(f"bgm_title={bgm_info['title'] if bgm_info else ''}")

    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"VIDEO_URL={output_path}\n")
        f.write(f"BGM_TITLE={bgm_info['title'] if bgm_info else ''}\n")


def generate_thumbnail(bg_path, thumb_path, first_line, filter_name):
    """
    サムネイルを静止画として生成。
    背景の中間フレームにフィルターをかけ、1行目を縦書きで中央に大きく表示。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import numpy as np
        from config import W, H, FONT_PATH, FONT_IDX, C_TEXT, PUNCT_OFFSET, ROTATE_CHARS
        from filters import apply_filter
        from background import (
            prepare_bg, is_video_file, extract_video_frames, load_video_frame
        )

        # 背景を1フレーム取得
        if is_video_file(bg_path):
            frames_dir = "/tmp/thumb_bgframes"
            extract_video_frames(bg_path, frames_dir, total_frames=60, fps=24)
            bg = load_video_frame(frames_dir, 30)  # 中間フレーム
            import shutil
            shutil.rmtree(frames_dir, ignore_errors=True)
        else:
            from background import prepare_bg, crop_and_resize
            bg = prepare_bg(bg_path)

        # フィルター適用
        frame = apply_filter(bg, filter_name, frame_idx=0)
        frame = frame.convert("RGBA")

        # 少し暗くして文字を際立たせる
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 60))
        frame = Image.alpha_composite(frame, overlay)

        # テキストレイヤー生成（縦書き・中央・大きめ）
        txt_layer = draw_thumbnail_text(first_line)
        frame = Image.alpha_composite(frame, txt_layer)

        frame.convert("RGB").save(thumb_path, quality=95)
        print(f"サムネイル生成完了: {thumb_path}", flush=True)

    except Exception as e:
        print(f"サムネイル生成エラー（スキップ）: {e}", flush=True)
        # フォールバック：動画の最初のフレームから切り出し
        cmd = [
            "ffmpeg", "-y", "-ss", "4.0",
            "-i", "/tmp/tameiki_output.mp4",
            "-vframes", "1", "-q:v", "2", thumb_path
        ]
        subprocess.run(cmd, capture_output=True)


def draw_thumbnail_text(first_line):
    """
    1行目を縦書きで画面中央に大きく描画したレイヤーを返す。
    フォントサイズは動画より大きめ（最大72px）。
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from config import W, H, FONT_PATH, FONT_IDX, C_TEXT, PUNCT_OFFSET, ROTATE_CHARS

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    # フォントサイズ：文字数に応じて調整（大きめに）
    n_chars   = len(first_line)
    font_size = max(48, min(72, int(720 / max(n_chars, 5))))
    char_gap  = int(font_size * 1.25)

    font = ImageFont.truetype(FONT_PATH, font_size, index=FONT_IDX)

    # 縦書き中央配置
    total_h = (n_chars - 1) * char_gap + font_size
    sx = W // 2  # 列は1列なので中央
    sy = H // 2 - total_h // 2

    for ci, ch in enumerate(first_line):
        x = sx - font_size // 2
        y = sy + ci * char_gap

        # 句読点オフセット
        if ch in PUNCT_OFFSET:
            dx_ratio, dy_ratio = PUNCT_OFFSET[ch]
            x += int(font_size * dx_ratio)
            y += int(font_size * dy_ratio)

        # 延ばし棒・ダッシュ系は回転
        if ch in ROTATE_CHARS:
            tmp = Image.new("RGBA", (font_size + 10, font_size + 10), (0, 0, 0, 0))
            td  = ImageDraw.Draw(tmp)
            td.text((0, 0), ch, font=font, fill=(*C_TEXT, 255))
            rotated = tmp.rotate(90, expand=True)
            layer.paste(rotated, (x, y), rotated)
        else:
            # テキストシャドウ（読みやすさ向上）
            d.text((x + 2, y + 2), ch, font=font, fill=(0, 0, 0, 120))
            d.text((x, y), ch, font=font, fill=(*C_TEXT, 255))

    # ほんのりグロー
    glow = layer.filter(ImageFilter.GaussianBlur(radius=3))
    result = Image.alpha_composite(glow, layer)
    return result


def increment_bgm_use_count(spreadsheet_id, creds_json_str, row, current_count):
    """BGMの使用回数をJ列にインクリメント"""
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheets = build("sheets", "v4", credentials=creds)
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"BGM!J{row}",
            valueInputOption="RAW",
            body={"values": [[current_count + 1]]}
        ).execute()
        print(f"BGM使用回数更新: {current_count} → {current_count + 1} (行{row})", flush=True)
    except Exception as e:
        print(f"BGM使用回数更新エラー（スキップ）: {e}", flush=True)


def merge_audio(video_path, bgm_path, se_paths, output_path, video_duration=20.0):
    """
    動画にBGM＋環境音を合成する。
    BGM: -20 LUFS相当（詩の邪魔をしない音量）
    環境音: -32 LUFS相当（さりげなく漂う程度）
    """
    import shutil

    fade_out_start = video_duration - 2.0

    inputs = ["-i", video_path]
    filter_parts = []
    audio_labels = []
    input_idx = 1

    if bgm_path and os.path.exists(bgm_path):
        bgm_lufs = measure_rms_lufs(bgm_path)
        bgm_vol  = calc_volume_factor(bgm_lufs, -20.0)
        print(f"BGM LUFS: {bgm_lufs:.1f} → volume={bgm_vol:.3f}", flush=True)
        inputs += ["-i", bgm_path]
        filter_parts.append(
            f"[{input_idx}:a]"
            f"volume={bgm_vol:.3f},"
            f"afade=t=out:st={fade_out_start}:d=2.0"
            f"[bgm]"
        )
        audio_labels.append("[bgm]")
        input_idx += 1
    else:
        print("BGMなし", flush=True)

    for i, se_path in enumerate(se_paths[:2]):
        if not se_path or not os.path.exists(se_path):
            continue
        se_lufs = measure_rms_lufs(se_path)
        se_vol  = calc_volume_factor(se_lufs, -32.0)
        label   = f"se{i+1}"
        print(f"環境音{i+1} LUFS: {se_lufs:.1f} → volume={se_vol:.3f}", flush=True)
        inputs += ["-stream_loop", "-1", "-i", se_path]
        filter_parts.append(
            f"[{input_idx}:a]"
            f"volume={se_vol:.3f},"
            f"afade=t=out:st={fade_out_start}:d=2.0"
            f"[{label}]"
        )
        audio_labels.append(f"[{label}]")
        input_idx += 1

    if not audio_labels:
        shutil.copy(video_path, output_path)
        print("音声素材なし・動画をそのまま使用", flush=True)
        return

    n = len(audio_labels)
    mix_inputs = "".join(audio_labels)
    filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={n}:duration=first:normalize=0[aout]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-t", str(video_duration),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"音声合成エラー: {result.stderr[-500:]}", flush=True)
        shutil.copy(video_path, output_path)
    else:
        print(f"音声合成完了: BGM×1 + 環境音×{len(se_paths)}", flush=True)


def download_bgm(spreadsheet_id, creds_json_str, clip_duration=20.0):
    """スプレッドシートからBGMをランダム選択・マスタリング・切り出しして返す"""
    if not spreadsheet_id or not creds_json_str:
        return None
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        import librosa
        import numpy as np
        import warnings

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets = build("sheets", "v4", credentials=creds)
        drive  = build("drive",  "v3", credentials=creds)

        result = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="BGM!A:L"
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            print("BGMが登録されていません", flush=True)
            return None

        candidates = []
        for i, row in enumerate(rows[1:], start=2):
            status = row[11] if len(row) >= 12 else ""
            if status != "有効":
                continue
            file_id   = row[1] if len(row) > 1 else ""
            file_name = row[0] if len(row) > 0 else "bgm.wav"
            title     = row[2] if len(row) > 2 else file_name
            use_count = int(row[9]) if len(row) > 9 and row[9] else 0
            if not file_id:
                continue
            candidates.append({
                "file_id":   file_id,
                "file_name": file_name,
                "title":     title,
                "use_count": use_count,
                "row":       i,
            })

        if not candidates:
            print("使用可能なBGMがありません", flush=True)
            return None

        min_count = min(c["use_count"] for c in candidates)
        max_count = max(c["use_count"] for c in candidates)
        if max_count == min_count:
            bgm = random.choice(candidates)
        else:
            weights = [1.0 / (c["use_count"] - min_count + 1) for c in candidates]
            bgm = random.choices(candidates, weights=weights, k=1)[0]

        print(f"BGM選択: {bgm['title']} (使用回数: {bgm['use_count']})", flush=True)

        ext = os.path.splitext(bgm["file_name"])[1] or ".m4a"
        raw_path = f"/tmp/bgm_raw_{bgm['file_id'][:8]}{ext}"
        if not os.path.exists(raw_path):
            print(f"BGMをダウンロード中: {bgm['file_name']}", flush=True)
            request = drive.files().get_media(fileId=bgm["file_id"])
            with open(raw_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            print(f"BGMダウンロード完了: {raw_path}", flush=True)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                y, sr = librosa.load(raw_path, sr=22050, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
            print(f"BGM長さ: {duration:.1f}秒", flush=True)

            if duration <= clip_duration + 2.0:
                start_sec = 0.0
                print("短い音源のためそのまま使用", flush=True)
            else:
                hop_length = 512
                rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
                rms_threshold = np.percentile(rms, 20)

                max_start = duration - clip_duration - 1.0
                valid_starts = []
                for t in np.arange(0.0, max_start, 0.5):
                    frame_start = int(t * sr / hop_length)
                    frame_end   = int((t + 5.0) * sr / hop_length)
                    segment_rms = rms[frame_start:frame_end]
                    if len(segment_rms) > 0 and np.mean(segment_rms) > rms_threshold:
                        valid_starts.append(float(t))

                if valid_starts:
                    start_sec = random.choice(valid_starts)
                    print(f"ランダム開始点: {start_sec:.1f}秒 (候補{len(valid_starts)}点)", flush=True)
                else:
                    start_sec = random.uniform(0.0, max_start)
                    print(f"有効候補なし・完全ランダム: {start_sec:.1f}秒", flush=True)

        except Exception as e:
            print(f"BGM解析エラー（フォールバック）: {e}", flush=True)
            start_sec = 0.0

        work_dir = f"/tmp/bgm_work_{bgm['file_id'][:8]}"
        os.makedirs(work_dir, exist_ok=True)

        wav_path = f"{work_dir}/00_raw.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_path,
            "-ar", "44100", "-ac", "2", wav_path
        ], capture_output=True)

        eq_path = f"{work_dir}/01_eq.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-af", (
                "equalizer=f=80:t=o:w=1:g=2,"
                "equalizer=f=300:t=o:w=1:g=-1,"
                "equalizer=f=3000:t=o:w=1:g=1.5,"
                "equalizer=f=10000:t=o:w=1:g=2,"
                "equalizer=f=16000:t=o:w=1:g=1.5"
            ),
            eq_path
        ], capture_output=True)
        print("EQ完了", flush=True)

        comp_path = f"{work_dir}/02_comp.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", eq_path,
            "-af", "acompressor=threshold=-18dB:ratio=3:attack=20:release=200:makeup=3dB",
            comp_path
        ], capture_output=True)
        print("コンプ完了", flush=True)

        sat_path = f"{work_dir}/03_sat.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", comp_path,
            "-af", "asoftclip=type=tanh:threshold=0.95:output=0.93",
            sat_path
        ], capture_output=True)
        print("サチュレーション完了", flush=True)

        rev_path = f"{work_dir}/04_rev.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", sat_path,
            "-af", "aecho=in_gain=1.0:out_gain=0.95:delays=40|52:decays=0.28|0.20",
            rev_path
        ], capture_output=True)
        print("リバーブ完了", flush=True)

        stereo_path = f"{work_dir}/05_stereo.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", rev_path,
            "-af", "stereotools=mlev=0.8,stereotools=sbal=0:slev=0.9",
            stereo_path
        ], capture_output=True)
        print("ステレオ処理完了", flush=True)

        mastered_path = f"{work_dir}/06_mastered.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", stereo_path,
            "-af", "loudnorm=I=-14.0:TP=-1.0:LRA=11",
            mastered_path
        ], capture_output=True)
        print("ラウドネス正規化完了", flush=True)

        clip_path = f"{work_dir}/07_clip.wav"
        fade_out_start = clip_duration - 2.0
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(clip_duration),
            "-i", mastered_path,
            "-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_start}:d=2.0",
            clip_path
        ], capture_output=True)
        print(f"切り出し完了: {start_sec:.1f}秒〜{start_sec + clip_duration:.1f}秒", flush=True)

        bgm["path"] = clip_path
        return bgm

    except Exception as e:
        print(f"BGMダウンロードエラー（スキップ）: {e}", flush=True)
        return None


def download_se(spreadsheet_id, creds_json_str, se_list):
    """
    select_assets.pyで選ばれたse_listの音源をダウンロード。
    - 音量チェック: -6 LUFS以上（大きすぎ）または -50 LUFS以下（小さすぎ）はスキップ
    - 使用回数（K列）をインクリメント
    - 最終使用日（M列）を記録
    """
    if not spreadsheet_id or not creds_json_str or not se_list:
        return []
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        from datetime import datetime, timezone, timedelta

        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST).isoformat()

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets = build("sheets", "v4", credentials=creds)
        drive  = build("drive",  "v3", credentials=creds)

        result = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="環境音!A:M"
        ).execute()
        all_rows = result.get("values", [])

        se_paths = []
        for se in se_list:
            file_id   = se.get("file_id", "")
            file_name = se.get("file_name", "")
            row_idx   = se.get("row_idx")
            if not file_id:
                continue

            ext = os.path.splitext(file_name)[1] or ".wav"
            output_path = f"/tmp/se_{file_id[:8]}{ext}"
            if not os.path.exists(output_path):
                print(f"環境音をダウンロード中: {file_name}", flush=True)
                request = drive.files().get_media(fileId=file_id)
                with open(output_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                print(f"環境音ダウンロード完了: {file_name}", flush=True)

            lufs = measure_rms_lufs(output_path)
            print(f"環境音 LUFS確認: {file_name} = {lufs:.1f} LUFS", flush=True)
            if lufs > -6.0:
                print(f"  ⚠ 音量大きすぎ（{lufs:.1f} LUFS）スキップ: {file_name}", flush=True)
                os.remove(output_path)
                continue
            if lufs < -50.0:
                print(f"  ⚠ 音量小さすぎ（{lufs:.1f} LUFS）スキップ: {file_name}", flush=True)
                os.remove(output_path)
                continue

            se_paths.append(output_path)

            if row_idx:
                try:
                    row_data = all_rows[row_idx - 1] if row_idx - 1 < len(all_rows) else []
                    current_count = int(row_data[10]) if len(row_data) > 10 and row_data[10] else 0
                    sheets.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f"環境音!K{row_idx}",
                        valueInputOption="RAW",
                        body={"values": [[current_count + 1]]}
                    ).execute()
                    sheets.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f"環境音!M{row_idx}",
                        valueInputOption="RAW",
                        body={"values": [[now_jst]]}
                    ).execute()
                    print(f"  環境音記録更新: {file_name} 使用回数{current_count}→{current_count+1}", flush=True)
                except Exception as e:
                    print(f"  環境音記録更新エラー（スキップ）: {e}", flush=True)

        return se_paths

    except Exception as e:
        print(f"環境音ダウンロードエラー（スキップ）: {e}", flush=True)
        return []


def download_video_asset(file_id):
    """Google DriveからDL"""
    if not file_id:
        return os.path.join(os.path.dirname(__file__), "..", "assets", "default_bg.jpg")

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    drive = build("drive", "v3", credentials=creds)

    output_path = f"/tmp/tameiki_bg_{file_id[:8]}.mp4"
    if os.path.exists(output_path):
        return output_path

    print(f"背景動画をDriveからダウンロード中: {file_id}", flush=True)
    request = drive.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    return output_path


if __name__ == "__main__":
    main()
