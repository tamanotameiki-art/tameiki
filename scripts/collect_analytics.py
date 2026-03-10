"""
collect_analytics.py
YouTube・Instagram の反応数を収集してスプレッドシートの投稿履歴シートに記録する
ヘッダーが不足している場合は自動追加する
翌朝 8:00 JST に GitHub Actions から実行される
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ── 定数 ──────────────────────────────────────────────
JST = timezone(timedelta(hours=9))
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
YOUTUBE_CHANNEL_ID = "UCE8QDag3lHM80xIyEGe9_5w"
INSTAGRAM_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
MAX_VIDEOS = 30

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# 不足していれば自動追加する列
REQUIRED_COLUMNS = [
    "YouTubeいいね数",
    "YouTubeコメント数",
    "Instagramいいね数",
    "Instagramコメント数",
    "Instagramインプレッション",
    "収集日時",
]

# ── Google Sheets 接続 ────────────────────────────────
def get_sheet():
    creds_json = os.environ["GOOGLE_CREDENTIALS"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)

# ── ヘッダー確認・自動追加 ────────────────────────────
def ensure_headers(sheet):
    headers = sheet.row_values(1)
    current_cols = sheet.col_count
    needed_cols = len(headers) + len(REQUIRED_COLUMNS)
    if needed_cols > current_cols:
        sheet.add_cols(needed_cols - current_cols)
        print(f"[Sheet] 列を{needed_cols - current_cols}列追加しました")
    for col_name in REQUIRED_COLUMNS:
        if col_name not in headers:
            next_col = len(headers) + 1
            sheet.update_cell(1, next_col, col_name)
            headers.append(col_name)
            print(f"[Sheet] 列追加: {col_name}")
    return headers

# ── YouTube: 直近N本の動画IDを取得 ────────────────────
def get_recent_video_ids(n=MAX_VIDEOS):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YOUTUBE_API_KEY,
        "channelId": YOUTUBE_CHANNEL_ID,
        "part": "id",
        "order": "date",
        "maxResults": n,
        "type": "video",
    }
    res = requests.get(url, params=params).json()
    if "error" in res:
        print(f"[YouTube] search error: {res['error']}")
        return []
    return [item["id"]["videoId"] for item in res.get("items", [])]

# ── YouTube: 動画の統計情報を取得 ─────────────────────
def get_video_stats(video_ids):
    if not video_ids:
        return {}
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YOUTUBE_API_KEY,
        "id": ",".join(video_ids),
        "part": "statistics,snippet",
    }
    res = requests.get(url, params=params).json()
    if "error" in res:
        print(f"[YouTube] videos error: {res['error']}")
        return {}
    stats = {}
    for item in res.get("items", []):
        vid = item["id"]
        s = item["statistics"]
        snippet = item["snippet"]
        stats[vid] = {
            "title": snippet.get("title", ""),
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0)),
        }
    return stats

# ── Instagram: ユーザーIDを取得 ───────────────────────
def get_instagram_user_id():
    url = "https://graph.instagram.com/me"
    params = {
        "fields": "id,username",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    res = requests.get(url, params=params).json()
    if "error" in res:
        print(f"[Instagram] user id error: {res['error']}")
        return None
    return res.get("id")

# ── Instagram: 直近N本のメディア統計を取得 ─────────────
def get_instagram_media_stats(user_id, n=MAX_VIDEOS):
    url = f"https://graph.instagram.com/{user_id}/media"
    params = {
        "fields": "id,timestamp,like_count,comments_count",
        "limit": n,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    res = requests.get(url, params=params).json()
    if "error" in res:
        print(f"[Instagram] media error: {res['error']}")
        return []
    result = []
    for media in res.get("data", []):
        insights = get_instagram_insights(media["id"])
        result.append({
            "id": media["id"],
            "timestamp": media.get("timestamp", ""),
            "likes": media.get("like_count", 0),
            "comments": media.get("comments_count", 0),
            "impressions": insights.get("impressions", 0),
            "saved": insights.get("saved", 0),
        })
    return result

# ── Instagram: インサイト取得 ──────────────────────────
def get_instagram_insights(media_id):
    url = f"https://graph.instagram.com/{media_id}/insights"
    params = {
        "metric": "impressions,saved",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    res = requests.get(url, params=params).json()
    if "error" in res:
        return {"impressions": 0, "saved": 0}
    return {item["name"]: item["values"][0]["value"] for item in res.get("data", [])}

# ── スプレッドシート更新 ───────────────────────────────
def update_spreadsheet(yt_stats, ig_stats):
    book = get_sheet()
    try:
        sheet = book.worksheet("投稿履歴")
    except gspread.WorksheetNotFound:
        print("[Sheet] 投稿履歴シートが見つかりません")
        return

    headers = ensure_headers(sheet)
    col_map = {h: i+1 for i, h in enumerate(headers)}
    now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    all_values = sheet.get_all_values()

    yt_id_col = col_map.get("YouTube投稿ID")
    ig_id_col = col_map.get("Instagram投稿ID")

    # YouTube更新
    yt_count = 0
    if yt_id_col:
        for row_idx, row_data in enumerate(all_values[1:], start=2):
            if len(row_data) < yt_id_col:
                continue
            cell_val = row_data[yt_id_col - 1]
            for vid, stat in yt_stats.items():
                if vid in cell_val:
                    updates = []
                    for col_name, value in [
                        ("YouTube再生数", stat["views"]),
                        ("YouTubeいいね数", stat["likes"]),
                        ("YouTubeコメント数", stat["comments"]),
                        ("収集日時", now_jst),
                    ]:
                        if col_name in col_map:
                            updates.append({
                                "range": gspread.utils.rowcol_to_a1(row_idx, col_map[col_name]),
                                "values": [[value]]
                            })
                    if updates:
                        sheet.batch_update(updates)
                        yt_count += 1
                    break
    print(f"[YouTube] {yt_count}件更新")

    # Instagram更新
    ig_count = 0
    if ig_id_col:
        for row_idx, row_data in enumerate(all_values[1:], start=2):
            if len(row_data) < ig_id_col:
                continue
            cell_val = row_data[ig_id_col - 1]
            for media in ig_stats:
                if media["id"] in cell_val:
                    updates = []
                    for col_name, value in [
                        ("Instagram再生数", media["impressions"]),
                        ("Instagramいいね数", media["likes"]),
                        ("Instagramコメント数", media["comments"]),
                        ("Instagramインプレッション", media["impressions"]),
                        ("Instagram保存数", media["saved"]),
                        ("収集日時", now_jst),
                    ]:
                        if col_name in col_map:
                            updates.append({
                                "range": gspread.utils.rowcol_to_a1(row_idx, col_map[col_name]),
                                "values": [[value]]
                            })
                    if updates:
                        sheet.batch_update(updates)
                        ig_count += 1
                    break
    print(f"[Instagram] {ig_count}件更新")

# ── メイン ────────────────────────────────────────────
def main():
    print("=== collect_analytics.py 開始 ===")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')} JST")

    # YouTube
    print("\n--- YouTube ---")
    video_ids = get_recent_video_ids(MAX_VIDEOS)
    print(f"動画ID取得: {len(video_ids)}本")
    yt_stats = get_video_stats(video_ids)
    print(f"統計取得: {len(yt_stats)}本")
    for vid, s in list(yt_stats.items())[:3]:
        print(f"  {s['title'][:30]}: 再生{s['views']} いいね{s['likes']} コメント{s['comments']}")

    # Instagram
    print("\n--- Instagram ---")
    user_id = get_instagram_user_id()
    if user_id:
        print(f"ユーザーID: {user_id}")
        ig_stats = get_instagram_media_stats(user_id, MAX_VIDEOS)
        print(f"メディア取得: {len(ig_stats)}件")
        for m in ig_stats[:3]:
            print(f"  {m['timestamp'][:10]}: いいね{m['likes']} コメント{m['comments']} 保存{m['saved']}")
    else:
        ig_stats = []
        print("Instagram ユーザーID取得失敗")

    # スプレッドシート更新
    print("\n--- スプレッドシート更新 ---")
    update_spreadsheet(yt_stats, ig_stats)

    print("\n=== 完了 ===")

if __name__ == "__main__":
    main()