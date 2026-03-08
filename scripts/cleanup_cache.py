#!/usr/bin/env python3
"""キャッシュ削除スクリプト"""
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

def main():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not creds_json:
        print("GOOGLE_CREDENTIALS未設定、スキップ")
        return

    try:
        creds_info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive = build("drive", "v3", credentials=creds)

        # tameiki_cacheフォルダを検索
        results = drive.files().list(
            q="name='tameiki_cache' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)"
        ).execute()
        folders = results.get("files", [])
        if not folders:
            print("キャッシュフォルダが見つかりません")
            return

        folder_id = folders[0]["id"]

        # フォルダ内のファイルを取得
        files = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            orderBy="createdTime",
            fields="files(id, name, createdTime)"
        ).execute().get("files", [])

        # 30件を超えた古いファイルを削除
        if len(files) > 30:
            to_delete = files[:len(files) - 30]
            for f in to_delete:
                drive.files().delete(fileId=f["id"]).execute()
                print(f"削除: {f['name']}")
        else:
            print(f"キャッシュ件数: {len(files)}件（削除不要）")

    except Exception as e:
        print(f"キャッシュ削除エラー（続行）: {e}")

if __name__ == "__main__":
    main()
