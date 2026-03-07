#!/usr/bin/env python3
"""
scripts/post_x.py — Xへの動画投稿
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

    video_path = os.environ["VIDEO_PATH"]
    caption    = os.environ.get("CAPTION", "")

    # 動画をアップロード
    print("Xに動画をアップロード中...", flush=True)
    media = api.media_upload(
        filename=video_path,
        media_category="tweet_video",
        chunked=True,
    )

    # ツイート投稿
    tweet = client.create_tweet(
        text=caption,
        media_ids=[media.media_id]
    )

    post_id = tweet.data["id"]
    print(f"X投稿完了: {post_id}", flush=True)
    print(f"post_id={post_id}")


if __name__ == "__main__":
    main()
