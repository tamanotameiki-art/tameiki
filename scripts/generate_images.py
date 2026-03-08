#!/usr/bin/env python3
"""
scripts/generate_images.py
動画素材から静止画を3比率で生成（翌朝投稿用）

YouTube コミュニティ: 1:1 (1080x1080)
Instagram フィード:   4:5 (1080x1350)
Pinterest:            2:3 (1000x1500)
"""
import os
import sys
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import FONT_PATH, FONT_IDX, C_TEXT
from filters import apply_filter
from background import prepare_bg
from easing import ease_out

SIZES = {
    "youtube_community": (1080, 1080),  # 1:1
    "instagram_feed":    (1080, 1350),  # 4:5
    "pinterest":         (1000, 1500),  # 2:3
}


def generate_still(poem, bg_path, filter_name, emotion_tags, output_dir="/tmp/tameiki_stills"):
    """静止画を3比率で生成"""
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    for name, (w, h) in SIZES.items():
        output_path = f"{output_dir}/{name}.jpg"

        # 背景を指定サイズでクロップ
        bg = prepare_bg_custom_size(bg_path, w, h)

        # フィルター適用（最もきれいなフレームとして fi=0 固定）
        frame = apply_filter(bg, filter_name, fi=0)

        # テキストを全文表示した静止画として描画
        frame_rgba = frame.convert("RGBA")
        txt_layer  = draw_full_text(poem, w, h, font_size=int(min(w, h) * 0.055))
        frame_rgba = Image.alpha_composite(frame_rgba, txt_layer)

        # ロゴを右下に配置（小さめ・控えめ・半透明）
        frame_rgba = add_logo(frame_rgba, w, h)

        # JPEG保存
        frame_rgba.convert("RGB").save(output_path, quality=95)
        paths[name] = output_path
        print(f"静止画生成: {name} → {output_path}", flush=True)

    return paths


def prepare_bg_custom_size(bg_path, w, h):
    """任意サイズに背景をクロップ"""
    img = Image.open(bg_path).convert("RGB")
    iw, ih = img.size
    target_ratio = h / w
    current_ratio = ih / iw

    if current_ratio > target_ratio:
        new_h = int(iw * target_ratio)
        top   = (ih - new_h) // 2
        img   = img.crop((0, top, iw, top + new_h))
    elif current_ratio < target_ratio:
        new_w = int(ih / target_ratio)
        left  = (iw - new_w) // 2
        img   = img.crop((left, 0, left + new_w, ih))

    return img.resize((w, h), Image.LANCZOS)


def draw_full_text(poem, w, h, font_size=56):
    """全文字を表示した縦書きテキストレイヤーを生成"""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    font  = ImageFont.truetype(FONT_PATH, font_size, index=FONT_IDX)

    lines     = poem.split("\n")
    char_gap  = int(font_size * 1.30)
    line_gap  = int(font_size * 2.6)
    max_chars = max(len(l) for l in lines)
    num_lines = len(lines)

    total_w = (num_lines - 1) * line_gap + font_size
    total_h = (max_chars - 1) * char_gap + font_size

    sx = w // 2 + total_w // 2 - font_size // 2
    sy = h // 2 - total_h // 2 + 20

    for li, line in enumerate(lines):
        for ci, ch in enumerate(line):
            x = sx - li * line_gap
            y = sy + ci * char_gap

            # グロー（奥行き感）
            glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd   = ImageDraw.Draw(glow)
            gd.text((x, y), ch, font=font, fill=(255, 248, 230, 180))
            glow = glow.filter(ImageFilter.GaussianBlur(radius=3))
            layer = Image.alpha_composite(layer, glow)
            d     = ImageDraw.Draw(layer)

            # 本体
            d.text((x, y), ch, font=font, fill=(*C_TEXT, 240))

    return layer


def add_logo(img, w, h):
    """右下に「たまのためいき。」ロゴを追加（控えめ・半透明）"""
    font_size = int(min(w, h) * 0.028)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size, index=FONT_IDX)
    except:
        return img

    logo_text = "たまのためいき。"
    logo_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo_layer)

    bbox = font.getbbox(logo_text)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]

    margin = int(min(w, h) * 0.04)
    x = w - lw - margin
    y = h - lh - margin

    d.text((x, y), logo_text, font=font, fill=(255, 248, 230, 120))  # 半透明
    return Image.alpha_composite(img, logo_layer)


def main():
    selection = json.loads(os.environ.get("SELECTION", "{}"))

    poem         = selection.get("poem", "")
    video_id     = selection.get("video_id", "")
    filter_name  = selection.get("filter_name", "写ルンです")
    emotion_tags = selection.get("emotion_tags", "")

    if not poem:
        print("詩が取得できませんでした", flush=True)
        return

    # 背景はキャッシュ済みのものを使う
    bg_path = f"/tmp/tameiki_bg_{video_id[:8]}.mp4" if video_id else None
    if not bg_path or not os.path.exists(bg_path):
        # デフォルト背景
        bg_path = os.path.join(os.path.dirname(__file__), "..", "assets", "default_bg.jpg")

    paths = generate_still(poem, bg_path, filter_name, emotion_tags)

    # DriveにアップロードしてURLを保存（翌朝投稿ワークフローが参照）
    upload_stills_to_drive(paths)


def upload_stills_to_drive(paths):
    """静止画をDriveの翌朝投稿フォルダに保存"""
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
        if not creds_json:
            return

        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        drive = build("drive", "v3", credentials=creds)

        folders = drive.files().list(
            q="name='tameiki_morning_post' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute().get("files", [])

        folder_id = folders[0]["id"] if folders else None

        for name, path in paths.items():
            metadata = {"name": f"{name}.jpg"}
            if folder_id:
                metadata["parents"] = [folder_id]
            media = MediaFileUpload(path, mimetype="image/jpeg")
            drive.files().create(body=metadata, media_body=media).execute()
            print(f"Drive保存完了: {name}", flush=True)

    except Exception as e:
        print(f"静止画Drive保存エラー（スキップ）: {e}", flush=True)


if __name__ == "__main__":
    main()
