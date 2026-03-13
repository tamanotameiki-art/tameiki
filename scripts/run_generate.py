def download_bgm(spreadsheet_id, creds_json_str):
    """スプレッドシートからBGMをランダム選択してダウンロード"""
    if not spreadsheet_id or not creds_json_str:
        return None
    try:
        import random
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets = build("sheets", "v4", credentials=creds)
        drive  = build("drive", "v3", credentials=creds)

        result = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="BGM!A:L"
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            print("BGMが登録されていません", flush=True)
            return None

        candidates = []
        for row in rows[1:]:
            status = row[11] if len(row) >= 12 else ""
            # 「有効」または「タイトル待ち」はどちらも使用可能
            if status in ("有効", "タイトル待ち"):
                # マスタリング済みファイルのDrive IDはH列(index=7)
                file_id   = row[7] if len(row) > 7 and row[7] else row[1]
                file_name = row[0]
                use_count = int(row[9]) if len(row) > 9 and row[9] else 0
                candidates.append({
                    "file_id":   file_id,
                    "file_name": file_name,
                    "use_count": use_count,
                })

        if not candidates:
            print("使用可能なBGMがありません（マスタリング待ちの曲は処理後に使用可能になります）", flush=True)
            return None

        # 使用回数が少ない曲ほど選ばれやすい重み付きランダム選択
        min_count = min(c["use_count"] for c in candidates)
        max_count = max(c["use_count"] for c in candidates)
        if max_count == min_count:
            bgm = random.choice(candidates)
        else:
            weights = [1.0 / (c["use_count"] - min_count + 1) for c in candidates]
            bgm = random.choices(candidates, weights=weights, k=1)[0]

        print(f"BGM選択: {bgm['file_name']} (使用回数: {bgm['use_count']})", flush=True)

        ext = os.path.splitext(bgm["file_name"])[1] or ".wav"
        output_path = f"/tmp/bgm_{bgm['file_id'][:8]}{ext}"
        if os.path.exists(output_path):
            return output_path

        print(f"BGMをダウンロード中: {bgm['file_name']}", flush=True)
        request = drive.files().get_media(fileId=bgm["file_id"])
        with open(output_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        print(f"BGMダウンロード完了: {output_path}", flush=True)
        return output_path

    except Exception as e:
        print(f"BGMダウンロードエラー（スキップ）: {e}", flush=True)
        return None
