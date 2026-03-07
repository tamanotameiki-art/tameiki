#!/usr/bin/env python3
"""
scripts/bgm_mastering.py
一流オーディオエンジニアとしてのBGMマスタリング処理

素材判別 → フルマスタリングコース or 仕上げコース
→ -14 LUFS / True Peak -1.0dBTP に正規化
→ クリップ生成（librosaで美味しいところを検出）
"""
import os
import sys
import json
import subprocess
import tempfile
import numpy as np

def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(r.stderr, flush=True)
        raise RuntimeError(f"コマンド失敗: {cmd[0]}")
    return r


# ===== 素材タイプ判別 =====
def detect_source_type(path):
    """
    撮って出し vs レコーディング済みを判別
    ノイズフロア・ダイナミクスで判定
    """
    try:
        import librosa
        y, sr = librosa.load(path, sr=None, mono=True, duration=10)

        # RMSエネルギーの変動係数（撮って出しは大きい）
        frame_length = int(sr * 0.05)
        rms = librosa.feature.rms(y=y, frame_length=frame_length)[0]
        cv  = np.std(rms) / (np.mean(rms) + 1e-8)

        # ノイズフロア（無音部分の平均レベル）
        silent_mask  = rms < np.percentile(rms, 10)
        noise_floor  = np.mean(rms[silent_mask]) if silent_mask.any() else 0

        print(f"変動係数: {cv:.3f} ノイズフロア: {noise_floor:.6f}", flush=True)

        # 判定：変動が大きいか、ノイズフロアが高ければ撮って出し
        is_rough = cv > 0.8 or noise_floor > 0.003
        source_type = "rough" if is_rough else "recorded"
        print(f"素材タイプ: {source_type}", flush=True)
        return source_type

    except ImportError:
        print("librosa未インストール → recorded扱い", flush=True)
        return "recorded"


# ===== EQフィルター（FFmpeg） =====
def build_eq_filters(source_type, analysis):
    """
    素材タイプと分析結果に基づいてEQを構築
    """
    filters = []

    if source_type == "rough":
        # 撮って出し：外科的処理
        # こもり除去
        filters.append("equalizer=f=300:width_type=o:width=2:g=-3")
        # 鼻づまり感
        filters.append("equalizer=f=800:width_type=o:width=1:g=-2")
        # 耳障りな中域
        filters.append("equalizer=f=3000:width_type=o:width=1:g=-1.5")
        # 高域のシャリつき
        filters.append("equalizer=f=10000:width_type=o:width=1:g=-1")

    # 共通：音楽的処理
    brightness = analysis.get("brightness", 0.5)
    energy     = analysis.get("energy", 0.5)

    # 低域に重心
    filters.append("equalizer=f=80:width_type=o:width=1:g=1.5")
    # 中域に温かみ
    filters.append("equalizer=f=1200:width_type=o:width=2:g=0.8")

    if brightness < 0.4:
        # 暗めの曲は高域に空気感
        filters.append("equalizer=f=8000:width_type=o:width=2:g=1.5")
        filters.append("equalizer=f=14000:width_type=o:width=2:g=2.0")
    elif brightness > 0.7:
        # 明るすぎる場合は少し抑える
        filters.append("equalizer=f=12000:width_type=o:width=2:g=-1.0")

    return ",".join(filters)


# ===== 曲調分析 =====
def analyze_audio(path):
    """BPM・キー・エネルギー・明暗を分析"""
    try:
        import librosa
        y, sr = librosa.load(path, sr=None, mono=True)

        # BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo)

        # エネルギー
        rms    = librosa.feature.rms(y=y)[0]
        energy = float(np.mean(rms))

        # 明暗（スペクトル重心）
        centroid   = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        brightness = float(np.mean(centroid)) / (sr / 2)

        # キー（クロマ）
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        key_idx = int(np.argmax(np.mean(chroma, axis=1)))
        keys    = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        key     = keys[key_idx]

        analysis = {
            "bpm":        round(bpm, 1),
            "key":        key,
            "energy":     round(energy, 4),
            "brightness": round(brightness, 3),
        }
        print(f"分析結果: {analysis}", flush=True)
        return analysis

    except Exception as e:
        print(f"分析エラー: {e}", flush=True)
        return {"bpm": 0, "key": "C", "energy": 0.1, "brightness": 0.5}


