#!/usr/bin/env python3
"""
scripts/bgm_download.py
Google DriveからBGMファイルをダウンロードする
"""
import os
import json

def main():
    file_id   = os.environ["FILE_ID"]
    file_name = os.environ["FILE_NAME"]

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

    output_path = f"/tmp/{file_name}"
    print(f"ダウンロード中: {file_name} ({file_id})", flush=True)

    request = drive.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"  {int(status.progress() * 100)}%", flush=True)

    print(f"ダウンロード完了: {output_path}", flush=True)

if __name__ == "__main__":
    main()
