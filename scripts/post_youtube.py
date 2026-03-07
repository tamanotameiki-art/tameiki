#!/usr/bin/env python3
"""
scripts/post_youtube.py — YouTube Shortsへの投稿 + エンドスクリーン設定
"""
import os
import json
import time
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def main():
    creds_json  = json.loads(os.environ["YOUTUBE_CREDENTIALS"])
    video_path  = os.environ["VIDEO_PATH"]
    thumb_path  = os.environ.get("THUMBNAIL_PATH", "")
    caption     = os.environ.get("CAPTION", "")
    poem        = os.environ.get("POEM", "")
    post_date   = os.environ.get("POST_DATE", "")

    # 認証
    creds = google.oauth2.credentials.Credentials(
        token         = creds_json.get("token"),
        refresh_token = creds_json.get("refresh_token"),
        token_uri     = "https://oauth2.googleapis.com/token",
        client_id     = creds_json.get("client_id"),
        client_secret = creds_json.get("client_secret"),
    )
    youtube = build("youtube", "v3", credentials=creds)

    # タイトル（詩の1行目）
    first_line = poem.split("\n")[0][:30] if poem else "たまのためいき。"
    title      = f"{first_line} / たまのためいき。"

    # 動画をアップロード
    print("YouTubeにアップロード中...", flush=True)
    body = {
        "snippet": {
            "title":       title,
            "description": f"{caption}\n\n{poem}\n\n#たまのためいき #shorts #詩 #ポエム #言葉",
            "tags":        ["たまのためいき", "詩", "ポエム", "shorts", "言葉", "朗読"],
            "categoryId":  "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024*1024*10  # 10MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"アップロード進捗: {int(status.progress() * 100)}%", flush=True)

    video_id = response["id"]
    print(f"YouTube投稿完了: {video_id}", flush=True)

    # サムネイル設定
    if thumb_path and os.path.exists(thumb_path):
        print("サムネイルを設定中...", flush=True)
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg")
            ).execute()
            print("サムネイル設定完了", flush=True)
        except Exception as e:
            print(f"サムネイル設定エラー（スキップ）: {e}", flush=True)

    # エンドスクリーン設定（動画終了5秒前から）
    print("エンドスクリーンを設定中...", flush=True)
    try:
        time.sleep(5)  # 処理待ち
        set_end_screen(youtube, video_id)
    except Exception as e:
        print(f"エンドスクリーン設定エラー（スキップ）: {e}", flush=True)

    print(f"video_id={video_id}")


def set_end_screen(youtube, video_id):
    """エンドスクリーン：チャンネル登録ボタン + おすすめ動画"""
    body = {
        "items": [
            {
                "type": "SUBSCRIBE",
                "startOffsetMs": 15000,  # 15秒から（20秒動画の場合5秒前）
                "endOffsetMs":   20000,
                "position": {
                    "type": "CORNER",
                    "cornerPosition": "TOP_LEFT"
                }
            },
            {
                "type": "RECENT_UPLOAD",
                "startOffsetMs": 15000,
                "endOffsetMs":   20000,
                "position": {
                    "type": "CORNER",
                    "cornerPosition": "TOP_RIGHT"
                }
            }
        ]
    }

    youtube.videos().update(
        part="endScreens",
        body={"id": video_id, "endScreens": body}
    ).execute()
    print("エンドスクリーン設定完了", flush=True)


if __name__ == "__main__":
    main()
