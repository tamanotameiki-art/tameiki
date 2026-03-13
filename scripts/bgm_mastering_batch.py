#!/usr/bin/env python3
"""
scripts/bgm_mastering_batch.py
スプレッドシートのBGMシートを確認し、「マスタリング待ち」の曲を順番に処理する。
手動トリガー時に FILE_ID/FILE_NAME/SHEET_ROW が指定されていれば1件のみ処理。
"""
import os
import sys
import json
import subprocess

def get_pending_bgms(spreadsheet_id, creds_json_str):
    """ステータスが「マスタリング待ち」の行を全件取得"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_info = json.loads(creds_json_str)
    creds = sa.Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    sheets = build("sheets", "v4", credentials=creds)
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="BGM!A:L"
    ).execute()
    rows = result.get("values", [])

    pending = []
    for i, row in enumerate(rows[1:], start=2):  # 2行目から（1行目はヘッダー）
        status = row[11] if len(row) >= 12 else ""
        if status == "マスタリング待ち":
            file_name = row[0] if len(row) > 0 else ""
            file_id   = row[1] if len(row) > 1 else ""
            if file_id:
                pending.append({
                    "row":       i,
                    "file_name": file_name,
                    "file_id":   file_id,
                })
    return pending

def download_from_drive(file_id, file_name, creds_json_str):
    """DriveからBGMをダウンロード"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    creds_info = json.loads(creds_json_str)
    creds = sa.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    drive = build("drive", "v3", credentials=creds)
    output_path = f"/tmp/{file_name}"
    print(f"ダウンロード中: {file_name} ({file_id})", flush=True)
    request = drive.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    print(f"ダウンロード完了: {output_path}", flush=True)
    return output_path

def mark_processing(spreadsheet_id, creds_json_str, row):
    """処理中マークをつける（二重実行防止）"""
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_info = json.loads(creds_json_str)
    creds = sa.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    sheets = build("sheets", "v4", credentials=creds)
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"BGM!L{row}",
        valueInputOption="RAW",
        body={"values": [["処理中"]]}
    ).execute()

def main():
    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    if not creds_json_str or not spreadsheet_id:
        print("GOOGLE_CREDENTIALS / SPREADSHEET_ID が未設定", flush=True)
        sys.exit(1)

    # 手動トリガーで特定ファイルが指定されている場合
    manual_file_id   = os.environ.get("FILE_ID", "")
    manual_file_name = os.environ.get("FILE_NAME", "")
    manual_row       = os.environ.get("SHEET_ROW", "")

    if manual_file_id and manual_file_name and manual_row:
        targets = [{"file_id": manual_file_id, "file_name": manual_file_name, "row": int(manual_row)}]
        print(f"手動指定: {manual_file_name}", flush=True)
    else:
        print("マスタリング待ちを自動検出中...", flush=True)
        targets = get_pending_bgms(spreadsheet_id, creds_json_str)
        print(f"マスタリング待ち: {len(targets)}件", flush=True)

    if not targets:
        print("処理対象なし。終了します。", flush=True)
        return

    # BGMマスタリング本体をインポート
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from bgm_mastering import (
        detect_source_type, analyze_audio, build_eq_filters,
        noise_reduction, apply_saturation, apply_reverb,
        process_stereo, normalize_loudness,
        generate_clips, extract_clip,
        upload_mastered_to_drive, update_bgm_sheet
    )

    for target in targets:
        file_id   = target["file_id"]
        file_name = target["file_name"]
        row       = target["row"]
        print(f"\n===== 処理開始: {file_name} (行{row}) =====", flush=True)

        # 処理中フラグを立てる（並列実行防止）
        mark_processing(spreadsheet_id, creds_json_str, row)

        try:
            # ダウンロード
            input_path = download_from_drive(file_id, file_name, creds_json_str)

            # マスタリング処理
            work_dir = f"/tmp/bgm_work_{row}"
            os.makedirs(work_dir, exist_ok=True)

            source_type = detect_source_type(input_path)
            analysis    = analyze_audio(input_path)
            current     = input_path

            import numpy as np
            if source_type == "rough":
                nr_path = f"{work_dir}/01_nr.wav"
                current = noise_reduction(current, nr_path)

            eq_path     = f"{work_dir}/02_eq.wav"
            eq_filters  = build_eq_filters(source_type, analysis)
            subprocess.run(["ffmpeg", "-y", "-i", current, "-af", eq_filters, eq_path],
                           capture_output=True, check=True)
            current = eq_path

            comp_path   = f"{work_dir}/03_comp.wav"
            comp_filter = ("acompressor=threshold=-18dB:ratio=3:attack=30:release=200:makeup=2dB"
                           if source_type == "rough"
                           else "acompressor=threshold=-12dB:ratio=2:attack=50:release=300:makeup=1dB")
            subprocess.run(["ffmpeg", "-y", "-i", current, "-af", comp_filter, comp_path],
                           capture_output=True, check=True)
            current = comp_path

            sat_path   = f"{work_dir}/04_sat.wav"
            sat_amount = 0.35 if source_type == "rough" else 0.15
            current    = apply_saturation(current, sat_path, sat_amount)

            rev_path  = f"{work_dir}/05_rev.wav"
            bpm       = analysis.get("bpm", 80)
            energy    = analysis.get("energy", 0.1)
            room_size = 0.4 if bpm < 80 and energy < 0.05 else 0.25
            wet       = 0.18 if bpm < 80 else 0.12
            current   = apply_reverb(current, rev_path, room_size, wet)

            st_path = f"{work_dir}/06_stereo.wav"
            current = process_stereo(current, st_path)

            mastered_path = f"{work_dir}/mastered.wav"
            normalize_loudness(current, mastered_path)

            clips      = generate_clips(mastered_path, total_duration=None)
            clip_paths = []
            for clip in clips:
                clip_path = f"{work_dir}/clip_{clip['type']}.wav"
                extract_clip(mastered_path, clip["start"], clip["end"], clip_path)
                clip_paths.append(clip_path)

            # Driveにアップロード・シート更新（ステータスが「有効」になる）
            os.environ["SHEET_ROW"] = str(row)
            preview_url = upload_mastered_to_drive(mastered_path, clip_paths, file_name)
            update_bgm_sheet(str(row), analysis, clips, preview_url)

            print(f"===== 完了: {file_name} =====\n", flush=True)

        except Exception as e:
            print(f"エラー（{file_name}）: {e}", flush=True)
            # エラー時はマスタリング待ちに戻す
            try:
                import google.oauth2.service_account as sa
                from googleapiclient.discovery import build
                creds_info = json.loads(creds_json_str)
                creds = sa.Credentials.from_service_account_info(
                    creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
                sheets = build("sheets", "v4", credentials=creds)
                sheets.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"BGM!L{row}",
                    valueInputOption="RAW",
                    body={"values": [["マスタリング待ち"]]}
                ).execute()
            except Exception:
                pass

if __name__ == "__main__":
    main()
