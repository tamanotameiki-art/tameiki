#!/usr/bin/env python3
"""
scripts/post_x.py — Xへのサムネイル画像投稿
動画の代わりにサムネイル画像＋キャプション＋YouTubeURLを投稿（無料プラン対応）
"""
import os
import tweepy


def main():
    client = tweepy.Client(
        consumer_key        = os.environ["X_API_KEY"],
        consumer_secret     = os.environ["X_API_SECRET"],
        access_token        = os.environ["X_ACCESS_TOKEN"],
        access_token_secret = os.environ["X_ACCESS_SECRET"],
    )
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    api = tweepy.API(auth)

    thumbnail_path = os.environ.get("THUMBNAIL_PATH", "")
    caption        = os.environ.get("CAPTION", "")
    youtube_url    = os.environ.get("YOUTUBE_URL", "")

    # キャプションにYouTubeのURLを付加
    if youtube_url:
        tweet_text = f"{caption}\n\n{youtube_url}"
    else:
        tweet_text = caption

    # サムネイル画像をアップロード
    if thumbnail_path and os.path.exists(thumbnail_path):
        print("Xにサムネイル画像をアップロード中...", flush=True)
        media = api.media_upload(filename=thumbnail_path)
        media_ids = [media.media_id]
        print(f"画像アップロード完了: {media.media_id}", flush=True)
    else:
        print("サムネイル画像なしで投稿", flush=True)
        media_ids = None

    # ツイート投稿
    tweet = client.create_tweet(
        text=tweet_text,
        media_ids=media_ids
    )
    post_id = tweet.data["id"]
    print(f"X投稿完了: {post_id}", flush=True)
    print(f"post_id={post_id}")


if __name__ == "__main__":
    main()
