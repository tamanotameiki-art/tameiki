#!/usr/bin/env python3
"""
scripts/post_instagram.py — Instagram Reels投稿 + ストーリーズ同時投稿
Meta Graph APIを使用。動画はGoogle Driveに一時アップして投稿後即削除。
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))
from drive_upload import upload_video_to_drive, delete_drive_file

GRAPH_URL = "https://graph.facebook.com/v19.0"


def main():
    access_token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    account_id   = os.environ["INSTAGRAM_ACCOUNT_ID"]
    video_path   = os.environ["VIDEO_PATH"]
    caption      = os.environ.get("CAPTION", "")

    if not os.path.exists(video_path):
        print(f"動画ファイルが見つかりません: {video_path}", flush=True)
        print("media_id=")
        return

    # Drive に一時アップロード
    drive_result = upload_video_to_drive(video_path)
    video_url = drive_result["url"]
    drive_file_id = drive_result["file_id"]

    try:
        # ===== Reels投稿 =====
        print("Instagram Reelsに投稿中...", flush=True)
        media_id = create_reels_container(account_id, access_token, video_url, caption)
        wait_for_container(account_id, access_token, media_id)
        result = publish_media(account_id, access_token, media_id)
        published_id = result.get("id", "")
        print(f"Instagram Reels投稿完了: {published_id}", flush=True)

        # ===== ストーリーズ同時投稿 =====
        print("ストーリーズに投稿中...", flush=True)
        try:
            story_id = post_story(account_id, access_token, video_url)
            print(f"ストーリーズ投稿完了: {story_id}", flush=True)
        except Exception as e:
            print(f"ストーリーズ投稿エラー（スキップ）: {e}", flush=True)

        print(f"media_id={published_id}")

    finally:
        # 投稿完了後にDriveの一時ファイルを即削除
        delete_drive_file(drive_file_id)


def create_reels_container(account_id, token, video_url, caption):
    """Reelsコンテナを作成"""
    url = f"{GRAPH_URL}/{account_id}/media"
    params = {
        "media_type":    "REELS",
        "video_url":     video_url,
        "caption":       caption,
        "share_to_feed": True,
        "access_token":  token,
    }
    r = requests.post(url, data=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise Exception(f"Instagramコンテナ作成エラー: {data['error']}")
    return data["id"]


def wait_for_container(account_id, token, media_id, max_wait=300):
    """コンテナの処理完了を待つ（最大5分）"""
    url = f"{GRAPH_URL}/{media_id}"
    for i in range(max_wait // 10):
        r = requests.get(url, params={
            "fields": "status_code,status",
            "access_token": token
        }, timeout=30)
        data = r.json()
        status = data.get("status_code", "")
        print(f"  コンテナ状態 ({i*10}秒): {status}", flush=True)
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise Exception(f"Instagramコンテナ処理エラー: {data}")
        time.sleep(10)
    raise Exception("コンテナ処理タイムアウト（5分）")


def publish_media(account_id, token, media_id):
    """メディアを公開"""
    url = f"{GRAPH_URL}/{account_id}/media_publish"
    r = requests.post(url, data={
        "creation_id":  media_id,
        "access_token": token,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise Exception(f"Instagram公開エラー: {data['error']}")
    return data


def post_story(account_id, token, video_url):
    """ストーリーズに投稿"""
    url = f"{GRAPH_URL}/{account_id}/media"
    r = requests.post(url, data={
        "media_type":   "STORIES",
        "video_url":    video_url,
        "access_token": token,
    }, timeout=60)
    r.raise_for_status()
    container_id = r.json()["id"]
    wait_for_container(account_id, token, container_id)
    result = publish_media(account_id, token, container_id)
    return result.get("id", "")


if __name__ == "__main__":
    main()
