"""Recolour the olive brain mascot to pink, in stills and video, identically."""
import numpy as np


def _rgb_to_hsv(a):
    a = a.astype(np.float32) / 255.0
    mx = a.max(-1); mn = a.min(-1)
    d = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-6
    idx = nz & (mx == r); h[idx] = ((g - b)[idx] / d[idx]) % 6
    idx = nz & (mx == g); h[idx] = ((b - r)[idx] / d[idx]) + 2
    idx = nz & (mx == b); h[idx] = ((r - g)[idx] / d[idx]) + 4
    h = h * 60.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx


def _hsv_to_rgb(h, s, v):
    h = np.mod(h, 360.0) / 60.0
    i = np.floor(h).astype(np.int32)
    f = h - i
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    i = i % 6
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [p, p, q, v, v, t])
    return np.clip(np.stack([r, g, b], -1) * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _ramp(x, lo, hi):
    return np.clip((x - lo) / (hi - lo), 0, 1)


def recolor(rgb, hue=345.0, sat=0.45, lift=1.5, spread=0.30):
    """rgb: uint8 (...,3). Olive pixels become pink; everything else is untouched."""
    h, s, v = _rgb_to_hsv(rgb)
    # Only the olive/yellow-green family, and only where there is real colour:
    # black outlines, white paper and the terracotta cheeks fall outside.
    w = np.minimum(np.minimum(_ramp(h, 36, 48), 1 - _ramp(h, 100, 118)),
                   _ramp(s, 0.10, 0.25))
    h2 = hue + (h - 62.0) * spread          # keep a little of the original variation
    s2 = s * sat
    v2 = v * (1 + lift * (1 - v))           # brighten mids, leave darks dark
    out = _hsv_to_rgb(np.where(w > 0, h2, h), s + (s2 - s) * w, np.clip(v + (v2 - v) * w, 0, 1))
    return np.where((w > 0)[..., None], out, rgb)
