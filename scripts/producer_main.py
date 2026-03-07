#!/usr/bin/env python3
"""
scripts/producer_main.py
AIプロデューサーのメインエンジン

- 自動ブラッシュアップ（毎日・通知なし）
- 週次レポート（毎週月曜・LINE通知）
- 月次レポート（毎月1日・LINE通知）
- 世界観の継続的学習・偏り検知
"""
import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
now = datetime.now(JST)

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_MODEL   = "claude-sonnet-4-20250514"


# ===== Sheets API =====
def get_sheets_service():
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


def get_range(service, spreadsheet_id, range_str):
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range_str
    ).execute()
    return result.get("values", [])


def set_range(service, spreadsheet_id, range_str, values):
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": values}
    ).execute()


def get_config(service, spreadsheet_id):
    rows = get_range(service, spreadsheet_id, "設定!A2:C")
    return {r[0]: r[1] for r in rows if len(r) >= 2}


def set_config(service, spreadsheet_id, key, value):
    rows = get_range(service, spreadsheet_id, "設定!A:A")
    for i, row in enumerate(rows):
        if row and row[0] == key:
            set_range(service, spreadsheet_id, f"設定!B{i+1}", [[value]])
            return


# ===== データ収集 =====
def get_recent_history(service, spreadsheet_id, days=30):
    rows  = get_range(service, spreadsheet_id, "投稿履歴!A2:U")
    cutoff = now - timedelta(days=days)
    recent = []
    for row in rows:
        if not row:
            continue
        try:
            post_date = datetime.fromisoformat(row[0].replace(" ", "T"))
            if post_date.replace(tzinfo=JST) >= cutoff:
                recent.append(row)
        except:
            recent.append(row)  # パースできない場合は含める
    return recent


def get_all_poems(service, spreadsheet_id):
    rows = get_range(service, spreadsheet_id, "文字列!A2:O")
    return [{"poem": r[0], "tags": r[1:11], "count": r[11] if len(r) > 11 else 0}
            for r in rows if r and r[0]]


def get_world_view(service, spreadsheet_id):
    """世界観定義を取得"""
    rows = get_range(service, spreadsheet_id, "設定!A:B")
    for row in rows:
        if row and row[0] == "world_view":
            return row[1] if len(row) > 1 else ""
    return ""


def set_world_view(service, spreadsheet_id, world_view):
    """世界観定義を更新"""
    rows = get_range(service, spreadsheet_id, "設定!A:A")
    for i, row in enumerate(rows):
        if row and row[0] == "world_view":
            set_range(service, spreadsheet_id, f"設定!B{i+1}", [[world_view]])
            return
    # なければ追記
    last = len(rows) + 1
    set_range(service, spreadsheet_id, f"設定!A{last}:B{last}",
              [["world_view", world_view]])


# ===== Claude API =====
def ask_claude(prompt, max_tokens=2000):
    if not CLAUDE_API_KEY:
        return ""
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
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Claude APIエラー: {e}", flush=True)
        return ""


def ask_claude_json(prompt, max_tokens=1000):
    text = ask_claude(prompt, max_tokens)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return {}


# ===== 自動ブラッシュアップ =====
def run_brushup(service, spreadsheet_id, history, poems, config):
    """
    毎日自動で微調整。通知なし。
    大きな変化ではなくパラメータの微調整のみ。
    """
    print("自動ブラッシュアップ開始...", flush=True)

    if not history:
        print("履歴データなし → スキップ", flush=True)
        return

    # 直近7日のデータ
    recent_7 = history[-7:] if len(history) >= 7 else history

    # パフォーマンス集計
    def safe_int(v):
        try:
            return int(v)
        except:
            return 0

    plays_by_filter = {}
    for row in recent_7:
        filter_name = row[3] if len(row) > 3 else ""
        plays = sum([
            safe_int(row[12] if len(row) > 12 else 0),
            safe_int(row[13] if len(row) > 13 else 0),
            safe_int(row[14] if len(row) > 14 else 0),
        ])
        if filter_name:
            plays_by_filter[filter_name] = plays_by_filter.get(filter_name, 0) + plays

    # 投稿時間の最適化（直近14日の曜日×時間帯パフォーマンス）
    # → 現状維持（大きな変更はLINE提案）

    # ハッシュタグの更新（トレンドタグは今後外部API連携）
    # → 現状維持

    # 世界観定義の自動追記（詩の傾向から）
    update_world_view(service, spreadsheet_id, poems)

    print("自動ブラッシュアップ完了", flush=True)


