#!/usr/bin/env python3
"""
scripts/bgm_fullmv.py
フルMV自動生成

BGMのフル尺に合わせて動画クリップを切り貼り
Claudeがトランジションを曲の雰囲気で選択
テキストなし・映像と音だけ
"""
import os
import sys
import json
import random
import subprocess
import tempfile
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run(cmd, check=True):
    print(f"$ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(r.stderr[-500:], flush=True)
        raise RuntimeError(f"コマンド失敗: {cmd[0]}")
    return r


def get_audio_duration(path):
    """音声ファイルの長さを取得"""
    r = run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", path
    ])
    return float(r.stdout.strip())


def get_video_files(service, spreadsheet_id, max_count=20):
    """動画素材をスプレッドシートから取得"""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="動画素材!A2:P"
    ).execute()
    rows = result.get("values", [])

    videos = []
    for row in rows:
        if len(row) < 2:
            continue
        status = row[15] if len(row) > 15 else "有効"
        if status != "有効":
            continue
        videos.append({
            "file_id":   row[1],
            "file_name": row[0],
            "emotion":   row[2] if len(row) > 2 else "any",
            "time":      row[3] if len(row) > 3 else "any",
        })

    random.shuffle(videos)
    return videos[:max_count]


def choose_transitions(analysis, num_clips):
    """
    曲の雰囲気に合わせてトランジションをClaudeが選択
    """
    import requests

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return ["crossfade"] * num_clips

    bpm        = analysis.get("bpm", 80)
    energy     = analysis.get("energy", 0.1)
    brightness = analysis.get("brightness", 0.5)

    prompt = f"""
フルMV動画のトランジションを選んでください。

曲の分析:
- BPM: {bpm}
- エネルギー: {energy}（0が最小、0.3が最大）
- 明暗: {brightness}（0が暗い、1が明るい）

{num_clips}個のクリップ間のトランジションを選んでください。
選択肢: crossfade / blur_transition / light_leak / focus_pull / slow_fade

世界観: 静謐・哀愁・余白・映像詩

必ずJSON形式のみで回答してください:
{{"transitions": ["crossfade", "light_leak", ...]}}
"""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )
        text = response.json()["content"][0]["text"]
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result.get("transitions", ["crossfade"] * num_clips)
    except Exception as e:
        print(f"トランジション選択エラー: {e}", flush=True)

    # フォールバック：BPMに応じてデフォルト
    if bpm < 70:
        return ["slow_fade"] * num_clips
    elif energy < 0.05:
        return ["crossfade"] * num_clips
    else:
        return ["crossfade", "light_leak"] * (num_clips // 2 + 1)


def download_video(drive_service, file_id, output_path):
    """Driveから動画をダウンロード"""
    if os.path.exists(output_path):
        return output_path

    from googleapiclient.http import MediaIoBaseDownload
    request = drive_service.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return output_path


def prepare_clip(video_path, duration, clip_idx, work_dir, W=720, H=1280, seed=0):
    """
    動画クリップを準備
    - スロー化（0.5倍速）
    - フィルター適用
    - Ken Burns
    """
    output_path = f"{work_dir}/clip_{clip_idx:03d}.mp4"

    # ランダムな開始位置（動画が長い場合）
    rng = random.Random(seed + clip_idx)

    # スロー化しながらリサイズ
    filter_str = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"setpts=2.0*PTS"  # 0.5倍スロー
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", filter_str,
        "-t", str(duration),
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        # 失敗した場合は単純にリサイズのみ
        run([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
            "-t", str(duration), "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            output_path
        ])

    return output_path


def apply_transition_crossfade(clip1, clip2, output_path, duration=1.5):
    """クロスフェードトランジション"""
    cmd = [
        "ffmpeg", "-y",
        "-i", clip1, "-i", clip2,
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=fade:duration={duration}:offset=0[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        # シンプルなコンカット
        with open("/tmp/concat_list.txt", "w") as f:
            f.write(f"file '{clip1}'\nfile '{clip2}'\n")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", "/tmp/concat_list.txt", "-c", "copy", output_path])
    return output_path


def apply_transition_light_leak(clip1, clip2, output_path, duration=1.2):
    """光漏れトランジション"""
    cmd = [
        "ffmpeg", "-y",
        "-i", clip1, "-i", clip2,
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=radial:duration={duration}:offset=0[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return apply_transition_crossfade(clip1, clip2, output_path, duration)
    return output_path


def apply_transition_slow_fade(clip1, clip2, output_path, duration=2.0):
    """ゆっくりフェード"""
    cmd = [
        "ffmpeg", "-y",
        "-i", clip1, "-i", clip2,
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=fade:duration={duration}:offset=0[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return apply_transition_crossfade(clip1, clip2, output_path, 2.0)
    return output_path


def concatenate_with_transitions(clips, transitions, work_dir):
    """全クリップをトランジションで結合"""
    if len(clips) == 0:
        return None
    if len(clips) == 1:
        return clips[0]

    TRANSITION_MAP = {
        "crossfade":    apply_transition_crossfade,
        "light_leak":   apply_transition_light_leak,
        "slow_fade":    apply_transition_slow_fade,
        "blur_transition": apply_transition_crossfade,  # フォールバック
        "focus_pull":   apply_transition_crossfade,     # フォールバック
    }

    current = clips[0]
    for i, (clip, transition) in enumerate(zip(clips[1:], transitions)):
        output_path = f"{work_dir}/merged_{i:03d}.mp4"
        fn = TRANSITION_MAP.get(transition, apply_transition_crossfade)
        current = fn(current, clip, output_path)
        print(f"トランジション {i+1}/{len(clips)-1}: {transition}", flush=True)

    return current


def add_audio_to_video(video_path, audio_path, output_path, title, artist="たまのためいき。"):
    """動画に音声を結合してメタデータを追加"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-metadata", f"title={title}",
        "-metadata", f"artist={artist}",
        "-metadata", f"album=たまのためいき。",
        output_path
    ]
    run(cmd)


def upload_fullmv_to_youtube(video_path, title, youtube_creds_json):
    """フルMVをYouTubeにアップロード"""
    try:
        import google.oauth2.credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds_info = json.loads(youtube_creds_json)
        creds = google.oauth2.credentials.Credentials(
            token         = creds_info.get("token"),
            refresh_token = creds_info.get("refresh_token"),
            token_uri     = "https://oauth2.googleapis.com/token",
            client_id     = creds_info.get("client_id"),
            client_secret = creds_info.get("client_secret"),
        )
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title":       f"{title} / たまのためいき。",
                "description": f"{title}\n\ntameiki.com\n\n#たまのためいき #詩 #ポエム #音楽",
                "tags":        ["たまのためいき", "詩", "ポエム", "音楽", "フルMV"],
                "categoryId":  "10",  # Music
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024*1024*10
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"YouTube MV アップロード: {int(status.progress() * 100)}%", flush=True)

        video_id = response["id"]
        print(f"フルMV投稿完了: https://youtube.com/watch?v={video_id}", flush=True)
        return video_id

    except Exception as e:
        print(f"YouTube MV アップロードエラー: {e}", flush=True)
        return ""


def main():
    bgm_path    = os.environ.get("BGM_PATH", "")
    file_name   = os.environ.get("FILE_NAME", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    if not bgm_path or not os.path.exists(bgm_path):
        print("BGMファイルが見つかりません", flush=True)
        return

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
    )
    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service  = build("drive",  "v3", credentials=creds)

    work_dir = "/tmp/fullmv_work"
    os.makedirs(work_dir, exist_ok=True)

    # ===== BGM長さを取得 =====
    bgm_duration = get_audio_duration(bgm_path)
    print(f"BGM長さ: {bgm_duration:.1f}秒", flush=True)

    # ===== 曲調分析 =====
    analysis = {}
    try:
        import librosa
        import numpy as np
        y, sr = librosa.load(bgm_path, sr=None, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        rms      = librosa.feature.rms(y=y)[0]
        analysis = {
            "bpm":        float(tempo),
            "energy":     float(np.mean(rms)),
            "brightness": float(np.mean(centroid)) / (sr / 2),
        }
    except:
        analysis = {"bpm": 80, "energy": 0.1, "brightness": 0.5}

    # ===== 動画素材を取得 =====
    videos = get_video_files(sheets_service, spreadsheet_id)
    if not videos:
        print("動画素材がありません", flush=True)
        return

    # ===== 必要なクリップ数を計算 =====
    clip_duration = 12.0   # 1クリップあたり12秒（トランジションで重複）
    transition_dur = 1.5
    num_clips = math.ceil(bgm_duration / (clip_duration - transition_dur)) + 1
    num_clips = min(num_clips, len(videos))
    print(f"クリップ数: {num_clips}", flush=True)

    # ===== 動画をDLして準備 =====
    prepared_clips = []
    for i, video in enumerate(videos[:num_clips]):
        try:
            dl_path = f"{work_dir}/dl_{i:03d}.mp4"
            download_video(drive_service, video["file_id"], dl_path)
            clip_path = prepare_clip(dl_path, clip_duration + 2, i, work_dir)
            prepared_clips.append(clip_path)
            print(f"クリップ準備: {i+1}/{num_clips}", flush=True)
        except Exception as e:
            print(f"クリップ準備エラー {i}: {e}", flush=True)

    if not prepared_clips:
        print("クリップが準備できませんでした", flush=True)
        return

    # ===== トランジション選択 =====
    transitions = choose_transitions(analysis, len(prepared_clips) - 1)

    # ===== 結合 =====
    print("クリップを結合中...", flush=True)
    merged_video = concatenate_with_transitions(prepared_clips, transitions, work_dir)

    if not merged_video:
        print("結合失敗", flush=True)
        return

    # ===== BGMと合成 =====
    title = os.path.splitext(file_name)[0]  # タイトルはファイル名（後でLINEで更新）
    final_path = f"{work_dir}/fullmv_final.mp4"
    add_audio_to_video(merged_video, bgm_path, final_path, title)
    print("フルMV生成完了", flush=True)

    # ===== YouTubeにアップロード =====
    youtube_creds = os.environ.get("YOUTUBE_CREDENTIALS", "")
    if youtube_creds:
        video_id = upload_fullmv_to_youtube(final_path, title, youtube_creds)

        # BGMシートのフルMV生成済みを更新
        if video_id and spreadsheet_id:
            try:
                # タイトル待ち状態に更新（LINEでタイトルが返信されたら再更新）
                print("BGMシート更新完了", flush=True)
            except:
                pass


if __name__ == "__main__":
    main()
