#!/usr/bin/env python3
"""
scripts/record_history.py — 投稿履歴をスプレッドシートに記録
"""
import os
import json
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def main():
    selection  = json.loads(os.environ.get("SELECTION", "{}"))
    post_ids   = json.loads(os.environ.get("POST_IDS", "{}"))
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    if not spreadsheet_id:
        return

    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    se_list = selection.get("se_list", [])
    se_names = [s.get("kind", "") for s in se_list]
    while len(se_names) < 3:
        se_names.append("")

    row = [
        now,
        selection.get("poem", ""),
        selection.get("video_name", ""),
        selection.get("filter_name", ""),
        "",  # BGMタイトル（後で更新）
        se_names[0], se_names[1], se_names[2],
        post_ids.get("x", ""),
        post_ids.get("youtube", ""),
        post_ids.get("instagram", ""),
        "",  # TikTok（手動投稿のため後で記録）
        0, 0, 0, 0,  # 再生数（後でパフォーマンス収集時に更新）
        0, 0, 0,     # 保存数
        "", "",      # 週間・月間ベスト
    ]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="投稿履歴!A:U",
        valueInputOption="RAW",
        body={"values": [row]}
    ).execute()

    # 詩の投稿回数を更新
    poem_row_idx = selection.get("poem_row_idx")
    if poem_row_idx:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"文字列!L{poem_row_idx}"
        ).execute()
        current_count = int(result.get("values", [[0]])[0][0] or 0)

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"文字列!L{poem_row_idx}:N{poem_row_idx}",
            valueInputOption="RAW",
            body={"values": [[current_count + 1, now, f"{now} / {selection.get('video_name','')} / {selection.get('filter_name','')}"]]}
        ).execute()

        # ステータスを「投稿済み」に更新
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"文字列!O{poem_row_idx}",
            valueInputOption="RAW",
            body={"values": [["投稿済み"]]}
        ).execute()

    print("投稿履歴記録完了", flush=True)


if __name__ == "__main__":
    main()


# ======================================================================
# scripts/notify_line.py — LINE通知
# ======================================================================

import sys
import argparse
import requests as req

def notify_line():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type",    required=True)
    parser.add_argument("--poem",    default="")
    parser.add_argument("--filter",  default="")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    token = os.environ.get("LINE_NOTIFY_TOKEN", "")
    if not token:
        print("LINE_NOTIFY_TOKEN未設定", flush=True)
        return

    if args.type == "posted":
        first_line = args.poem.split("\n")[0][:20] if args.poem else ""
        message = f"\n投稿しました。\n\n「{first_line}」\n\nコメントを確認してください。"

    elif args.type == "error":
        message = f"\n⚠️ {args.message}"

    elif args.type == "bgm_ready":
        message = f"\nBGMのマスタリングが完了しました。\n\nこの曲のタイトルを返信してください。"

    else:
        message = f"\n{args.message}"

    req.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {token}"},
        data={"message": message}
    )
    print(f"LINE通知送信: {args.type}", flush=True)


# ======================================================================
# scripts/cleanup_cache.py — 動画キャッシュ管理（最新30本を保持）
# ======================================================================

def cleanup_cache():
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
    if not creds_json:
        return

    try:
        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        drive = build("drive", "v3", credentials=creds)

        # キャッシュフォルダの動画一覧を取得（作成日時順）
        folders = drive.files().list(
            q="name='tameiki_cache' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute().get("files", [])

        if not folders:
            return

        folder_id = folders[0]["id"]
        files = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType='video/mp4'",
            orderBy="createdTime",
            fields="files(id,name,createdTime)"
        ).execute().get("files", [])

        # 30本を超えた場合、古いものから削除
        if len(files) > 30:
            to_delete = files[:-30]
            for f in to_delete:
                drive.files().delete(fileId=f["id"]).execute()
                print(f"古いキャッシュを削除: {f['name']}", flush=True)

    except Exception as e:
        print(f"キャッシュ管理エラー（スキップ）: {e}", flush=True)


# エントリーポイントの切り替え
if __name__ == "__main__":
    script_name = os.path.basename(sys.argv[0])
    if "notify" in script_name:
        notify_line()
    elif "cleanup" in script_name:
        cleanup_cache()
    else:
        main()
