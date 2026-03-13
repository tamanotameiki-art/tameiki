#!/usr/bin/env python3
"""
scripts/prepare_tiktok.py
TikTok用ファイルをiPhoneショートカット経由で投稿できるよう準備
TikTokは公式APIが制限されているため、
生成した動画とキャプションをDriveの専用フォルダに保存し
iPhoneショートカットから投稿する半自動フロー。
※ サービスアカウントのDriveアップロード制限により現在はスキップ。
"""
import os

def main():
    video_path = os.environ.get("VIDEO_PATH", "")
    caption    = os.environ.get("CAPTION", "")

    if not video_path or not os.path.exists(video_path):
        print("動画ファイルが見つかりません。スキップ", flush=True)
        return

    print("TikTok Drive保存はスキップ（サービスアカウント制限）", flush=True)
    print(f"キャプション: {caption}", flush=True)
    print("iPhoneショートカットからの手動投稿をお願いします", flush=True)

if __name__ == "__main__":
    main()