# ===== ノイズリダクション =====
def noise_reduction(input_path, output_path):
    """ノイズリダクション（息づかい・部屋鳴りを残す）"""
    try:
        import librosa
        import soundfile as sf
        import noisereduce as nr

        y, sr = librosa.load(input_path, sr=None, mono=False)

        if y.ndim == 1:
            # モノラル
            reduced = nr.reduce_noise(y=y, sr=sr, prop_decrease=0.7)
        else:
            # ステレオ（各チャンネル処理）
            reduced = np.array([
                nr.reduce_noise(y=ch, sr=sr, prop_decrease=0.7)
                for ch in y
            ])

        sf.write(output_path, reduced.T if reduced.ndim > 1 else reduced, sr)
        print(f"ノイズリダクション完了: {output_path}", flush=True)
        return output_path

    except Exception as e:
        print(f"ノイズリダクションエラー（スキップ）: {e}", flush=True)
        return input_path


# ===== サチュレーション（テープ感） =====
def apply_saturation(input_path, output_path, amount=0.3):
    """軽いテープサチュレーションでデジタルの無機質さを取る"""
    # FFmpegのasoftclipフィルターで軽いサチュレーション
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", f"asoftclip=type=tanh:threshold={1.0 - amount * 0.3}:output={0.95 - amount * 0.1}",
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return input_path
    return output_path


# ===== リバーブ =====
def apply_reverb(input_path, output_path, room_size=0.3, wet=0.15):
    """空間感を付加するリバーブ"""
    # FFmpegのafirフィルターまたはaecho
    delay_ms  = int(20 + room_size * 80)
    decay     = 0.2 + room_size * 0.3
    wet_gain  = wet

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", (
            f"aecho=in_gain=1.0:out_gain={1 - wet_gain * 0.3}:"
            f"delays={delay_ms}|{delay_ms * 1.3}:"
            f"decays={decay}|{decay * 0.7}"
        ),
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return input_path
    return output_path


