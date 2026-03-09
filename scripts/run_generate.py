#!/usr/bin/env python3
"""
scripts/run_generate.py
動画生成を実行し、サムネイル抽出・BGM合成・Drive保存・URL取得を行う
"""
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    selection  = json.loads(os.environ.get("SELECTION", "{}"))
    conditions = json.loads(os.environ.get("CONDITIONS", "{}"))

    poem        = selection.get("poem", "")
    video_id    = selection.get("video_id", "")
    filter_name = selection.get("filter_name", "写ルンです")
    emotion_tags_str = selection.get("emotion_tags", "")
    emotion_tags = [t.strip() for t in emotion_tags_str.split("・") if t.strip()]

    # 動画素材をDriveからダウンロード
    bg_path = download_video_asset(video_id)

    # 動画生成
    output_path_silent = "/tmp/tameiki_silent.mp4"
    output_path        = "/tmp/tameiki_output.mp4"
    thumbnail_path     = "/tmp/tameiki_thumb.jpg"
    print(f"動画生成開始: {filter_name} / {emotion_tags}", flush=True)
    from generate import generate
    success = generate(
        text         = poem,
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

    # BGMをダウンロードして合成
    bgm_path = download_bgm(
        os.environ.get("SPREADSHEET_ID", ""),
        os.environ.get("GOOGLE_CREDENTIALS", "")
    )
    if bgm_path:
        merge_bgm(output_path_silent, bgm_path, output_path)
    else:
        # BGMなしの場合はそのまま使用
        import shutil
        shutil.copy(output_path_silent, output_path)
        print("BGMなしで続行", flush=True)

    # サムネイル抽出
    extract_thumbnail(output_path, thumbnail_path, poem)

    video_url = output_path
    print(f"success=true")
    print(f"video_path={output_path}")
    print(f"thumbnail_path={thumbnail_path}")
    print(f"video_url={video_url}")

    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"VIDEO_URL={video_url}\n")


def download_bgm(spreadsheet_id, creds_json_str):
    """スプレッドシートからBGMを選んでダウンロード"""
    if not spreadsheet_id or not creds_json_str:
        return None
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        import io

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets = build("sheets", "v4", credentials=creds)
        drive  = build("drive", "v3", credentials=creds)

        # BGMシートから有効なBGMを取得
        result = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="BGM!A:L"
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            print("BGMが登録されていません", flush=True)
            return None

        # ステータスが「有効」のBGMを選ぶ
        candidates = []
        for row in rows[1:]:
            if len(row) >= 12 and row[11] == "有効":
                candidates.append({"file_id": row[1], "file_name": row[0], "use_count": int(row[9]) if row[9] else 0})

        if not candidates:
            print("有効なBGMがありません", flush=True)
            return None

        # 使用回数が少ない順に選ぶ
        candidates.sort(key=lambda x: x["use_count"])
        bgm = candidates[0]

        output_path = f"/tmp/bgm_{bgm['file_id'][:8]}{os.path.splitext(bgm['file_name'])[1]}"
        if os.path.exists(output_path):
            return output_path

        print(f"BGMをダウンロード中: {bgm['file_name']}", flush=True)
        request = drive.files().get_media(fileId=bgm["file_id"])
        with open(output_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        print(f"BGMダウンロード完了: {output_path}", flush=True)
        return output_path

    except Exception as e:
        print(f"BGMダウンロードエラー（スキップ）: {e}", flush=True)
        return None


def merge_bgm(video_path, bgm_path, output_path, video_duration=20.0):
    """動画にBGMを合成する（BGMをループ・フェードアウト付き）"""
    try:
        fade_out_start = video_duration - 2.0
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-t", str(video_duration),
            "-filter_complex",
            f"[1:a]afade=t=out:st={fade_out_start}:d=2.0,volume=0.7[bgm]",
            "-map", "0:v",
            "-map", "[bgm]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"BGM合成エラー: {result.stderr}", flush=True)
            import shutil
            shutil.copy(video_path, output_path)
        else:
            print(f"BGM合成完了: {output_path}", flush=True)
    except Exception as e:
        print(f"BGM合成例外（スキップ）: {e}", flush=True)
        import shutil
        shutil.copy(video_path, output_path)


def download_video_asset(file_id):
    """Google DriveからDL"""
    if not file_id:
        return os.path.join(os.path.dirname(__file__), "..", "assets", "default_bg.jpg")

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io

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