def update_world_view(service, spreadsheet_id, poems):
    """詩の傾向から世界観定義を自動更新"""
    if len(poems) < 10:
        return  # 最低10本の詩が必要

    poem_texts = "\n---\n".join([p["poem"] for p in poems[-50:]])
    current_wv = get_world_view(service, spreadsheet_id)

    prompt = f"""
以下の詩を分析して、このアカウントの「世界観定義」を更新してください。

【現在の世界観定義】
{current_wv or "（未設定）"}

【詩の一覧（最新50本）】
{poem_texts}

分析して以下のJSON形式で回答してください：
{{
  "頻出感情": ["孤独", "哀愁", ...],
  "頻出意象": ["月", "雨", "窓", ...],
  "文体の特徴": "文末が体言止め・余白が多い...",
  "よく使う表現": ["〜のように", "〜を残して", ...],
  "世界観の核心": "一文で表現した本質",
  "新しい世界観定義": "現在の定義を踏まえて追記・更新した文章（200字以内）"
}}
"""

    result = ask_claude_json(prompt, max_tokens=800)
    if result and result.get("新しい世界観定義"):
        set_world_view(service, spreadsheet_id, result["新しい世界観定義"])
        print(f"世界観定義を更新しました", flush=True)


# ===== 週次レポート =====
def run_weekly_report(service, spreadsheet_id, history, poems):
    """毎週月曜日にLINEに送る3行サマリー + AIからの一言"""
    print("週次レポート生成中...", flush=True)

    recent = history[-7:] if len(history) >= 7 else history

    # 数字集計
    def safe_int(v):
        try: return int(v)
        except: return 0

    total_plays = sum(
        safe_int(r[12] if len(r) > 12 else 0) +
        safe_int(r[13] if len(r) > 13 else 0) +
        safe_int(r[14] if len(r) > 14 else 0)
        for r in recent
    )
    post_count = len(recent)

    # 今週のベスト投稿（再生数合計）
    best_row   = max(recent, key=lambda r: (
        safe_int(r[12] if len(r) > 12 else 0) +
        safe_int(r[13] if len(r) > 13 else 0) +
        safe_int(r[14] if len(r) > 14 else 0)
    ), default=None)
    best_poem   = best_row[1][:20] if best_row and len(best_row) > 1 else ""
    best_filter = best_row[3]      if best_row and len(best_row) > 3 else ""

    # 天気・タグ傾向
    weather_counts = {}
    for row in recent:
        # タグは詩シートと突合する必要があるが、簡易的にフィルターで代用
        f = row[3] if len(row) > 3 else ""
        weather_counts[f] = weather_counts.get(f, 0) + 1
    top_filter = max(weather_counts, key=weather_counts.get, default="")

    # Claudeにプロデューサー視点の一言を生成
    prompt = f"""
あなたは詩人「たまのためいき。」の音楽プロデューサーです。
今週のデータを見て、プロデューサーとして一言コメントしてください。

今週のデータ:
- 投稿数: {post_count}本
- 総再生数: {total_plays:,}回
- 最も再生された詩: 「{best_poem}」（{best_filter}フィルター）
- 最も使ったフィルター: {top_filter}

コメントは2〜3文で、編集者が作家に送るような文体で。
データの読み解き + 来週への提案 を含める。
LINEに送るのでMarkdown不要・絵文字なし。
"""

    comment = ask_claude(prompt, max_tokens=300)

    # サマリー3行
    summary_lines = [
        f"今週: {post_count}本投稿・{total_plays:,}回再生",
        f"ベスト: 「{best_poem}」",
        f"よく使ったフィルター: {top_filter}",
    ]
    summary = "\n".join(summary_lines)

    message = f"\n今週のサマリー\n\n{summary}\n\n---\n{comment}"
    send_line(message)
    print("週次レポート送信完了", flush=True)


