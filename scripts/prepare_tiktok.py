#!/usr/bin/env python3
"""
scripts/prepare_tiktok.py
TikTok用ファイルをiPhoneショートカット経由で投稿できるよう準備

TikTokは公式APIが制限されているため、
生成した動画とキャプションをDriveの専用フォルダに保存し
iPhoneショートカットから投稿する半自動フロー。
"""
import os
import io
import json

def main():
    video_path = os.environ.get("VIDEO_PATH", "")
    caption    = os.environ.get("CAPTION", "")

    if not video_path or not os.path.exists(video_path):
        print("動画ファイルが見つかりません。スキップ", flush=True)
        return

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    drive = build("drive", "v3", credentials=creds)

    # TikTok専用フォルダID直接指定
    folder_id = "14F-s_vz5blc6Vu3dhEzehPm2CixSAaE9"

    # 動画をアップロード
    metadata = {"name": "tiktok_today.mp4", "parents": [folder_id]}
    media = MediaFileUpload(video_path, mimetype="video/mp4")
    drive.files().create(body=metadata, media_body=media).execute()

    # キャプションをテキストファイルとして保存
    caption_bytes = caption.encode("utf-8")
    caption_metadata = {"name": "tiktok_caption.txt", "parents": [folder_id]}
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

if __name__ == "__main__":
    main()
