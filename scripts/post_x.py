#!/usr/bin/env python3
"""
scripts/post_x.py — Xへのサムネイル画像投稿
動画の代わりにサムネイル画像＋キャプション＋YouTubeURLを投稿（無料プラン対応）
v2メディアアップロードエンドポイント使用（v1.1は2025/4/30廃止済み）
"""
import os
import time
import requests
import tweepy


def upload_media_v2(api_key, api_secret, access_token, access_secret, image_path):
    """
    X API v2のメディアアップロードエンドポイントで画像をアップロード。
    返り値: media_id文字列
    """
    upload_url = "https://upload.twitter.com/2/media/upload"

    from requests_oauthlib import OAuth1
    auth = OAuth1(api_key, api_secret, access_token, access_secret)

    with open(image_path, "rb") as f:
        image_data = f.read()

    total_bytes = len(image_data)

    # INIT
    init_resp = requests.post(
        upload_url,
        auth=auth,
        json={
            "media_category": "tweet_image",
            "total_bytes": total_bytes,
            "media_type": "image/jpeg",
        }
    )
    if init_resp.status_code not in (200, 201, 202):
        raise Exception(f"INIT失敗: {init_resp.status_code} {init_resp.text}")

    media_id = init_resp.json()["data"]["id"]
    print(f"メディアID取得: {media_id}", flush=True)

    # APPEND（5MB以下なら1回）
    chunk_size = 5 * 1024 * 1024
    segment = 0
    for i in range(0, total_bytes, chunk_size):
        chunk = image_data[i:i + chunk_size]
        append_resp = requests.post(
            upload_url,
            auth=auth,
            params={"command": "APPEND", "media_id": media_id, "segment_index": segment},
            files={"media": chunk}
        )
        if append_resp.status_code not in (200, 201, 202, 204):
            raise Exception(f"APPEND失敗: {append_resp.status_code} {append_resp.text}")
        segment += 1

    # FINALIZE
    finalize_resp = requests.post(
        upload_url,
        auth=auth,
        params={"command": "FINALIZE", "media_id": media_id}
    )
    if finalize_resp.status_code not in (200, 201, 202):
        raise Exception(f"FINALIZE失敗: {finalize_resp.status_code} {finalize_resp.text}")

    # 非同期処理待ち
    state = finalize_resp.json().get("data", {}).get("processing_info", {}).get("state")
    if state == "pending":
        time.sleep(3)

    print(f"画像アップロード完了: {media_id}", flush=True)
    return media_id


def main():
    api_key       = os.environ["X_API_KEY"]
    api_secret    = os.environ["X_API_SECRET"]
    access_token  = os.environ["X_ACCESS_TOKEN"]
    access_secret = os.environ["X_ACCESS_SECRET"]

    thumbnail_path = os.environ.get("THUMBNAIL_PATH", "")
    caption        = os.environ.get("CAPTION", "")
    youtube_url    = os.environ.get("YOUTUBE_URL", "")

    # キャプションにYouTubeのURLを付加
    if youtube_url:
        tweet_text = f"{caption}\n\n{youtube_url}"
    else:
        tweet_text = caption

    # tweepy v2クライアント
    client = tweepy.Client(
        consumer_key        = api_key,
        consumer_secret     = api_secret,
        access_token        = access_token,
        access_token_secret = access_secret,
    )

    # サムネイル画像をv2でアップロード
    media_ids = None
    if thumbnail_path and os.path.exists(thumbnail_path):
        print("Xにサムネイル画像をアップロード中...", flush=True)
        try:
            media_id = upload_media_v2(
                api_key, api_secret, access_token, access_secret, thumbnail_path
            )
            media_ids = [media_id]
        except Exception as e:
            print(f"画像アップロードエラー（テキストのみで投稿）: {e}", flush=True)
            media_ids = None
    else:
        print("サムネイル画像なしで投稿", flush=True)

    # 投稿
    print("Xに投稿中...", flush=True)
    tweet = client.create_tweet(
        text=tweet_text,
        media_ids=media_ids
    )
    post_id = tweet.data["id"]
    print(f"X投稿完了: {post_id}", flush=True)
    print(f"post_id={post_id}")


if __name__ == "__main__":
    main()
