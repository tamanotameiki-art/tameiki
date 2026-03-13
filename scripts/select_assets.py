#!/usr/bin/env python3
"""
scripts/select_assets.py
当日の条件に基づいて詩・動画・フィルター・環境音を選択
Claudeによる相性チェック付き（最大3回リトライ）
"""
import os
import json
import random
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# ===== Sheets API =====
def get_sheets_service():
    import google.oauth2.service_account as sa
    from googleapiclient.discovery import build

    creds_json = os.environ["GOOGLE_CREDENTIALS"]
    creds_info = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = sa.Credentials.from_service_account_info(creds_info, scopes=scopes)
    return build("sheets", "v4", credentials=creds)

def get_sheet_data(service, spreadsheet_id, sheet_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:Z"
    ).execute()
    return result.get("values", [])


# ===== タグ一致チェック =====
def match_tag(tag_value, condition):
    if not tag_value or not condition:
        return False
    if str(tag_value).strip() == "any":
        return True
    return any(t.strip() == str(condition).strip()
               for t in str(tag_value).split("・"))


def score_poem(row, conditions, headers):
    """詩のタグ一致スコアを計算"""
    if len(row) < 11:
        return 0
    score = 0
    tag_map = {
        "時間": conditions.get("time"),
        "天気": conditions.get("weather"),
        "季節": conditions.get("season"),
        "曜日": conditions.get("weekday"),
        "気温感": conditions.get("temperature"),
        "月齢": conditions.get("moon_phase"),
        "社会的ムード": conditions.get("social_mood"),
    }
    col_map = {h: i for i, h in enumerate(headers)}
    for tag_name, cond_value in tag_map.items():
        col_idx = col_map.get(tag_name)
        if col_idx is not None and col_idx < len(row):
            if match_tag(row[col_idx], cond_value):
                score += 1
    return score


def select_poem(service, spreadsheet_id, conditions):
    """詩を選択（仕様通りの優先順位）"""
    data    = get_sheet_data(service, spreadsheet_id, "文字列")
    if len(data) <= 1:
        raise ValueError("文字列が登録されていません")

    headers = data[0]
    rows    = data[1:]

    scored = []
    for i, row in enumerate(rows):
        poem = row[0] if row else ""
        if not poem.strip():
            continue
        status_idx = headers.index("ステータス") if "ステータス" in headers else 14
        status = row[status_idx] if len(row) > status_idx else "未投稿"
        count_idx = headers.index("投稿回数") if "投稿回数" in headers else 11
        post_count = int(row[count_idx]) if len(row) > count_idx and row[count_idx] else 0
        score = score_poem(row, conditions, headers)
        scored.append({
            "row_idx": i + 2,
            "poem": poem,
            "status": status,
            "post_count": post_count,
            "score": score,
            "row": row,
            "headers": headers,
        })

    unpublished = [x for x in scored if x["status"] == "未投稿"]
    published   = [x for x in scored if x["status"] != "未投稿"]

    candidates = [x for x in unpublished if x["score"] >= 2]
    if not candidates:
        candidates = [x for x in unpublished if x["score"] >= 1]
    if not candidates:
        candidates = unpublished

    if candidates and all(x["score"] == 0 for x in candidates):
        better_past = [x for x in published if x["score"] >= 1]
        if better_past:
            candidates = better_past

    if not candidates:
        candidates = sorted(published, key=lambda x: x["post_count"])

    if not candidates:
        raise ValueError("選択できる詩がありません")

    candidates.sort(key=lambda x: (-x["score"], x["post_count"]))
    return candidates[0]


def select_video(service, spreadsheet_id, poem_data, used_video_ids=None):
    """動画素材を選択（スコア上位からランダム選択）"""
    data = get_sheet_data(service, spreadsheet_id, "動画素材")
    if len(data) <= 1:
        return None

    headers = data[0]
    rows    = data[1:]
    used    = used_video_ids or []

    poem_tags = {
        "emotion": poem_data["row"][1] if len(poem_data["row"]) > 1 else "any",
        "time":    poem_data["row"][2] if len(poem_data["row"]) > 2 else "any",
        "weather": poem_data["row"][3] if len(poem_data["row"]) > 3 else "any",
        "season":  poem_data["row"][4] if len(poem_data["row"]) > 4 else "any",
    }

    scored = []
    for i, row in enumerate(rows):
        file_id = row[1] if len(row) > 1 else ""
        if not file_id or file_id in used:
            continue
        status_idx = 15
        status = row[status_idx] if len(row) > status_idx else "有効"
        if status != "有効":
            continue

        score = 0
        if match_tag(row[2] if len(row) > 2 else "", poem_tags["emotion"]): score += 1
        if match_tag(row[3] if len(row) > 3 else "", poem_tags["time"]):    score += 1
        if match_tag(row[4] if len(row) > 4 else "", poem_tags["weather"]): score += 1
        if match_tag(row[5] if len(row) > 5 else "", poem_tags["season"]):  score += 1

        use_count = int(row[11]) if len(row) > 11 and row[11] else 0
        scored.append({
            "file_id":   file_id,
            "file_name": row[0] if row else "",
            "score":     score,
            "use_count": use_count,
            "row_idx":   i + 2,
        })

    if not scored:
        return None

    # スコア最高値のグループからランダム選択
    # ただし使用回数が少ない素材を優遇（重み付き）
    max_score = max(s["score"] for s in scored)
    top_candidates = [s for s in scored if s["score"] == max_score]

    # 使用回数が少ないほど選ばれやすい重み付き
    min_count = min(c["use_count"] for c in top_candidates)
    max_count = max(c["use_count"] for c in top_candidates)
    if max_count == min_count:
        return random.choice(top_candidates)
    else:
        weights = [1.0 / (c["use_count"] - min_count + 1) for c in top_candidates]
        return random.choices(top_candidates, weights=weights, k=1)[0]


