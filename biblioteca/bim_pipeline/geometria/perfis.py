#!/usr/bin/env python3
"""
perfis.py — seções transversais 2D extrudadas: a geometria REPRESENTATIVA de perfis estruturais,
tubos, caixas e chapas perfiladas quando a fonte dá as cotas da seção mas não a malha (é o caso de
uma família Revit lida sem o Revit — `docs/conhecimento/revit-familias.md`).

É a irmã de `aq/formas_parametricas.py` (revolução e varredura para peças hidráulicas), com a mesma
convenção: **centímetros, Z-up**, e cada gerador devolve `[(verts, tris, rgba)]` — uma lista de
malhas por peça, sem união booleana (sobreposição de sólidos é aceitável, é o que o OQ3D faz).

A primitiva é `extrudar(aneis, comprimento)`: um ou dois anéis 2D (contorno externo e, se a seção é
vazada, o furo) → paredes laterais + tampas. Com um anel a tampa é triangulada por *ear clipping*
(serve para I, U, L e qualquer polígono simples); com dois anéis de mesmo número de vértices a tampa
é a faixa entre eles (tubo retangular, tubo redondo). Todo sólido sai FECHADO — zero arestas de
borda — o que o teste confere contando arestas com um só triângulo (a checagem de
`formas-representativas.md`).

Orientação: o perfil é desenhado no plano XY e extrudado em +Z — a posição natural de um pilar. Para
uma viga, `deitar()` leva o comprimento para +X mantendo a altura da seção na vertical.
"""
import math

# Cores de visualização (não são dado do fabricante)
COR = {
    'aco':      (176, 178, 182, 255),
    'aco_galv': (200, 202, 206, 255),
    'concreto': (214, 211, 202, 255),
    'generico': (150, 152, 158, 255),
}


# --- Anéis 2D (cm), sentido anti-horário --------------------------------

def retangulo(b, h, cx=0.0, cy=0.0):
    """Largura `b` em X, altura `h` em Y, centrado."""
    x0, x1, y0, y1 = cx - b / 2, cx + b / 2, cy - h / 2, cy + h / 2
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def circulo(d, lados=48, cx=0.0, cy=0.0):
    r = d / 2
    return [(cx + r * math.cos(2 * math.pi * i / lados), cy + r * math.sin(2 * math.pi * i / lados)) for i in range(lados)]


def secao_i(b, h, tf, tw):
    """Perfil I/H simétrico: mesa `b` × `tf`, alma `tw`, altura total `h`. Um só anel (12 vértices)."""
    x0, x1 = -b / 2, b / 2
    xa0, xa1 = -tw / 2, tw / 2
    y0, y1 = -h / 2, h / 2
    return [(x0, y0), (x1, y0), (x1, y0 + tf), (xa1, y0 + tf), (xa1, y1 - tf), (x1, y1 - tf),
            (x1, y1), (x0, y1), (x0, y1 - tf), (xa0, y1 - tf), (xa0, y0 + tf), (x0, y0 + tf)]


def secao_u(b, h, tf, tw):
    """Perfil U (canal) com a alma à esquerda e as mesas para +X."""
    x0, x1 = -b / 2, b / 2
    y0, y1 = -h / 2, h / 2
    return [(x0, y0), (x1, y0), (x1, y0 + tf), (x0 + tw, y0 + tf), (x0 + tw, y1 - tf), (x1, y1 - tf), (x1, y1), (x0, y1)]


def secao_l(b, h, t):
    """Cantoneira: abas `b` (X) e `h` (Y), espessura `t`, canto na origem."""
    return [(0.0, 0.0), (b, 0.0), (b, t), (t, t), (t, h), (0.0, h)]


def _area2(anel):
    return sum(anel[i][0] * anel[(i + 1) % len(anel)][1] - anel[(i + 1) % len(anel)][0] * anel[i][1] for i in range(len(anel))) / 2


def anti_horario(anel):
    return anel if _area2(anel) > 0 else list(reversed(anel))


# --- Triangulação de polígono simples (ear clipping) ---------------------

def triangular(anel):
    """Índices (i, j, k) que cobrem um polígono simples anti-horário. O(n²), n é pequeno."""
    idx = list(range(len(anel)))
    tris = []

    def convexo(a, b, c):
        (ax, ay), (bx, by), (cx, cy) = anel[a], anel[b], anel[c]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 1e-12

    def dentro(p, a, b, c):
        def s(u, v, w):
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
        d1, d2, d3 = s(anel[a], anel[b], p), s(anel[b], anel[c], p), s(anel[c], anel[a], p)
        return not ((d1 < -1e-12 or d2 < -1e-12 or d3 < -1e-12) and (d1 > 1e-12 or d2 > 1e-12 or d3 > 1e-12))

    guarda = 0
    while len(idx) > 3 and guarda < 10000:
        guarda += 1
        n = len(idx)
        for k in range(n):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % n]
            if not convexo(a, b, c):
                continue
            if any(dentro(anel[o], a, b, c) for o in idx if o not in (a, b, c)):
                continue
            tris.append((a, b, c))
            del idx[k]
            break
        else:
            # polígono degenerado (colinear): remove o vértice do meio e segue
            del idx[0]
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


# --- Extrusão ------------------------------------------------------------