# ===== ラウドネス正規化 =====
def normalize_loudness(input_path, output_path,
                        target_lufs=-14.0, true_peak=-1.0):
    """
    -14 LUFS / True Peak -1.0dBTP に正規化
    全SNSのストリーミング標準
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", (
            f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:"
            "print_format=json"
        ),
        output_path
    ]
    run(cmd)
    print(f"ラウドネス正規化完了: {target_lufs} LUFS, TP {true_peak} dBTP", flush=True)


# ===== ステレオ処理 =====
def process_stereo(input_path, output_path):
    """
    低域をモノラルに近づける（スピーカー再生でも安定）
    中高域は自然なステレオ幅を保つ
    """
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", (
            # 低域（200Hz以下）をモノラルに
            "stereotools=mlev=0.8,"
            # ステレオ幅を自然に整える（過度な広がりを抑える）
            "stereotools=sbal=0:slev=0.9"
        ),
        output_path
    ]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return input_path
    return output_path


# ===== クリップ生成（librosaで美味しいところを検出） =====
def generate_clips(mastered_path, total_duration, target_duration=20.0):
    """
    楽曲の「美味しいところ」を検出して20秒クリップを複数生成
    """
    clips = []
    try:
        import librosa
        y, sr = librosa.load(mastered_path, sr=None, mono=True)
        duration = len(y) / sr

        if duration <= target_duration:
            # 曲が短い場合はそのまま
            clips.append({"start": 0, "end": duration, "type": "full"})
            return clips

        # エネルギー曲線を計算
        hop_length = int(sr * 0.1)  # 0.1秒単位
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        times = librosa.times_like(rms, sr=sr, hop_length=hop_length)

        # 区間ごとのエネルギー合計（20秒窓）
        window_frames = int(target_duration / 0.1)
        scores = []
        for i in range(len(rms) - window_frames):
            window_energy = np.mean(rms[i:i + window_frames])
            # イントロ・アウトロを避けるため中央部分にボーナス
            center_bonus = 1.0 - abs(i / len(rms) - 0.5) * 0.4
            scores.append(window_energy * center_bonus)

        # スコアが高い上位3区間を取得（重複しないよう間隔をとる）
        min_gap_frames = int(30 / 0.1)  # 30秒以上離れた区間
        top_clips = []
        sorted_indices = np.argsort(scores)[::-1]

        for idx in sorted_indices:
            start_time = times[idx]
            end_time   = start_time + target_duration

            if end_time > duration:
                continue

            # 既存クリップと重複チェック
            overlap = any(
                abs(start_time - c["start"]) < 30
                for c in top_clips
            )
            if overlap:
                continue

            top_clips.append({
                "start": round(start_time, 2),
                "end":   round(end_time, 2),
                "score": round(float(scores[idx]), 4),
                "type":  f"clip_{len(top_clips) + 1}"
            })

            if len(top_clips) >= 3:
                break

        clips = top_clips if top_clips else [{"start": 30, "end": 30 + target_duration, "type": "clip_1"}]
        print(f"クリップ候補: {clips}", flush=True)

    except Exception as e:
        print(f"クリップ生成エラー: {e}", flush=True)
        clips = [{"start": 0, "end": target_duration, "type": "clip_1"}]

    return clips


def extract_clip(mastered_path, start, end, output_path):
    """クリップを切り出し（フェードイン・アウト付き）"""
    duration     = end - start
    fade_in_dur  = min(1.5, duration * 0.1)
    fade_out_dur = min(2.0, duration * 0.12)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t",  str(duration),
        "-i",  mastered_path,
        "-af", (
            f"afade=t=in:st=0:d={fade_in_dur},"
            f"afade=t=out:st={duration - fade_out_dur}:d={fade_out_dur},"
            f"loudnorm=I=-14:TP=-1:LRA=11"
        ),
        output_path
    ]
    run(cmd)


# ===== メイン =====
def main():
    file_id   = os.environ.get("FILE_ID", "")
    file_name = os.environ.get("FILE_NAME", "bgm.wav")
    sheet_row = os.environ.get("SHEET_ROW", "")
    input_path = f"/tmp/bgm_input_{file_id[:8]}{os.path.splitext(file_name)[1]}"

    if not os.path.exists(input_path):
        print(f"入力ファイルが見つかりません: {input_path}", flush=True)
        return

    work_dir = "/tmp/bgm_work"
    os.makedirs(work_dir, exist_ok=True)

    # ===== 1. 素材タイプ判別 =====
    source_type = detect_source_type(input_path)

    # ===== 2. 曲調分析 =====
    analysis = analyze_audio(input_path)

    current = input_path

    # ===== 3. ノイズリダクション（撮って出しのみ） =====
    if source_type == "rough":
        nr_path = f"{work_dir}/01_nr.wav"
        current = noise_reduction(current, nr_path)

    # ===== 4. EQ =====
    eq_path = f"{work_dir}/02_eq.wav"
    eq_filters = build_eq_filters(source_type, analysis)
    run(["ffmpeg", "-y", "-i", current, "-af", eq_filters, eq_path])
    current = eq_path
    print("EQ完了", flush=True)

    # ===== 5. コンプレッサー =====
    comp_path = f"{work_dir}/03_comp.wav"
    if source_type == "rough":
        # マルチバンド的に：フルレンジコンプ
        comp_filter = "acompressor=threshold=-18dB:ratio=3:attack=30:release=200:makeup=2dB"
    else:
        # バスコンプ（グルー感）
        comp_filter = "acompressor=threshold=-12dB:ratio=2:attack=50:release=300:makeup=1dB"
    run(["ffmpeg", "-y", "-i", current, "-af", comp_filter, comp_path])
    current = comp_path
    print("コンプレッサー完了", flush=True)

    # ===== 6. サチュレーション =====
    sat_path = f"{work_dir}/04_sat.wav"
    sat_amount = 0.35 if source_type == "rough" else 0.15
    current = apply_saturation(current, sat_path, sat_amount)
    print("サチュレーション完了", flush=True)

    # ===== 7. リバーブ =====
    rev_path = f"{work_dir}/05_rev.wav"
    bpm = analysis.get("bpm", 80)
    energy = analysis.get("energy", 0.1)
    # ゆっくり・静かな曲はリバーブを長め
    room_size = 0.4 if bpm < 80 and energy < 0.05 else 0.25
    wet       = 0.18 if bpm < 80 else 0.12
    current   = apply_reverb(current, rev_path, room_size, wet)
    print("リバーブ完了", flush=True)

    # ===== 8. ステレオ処理 =====
    st_path = f"{work_dir}/06_stereo.wav"
    current = process_stereo(current, st_path)
    print("ステレオ処理完了", flush=True)

    # ===== 9. ラウドネス正規化 =====
    mastered_path = f"{work_dir}/mastered.wav"
    normalize_loudness(current, mastered_path)
    print("マスタリング完了", flush=True)

    # ===== 10. クリップ生成 =====
    clips = generate_clips(mastered_path, total_duration=None)
    clip_paths = []
    for clip in clips:
        clip_path = f"{work_dir}/clip_{clip['type']}.wav"
        extract_clip(mastered_path, clip["start"], clip["end"], clip_path)
        clip_paths.append(clip_path)

    # ===== 11. Driveにアップロード =====
    preview_url = upload_mastered_to_drive(mastered_path, clip_paths, file_name)

    # ===== 12. スプレッドシートを更新 =====
    update_bgm_sheet(sheet_row, analysis, clips, preview_url)

    print(f"mastered_path={mastered_path}")
    print(f"preview_url={preview_url}")
    print(f"bpm={analysis['bpm']}")
    print(f"key={analysis['key']}")

    print(f"\n処理サマリー:", flush=True)
    print(f"  素材タイプ: {source_type}", flush=True)
    print(f"  BPM: {analysis['bpm']}", flush=True)
    print(f"  キー: {analysis['key']}", flush=True)
    print(f"  クリップ数: {len(clip_paths)}", flush=True)


def upload_mastered_to_drive(mastered_path, clip_paths, original_name):
    """マスタリング済みファイルをDriveにアップロード"""
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
        if not creds_json:
            return ""

        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        drive = build("drive", "v3", credentials=creds)

        # マスタリング済みフォルダ
        folders = drive.files().list(
            q="name='tameiki_bgm_mastered' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute().get("files", [])
        folder_id = folders[0]["id"] if folders else None

        # マスタリング済みをアップロード
        base_name = os.path.splitext(original_name)[0]
        metadata  = {"name": f"{base_name}_mastered.wav"}
        if folder_id:
            metadata["parents"] = [folder_id]
        media = MediaFileUpload(mastered_path, mimetype="audio/wav")
        file  = drive.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()
        drive.permissions().create(
            fileId=file["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()
        preview_url = f"https://drive.google.com/file/d/{file['id']}/view"

        # クリップもアップロード
        for i, clip_path in enumerate(clip_paths):
            clip_metadata = {"name": f"{base_name}_clip{i+1}.wav"}
            if folder_id:
                clip_metadata["parents"] = [folder_id]
            clip_media = MediaFileUpload(clip_path, mimetype="audio/wav")
            drive.files().create(
                body=clip_metadata, media_body=clip_media
            ).execute()

        print(f"Drive保存完了: {preview_url}", flush=True)
        return preview_url

    except Exception as e:
        print(f"Drive保存エラー: {e}", flush=True)
        return ""


def update_bgm_sheet(row, analysis, clips, preview_url):
    """BGMシートのマスタリング情報を更新"""
    if not row:
        return
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build

        creds_json = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))
        creds = sa.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)
        spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"BGM!D{row}:L{row}",
            valueInputOption="RAW",
            body={"values": [[
                analysis.get("bpm", ""),
                analysis.get("key", ""),
                round(analysis.get("energy", 0), 4),
                round(analysis.get("brightness", 0), 3),
                "完了",   # マスタリング済み
                "待機中", # フルMV生成済み（タイトル待ち）
                0,        # 使用回数
                "",       # タイトル（LINEで返信後に更新）
                "タイトル待ち"  # ステータス
            ]]}
        ).execute()
        print("BGMシート更新完了", flush=True)
    except Exception as e:
        print(f"シート更新エラー: {e}", flush=True)


if __name__ == "__main__":
    main()
