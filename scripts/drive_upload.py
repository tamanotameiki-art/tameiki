#!/usr/bin/env python3
"""
scripts/drive_upload.py — Google Drive一時アップロード共通モジュール

動画をDriveの一時保管フォルダにアップロードし、公開URLを返す。
投稿完了後は delete_drive_file() で即削除すること。
"""
import os
import json
import time

TEMP_FOLDER_ID = "1wFWo7a6kYrkyGQCfrQhanrGd3tr2EW-7"


def get_drive_service():
    """Google Drive APIクライアントを返す"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS が設定されていません")

    creds_info = json.loads(creds_json)
    creds = sa.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def upload_video_to_drive(video_path, filename=None):
    """
    動画ファイルをDriveの一時フォルダにアップロードし、
    公開URL と file_id を返す。

    Returns:
        dict: {"url": str, "file_id": str}
    """
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

    drive = get_drive_service()

    if not filename:
        timestamp = int(time.time())
        filename = f"tameiki_temp_{timestamp}.mp4"

    print(f"Driveに動画をアップロード中: {filename}", flush=True)

    file_metadata = {
        "name": filename,
        "parents": [TEMP_FOLDER_ID],
    }
    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10  # 10MB chunks
    )

    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file["id"]
    print(f"Driveアップロード完了: file_id={file_id}", flush=True)

    # 全員が読み取り可能な共有設定にする
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    print("Drive共有設定完了（anyone/reader）", flush=True)

    # 直接ダウンロードURL（Instagram/Pinterestが取り込める形式）
    public_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    return {"url": public_url, "file_id": file_id}


def delete_drive_file(file_id):
    """
    DriveのファイルをIDで削除する。
    投稿完了後に必ず呼ぶこと。
    """
    if not file_id:
        return
    try:
        drive = get_drive_service()
        drive.files().delete(fileId=file_id).execute()
        print(f"Drive一時ファイル削除完了: {file_id}", flush=True)
    except Exception as e:
        print(f"Drive一時ファイル削除エラー（スキップ）: {e}", flush=True)
