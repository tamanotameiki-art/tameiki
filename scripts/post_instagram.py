#!/usr/bin/env python3
"""
scripts/post_instagram.py — Instagram Reels投稿 + ストーリーズ同時投稿
Meta Graph APIを使用
"""
import os
import json
import time
import requests

GRAPH_URL = "https://graph.facebook.com/v18.0"

def main():
    access_token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    account_id   = os.environ["INSTAGRAM_ACCOUNT_ID"]
    video_path   = os.environ["VIDEO_PATH"]
    caption      = os.environ.get("CAPTION", "")

    # 動画をGoogle Driveに一時アップしてURLを取得
    # （InstagramはURLからの取り込みが必要）
    video_url = upload_to_temp_storage(video_path)

    # ===== Reels投稿 =====
    print("Instagram Reelsに投稿中...", flush=True)
    media_id = create_reels_container(
        account_id, access_token, video_url, caption
    )

    # コンテナ処理完了を待つ
    wait_for_container(account_id, access_token, media_id)

    # 投稿を公開
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
    r = requests.post(url, data=params)
    r.raise_for_status()
    return r.json()["id"]


def wait_for_container(account_id, token, media_id, max_wait=120):
    """コンテナの処理完了を待つ"""
    url = f"{GRAPH_URL}/{media_id}"
    for i in range(max_wait // 10):
        r = requests.get(url, params={
            "fields": "status_code",
            "access_token": token
        })
        status = r.json().get("status_code", "")
        print(f"  コンテナ状態: {status}", flush=True)
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise Exception("Instagramコンテナ処理エラー")
        time.sleep(10)

    raise Exception("コンテナ処理タイムアウト")


def publish_media(account_id, token, media_id):
    """メディアを公開"""
    url = f"{GRAPH_URL}/{account_id}/media_publish"
    r = requests.post(url, data={
        "creation_id":  media_id,
        "access_token": token,
    })
    r.raise_for_status()
    return r.json()


def post_story(account_id, token, video_url):
    """ストーリーズに投稿"""
    # コンテナ作成
    url = f"{GRAPH_URL}/{account_id}/media"
    r = requests.post(url, data={
        "media_type":   "STORIES",
        "video_url":    video_url,
        "access_token": token,
    })
    r.raise_for_status()
    container_id = r.json()["id"]

    # 処理待ち
    wait_for_container(account_id, token, container_id)

    # 公開
    result = publish_media(account_id, token, container_id)
    return result.get("id", "")


def upload_to_temp_storage(video_path):
    """
    動画をGoogle Driveに一時アップロードしてURLを返す。
    InstagramはURLからの動画取り込みが必要なため。
    実装はrun_generate.pyで動画をDriveにアップロードする想定。
    """
    # 環境変数からURLを取得（run_generate.pyがセットする）
    video_url = os.environ.get("VIDEO_URL", "")
    if not video_url:
        raise ValueError("VIDEO_URL環境変数が設定されていません")
    return video_url


if __name__ == "__main__":
    main()
