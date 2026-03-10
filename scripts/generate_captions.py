#!/usr/bin/env python3
"""
scripts/generate_captions.py
詩の言語学習に基づいたSNS別キャプション自動生成
"""
import os
import json
import requests
import re

def get_poem_corpus(service, spreadsheet_id):
    """過去の詩を全て取得（言語学習用）"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="文字列!A2:A"
        ).execute()
        poems = [row[0] for row in result.get("values", []) if row]
        return "\n---\n".join(poems[:50])  # 最新50本
    except:
        return ""

def generate_captions(poem, emotion_tags, conditions, corpus):
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return get_fallback_captions(poem)

    prompt = f"""
あなたは詩人「たまのためいき。」のSNS投稿キャプションを書きます。

【今日の詩】
{poem}

【感情タグ】{emotion_tags}
【今日の条件】天気={conditions.get('weather')} 季節={conditions.get('season')} 時間={conditions.get('time')} 月齢={conditions.get('moon_phase')}

【このアカウントの過去の詩（言語・文体の参照用）】
{corpus}

【アカウントの世界観・トーン】
- 少し年上のお兄さんが夜にぽつりと語りかける温度感
- 媚びない・押しつけない・余白がある
- 詩の続きのような言葉・断言よりも余韻
- NGワード: 「一緒に」「繋がりたい」「刺さった」「泣ける」「エモい」「共感」「お疲れ様」

【各SNSの仕様】
- X: 10〜30文字・問いかけ形式または断言・余白を残す（YouTubeのURLを後で付加するので短めに）
- Instagram: 100〜200文字・情緒的・詩の続きのような一段落
- YouTube: 50〜100文字・検索キーワードを自然に含む（「詩」「言葉」「朗読」など）
- TikTok: 20〜40文字・静かに語りかける・夜感がある
- Pinterest: 30〜60文字・詩の余韻・保存したくなるような静かな言葉

必ず以下のJSON形式のみで回答してください（説明文不要）：
{{
  "x": "",
  "instagram": "",
  "youtube": "",
  "tiktok": "",
  "pinterest": ""
}}
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
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        text = response.json()["content"][0]["text"]
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            captions = json.loads(match.group())
            return captions
    except Exception as e:
        print(f"キャプション生成エラー: {e}")

    return get_fallback_captions(poem)


def get_fallback_captions(poem):
    """Claude API失敗時のフォールバック（ルールベース）"""
    first_line = poem.split("\n")[0][:20]
    return {
        "x":          first_line,
        "instagram":  poem,
        "youtube":    f"心に響く詩｜たまのためいき。{first_line}",
        "tiktok":     first_line,
        "pinterest":  first_line,
    }


def main():
    poem         = os.environ.get("POEM", "")
    emotion_tags = os.environ.get("EMOTION_TAGS", "")
    conditions   = json.loads(os.environ.get("CONDITIONS", "{}"))
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    corpus = ""
    if spreadsheet_id:
        try:
            import google.oauth2.service_account as sa
            from googleapiclient.discovery import build
            creds_json = os.environ["GOOGLE_CREDENTIALS"]
            creds_info = json.loads(creds_json)
            scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
            creds  = sa.Credentials.from_service_account_info(creds_info, scopes=scopes)
            service = build("sheets", "v4", credentials=creds)
            corpus = get_poem_corpus(service, spreadsheet_id)
        except Exception as e:
            print(f"コーパス取得エラー（スキップ）: {e}")

    captions = generate_captions(poem, emotion_tags, conditions, corpus)

    print(f"x_caption={captions.get('x', '')}")
    print(f"instagram_caption={captions.get('instagram', '')}")
    print(f"youtube_caption={captions.get('youtube', '')}")
    print(f"tiktok_caption={captions.get('tiktok', '')}")
    print(f"pinterest_caption={captions.get('pinterest', '')}")

    print("\n--- 生成されたキャプション ---", flush=True)
    for platform, text in captions.items():
        print(f"[{platform}] {text}", flush=True)


if __name__ == "__main__":
    main()