def select_filter(poem_tags, video_tags=None, used_filters=None):
    """フィルターを選択"""
    FILTER_TAGS = {
        "写ルンです":   ["哀愁", "温かい", "夜", "曇", "秋", "冬"],
        "VHS":          ["哀愁", "孤独", "夜", "都市", "雨", "冬"],
        "燃えたフィルム": ["哀愁", "孤独", "空虚", "夜", "秋", "冬"],
        "ドリーミー":   ["静謐", "希望", "朝", "春", "晴"],
        "サイレント映画": ["静謐", "孤独", "空虚", "深夜", "冬"],
        "ゴールデンアワー": ["希望", "温かい", "晴", "春", "夏"],
        "霧の中":       ["静謐", "哀愁", "朝", "曇", "雨", "冬"],
        "水の底":       ["孤独", "空虚", "哀愁", "深夜", "夏"],
        "夜光":         ["哀愁", "孤独", "夜", "深夜", "都市"],
        "色褪せた夏":   ["哀愁", "孤独", "夏", "昼", "晴"],
        "朝靄":         ["希望", "静謐", "朝", "春", "晴"],
        "廃墟のロマン": ["孤独", "空虚", "哀愁", "秋", "曇"],
        "月明かり":     ["静謐", "孤独", "哀愁", "夜", "深夜", "冬"],
        "インスタント": ["温かい", "希望", "昼", "夏", "晴"],
    }

    used = used_filters or []
    all_tags = []
    for v in poem_tags.values():
        if v and v != "any":
            all_tags.extend(v.split("・"))

    scored = []
    for name, tags in FILTER_TAGS.items():
        if name in used:
            continue
        score = sum(1 for t in tags if t in all_tags)
        scored.append({"name": name, "score": score})

    scored.sort(key=lambda x: -x["score"])

    if scored and scored[0]["score"] > 0 and random.random() < 0.85:
        return scored[0]["name"]
    if scored:
        return random.choice(scored[:min(3, len(scored))])["name"]
    return "写ルンです"


def select_se(service, spreadsheet_id, poem_tags, filter_name):
    """環境音を選択（フィルター優先＋使用回数少ない順にランダム）"""
    data = get_sheet_data(service, spreadsheet_id, "環境音")
    if len(data) <= 1:
        return []
    rows = data[1:]

    FILTER_SE_MAP = {
        "写ルンです":   [("レコードノイズ", "メイン"), ("雨", "サブ")],
        "VHS":          [("ブラウン管ノイズ", "メイン"), ("雑踏", "サブ")],
        "燃えたフィルム": [("風", "メイン"), ("虫", "アクセント")],
        "ドリーミー":   [("川", "メイン"), ("風", "サブ")],
        "サイレント映画": [("レコードノイズ", "メイン")],
        "ゴールデンアワー": [("鳥", "メイン"), ("風", "サブ")],
        "霧の中":       [("雨", "メイン"), ("水滴", "サブ")],
        "水の底":       [("水", "メイン"), ("深い静寂", "サブ")],
        "夜光":         [("雑踏", "メイン"), ("電車", "アクセント")],
        "色褪せた夏":   [("蝉", "メイン"), ("風", "サブ")],
        "朝靄":         [("鳥", "メイン"), ("風", "サブ")],
        "廃墟のロマン": [("風", "メイン"), ("虫", "サブ")],
        "月明かり":     [("鈴虫", "メイン"), ("風", "アクセント")],
        "インスタント": [("雑踏", "メイン"), ("風", "サブ")],
    }

    preferred = FILTER_SE_MAP.get(filter_name, [])
    selected  = []

    for se_kind, layer in preferred:
        # 該当する種類の音源を全て集める
        matches = [r for r in rows if len(r) > 2 and se_kind in str(r[2])]
        if not matches:
            continue
        # 使用回数が少ないものを優遇（重み付きランダム）
        use_counts = []
        for r in matches:
            count = int(r[10]) if len(r) > 10 and r[10] else 0
            use_counts.append(count)
        min_count = min(use_counts)
        max_count = max(use_counts)
        if max_count == min_count:
            chosen = random.choice(matches)
        else:
            weights = [1.0 / (c - min_count + 1) for c in use_counts]
            chosen = random.choices(matches, weights=weights, k=1)[0]

        selected.append({
            "file_id":   chosen[1] if len(chosen) > 1 else "",
            "file_name": chosen[0] if chosen else "",
            "kind":      se_kind,
            "layer":     layer,
        })
        if len(selected) >= 3:
            break

    return selected


