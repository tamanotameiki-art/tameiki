"""
たまのためいき。— 設定ファイル
全ての定数・パラメータをここで管理する
"""

# ===== 画面サイズ =====
W, H = 720, 1280
FPS  = 24

# ===== フォント =====
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_IDX  = 0

# ===== カラーパレット =====
C_MIST   = (250, 228, 195)
C_TEXT   = (255, 248, 230)
C_DARK   = (8,   5,   3)
C_GOLD   = (240, 192, 112)
C_AMBER  = (255, 225, 160)
C_WHITE  = (255, 250, 220)

# ===== タイムライン =====
INTRO_DUR    = 2.0
TEXT_DELAY   = 3.5
CHAR_INTERVAL= 0.28   # ★ 0.20→0.28秒：文字の出現間隔を少し広げてゆったりさせる
ENDING_START = 18.0
TOTAL_SEC    = 20.0

# ===== テキストアニメーション =====
CHAR_FADEIN_SEC = 1.20   # ★ 0.28→1.20秒：じわぁと滲み出る時間を大幅に延ばす
                          #   CHAR_INTERVAL(0.28)より長いため複数文字が重なって出てくる
LINE_PAUSE_SEC  = [1.6, 2.8]

# ===== SNS安全エリア =====
SAFE_TOP    = 0.12
SAFE_BOTTOM = 0.75
SAFE_LEFT   = 0.08
SAFE_RIGHT  = 0.85

# ===== 縦書き：句読点・記号オフセット =====
PUNCT_OFFSET = {
    "、": (0.35, -0.10),
    "。": (0.35, -0.10),
    "，": (0.35, -0.10),
    "．": (0.35, -0.10),
    "！": (0.00,  0.00),
    "？": (0.00,  0.00),
    "…": (0.00,  0.00),
}

ROTATE_CHARS = set("ーー〜～-—―…")

VERTICAL_GLYPH_MAP = {
    "「": "﹁",
    "」": "﹂",
    "『": "﹃",
    "』": "﹄",
    "（": "︵",
    "）": "︶",
    "【": "︻",
    "】": "︼",
    "〔": "︹",
    "〕": "︺",
}