# ===== 月次レポート =====
def run_monthly_report(service, spreadsheet_id, history, poems):
    """毎月1日に詳細な月次レポートをLINEに送る"""
    print("月次レポート生成中...", flush=True)

    recent_30 = history[-30:] if len(history) >= 30 else history

    def safe_int(v):
        try: return int(v)
        except: return 0

    # 数字集計
    total_plays = sum(
        safe_int(r[12] if len(r) > 12 else 0) +
        safe_int(r[13] if len(r) > 13 else 0) +
        safe_int(r[14] if len(r) > 14 else 0)
        for r in recent_30
    )
    post_count  = len(recent_30)
    unpublished = sum(1 for p in poems if p.get("count") == 0 or p.get("count") == "0")

    # フィルター別パフォーマンス
    filter_plays = {}
    for row in recent_30:
        f = row[3] if len(row) > 3 else "不明"
        plays = (safe_int(row[12] if len(row) > 12 else 0) +
                 safe_int(row[13] if len(row) > 13 else 0) +
                 safe_int(row[14] if len(row) > 14 else 0))
        filter_plays[f] = filter_plays.get(f, 0) + plays

    top_filters = sorted(filter_plays.items(), key=lambda x: -x[1])[:3]

    # 詩の傾向分析（Claude）
    poem_sample = "\n---\n".join([p["poem"] for p in poems[-30:]])
    analysis_prompt = f"""
以下の詩（最新30本）を分析してください。

{poem_sample}

以下をJSON形式で答えてください：
{{
  "頻出感情タグ": ["哀愁", ...],
  "頻出キーワード": ["月", "雨", ...],
  "文体の変化": "3ヶ月前と比べた変化の傾向",
  "強み": "このアカウントが持つ独自性",
  "来月の提案": "次の1ヶ月で試してみてほしいこと（詩の方向性・実験）"
}}
"""
    analysis = ask_claude_json(analysis_prompt, max_tokens=600)

    # 月次レポート本文
    top_filter_text = "、".join([f"{f}（{p:,}再生）" for f, p in top_filters])
    report_lines = [
        f"今月: {post_count}本投稿・{total_plays:,}再生",
        f"未投稿在庫: {unpublished}本",
        f"好調フィルター: {top_filter_text}",
        "",
        f"詩の傾向: {', '.join(analysis.get('頻出感情タグ', []))}",
        f"よく出る意象: {', '.join(analysis.get('頻出キーワード', []))}",
        "",
        f"強み: {analysis.get('強み', '')}",
        "",
        f"来月の提案:\n{analysis.get('来月の提案', '')}",
    ]

    message = "\n今月のレポート\n\n" + "\n".join(report_lines)

    # 素材収集のサマリーも追記
    message += f"\n\n在庫が少ない場合は素材追加をお願いします（目安: 各30本以上）"

    send_line(message)
    print("月次レポート送信完了", flush=True)

    # 偏り検知 → 素材収集の方向性を更新
    detect_and_update_bias(service, spreadsheet_id, analysis)


def detect_and_update_bias(service, spreadsheet_id, analysis):
    """
    詩の傾向の偏りを検知して、素材収集の方向性を世界観定義に追記
    偏りが強まる = ブランド化
    """
    emotion_tags = analysis.get("頻出感情タグ", [])
    keywords     = analysis.get("頻出キーワード", [])

    if not emotion_tags:
        return

    bias_note = (
        f"【自動更新: {now.strftime('%Y-%m')}】"
        f"頻出感情={','.join(emotion_tags[:3])} "
        f"頻出意象={','.join(keywords[:5])}"
    )

    current_wv = get_world_view(service, spreadsheet_id)
    # 前月の自動更新があれば差し替え
    new_wv = re.sub(r'【自動更新:.*?】[^\n]*', '', current_wv).strip()
    new_wv = f"{new_wv}\n{bias_note}".strip()
    set_world_view(service, spreadsheet_id, new_wv)
    print(f"偏り検知・世界観更新: {bias_note}", flush=True)


# ===== LINE通知 =====
def send_line(message):
    token = os.environ.get("LINE_NOTIFY_TOKEN", "")
    if not token:
        print(f"LINE通知（未送信）:\n{message}", flush=True)
        return
    requests.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {token}"},
        data={"message": message}
    )


# ===== メイン =====
def main():
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
    mode           = os.environ.get("MODE", "brushup")

    if not spreadsheet_id:
        print("SPREADSHEET_ID未設定", flush=True)
        return

    service = get_sheets_service()
    history = get_recent_history(service, spreadsheet_id, days=60)
    poems   = get_all_poems(service, spreadsheet_id)
    config  = get_config(service, spreadsheet_id)

    print(f"実行モード: {mode}", flush=True)
    print(f"履歴: {len(history)}件 詩: {len(poems)}本", flush=True)

    if mode == "brushup":
        run_brushup(service, spreadsheet_id, history, poems, config)

    elif mode == "weekly":
        run_brushup(service, spreadsheet_id, history, poems, config)  # 毎日の処理も実行
        run_weekly_report(service, spreadsheet_id, history, poems)

    elif mode == "monthly":
        run_brushup(service, spreadsheet_id, history, poems, config)
        run_monthly_report(service, spreadsheet_id, history, poems)

    elif mode == "full_analysis":
        run_brushup(service, spreadsheet_id, history, poems, config)
        run_weekly_report(service, spreadsheet_id, history, poems)
        run_monthly_report(service, spreadsheet_id, history, poems)


if __name__ == "__main__":
    main()