# ===== Claude 相性チェック =====
def check_compatibility(poem, video_name, filter_name, conditions):
    """ClaudeによるNGチェック（3回まで）"""
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return True

    prompt = f"""
以下の組み合わせが「たまのためいき。」の世界観として成立するか判断してください。

詩：{poem}
背景動画：{video_name}
フィルター：{filter_name}
今日の条件：天気={conditions.get('weather')} 季節={conditions.get('season')} 時間={conditions.get('time')}

世界観：静謐・哀愁・希望・余白がある・媚びない・押しつけない

NGの場合のみその理由を教えてください。
必ずJSON形式のみで回答してください：
{{"ok": true/false, "reason": "NGの場合のみ記載"}}
"""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        text = response.json()["content"][0]["text"]
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result.get("ok", True)
    except Exception as e:
        print(f"相性チェックエラー（スキップ）: {e}")

    return True


# ===== メイン =====
def main():
    conditions = json.loads(os.environ.get("CONDITIONS", "{}"))
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    force_poem   = os.environ.get("FORCE_POEM",   "").strip()
    force_filter = os.environ.get("FORCE_FILTER", "").strip()

    service = get_sheets_service()

    for attempt in range(3):
        print(f"素材選択 試行 {attempt + 1}/3", flush=True)

        if force_poem:
            poem_data = {"poem": force_poem, "row": [], "row_idx": None, "score": 0}
        else:
            poem_data = select_poem(service, spreadsheet_id, conditions)

        poem = poem_data["poem"]
        print(f"詩: {poem[:30]}...", flush=True)

        history = get_sheet_data(service, spreadsheet_id, "投稿履歴")
        used_videos  = []
        used_filters = []
        for row in history[1:]:
            if len(row) > 0 and row[1] == poem:
                if len(row) > 2: used_videos.append(row[2])
                if len(row) > 3: used_filters.append(row[3])

        video_data = select_video(service, spreadsheet_id, poem_data, used_videos)
        video_name = video_data["file_name"] if video_data else "default"
        video_id   = video_data["file_id"]   if video_data else ""
        print(f"動画: {video_name}", flush=True)

        poem_tags = {}
        if poem_data.get("row") and len(poem_data["row"]) > 10:
            row = poem_data["row"]
            poem_tags = {
                "emotion": row[1], "time": row[2], "weather": row[3],
                "season":  row[4], "weekday": row[5], "temperature": row[6],
                "moon":    row[7], "social": row[8], "color": row[9], "tempo": row[10],
            }

        filter_name = force_filter if force_filter else select_filter(
            poem_tags, None, used_filters
        )
        print(f"フィルター: {filter_name}", flush=True)

        ok = check_compatibility(poem, video_name, filter_name, conditions)
        if ok:
            print(f"相性チェック: OK", flush=True)
            break
        else:
            print(f"相性チェック: NG リトライ", flush=True)
            if attempt == 2:
                print("3回NGのため最後の組み合わせで続行", flush=True)

    se_list = select_se(service, spreadsheet_id, poem_tags, filter_name)
    print(f"環境音: {[s['kind'] for s in se_list]}", flush=True)

    emotion_tags = poem_tags.get("emotion", "any")

    selection = {
        "poem":          poem,
        "poem_row_idx":  poem_data.get("row_idx"),
        "video_id":      video_id,
        "video_name":    video_name,
        "video_row_idx": video_data.get("row_idx") if video_data else None,
        "filter_name":   filter_name,
        "se_list":       se_list,
        "emotion_tags":  emotion_tags,
        "poem_tags":     poem_tags,
    }

    selection_json = json.dumps(selection, ensure_ascii=False)
    print(f"selection_json={selection_json}")
    print(f"poem={poem}")
    print(f"filter_name={filter_name}")
    print(f"video_id={video_id}")
    print(f"emotion_tags={emotion_tags}")


if __name__ == "__main__":
    main()