# ===== フィルター定義（全20種） =====
FILTERS = {

    "写ルンです": {
        "tags": ["哀愁", "温かい", "夜", "曇", "秋", "冬"],
        "grain": 14,
        "color_matrix": {
            "R": (1.10, 0.03), "G": (1.02, 0.01), "B": (0.84, 0.0)
        },
        "contrast": 1.08,
        "lift": 0.02,
        "vignette": 190,
        "chroma_aber": 1.2,
        "bloom":      0.15,
        "halation":   0.14,
        "light_leak": True,
        "leak_strength": 0.45,
    },

    "VHS": {
        "tags": ["哀愁", "孤独", "夜", "都市", "雨", "冬"],
        "grain": 18,
        "color_matrix": {
            "R": (0.95, 0.02), "G": (0.92, 0.02), "B": (1.08, 0.04)
        },
        "contrast": 1.05,
        "lift": 0.03,
        "vignette": 210,
        "chroma_aber": 2.5,
        "bloom":      0.08,
        "halation":   0.06,
        "scanline":   True,
        "gate_glitch": True,
        "vhs_noise_band":   True,
        "noise_band_strength": 0.30,
        "vhs_color_bleed":  True,
        "color_bleed_strength": 5,
    },

    "燃えたフィルム": {
        "tags": ["哀愁", "孤独", "空虚", "夜", "秋", "冬", "曇"],
        "grain": 20,
        "color_matrix": {
            "R": (1.08, 0.05), "G": (0.98, 0.03), "B": (0.78, 0.0)
        },
        "contrast": 1.12,
        "lift": 0.04,
        "vignette": 220,
        "chroma_aber": 1.8,
        "bloom":      0.20,
        "halation":   0.18,
        "burn_edges": True,
        "film_burn_organic": True,
        "burn_strength": 0.55,
    },

    "ドリーミー": {
        "tags": ["静謐", "希望", "朝", "春", "晴", "曇"],
        "grain": 8,
        "color_matrix": {
            "R": (0.96, 0.02), "G": (0.98, 0.02), "B": (1.06, 0.04)
        },
        "contrast": 0.96,
        "lift": 0.05,
        "vignette": 150,
        "chroma_aber": 0.6,
        "bloom":      0.35,
        "halation":   0.08,
        "soft_focus": True,
    },

    "サイレント映画": {
        "tags": ["静謐", "孤独", "空虚", "深夜", "冬"],
        "grain": 22,
        "color_matrix": None,
        "contrast": 1.15,
        "lift": 0.0,
        "vignette": 230,
        "chroma_aber": 0.0,
        "bloom":      0.10,
        "halation":   0.05,
        "monochrome": True,
        "flicker":    True,
        "flicker_strength": 0.07,
        "vertical_jitter": True,
        "perforation": True,
    },

    "ゴールデンアワー": {
        "tags": ["希望", "温かい", "夕方", "晴", "春", "夏"],
        "grain": 10,
        "color_matrix": {
            "R": (1.12, 0.04), "G": (1.04, 0.02), "B": (0.80, 0.0)
        },
        "contrast": 1.08,
        "lift": 0.02,
        "vignette": 170,
        "chroma_aber": 0.8,
        "bloom":      0.28,
        "halation":   0.22,
    },

    "霧の中": {
        "tags": ["静謐", "哀愁", "朝", "曇", "雨", "冬", "春"],
        "grain": 10,
        "color_matrix": {
            "R": (0.92, 0.04), "G": (0.94, 0.04), "B": (1.02, 0.06)
        },
        "contrast": 0.90,
        "lift": 0.08,
        "vignette": 160,
        "chroma_aber": 0.4,
        "bloom":      0.40,
        "halation":   0.05,
        "soft_focus": True,
        "mist":       True,
    },

    "水の底": {
        "tags": ["孤独", "空虚", "哀愁", "深夜", "夏"],
        "grain": 12,
        "color_matrix": {
            "R": (0.82, 0.0), "G": (0.96, 0.04), "B": (1.10, 0.06)
        },
        "contrast": 1.06,
        "lift": 0.02,
        "vignette": 200,
        "chroma_aber": 1.0,
        "bloom":      0.20,
        "halation":   0.08,
        "ripple":     True,
        "ripple_strength": 1.5,
    },

    "夜光": {
        "tags": ["哀愁", "孤独", "夜", "深夜", "都市", "雨"],
        "grain": 16,
        "color_matrix": {
            "R": (1.04, 0.03), "G": (0.90, 0.01), "B": (0.82, 0.0)
        },
        "contrast": 1.10,
        "lift": 0.01,
        "vignette": 215,
        "chroma_aber": 1.5,
        "bloom":      0.25,
        "halation":   0.20,
    },

    "色褪せた夏": {
        "tags": ["哀愁", "孤独", "夏", "昼", "晴", "休日"],
        "grain": 14,
        "color_matrix": {
            "R": (0.98, 0.04), "G": (0.98, 0.04), "B": (1.04, 0.06)
        },
        "contrast": 0.94,
        "lift": 0.06,
        "vignette": 175,
        "chroma_aber": 1.0,
        "bloom":      0.18,
        "halation":   0.10,
        "fade":       True,
    },

    "朝靄": {
        "tags": ["希望", "静謐", "朝", "春", "晴", "新月"],
        "grain": 7,
        "color_matrix": {
            "R": (1.02, 0.04), "G": (0.98, 0.03), "B": (0.98, 0.04)
        },
        "contrast": 0.92,
        "lift": 0.07,
        "vignette": 140,
        "chroma_aber": 0.3,
        "bloom":      0.45,
        "halation":   0.06,
        "soft_focus": True,
        "mist":       True,
    },

    "廃墟のロマン": {
        "tags": ["孤独", "空虚", "哀愁", "秋", "曇", "雨"],
        "grain": 24,
        "color_matrix": {
            "R": (0.90, 0.02), "G": (1.00, 0.04), "B": (0.82, 0.0)
        },
        "contrast": 1.14,
        "lift": 0.02,
        "vignette": 235,
        "chroma_aber": 2.0,
        "bloom":      0.12,
        "halation":   0.08,
        "fade":       True,
        "burn_edges": True,
    },

    "月明かり": {
        "tags": ["静謐", "孤独", "哀愁", "夜", "深夜", "冬", "秋", "満月"],
        "grain": 9,
        "color_matrix": {
            "R": (0.80, 0.01), "G": (0.88, 0.02), "B": (1.08, 0.05)
        },
        "contrast": 1.06,
        "lift": 0.0,
        "vignette": 200,
        "chroma_aber": 0.5,
        "bloom":      0.15,
        "halation":   0.10,
    },

    "インスタント": {
        "tags": ["温かい", "希望", "昼", "夏", "晴", "休日"],
        "grain": 11,
        "color_matrix": {
            "R": (1.06, 0.03), "G": (1.04, 0.02), "B": (0.96, 0.01)
        },
        "contrast": 1.10,
        "lift": 0.01,
        "vignette": 155,
        "chroma_aber": 1.2,
        "bloom":      0.14,
        "halation":   0.08,
    },

    "古い映写機": {
        "tags": ["孤独", "哀愁", "静謐", "深夜", "冬", "曇"],
        "grain": 28,
        "color_matrix": {
            "R": (1.02, 0.06), "G": (0.98, 0.05), "B": (0.82, 0.02)
        },
        "contrast": 1.18,
        "lift": 0.03,
        "vignette": 240,
        "chroma_aber": 1.0,
        "bloom":      0.08,
        "halation":   0.06,
        "flicker":    True,
        "flicker_strength": 0.10,
        "vertical_jitter": True,
        "perforation": True,
        "burn_edges": True,
    },

    "光漏れフィルム": {
        "tags": ["温かい", "哀愁", "希望", "夕方", "夏", "秋"],
        "grain": 16,
        "color_matrix": {
            "R": (1.12, 0.05), "G": (1.00, 0.02), "B": (0.80, 0.0)
        },
        "contrast": 1.10,
        "lift": 0.03,
        "vignette": 180,
        "chroma_aber": 1.6,
        "bloom":      0.22,
        "halation":   0.20,
        "light_leak": True,
        "leak_strength": 0.70,
    },

    "テープの記憶": {
        "tags": ["哀愁", "孤独", "空虚", "深夜", "冬", "雨"],
        "grain": 26,
        "color_matrix": {
            "R": (0.90, 0.03), "G": (0.86, 0.02), "B": (1.04, 0.05)
        },
        "contrast": 0.98,
        "lift": 0.05,
        "vignette": 225,
        "chroma_aber": 3.5,
        "bloom":      0.06,
        "halation":   0.04,
        "vhs_noise_band":   True,
        "noise_band_strength": 0.50,
        "vhs_color_bleed":  True,
        "color_bleed_strength": 8,
        "scanline":   True,
        "gate_glitch": True,
        "fade":       True,
    },

    "真夜中の体温": {
        "tags": ["孤独", "哀愁", "静謐", "空虚", "深夜", "冬"],
        "grain": 18,
        "color_matrix": {
            "R": (1.06, 0.05), "G": (0.88, 0.01), "B": (0.72, 0.0)
        },
        "contrast": 1.14,
        "lift": 0.04,
        "vignette": 245,
        "chroma_aber": 0.8,
        "bloom":      0.12,
        "halation":   0.16,
    },

    "錆びた午後": {
        "tags": ["哀愁", "孤独", "夏", "秋", "昼", "曇"],
        "grain": 20,
        "color_matrix": {
            "R": (1.08, 0.04), "G": (0.82, 0.01), "B": (0.76, 0.0)
        },
        "contrast": 1.06,
        "lift": 0.02,
        "vignette": 210,
        "chroma_aber": 1.4,
        "bloom":      0.10,
        "halation":   0.12,
        "fade":       True,
    },

    "海底の夢": {
        "tags": ["孤独", "空虚", "静謐", "深夜", "夏"],
        "grain": 14,
        "color_matrix": {
            "R": (0.68, 0.0), "G": (0.92, 0.04), "B": (1.14, 0.08)
        },
        "contrast": 1.08,
        "lift": 0.01,
        "vignette": 220,
        "chroma_aber": 1.2,
        "bloom":      0.18,
        "halation":   0.06,
        "ripple":     True,
        "ripple_strength": 2.5,
        "caustics":   True,
        "caustics_strength": 0.16,
        "soft_focus": True,
    },
}

# ===== エンディングパターン =====
ENDING_PATTERNS = {
    "希望":   "white_flash",
    "温かい": "white_flash",
    "哀愁":   "mist_fade",
    "孤独":   "mist_fade",
    "静謐":   "slow_dark",
    "空虚":   "slow_dark",
    "default":"dark_flash",
}

# ===== テキスト出現パターン =====
TEXT_APPEAR_PATTERNS = {
    "静謐":   "mist",
    "哀愁":   "mist",
    "希望":   "rise",
    "温かい": "rise",
    "空虚":   "dissolve",
    "孤独":   "dissolve",
    "default":"mist",
}

# ===== ビネット強度のランダム揺らぎ範囲 =====
VIGNETTE_JITTER = 0.08

# ===== Ken Burnsのランダム揺らぎ =====
KB_ZOOM_BASE  = 0.08
KB_ZOOM_JITTER= 0.02
KB_PAN_JITTER = 15
