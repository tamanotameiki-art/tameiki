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

    poem_lines  = wrap_poem(poem)
    poem_wrapped = "\n".join(poem_lines)
    print(f"詩（改行後）:\n{poem_wrapped}", flush=True)

    bg_path = download_video_asset(video_id)

    output_path_silent = "/tmp/tameiki_silent.mp4"
    output_path        = "/tmp/tameiki_output.mp4"
    thumbnail_path     = "/tmp/tameiki_thumb.jpg"
    print(f"動画生成開始: {filter_name} / {emotion_tags}", flush=True)
    from generate import generate
    success = generate(
        text         = poem_wrapped,
        bg_path      = bg_path,
        filter_name  = filter_name,
        emotion_tags = emotion_tags,
        output_path  = output_path_silent,
        frames_dir   = "/tmp/tameiki_frames",
        seed         = hash(poem + filter_name) % 10000,
    )
    if not success:
        print("動画生成失敗", flush=True)
        print("success=false")
        return

    creds_str      = os.environ.get("GOOGLE_CREDENTIALS", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    bgm_info = download_bgm(spreadsheet_id, creds_str)
    se_paths = download_se(spreadsheet_id, creds_str, emotion_tags)

    merge_audio(output_path_silent, bgm_info["path"] if bgm_info else None, se_paths, output_path)

    extract_thumbnail(output_path, thumbnail_path, poem_wrapped)

    # BGM使用回数をインクリメント
    if bgm_info and bgm_info.get("row"):
        increment_bgm_use_count(spreadsheet_id, creds_str, bgm_info["row"], bgm_info["use_count"])

    video_url = output_path
    print(f"success=true")
    print(f"video_path={output_path}")
    print(f"thumbnail_path={thumbnail_path}")
    print(f"video_url={video_url}")
    print(f"poem_first_line={poem_lines[0]}")
    print(f"bgm_title={bgm_info['title'] if bgm_info else ''}")

    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"VIDEO_URL={video_url}\n")
        f.write(f"BGM_TITLE={bgm_info['title'] if bgm_info else ''}\n")


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
    環境音: -28 LUFS相当（うっすら漂う程度）
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
        inputs += ["-stream_loop", "-1", "-i", bgm_path]
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
        se_vol  = calc_volume_factor(se_lufs, -28.0)
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


def download_bgm(spreadsheet_id, creds_json_str):
    """スプレッドシートからBGMを重み付きランダム選択してダウンロード"""
    if not spreadsheet_id or not creds_json_str:
        return None
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

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
            # H列(index=7)にマスタリング済みDrive ID、なければB列(index=1)の元ファイルIDを使用
            mastered_id = row[7] if len(row) > 7 and row[7] else ""
            original_id = row[1] if len(row) > 1 else ""
            file_id     = mastered_id if mastered_id else original_id
            file_name   = row[0] if len(row) > 0 else "bgm.wav"
            title       = row[2] if len(row) > 2 else file_name
            use_count   = int(row[9]) if len(row) > 9 and row[9] else 0
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
            print("使用可能なBGMがありません（マスタリング待ちの曲は処理後に使用可能になります）", flush=True)
            return None

        # 使用回数が少ない曲ほど選ばれやすい重み付きランダム選択
        min_count = min(c["use_count"] for c in candidates)
        max_count = max(c["use_count"] for c in candidates)
        if max_count == min_count:
            bgm = random.choice(candidates)
        else:
            weights = [1.0 / (c["use_count"] - min_count + 1) for c in candidates]
            bgm = random.choices(candidates, weights=weights, k=1)[0]

        print(f"BGM選択: {bgm['title']} (使用回数: {bgm['use_count']})", flush=True)

        ext = os.path.splitext(bgm["file_name"])[1] or ".wav"
        output_path = f"/tmp/bgm_{bgm['file_id'][:8]}{ext}"
        if os.path.exists(output_path):
            bgm["path"] = output_path
            return bgm

        print(f"BGMをダウンロード中: {bgm['file_name']}", flush=True)
        request = drive.files().get_media(fileId=bgm["file_id"])
        with open(output_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        print(f"BGMダウンロード完了: {output_path}", flush=True)
        bgm["path"] = output_path
        return bgm

    except Exception as e:
        print(f"BGMダウンロードエラー（スキップ）: {e}", flush=True)
        return None


def download_se(spreadsheet_id, creds_json_str, emotion_tags):
    """スプレッドシートから環境音を最大2本選んでダウンロード"""
    if not spreadsheet_id or not creds_json_str:
        return []
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

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
            range="環境音!A:L"
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            print("環境音が登録されていません", flush=True)
            return []

        scored = []
        for row in rows[1:]:
            if len(row) < 2 or not row[1]:
                continue
            file_id   = row[1]
            file_name = row[0]
            use_count = int(row[10]) if len(row) > 10 and row[10] else 0
            se_tags   = [str(row[i]) for i in range(3, 9) if i < len(row) and row[i]]
            score = sum(1 for et in emotion_tags if any(et in st for st in se_tags))
            scored.append({"file_id": file_id, "file_name": file_name, "score": score, "use_count": use_count})

        scored.sort(key=lambda x: (-x["score"], x["use_count"]))

        se_paths = []
        for se in scored[:2]:
            ext = os.path.splitext(se["file_name"])[1]
            output_path = f"/tmp/se_{se['file_id'][:8]}{ext}"
            if not os.path.exists(output_path):
                print(f"環境音をダウンロード中: {se['file_name']}", flush=True)
                request = drive.files().get_media(fileId=se["file_id"])
                with open(output_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
            se_paths.append(output_path)
            print(f"環境音ダウンロード完了: {se['file_name']}", flush=True)

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


def extract_thumbnail(video_path, thumb_path, poem):
    """サムネイル抽出"""
    from config import TEXT_DELAY, CHAR_INTERVAL
    first_line = poem.split("\n")[0]
    t = TEXT_DELAY + len(first_line) * CHAR_INTERVAL + 0.5
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path
    ]
    subprocess.run(cmd, capture_output=True)
    print(f"サムネイル抽出: {t:.1f}秒地点 → {thumb_path}", flush=True)


if __name__ == "__main__":
    main()
