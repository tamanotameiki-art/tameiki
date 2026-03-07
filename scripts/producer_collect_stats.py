#!/usr/bin/env python3
"""
scripts/producer_collect_stats.py
各SNSのパフォーマンスデータを収集してスプレッドシートに記録
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
now = datetime.now(JST)


def get_sheets_service():
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = sa.Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


def collect_x_stats(post_ids):
    """X（Twitter）の再生数・保存数を取得"""
    token = os.environ.get("X_BEARER_TOKEN", "")
    if not token or not post_ids:
        return {}

    results = {}
    for post_id in post_ids[:10]:  # APIレート制限対策
        try:
            url = f"https://api.twitter.com/2/tweets/{post_id}"
            params = {
                "tweet.fields": "public_metrics,non_public_metrics",
            }
            r = requests.get(url, headers={
                "Authorization": f"Bearer {token}"
            }, params=params, timeout=10)

            if r.status_code == 200:
                data = r.json().get("data", {})
                metrics = data.get("public_metrics", {})
                results[post_id] = {
                    "plays":      metrics.get("impression_count", 0),
                    "likes":      metrics.get("like_count", 0),
                    "retweets":   metrics.get("retweet_count", 0),
                    "bookmarks":  metrics.get("bookmark_count", 0),
                }
        except Exception as e:
            print(f"X stats エラー ({post_id}): {e}", flush=True)

    return results


def collect_youtube_stats(video_ids):
    """YouTube Shortsの再生数・視聴維持率を取得"""
    creds_json = os.environ.get("YOUTUBE_CREDENTIALS", "")
    if not creds_json or not video_ids:
        return {}

    try:
        import google.oauth2.credentials
        from googleapiclient.discovery import build

        creds_info = json.loads(creds_json)
        creds = google.oauth2.credentials.Credentials(
            token=creds_info.get("token"),
            refresh_token=creds_info.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_info.get("client_id"),
            client_secret=creds_info.get("client_secret"),
        )
        youtube = build("youtube", "v3", credentials=creds)

        ids_str = ",".join(video_ids[:50])
        result  = youtube.videos().list(
            part="statistics",
            id=ids_str
        ).execute()

        stats = {}
        for item in result.get("items", []):
            vid_id = item["id"]
            s = item.get("statistics", {})
            stats[vid_id] = {
                "plays":     int(s.get("viewCount",    0)),
                "likes":     int(s.get("likeCount",    0)),
                "comments":  int(s.get("commentCount", 0)),
                "saves":     int(s.get("favoriteCount",0)),
            }
        return stats

    except Exception as e:
        print(f"YouTube stats エラー: {e}", flush=True)
        return {}


def collect_instagram_stats(media_ids):
    """Instagramの再生数・保存数を取得"""
    token      = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    account_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")
    if not token or not media_ids:
        return {}

    GRAPH_URL = "https://graph.facebook.com/v18.0"
    results   = {}

    for media_id in media_ids[:20]:
        try:
            r = requests.get(
                f"{GRAPH_URL}/{media_id}/insights",
                params={
                    "metric": "plays,saved,reach,likes",
                    "access_token": token,
                },
                timeout=10
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                metric_map = {d["name"]: d.get("values", [{}])[0].get("value", 0)
                              for d in data}
                results[media_id] = {
                    "plays": metric_map.get("plays", 0),
                    "saves": metric_map.get("saved", 0),
                    "reach": metric_map.get("reach", 0),
                    "likes": metric_map.get("likes", 0),
                }
        except Exception as e:
            print(f"Instagram stats エラー ({media_id}): {e}", flush=True)

    return results


def update_history_stats(service, spreadsheet_id,
                          x_stats, yt_stats, ig_stats):
    """投稿履歴シートの数字を更新"""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="投稿履歴!A2:L"
    ).execute()
    rows = result.get("values", [])

    updates = []
    for i, row in enumerate(rows):
        row_num = i + 2
        x_id  = row[8]  if len(row) > 8  else ""
        yt_id = row[9]  if len(row) > 9  else ""
        ig_id = row[10] if len(row) > 10 else ""

        row_updates = {}

        if x_id and x_id in x_stats:
            s = x_stats[x_id]
            row_updates[13] = s.get("plays", 0)    # M列: X再生数
            row_updates[17] = s.get("bookmarks", 0) # Q列: X保存数

        if yt_id and yt_id in yt_stats:
            s = yt_stats[yt_id]
            row_updates[14] = s.get("plays", 0)    # N列: YouTube再生数
            row_updates[18] = s.get("saves", 0)    # R列: YouTube保存数

        if ig_id and ig_id in ig_stats:
            s = ig_stats[ig_id]
            row_updates[15] = s.get("plays", 0)    # O列: Instagram再生数
            row_updates[19] = s.get("saves", 0)    # S列: Instagram保存数

        for col_idx, value in row_updates.items():
            col_letter = chr(ord('A') + col_idx)
            updates.append({
                "range": f"投稿履歴!{col_letter}{row_num}",
                "values": [[value]]
            })

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": updates
            }
        ).execute()
        print(f"パフォーマンスデータ更新: {len(updates)}件", flush=True)


def main():
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
    if not spreadsheet_id:
        return

    service = get_sheets_service()

    # 投稿履歴からID一覧を取得
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="投稿履歴!I2:K"
    ).execute()
    rows = result.get("values", [])

    x_ids  = [r[0] for r in rows if len(r) > 0 and r[0]]
    yt_ids = [r[1] for r in rows if len(r) > 1 and r[1]]
    ig_ids = [r[2] for r in rows if len(r) > 2 and r[2]]

    print(f"収集対象: X={len(x_ids)}件 YouTube={len(yt_ids)}件 Instagram={len(ig_ids)}件", flush=True)

    # 各SNSのデータ収集
    x_stats  = collect_x_stats(x_ids[-30:])    # 直近30件
    yt_stats = collect_youtube_stats(yt_ids[-50:])
    ig_stats = collect_instagram_stats(ig_ids[-30:])

    # 履歴を更新
    update_history_stats(service, spreadsheet_id, x_stats, yt_stats, ig_stats)

    print("パフォーマンスデータ収集完了", flush=True)


if __name__ == "__main__":
    main()
