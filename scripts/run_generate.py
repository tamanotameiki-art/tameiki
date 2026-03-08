#!/usr/bin/env python3
"""
scripts/run_generate.py
動画生成を実行し、サムネイル抽出・Drive保存・URL取得を行う
"""
import os
import sys
import json
import subprocess
import tempfile

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
    output_path   = "/tmp/tameiki_output.mp4"
    thumbnail_path = "/tmp/tameiki_thumb.jpg"

    print(f"動画生成開始: {filter_name} / {emotion_tags}", flush=True)

 import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generate import generate
    success = generate(
        text          = poem,
        bg_path       = bg_path,
        filter_name   = filter_name,
        emotion_tags  = emotion_tags,
        output_path   = output_path,
        frames_dir    = "/tmp/tameiki_frames",
        seed          = hash(poem + filter_name) % 10000,
    )

    if not success:
        print("動画生成失敗", flush=True)
        print("success=false")
        return

    # サムネイル抽出（1行目テキスト表示完了フレーム）
    extract_thumbnail(output_path, thumbnail_path, poem)

    # DriveにアップロードしてURLを取得
    video_url = upload_to_drive(output_path, f"tameiki_{conditions.get('date','')}.mp4")

    print(f"success=true")
    print(f"video_path={output_path}")
    print(f"thumbnail_path={thumbnail_path}")
    print(f"video_url={video_url}")

    # 環境変数に設定（post_instagram.pyが参照）
    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"VIDEO_URL={video_url}\n")


def download_video_asset(file_id):
    """Google DriveからDL"""
    if not file_id:
        # デフォルト背景（静止画）
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
    """
    サムネイル抽出：1行目の最後の文字が表示された瞬間のフレーム
    TEXT_DELAY + (1行目の文字数 * CHAR_INTERVAL) 秒地点
    """
    from config import TEXT_DELAY, CHAR_INTERVAL

    first_line = poem.split("\n")[0]
    t = TEXT_DELAY + len(first_line) * CHAR_INTERVAL + 0.5  # 少し余裕

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


def upload_to_drive(file_path, file_name):
    """DrivにアップロードしてURLを返す"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)

    # キャッシュフォルダに保存
    folders = drive.files().list(
        q="name='tameiki_cache' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id)"
    ).execute().get("files", [])

    folder_id = folders[0]["id"] if folders else None

    metadata = {"name": file_name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    file = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id,webContentLink"
    ).execute()

    # 公開アクセスを設定
    drive.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"}
    ).execute()

    url = f"https://drive.google.com/uc?id={file['id']}"
    print(f"Drive URL: {url}", flush=True)
    return url


if __name__ == "__main__":
    main()


# ======================================================================
# scripts/prepare_tiktok.py
# TikTok用ファイルをiPhoneショートカット経由で投稿できるよう準備
# ======================================================================
"""
TikTokは公式APIが制限されているため、
生成した動画とキャプションをDriveの専用フォルダに保存し
iPhoneショートカットから投稿する半自動フロー。
"""

import os
import json

def prepare_tiktok():
    video_path  = os.environ.get("VIDEO_PATH", "")
    caption     = os.environ.get("CAPTION", "")

    if not video_path:
        return

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)

    # TikTok専用フォルダを探す
    folders = drive.files().list(
        q="name='tameiki_tiktok' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id)"
    ).execute().get("files", [])

    folder_id = folders[0]["id"] if folders else None

    # 動画をアップロード
    metadata = {"name": "tiktok_today.mp4"}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(video_path, mimetype="video/mp4")
    drive.files().create(body=metadata, media_body=media).execute()

    # キャプションをテキストファイルとして保存
    caption_metadata = {"name": "tiktok_caption.txt"}
    if folder_id:
        caption_metadata["parents"] = [folder_id]

    import io
    from googleapiclient.http import MediaIoBaseUpload
    caption_bytes = caption.encode("utf-8")
    media_caption = MediaIoBaseUpload(
        io.BytesIO(caption_bytes),
        mimetype="text/plain"
    )
    drive.files().create(
        body=caption_metadata,
        media_body=media_caption
    ).execute()

    print("TikTok用ファイルをDriveに保存しました", flush=True)
    print("iPhoneショートカットから投稿してください", flush=True)
