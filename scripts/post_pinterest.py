#!/usr/bin/env python3
"""
scripts/post_pinterest.py — Pinterestへの画像投稿
サムネイル画像をピンとして投稿する
"""
import os
import requests


def main():
    access_token   = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    thumbnail_path = os.environ.get("THUMBNAIL_PATH", "")
    caption        = os.environ.get("CAPTION", "")
    poem           = os.environ.get("POEM", "")

    if not access_token:
        print("PINTEREST_ACCESS_TOKENが設定されていません。スキップ", flush=True)
        return

    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print("サムネイル画像が見つかりません。スキップ", flush=True)
        return

    headers = {"Authorization": f"Bearer {access_token}"}

    # 画像をアップロード
    print("Pinterestに画像をアップロード中...", flush=True)
    with open(thumbnail_path, "rb") as f:
        upload_response = requests.post(
            "https://api.pinterest.com/v5/media",
            headers=headers,
            files={"file": ("thumbnail.jpg", f, "image/jpeg")},
            data={"media_type": "image"}
        )

    if upload_response.status_code not in (200, 201):
        print(f"画像アップロードエラー: {upload_response.status_code} {upload_response.text}", flush=True)
        return

    media_id = upload_response.json().get("media_id", "")
    print(f"画像アップロード完了: media_id={media_id}", flush=True)

    # ピンを作成
    pin_data = {
        "title": poem[:100] if poem else "たまのためいき。",
        "description": caption,
        "media_source": {
            "source_type": "media_id",
            "media_id": media_id
        }
    }

    print("ピンを作成中...", flush=True)
    pin_response = requests.post(
        "https://api.pinterest.com/v5/pins",
        headers={**headers, "Content-Type": "application/json"},
        json=pin_data
    )

    if pin_response.status_code not in (200, 201):
        print(f"ピン作成エラー: {pin_response.status_code} {pin_response.text}", flush=True)
        return

    pin_id = pin_response.json().get("id", "")
    print(f"Pinterest投稿完了: {pin_id}", flush=True)
    print(f"pin_id={pin_id}")


if __name__ == "__main__":
    main()