def extrudar(aneis, comprimento, z0=0.0):
    """
    `aneis` = `[externo]` ou `[externo, furo]` (listas de (x, y) em cm; a orientação é corrigida aqui),
    extrudados de `z0` a `z0 + comprimento`. Devolve `(verts, tris)` de um sólido fechado.
    """
    if not aneis or comprimento <= 0:
        raise ValueError('extrudar: precisa de um anel e comprimento > 0')
    externo = anti_horario(aneis[0])
    furo = anti_horario(aneis[1]) if len(aneis) > 1 else None
    if furo is not None and len(furo) != len(externo):
        raise ValueError(f'extrudar: anel externo com {len(externo)} vértices e furo com {len(furo)} — precisam ser iguais')
    z1 = z0 + comprimento
    verts, tris = [], []

    def anel3d(anel, z):
        base = len(verts)
        verts.extend((x, y, z) for x, y in anel)
        return base

    e0, e1 = anel3d(externo, z0), anel3d(externo, z1)
    n = len(externo)
    for i in range(n):                        # parede externa, normal para fora
        j = (i + 1) % n
        tris.append((e0 + i, e0 + j, e1 + j))
        tris.append((e0 + i, e1 + j, e1 + i))
    if furo is None:
        for a, b, c in triangular(externo):   # tampa de cima (normal +Z) e de baixo (−Z)
            tris.append((e1 + a, e1 + b, e1 + c))
            tris.append((e0 + a, e0 + c, e0 + b))
        return verts, tris

    f0, f1 = anel3d(furo, z0), anel3d(furo, z1)
    # o furo tem o vértice inicial mais próximo do vértice 0 do externo, para as faixas não cruzarem
    k0 = min(range(n), key=lambda k: (furo[k][0] - externo[0][0]) ** 2 + (furo[k][1] - externo[0][1]) ** 2)
    for i in range(n):
        j = (i + 1) % n
        fi, fj = f0 + (k0 + i) % n, f0 + (k0 + j) % n
        gi, gj = f1 + (k0 + i) % n, f1 + (k0 + j) % n
        # parede interna, normal para dentro do furo
        tris.append((fi, gj, fj))
        tris.append((fi, gi, gj))
        # tampa de cima (faixa externo↔furo, normal +Z)
        tris.append((e1 + i, e1 + j, gj))
        tris.append((e1 + i, gj, gi))
        # tampa de baixo (normal −Z)
        tris.append((e0 + i, fj, e0 + j))
        tris.append((e0 + i, fi, fj))
    return verts, tris


def deitar(verts):
    """Pilar (comprimento em +Z, altura da seção em +Y) → viga (comprimento em +X, altura em +Z). Rotação própria: as normais continuam para fora."""
    return [(z, x, y) for x, y, z in verts]


def assentar(verts, comprimento):
    """Chapa extrudada em +Z com a altura da nervura em +Y → chapa deitada: comprimento em +Y (de 0 a `comprimento`), nervura para +Z. Rotação de 90° em X (própria)."""
    return [(x, comprimento - z, y) for x, y, z in verts]


def transladar(verts, dx=0.0, dy=0.0, dz=0.0):
    return [(x + dx, y + dy, z + dz) for x, y, z in verts]


# --- Formas de peça inteira -----------------------------------------------

def caixa(dx, dy, dz, z0=0.0):
    """Paralelepípedo centrado em XY, de `z0` a `z0 + dz`."""
    return extrudar([retangulo(dx, dy)], dz, z0)


def chapa_trapezoidal(largura, altura, espessura, passo, topo=None, comprimento=100.0):
    """
    Chapa perfilada (telha-forma / steel deck) de seção trapezoidal: `largura` do módulo em X,
    `altura` da nervura em Y (perfil no plano XY, comprimento da telha em +Z), `passo` entre
    nervuras, `topo` = largura da mesa superior (padrão passo/3). Cada trecho reto vira uma placa
    de `espessura` — sólidos separados que se sobrepõem nos cantos, como o OQ3D aceita.
    Devolve `[(verts, tris)]`.
    """
    topo = topo if topo else passo / 3.0
    base = max(passo - topo, 0.1)
    n = max(1, int(round(largura / passo)))
    passo = largura / n                     # ajusta para caber exatamente `n` nervuras na largura
    topo = min(topo, passo * 0.6)
    base = passo - topo
    rampa = base / 4.0                      # projeção horizontal de cada rampa; o vale fica com base/2
    vale = base - 2 * rampa
    x = -largura / 2
    pontos = []
    for _ in range(n):
        pontos += [(x, 0.0), (x + vale / 2, 0.0), (x + vale / 2 + rampa, altura), (x + vale / 2 + rampa + topo, altura),
                   (x + vale / 2 + rampa + topo + rampa, 0.0), (x + passo, 0.0)]
        x += passo
    # remove pontos repetidos consecutivos
    linha = [pontos[0]]
    for p in pontos[1:]:
        if abs(p[0] - linha[-1][0]) > 1e-9 or abs(p[1] - linha[-1][1]) > 1e-9:
            linha.append(p)
    malhas = []
    for (x0, y0), (x1, y1) in zip(linha, linha[1:]):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        nx, ny = -dy / L * espessura, dx / L * espessura       # normal para cima, escalada
        anel = [(x0, y0), (x1, y1), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]
        malhas.append(extrudar([anel], comprimento))
    return malhas


def arestas_de_borda(tris):
    """Quantas arestas têm um só triângulo — zero num sólido fechado (checagem de formas-representativas.md)."""
    cont = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (u, v) if u < v else (v, u)
            cont[k] = cont.get(k, 0) + 1
    return sum(1 for n in cont.values() if n != 2)


def volume_assinado(verts, tris):
    """Volume pelo teorema da divergência — positivo quando as normais apontam para fora."""
    v = 0.0
    for a, b, c in tris:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = verts[a], verts[b], verts[c]
        v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return v / 6.0


def bbox(verts):
    """(dx, dy, dz) em cm."""
    if not verts:
        return (0.0, 0.0, 0.0)
    return tuple(round(max(v[i] for v in verts) - min(v[i] for v in verts), 4) for i in range(3))
