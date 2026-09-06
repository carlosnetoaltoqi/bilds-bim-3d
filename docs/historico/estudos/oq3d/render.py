#!/usr/bin/env python3
"""Rasterizador z-buffer minimo para validar geometria (numpy puro)."""
import numpy as np


def render(tris, cols, size=420, elev=25.0, azim=45.0, bg=(255, 255, 255)):
    """
    tris : (N,3,3) float  — triangulos em coordenadas de mundo
    cols : (N,3)   float  — cor RGB 0-255 por triangulo
    """
    tris = np.asarray(tris, dtype=np.float64)
    cols = np.asarray(cols, dtype=np.float64)

    # camera orbital
    a, e = np.radians(azim), np.radians(elev)
    fwd = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    up0 = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up0); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)

    P = tris.reshape(-1, 3)
    center = (P.min(0) + P.max(0)) / 2.0
    Q = P - center
    x = Q @ right
    y = Q @ up
    z = Q @ fwd                      # profundidade (maior = mais longe)

    span = max(x.max() - x.min(), y.max() - y.min()) * 1.12
    sx = (x - x.min() + (span - (x.max() - x.min())) / 2) / span * (size - 1)
    sy = (size - 1) - (y - y.min() + (span - (y.max() - y.min())) / 2) / span * (size - 1)

    sx = sx.reshape(-1, 3); sy = sy.reshape(-1, 3); sz = z.reshape(-1, 3)

    # normal + shading difuso (luz na direcao da camera + ambiente)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(n, axis=1); ln[ln == 0] = 1
    n /= ln[:, None]
    light = np.array([0.4, -0.7, 0.6]); light /= np.linalg.norm(light)
    lam = np.abs(n @ light)
    shade = (0.35 + 0.65 * lam)[:, None]
    tri_col = np.clip(cols * shade, 0, 255)

    img = np.full((size, size, 3), bg, dtype=np.float64)
    zbuf = np.full((size, size), np.inf)

    order = np.argsort(-sz.mean(1))       # pinta do fundo para a frente
    for i in order:
        ax, ay, az = sx[i], sy[i], sz[i]
        x0 = max(int(np.floor(ax.min())), 0); x1 = min(int(np.ceil(ax.max())) + 1, size)
        y0 = max(int(np.floor(ay.min())), 0); y1 = min(int(np.ceil(ay.max())) + 1, size)
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = ((ay[1] - ay[2]) * (ax[0] - ax[2]) + (ax[2] - ax[1]) * (ay[0] - ay[2]))
        if abs(d) < 1e-12:
            continue
        w0 = ((ay[1] - ay[2]) * (xx - ax[2]) + (ax[2] - ax[1]) * (yy - ay[2])) / d
        w1 = ((ay[2] - ay[0]) * (xx - ax[2]) + (ax[0] - ax[2]) * (yy - ay[2])) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not m.any():
            continue
        zi = w0 * az[0] + w1 * az[1] + w2 * az[2]
        sub = zbuf[y0:y1, x0:x1]
        vis = m & (zi < sub)
        if not vis.any():
            continue
        sub[vis] = zi[vis]
        img[y0:y1, x0:x1][vis] = tri_col[i]
    return img.astype(np.uint8)
