#!/usr/bin/env python3
"""
scripts/get_conditions.py
当日の投稿条件（天気・時間・季節・月齢・曜日・社会的ムード）を取得
GitHub Actionsのoutputに書き出す
"""
import os
import json
import requests
from datetime import datetime, timezone, timedelta
import ephem
import math

# 日本時間
JST = timezone(timedelta(hours=9))
now = datetime.now(JST)

def get_weather():
    """OpenWeatherMap APIで東京の天気・気温を取得"""
    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    if not api_key:
        return {"weather": "any", "temperature": "any", "temp_c": None}

    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {"q": "Tokyo,JP", "appid": api_key, "units": "metric", "lang": "ja"}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        weather_id = data["weather"][0]["id"]
        temp_c     = data["main"]["temp"]

        # 天気タグに変換
        if weather_id >= 600:   weather = "雪"
        elif weather_id >= 500: weather = "雨"
        elif weather_id >= 300: weather = "雨"
        elif weather_id >= 200: weather = "雨"
        elif weather_id >= 801: weather = "曇"
        else:                   weather = "晴"

        # 気温感タグ
        if temp_c < 8:    temperature = "寒い"
        elif temp_c < 18: temperature = "涼しい"
        elif temp_c < 27: temperature = "温かい"
        else:             temperature = "暑い"

        return {"weather": weather, "temperature": temperature, "temp_c": temp_c}

    except Exception as e:
        print(f"天気取得エラー: {e}", flush=True)
        return {"weather": "any", "temperature": "any", "temp_c": None}


def get_time_tag():
    """時間タグを返す"""
    hour = now.hour
    if 5  <= hour < 10: return "朝"
    elif 10 <= hour < 17: return "昼"
    elif 17 <= hour < 23: return "夜"
    else:                  return "深夜"


def get_season():
    """季節タグを返す（境目2週間は両方対応）"""
    month = now.month
    day   = now.day

    # 境目（前後2週間は両方）
    if (month == 3 and day >= 6) or (month >= 4 and month <= 5): return "春"
    elif month == 3 and day < 6:  return "冬"   # 冬→春の境目
    elif month == 6 and day < 15: return "春"   # 春→夏の境目
    elif (month == 6 and day >= 15) or (month >= 7 and month <= 8): return "夏"
    elif month == 9 and day < 15: return "夏"   # 夏→秋の境目
    elif (month == 9 and day >= 15) or (month >= 10 and month <= 11): return "秋"
    elif month == 12 and day < 6: return "秋"   # 秋→冬の境目
    else:                          return "冬"


def get_moon_phase():
    """月齢タグを返す"""
    try:
        moon = ephem.Moon(now.strftime("%Y/%m/%d"))
        phase = moon.phase  # 0〜100（0=新月、50=満月）

        if phase < 10 or phase > 90:  return "新月"
        elif 40 <= phase <= 60:        return "満月"
        else:                          return "半月"
    except:
        return "any"


def get_weekday():
    """曜日タグを返す"""
    weekday = now.weekday()  # 0=月曜 〜 6=日曜
    return "休日" if weekday >= 5 else "平日"


def get_social_mood():
    """社会的ムードを返す"""
    month = now.month
    day   = now.day
    weekday = now.weekday()

    # 年末年始
    if month == 12 and day >= 28: return "年末"
    if month == 1  and day <= 4:  return "年始"

    # お盆
    if month == 8 and 13 <= day <= 16: return "お盆"

    # 連休の判定（祝日APIを使わず簡易判定）
    # 月曜が祝日パターン（ハッピーマンデー）は簡易的にスキップ
    # GW（4月末〜5月頭）
    if month == 4 and day >= 28: return "連休前"
    if month == 5 and day <= 6:  return "お盆" if day <= 3 else "連休明け"

    # 週末前後
    if weekday == 4: return "連休前"   # 金曜
    if weekday == 0: return "連休明け"  # 月曜

    return "通常"


# ===== メイン =====
weather_data = get_weather()

conditions = {
    "date":          now.strftime("%Y-%m-%d"),
    "time":          get_time_tag(),
    "season":        get_season(),
    "moon_phase":    get_moon_phase(),
    "weekday":       get_weekday(),
    "social_mood":   get_social_mood(),
    "weather":       weather_data["weather"],
    "temperature":   weather_data["temperature"],
    "temp_c":        weather_data["temp_c"],
    "hour":          now.hour,
    "month":         now.month,
    "day":           now.day,
}

conditions_json = json.dumps(conditions, ensure_ascii=False)

print(f"conditions_json={conditions_json}")
print(f"date={conditions['date']}")
print(f"weather={conditions['weather']}")
print(f"season={conditions['season']}")
print(f"moon_phase={conditions['moon_phase']}")

# デバッグ出力
print(f"--- 本日の条件 ---", flush=True)
for k, v in conditions.items():
    print(f"  {k}: {v}", flush=True)
