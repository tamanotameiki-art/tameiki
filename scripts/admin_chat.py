#!/usr/bin/env python3
"""
scripts/admin_chat.py
管理画面の埋め込みAIチャットバックエンド

GitHub Pages（静的）からGitHub Actions経由でClaudeに問い合わせる。
スプレッドシートのデータをリアルタイムで参照して回答。

エンドポイント: GitHub Actions workflow_dispatch
→ 管理画面JSからGitHub APIを叩いてworkflowをdispatch
→ 結果をDriveの共有ファイルに書き出し
→ 管理画面がポーリングして表示
"""
import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta

JST            = timezone(timedelta(hours=9))
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_MODEL   = "claude-sonnet-4-20250514"


def get_context(service, spreadsheet_id):
    """スプレッドシートから現在の状態を取得してコンテキストを構築"""

    def get_range(range_str):
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_str
            ).execute()
            return result.get("values", [])
        except:
            return []

    # 最新投稿履歴（直近10件）
    history = get_range("投稿履歴!A2:U")[-10:]
    history_text = "\n".join([
        f"- {r[0]} 「{r[1][:15] if len(r)>1 else ''}」 {r[3] if len(r)>3 else ''} "
        f"/ X:{r[12] if len(r)>12 else 0}再生 YT:{r[13] if len(r)>13 else 0}再生 IG:{r[14] if len(r)>14 else 0}再生"
        for r in history if r
    ])

    # 在庫状況
    poems  = get_range("文字列!A2:O")
    videos = get_range("動画素材!A2:P")
    bgm    = get_range("BGM!A2:L")

    unpublished_poems  = sum(1 for r in poems  if len(r) > 14 and r[14] == "未投稿")
    active_videos      = sum(1 for r in videos if len(r) > 15 and r[15] == "有効")
    available_bgm      = sum(1 for r in bgm    if len(r) > 11 and r[11] != "マスタリング待ち")

    # 世界観定義
    config = get_range("設定!A:B")
    world_view = ""
    for row in config:
        if row and row[0] == "world_view":
            world_view = row[1] if len(row) > 1 else ""

    # 全詩リスト（最新30本）
    poem_texts = "\n".join([r[0] for r in poems[-30:] if r])

    context = f"""
【現在時刻】{datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST

【在庫状況】
- 未投稿の詩: {unpublished_poems}本
- 有効な動画素材: {active_videos}本
- 使用可能BGM: {available_bgm}本

【最近10件の投稿】
{history_text or "データなし"}

【世界観定義】
{world_view or "未設定"}

【最新30本の詩】
{poem_texts}
"""
    return context


def build_system_prompt(context):
    return f"""
あなたは詩人「たまのためいき。」の専属AIプロデューサーです。
運用歴を重ねるごとに深くなる関係性を持ち、創作の歴史を一番よく知る存在です。

このアカウントの世界観・トーン・詩の傾向を深く理解した上で回答してください。

【あなたの役割】
1. システムへの直接指示の解釈・実行（投稿キャンセル・時間変更・フィルター固定）
2. 素材・コンテンツ相談（詩の評価・雰囲気確認・タグ確認）
3. 分析・アドバイス（フォロワー伸び悩み・フィルター反応・SNS別最適化）
4. システム状態の確認・説明

【トーン】
- 少し年上のプロデューサーとして、過度に丁寧にならず自然に話す
- 数字を読む時はそのまま伝え、過度に解釈しない
- 「いいですね」「素晴らしい」など過剰な肯定は避ける
- 必要なら正直に「今週は伸びなかった」と言う

【現在のシステム状態】
{context}
"""


def process_command(message, context):
    """
    コマンド的なメッセージを解釈して実行可能なアクションを返す
    例: 「今日の投稿をキャンセルして」→ GitHub Actionsのキャンセル指示
    """
    # 投稿キャンセル
    if re.search(r'キャンセル|取り消し|やめ', message):
        return {
            "action": "cancel_post",
            "message": "今日の投稿をキャンセルします。GitHub Actionsのワークフローを停止します。"
        }

    # フィルター固定
    filter_match = re.search(
        r'(写ルンです|VHS|燃えたフィルム|ドリーミー|サイレント映画|ゴールデンアワー|'
        r'霧の中|水の底|夜光|色褪せた夏|朝靄|廃墟のロマン|月明かり|インスタント).*?(固定|使って)',
        message
    )
    if filter_match:
        filter_name = filter_match.group(1)
        return {
            "action": "fix_filter",
            "filter": filter_name,
            "message": f"{filter_name}フィルターを次回の投稿に使用します。設定を更新しました。"
        }

    # 投稿時間変更
    time_match = re.search(r'(\d{1,2})[時:](\d{2})?.*?に(変更|直し|して)', message)
    if time_match:
        hour   = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        return {
            "action": "change_time",
            "time":   f"{hour:02d}:{minute:02d}",
            "message": f"投稿時間を{hour}時{minute:02d}分に変更します。"
        }

    return None


