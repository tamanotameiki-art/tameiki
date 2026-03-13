def download_bgm(spreadsheet_id, creds_json_str):
    """スプレッドシートからBGMをランダム選択・マスタリング・切り出しして返す"""
    if not spreadsheet_id or not creds_json_str:
        return None
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        import librosa
        import numpy as np

        creds_info = json.loads(creds_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets = build("sheets", "v4", credentials=creds)
        drive  = build("drive",  "v3", credentials=creds)

        result = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="BGM!A:L"
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            print("BGMが登録されていません", flush=True)
            return None

        candidates = []
        for i, row in enumerate(rows[1:], start=2):
            status = row[11] if len(row) >= 12 else ""
            if status != "有効":
                continue
            file_id   = row[1] if len(row) > 1 else ""
            file_name = row[0] if len(row) > 0 else "bgm.wav"
            title     = row[2] if len(row) > 2 else file_name
            use_count = int(row[9]) if len(row) > 9 and row[9] else 0
            if not file_id:
                continue
            candidates.append({
                "file_id":   file_id,
                "file_name": file_name,
                "title":     title,
                "use_count": use_count,
                "row":       i,
            })

        if not candidates:
            print("使用可能なBGMがありません", flush=True)
            return None

        # 使用回数が少ない曲ほど選ばれやすい重み付きランダム選択
        min_count = min(c["use_count"] for c in candidates)
        max_count = max(c["use_count"] for c in candidates)
        if max_count == min_count:
            bgm = random.choice(candidates)
        else:
            weights = [1.0 / (c["use_count"] - min_count + 1) for c in candidates]
            bgm = random.choices(candidates, weights=weights, k=1)[0]

        print(f"BGM選択: {bgm['title']} (使用回数: {bgm['use_count']})", flush=True)

        # ダウンロード
        ext = os.path.splitext(bgm["file_name"])[1] or ".m4a"
        raw_path = f"/tmp/bgm_raw_{bgm['file_id'][:8]}{ext}"
        if not os.path.exists(raw_path):
            print(f"BGMをダウンロード中: {bgm['file_name']}", flush=True)
            request = drive.files().get_media(fileId=bgm["file_id"])
            with open(raw_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            print(f"BGMダウンロード完了: {raw_path}", flush=True)

        # --- librosaで曲の長さと有効範囲を解析 ---
        CLIP_DURATION = 20.0
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                y, sr = librosa.load(raw_path, sr=22050, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
            print(f"BGM長さ: {duration:.1f}秒", flush=True)

            if duration <= CLIP_DURATION + 2.0:
                # 短い音源はそのまま使う
                start_sec = 0.0
                print(f"短い音源のためそのまま使用", flush=True)
            else:
                # 無音区間を除外した有効開始点を探す
                # RMSエネルギーで無音判定
                frame_length = 2048
                hop_length = 512
                rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
                rms_threshold = np.percentile(rms, 20)  # 下位20%を無音とみなす

                # 有効な開始点候補（最後の20秒は除外）
                max_start = duration - CLIP_DURATION - 1.0
                step = 0.5  # 0.5秒刻みで候補を作成
                valid_starts = []
                for t in np.arange(0.0, max_start, step):
                    # その開始点から5秒間のRMSを確認
                    frame_start = int(t * sr / hop_length)
                    frame_end = int((t + 5.0) * sr / hop_length)
                    segment_rms = rms[frame_start:frame_end]
                    if len(segment_rms) > 0 and np.mean(segment_rms) > rms_threshold:
                        valid_starts.append(float(t))

                if valid_starts:
                    start_sec = random.choice(valid_starts)
                    print(f"ランダム開始点: {start_sec:.1f}秒 (候補{len(valid_starts)}点)", flush=True)
                else:
                    start_sec = random.uniform(0.0, max_start)
                    print(f"有効候補なし・完全ランダム: {start_sec:.1f}秒", flush=True)

        except Exception as e:
            print(f"BGM解析エラー（スキップ）: {e}", flush=True)
            duration = 999.0
            start_sec = 0.0

        # --- ffmpegフルマスタリングチェーン ---
        work_dir = f"/tmp/bgm_work_{bgm['file_id'][:8]}"
        os.makedirs(work_dir, exist_ok=True)

        # Step1: WAVに変換
        wav_path = f"{work_dir}/00_raw.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_path,
            "-ar", "44100", "-ac", "2",
            wav_path
        ], capture_output=True)

        # Step2: EQ（高域の空気感を出す、低域を整える）
        eq_path = f"{work_dir}/01_eq.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-af", (
                "equalizer=f=80:t=o:w=1:g=2,"      # 低域ふくらみ
                "equalizer=f=300:t=o:w=1:g=-1,"     # こもり除去
                "equalizer=f=3000:t=o:w=1:g=1.5,"   # 中高域の存在感
                "equalizer=f=10000:t=o:w=1:g=2,"    # 空気感・高域の艶
                "equalizer=f=16000:t=o:w=1:g=1.5"   # 超高域の煌めき
            ),
            eq_path
        ], capture_output=True)
        print("EQ完了", flush=True)

        # Step3: コンプレッサー（ダイナミクスを整える）
        comp_path = f"{work_dir}/02_comp.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", eq_path,
            "-af", "acompressor=threshold=-18dB:ratio=3:attack=20:release=200:makeup=3dB",
            comp_path
        ], capture_output=True)
        print("コンプ完了", flush=True)

        # Step4: サチュレーション（音に温かみと倍音を加える）
        sat_path = f"{work_dir}/03_sat.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", comp_path,
            "-af", "asoftclip=type=tanh:threshold=0.95:output=0.93",
            sat_path
        ], capture_output=True)
        print("サチュレーション完了", flush=True)

        # Step5: リバーブ（空間の広がりを出す）
        rev_path = f"{work_dir}/04_rev.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", sat_path,
            "-af", "aecho=in_gain=1.0:out_gain=0.95:delays=40|52:decays=0.28|0.20",
            rev_path
        ], capture_output=True)
        print("リバーブ完了", flush=True)

        # Step6: ステレオ処理（広がりを整える）
        stereo_path = f"{work_dir}/05_stereo.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", rev_path,
            "-af", "stereotools=mlev=0.8,stereotools=sbal=0:slev=0.9",
            stereo_path
        ], capture_output=True)
        print("ステレオ処理完了", flush=True)

        # Step7: ラウドネス正規化（-14 LUFS）
        mastered_path = f"{work_dir}/06_mastered.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", stereo_path,
            "-af", "loudnorm=I=-14.0:TP=-1.0:LRA=11",
            mastered_path
        ], capture_output=True)
        print("ラウドネス正規化完了", flush=True)

        # Step8: 開始点から20秒切り出し＋フェード
        clip_path = f"{work_dir}/07_clip.wav"
        fade_out_start = CLIP_DURATION - 2.0
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(CLIP_DURATION),
            "-i", mastered_path,
            "-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_start}:d=2.0",
            clip_path
        ], capture_output=True)
        print(f"切り出し完了: {start_sec:.1f}秒〜{start_sec+CLIP_DURATION:.1f}秒", flush=True)

        bgm["path"] = clip_path
        return bgm

    except Exception as e:
        print(f"BGMダウンロードエラー（スキップ）: {e}", flush=True)
        return None
