#!/usr/bin/env python3
"""
scripts/post_pinterest.py — Pinterestへの動画投稿
動画はGoogle Driveに一時アップして投稿後即削除。
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))
from drive_upload import upload_video_to_drive, delete_drive_file

PINTEREST_API = "https://api.pinterest.com/v5"


def main():
    access_token = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    video_path   = os.environ.get("VIDEO_PATH", "")
    caption      = os.environ.get("CAPTION", "")
    poem         = os.environ.get("POEM", "")

    if not access_token:
        print("PINTEREST_ACCESS_TOKENが設定されていません。スキップ", flush=True)
        print("pin_id=")
        return

    if not video_path or not os.path.exists(video_path):
        print(f"動画ファイルが見つかりません: {video_path}", flush=True)
        print("pin_id=")
        return

    # Drive に一時アップロード
    drive_result = upload_video_to_drive(video_path)
    video_url = drive_result["url"]
    drive_file_id = drive_result["file_id"]

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # 動画をPinterestに登録（media upload）
        print("Pinterestに動画をアップロード中...", flush=True)
        upload_resp = requests.post(
            f"{PINTEREST_API}/media",
            headers=headers,
            json={"media_type": "video"},
            timeout=60,
        )
        if upload_resp.status_code not in (200, 201):
            print(f"Pinterestメディア登録エラー: {upload_resp.status_code} {upload_resp.text}", flush=True)
            print("pin_id=")
            return

        upload_data = upload_resp.json()
        media_id    = upload_data.get("media_id", "")
        upload_url  = upload_data.get("upload_url", "")
        upload_parameters = upload_data.get("upload_parameters", {})

        if not upload_url:
            print(f"upload_urlが取得できませんでした: {upload_data}", flush=True)
            print("pin_id=")
            return

        print(f"Pinterestメディア登録完了: media_id={media_id}", flush=True)

        # 動画ファイルをアップロード先URLにPUT
        print("動画ファイルをPinterestにアップロード中...", flush=True)
        with open(video_path, "rb") as f:
            # upload_parametersがあればmultipart、なければ直接PUT
            if upload_parameters:
                put_resp = requests.post(
                    upload_url,
                    data=upload_parameters,
                    files={"file": ("video.mp4", f, "video/mp4")},
                    timeout=300,
                )
            else:
                put_resp = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": "video/mp4"},
                    timeout=300,
                )

        if put_resp.status_code not in (200, 201, 204):
            print(f"Pinterest動画アップエラー: {put_resp.status_code} {put_resp.text}", flush=True)
            print("pin_id=")
            return

        print("Pinterest動画アップロード完了", flush=True)

        # アップロード処理完了を待つ
        wait_for_pinterest_media(headers, media_id)

        # ピンを作成
        title = (poem[:100] if poem else "たまのためいき。")
        pin_data = {
            "title":       title,
            "description": caption,
            "media_source": {
                "source_type": "media_id",
                "media_id":    media_id,
            },
        }
        print("ピンを作成中...", flush=True)
        pin_resp = requests.post(
            f"{PINTEREST_API}/pins",
            headers=headers,
            json=pin_data,
            timeout=60,
        )
        if pin_resp.status_code not in (200, 201):
            print(f"ピン作成エラー: {pin_resp.status_code} {pin_resp.text}", flush=True)
            print("pin_id=")
            return

        pin_id = pin_resp.json().get("id", "")
        print(f"Pinterest投稿完了: {pin_id}", flush=True)
        print(f"pin_id={pin_id}")

    finally:
        # 投稿完了後にDriveの一時ファイルを即削除
        delete_drive_file(drive_file_id)


def wait_for_pinterest_media(headers, media_id, max_wait=300):
    """Pinterestのメディア処理完了を待つ（最大5分）"""
    if not media_id:
        return
    for i in range(max_wait // 10):
        try:
            r = requests.get(
                f"{PINTEREST_API}/media/{media_id}",
                headers=headers,
                timeout=30,
            )
            if r.status_code == 200:
                status = r.json().get("status", "")
                print(f"  Pinterestメディア状態 ({i*10}秒): {status}", flush=True)
                if status in ("succeeded", "SUCCEEDED", "ready", "READY"):
                    return
                if status in ("failed", "FAILED"):
                    raise Exception(f"Pinterestメディア処理失敗: {r.json()}")
        except Exception as e:
            print(f"  メディア状態確認エラー（継続）: {e}", flush=True)
        time.sleep(10)
    print("Pinterestメディア処理タイムアウト（続行）", flush=True)


if __name__ == "__main__":
    main()
