"""
tameiki/easing.py — イージング関数・数学ユーティリティ
有機的な動きを作るための関数群
"""
import math


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(t):
    """cubic ease-out：ゆっくり減速"""
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in(t):
    """cubic ease-in：ゆっくり加速"""
    t = clamp(t)
    return t ** 3


def ease_io(t):
    """smoothstep：加速→減速"""
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_expo(t):
    """指数的ease-out：鋭い減速"""
    t = clamp(t)
    return 1 - 2 ** (-10 * t) if t > 0 else 0


def ease_organic(t, seed=0):
    """
    有機的なイージング：微妙な揺らぎを加えた自然な動き
    完全な数式的なカーブではなく、息をしているような緩急
    """
    t = clamp(t)
    base = ease_io(t)
    # シードベースの微細な揺らぎ（常に同じシードなら同じ揺らぎ）
    jitter = math.sin(t * math.pi * 2.3 + seed) * 0.012
    return clamp(base + jitter)


def breath_curve(t, freq=1.0, phase=0.0):
    """
    呼吸のような波：ゆっくり膨らんで縮む
    """
    t = clamp(t)
    return 0.5 + 0.5 * math.sin(t * math.pi * 2 * freq + phase)


def flicker(t, fi, strength=0.03):
    """
    フリッカー：フィルム映写機のような微細な明滅
    フレームインデックスに依存するのでランダムに見える
    """
    import random
    rng = random.Random(fi * 7 + int(t * 100))
    return 1.0 + rng.uniform(-strength, strength)


def random_jitter(fi, scale=1.0, seed=0):
    """
    フレームに依存した再現可能なランダム値
    同じフレームなら常に同じ値が返る
    """
    import random
    rng = random.Random(fi + seed * 10000)
    return rng.uniform(-scale, scale)