def chat(message, history=None):
    """メインチャット処理"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
    creds_json     = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))

    # コンテキスト取得
    context = ""
    if spreadsheet_id and creds_json:
        try:
            creds = sa.Credentials.from_service_account_info(
                creds_json,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
            )
            service = build("sheets", "v4", credentials=creds)
            context = get_context(service, spreadsheet_id)
        except Exception as e:
            print(f"コンテキスト取得エラー: {e}", flush=True)

    # コマンド解釈
    command = process_command(message, context)
    if command:
        execute_command(command, spreadsheet_id, creds_json)

    # Claude に問い合わせ
    system_prompt = build_system_prompt(context)

    messages = []
    if history:
        for turn in history[-10:]:  # 直近10ターンを履歴として渡す
            messages.append({"role": "user",      "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})
    messages.append({"role": "user", "content": message})

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 800,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=30
        )
        response = r.json()["content"][0]["text"].strip()
    except Exception as e:
        response = f"エラーが発生しました: {e}"

    return response, command


def execute_command(command, spreadsheet_id, creds_json):
    """コマンドをスプレッドシートに反映"""
    if not spreadsheet_id or not creds_json:
        return

    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build

        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)

        if command["action"] == "fix_filter":
            # 設定シートのforce_filterを更新
            rows = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range="設定!A:A"
            ).execute().get("values", [])
            for i, row in enumerate(rows):
                if row and row[0] == "force_filter":
                    service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f"設定!B{i+1}",
                        valueInputOption="RAW",
                        body={"values": [[command["filter"]]]}
                    ).execute()
                    break

        elif command["action"] == "change_time":
            rows = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range="設定!A:A"
            ).execute().get("values", [])
            for i, row in enumerate(rows):
                if row and row[0] == "post_time_jst":
                    service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f"設定!B{i+1}",
                        valueInputOption="RAW",
                        body={"values": [[command["time"]]]}
                    ).execute()
                    break

        print(f"コマンド実行: {command['action']}", flush=True)

    except Exception as e:
        print(f"コマンド実行エラー: {e}", flush=True)


def save_response_to_drive(response, command, request_id):
    """レスポンスをDriveに保存（管理画面がポーリングして読む）"""
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        import io

        creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        drive = build("drive", "v3", credentials=creds)

        content = json.dumps({
            "response":   response,
            "command":    command,
            "request_id": request_id,
            "timestamp":  datetime.now(JST).isoformat(),
        }, ensure_ascii=False)

        # 既存ファイルを検索して上書き
        existing = drive.files().list(
            q=f"name='chat_response_{request_id}.json'",
            fields="files(id)"
        ).execute().get("files", [])

        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="application/json"
        )

        if existing:
            drive.files().update(
                fileId=existing[0]["id"],
                media_body=media
            ).execute()
        else:
            folders = drive.files().list(
                q="name='tameiki_admin' and mimeType='application/vnd.google-apps.folder'",
                fields="files(id)"
            ).execute().get("files", [])
            folder_id = folders[0]["id"] if folders else None

            metadata = {"name": f"chat_response_{request_id}.json"}
            if folder_id:
                metadata["parents"] = [folder_id]
            file = drive.files().create(
                body=metadata, media_body=media, fields="id"
            ).execute()
            drive.permissions().create(
                fileId=file["id"],
                body={"type": "anyone", "role": "reader"}
            ).execute()

        print(f"レスポンス保存完了: chat_response_{request_id}.json", flush=True)

    except Exception as e:
        print(f"レスポンス保存エラー: {e}", flush=True)


def main():
    message    = os.environ.get("CHAT_MESSAGE",  "")
    history_js = os.environ.get("CHAT_HISTORY",  "[]")
    request_id = os.environ.get("CHAT_REQUEST_ID", "0")

    if not message:
        print("メッセージが空です", flush=True)
        return

    history = json.loads(history_js)
    print(f"チャットリクエスト: {message[:50]}...", flush=True)

    response, command = chat(message, history)
    print(f"レスポンス: {response[:100]}...", flush=True)

    save_response_to_drive(response, command, request_id)


if __name__ == "__main__":
    main()
