"""
bocais.py — achar na malha os pontos de ligação da peça (as `ENTRADA_3D` do `.aq`).

O `.aq` guarda em `ENTRADA_3D` o ponto onde a peça encaixa na rede, e nenhuma fonte de
geometria (IFC, STEP, família Revit) marca bocal. Este módulo recupera esses pontos da
própria malha, na forma que as bibliotecas nativas usam.

A forma, medida em bibliotecas nativas de aquecedores, de conexões de esgoto e de bombas:
o bocal é a **face anelar** na ponta de um tubo — dois círculos concêntricos coplanares,
raio interno e externo separados pela espessura da parede — e a `ENTRADA_3D` fica no
**centro** dela, com o raio **interno** valendo a bitola. Numa nativa de conexões o par
(raio interno, código de diâmetro) reproduz a escala nominal do AltoQi: 2,56 cm ↔ 50 mm,
3,78 ↔ 75, 5,08 ↔ 100, 7,50 ↔ 150, 10,00 ↔ 200.

Três armadilhas que o detector tem de tratar, e que motivam cada filtro:

1. **Malha de fabricante pode ser estanque.** Nas nativas de aquecedores não há uma única
   aresta de borda: a ponta do tubo é fechada por triângulos coplanares, não por um
   buraco. Procurar "buraco na malha" acha zero bocal. O critério é geométrico
   (coplanar + circular), nunca topológico.
2. **Um tubo tem faces circulares no meio do caminho** — tampa interna, degrau de parede,
   friso. Bocal é a face extrema de **cada lado** do eixo: um tubo reto tem bocal nas duas
   pontas, e nenhuma no meio.
3. **O *winding* não é confiável.** A normal do grupo coplanar aponta para dentro em parte
   das faces de malha de fabricante, então "lado de fora" se decide pela distância ao
   centro do corpo, não pelo sinal da normal.

Coordenadas: as mesmas da malha recebida. Para casar com `ENTRADA_3D` a malha precisa vir
em centímetro, Z-up e **já com o *placement* da simbologia aplicado** — a rotação
`ANGULO_PLANO_*` e o `DESLOCAMENTO_*` (ver `docs/conhecimento/aq-formato.md`).
"""
from collections import defaultdict

import numpy as np

# Um bocal é um anel com tubo atrás, em duas variantes medidas nas nativas: **ponta de
# tubo**, onde o anel é a parede (raio_interno/raio_externo >= 0,84 nas nativas), e **face
# de flange**, onde o anel é o disco largo em volta do furo e essa razão cai para ~0,5. As
# duas se reconhecem pelo cilindro atrás da face: >= 1,9 raio de tubo de comprimento e
# >= 68 % dos vértices do trecho na casca. Os limites são o pior caso medido, com folga.
RAZAO_PAREDE_MIN = 0.70
TUBO_MIN = 1.8
CASCA_MIN = 0.65


def solda(malhas, tol=1e-4):
    """`[(verts, tris, ...)]` → `(V, F)` com os vértices soldados por posição.

    As malhas do OQ3D vêm uma por cor, cada uma com seus próprios vértices; sem soldar,
    nenhuma face atravessa a fronteira entre duas malhas e o contorno sai picado.
    """
    Vs, Fs, base = [], [], 0
    for verts, tris, *_ in malhas:
        v = np.asarray(verts, dtype=np.float64)
        Vs.append(v)
        Fs.append(np.asarray(tris, dtype=np.int64) + base)
        base += len(v)
    if not Vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    V = np.concatenate(Vs)
    F = np.concatenate(Fs)
    chave = np.round(V / tol).astype(np.int64)
    _, primeiro, inverso = np.unique(chave, axis=0, return_index=True, return_inverse=True)
    return V[primeiro], inverso.reshape(-1)[F]


def _normais(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    area = np.linalg.norm(n, axis=1) / 2.0
    n = n / np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-12)
    return n, area


def _triangulos_por_aresta(F):
    mapa = defaultdict(list)
    for i, (a, b, c) in enumerate(F):
        for u, v in ((a, b), (b, c), (c, a)):
            mapa[(min(u, v), max(u, v))].append(i)
    return mapa


def _pares_adjacentes(F):
    """Pares de triângulos que compartilham uma aresta, vetorizado."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    tri = np.tile(np.arange(len(F)), 3)
    chave = np.sort(e, axis=1)
    ordem = np.lexsort((chave[:, 1], chave[:, 0]))
    chave, tri = chave[ordem], tri[ordem]
    igual = np.all(chave[1:] == chave[:-1], axis=1)
    return tri[:-1][igual], tri[1:][igual]


def grupos_coplanares(V, F, tol_normal=0.999, tol_plano=1e-3):
    """Componentes conexas de triângulos coplanares → `[(indices, normal, area)]`.

    A união é feita sobre os pares de triângulos adjacentes, filtrados de uma vez em
    numpy: o laço Python triângulo a triângulo custava segundos numa simbologia de 100
    mil vértices — tempo que, multiplicado pelas ~1.400 simbologias de um catálogo,
    inviabiliza a exportação. Agrupar por plano quantizado seria mais rápido ainda e
    **está errado**: grupo que cruza a fronteira do balde sai partido em dois.
    """
    n, area = _normais(V, F)
    d = np.einsum('ij,ij->i', n, V[F[:, 0]])
    a, b = _pares_adjacentes(F)
    if len(a):
        junta = (np.einsum('ij,ij->i', n[a], n[b]) >= tol_normal) & (np.abs(d[a] - d[b]) <= tol_plano)
        a, b = a[junta], b[junta]

    pai = np.arange(len(F))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    for i, j in zip(a.tolist(), b.tolist()):
        ri, rj = raiz(i), raiz(j)
        if ri != rj:
            pai[ri] = rj

    por_raiz = {}
    for i in range(len(F)):
        por_raiz.setdefault(raiz(i), []).append(i)
    return [(np.array(g), n[g[0]], float(area[g].sum())) for g in por_raiz.values()]


def _lacos(arestas, minimo=5):
    """Laços fechados de um conjunto de arestas; cadeia aberta e junção são descartadas."""
    adj = defaultdict(list)
    for a, b in arestas:
        adj[int(a)].append(int(b))
        adj[int(b)].append(int(a))
    vistos, saida = set(), []
    for inicio in adj:
        if inicio in vistos or len(adj[inicio]) != 2:
            continue
        laco, atual, anterior = [inicio], inicio, None
        vistos.add(inicio)
        while True:
            viz = [x for x in adj[atual] if x != anterior]
            if len(adj[atual]) != 2 or not viz:
                laco = None
                break
            prox = viz[0]
            if prox == inicio:
                break
            if prox in vistos:
                laco = None
                break
            vistos.add(prox)
            laco.append(prox)
            anterior, atual = atual, prox
        if laco and len(laco) >= minimo:
            saida.append(laco)
    return saida


def _contorno(F, indices):
    """Arestas que aparecem uma só vez dentro do subconjunto de triângulos."""
    sub = F[indices]
    e = np.concatenate([sub[:, [0, 1]], sub[:, [1, 2]], sub[:, [2, 0]]])
    uniq, cont = np.unique(np.sort(e, axis=1), axis=0, return_counts=True)
    return uniq[cont == 1]


def _circulo(P):
    """`(centro, raio, normal, erro_plano, dispersão relativa do raio)`."""
    c = P.mean(0)
    Q = P - c
    _, _, Vt = np.linalg.svd(Q, full_matrices=False)
    normal = Vt[2]
    erro = float(np.abs(Q @ normal).max())
    r = np.linalg.norm(Q - np.outer(Q @ normal, normal), axis=1)
    return c, float(r.mean()), normal, erro, float(r.std() / max(r.mean(), 1e-9))


def _faces_anelares(V, F, disp_max=0.08):
    """Faces planas com dois ou mais círculos concêntricos no contorno.

    → `[{centro, raio_interno, raio_externo, normal, area}]`. Um contorno de um só
    círculo (tampa cheia, disco decorativo) não entra: bocal é anel.
    """
    saida = []
    for indices, normal, area in grupos_coplanares(V, F):
        # Uma face anelar precisa de dois laços de >= 5 vértices, e a faixa entre eles tem
        # dois triângulos por vértice: menos de 10 triângulos não fecha anel. O corte é
        # o que evita rodar contorno e ajuste de círculo nos milhares de grupos de um
        # triângulo em que a malha de fabricante se quebra.
        if len(indices) < 10:
            continue
        circulos = []
        for laco in _lacos(_contorno(F, indices)):
            c, r, _, erro, disp = _circulo(V[laco])
            if disp > disp_max or erro > max(0.02, 0.02 * r):
                continue
            circulos.append((c, r))
        while circulos:
            c0, r0 = circulos.pop(0)
            mesmo, resto = [(c0, r0)], []
            for c, r in circulos:
                if np.linalg.norm(c - c0) < 0.15 * max(r, r0):
                    mesmo.append((c, r))
                else:
                    resto.append((c, r))
            circulos = resto
            if len(mesmo) < 2:
                continue
            raios = sorted(r for _, r in mesmo)
            saida.append({'centro': np.mean([c for c, _ in mesmo], axis=0),
                          'raio_interno': raios[0], 'raio_externo': raios[-1],
                          'normal': normal, 'area': area})
    return saida


def _tubo_atras(V, centro, eixo, r_int, r_ext, centro_corpo):
    """`(comprimento do tubo atrás da face em raios externos, fração na casca)`.

    É o que separa a ponta de tubo de um anel qualquer — friso, degrau, furo de parafuso
    de flange: atrás de um bocal existe parede cilíndrica do mesmo eixo e raio.
    """
    dentro = eixo if (centro_corpo - centro) @ eixo > 0 else -eixo
    d = V - centro
    t = d @ dentro
    radial = np.linalg.norm(d - np.outer(t, dentro), axis=1)
    faixa = (t > 0.02) & (t < 8 * r_ext) & (radial < 1.6 * r_ext)
    if not faixa.any():
        return 0.0, 0.0
    casca = (radial[faixa] > 0.7 * r_int) & (radial[faixa] < 1.4 * r_ext)
    # Um tubo longo não é mais bocal que um tubo de dois raios: o comprimento entra
    # saturado, senão o limite viraria uma medida do comprimento da peça.
    return float(min(t[faixa].max(), 4 * r_ext) / r_ext), float(casca.mean())


def bocais(malhas, raio_min=0.3, raio_max=25.0, folga_area=0.35):
    """Bocais da malha: `[{centro, raio, raio_externo, normal, comprimento_tubo}]`.

    `raio` é a bitola (o raio interno do anel). Maior primeiro. Coordenadas na unidade e
    no frame da malha recebida — ver o cabeçalho do módulo.
    """
    V, F = solda(malhas)
    if not len(F):
        return []
    centro_corpo = (V.min(0) + V.max(0)) / 2.0

    achados = []
    for face in _faces_anelares(V, F):
        r_int, r_ext = face['raio_interno'], face['raio_externo']
        if not (raio_min <= r_int <= raio_max) or r_int / r_ext < RAZAO_PAREDE_MIN:
            continue
        esperada = np.pi * (r_ext ** 2 - r_int ** 2)
        if abs(face['area'] - esperada) > folga_area * esperada:
            continue
        eixo = face['normal'] / np.linalg.norm(face['normal'])
        # Ponta de tubo: a casca é a própria parede do anel. Face de flange: o anel é o
        # disco e o que importa é o furo, então o cilindro se mede em volta do raio
        # interno. Basta uma das duas leituras convencer.
        leituras = [_tubo_atras(V, face['centro'], eixo, r_int, r_ext, centro_corpo)]
        if r_int / r_ext < RAZAO_PAREDE_MIN:
            leituras.append(_tubo_atras(V, face['centro'], eixo, r_int, r_int * 1.15,
                                        centro_corpo))
        comprimento, casca = max(
            ((c, k) for c, k in leituras if k >= CASCA_MIN), default=(0.0, 0.0))
        if comprimento < TUBO_MIN:
            continue
        # A normal sai orientada para FORA do corpo: o azimute que vira `ANGULO_EP`
        # depende do sentido, e o do triângulo não serve (item 3 do cabeçalho).
        radial = (face['centro'] - centro_corpo) @ eixo
        achados.append({'centro': face['centro'], 'raio': r_int, 'raio_externo': r_ext,
                        'normal': eixo if radial >= 0 else -eixo,
                        'comprimento_tubo': comprimento})

    # Faces do mesmo eixo são o mesmo tubo: fica a extrema de cada lado do corpo.
    eixos = []
    for a in sorted(achados, key=lambda x: -x['raio_externo']):
        for ref, eixo, grupo in eixos:
            if abs(eixo @ a['normal']) < 0.99:
                continue
            delta = a['centro'] - ref
            if np.linalg.norm(delta - (delta @ eixo) * eixo) < 0.5 * a['raio_externo']:
                grupo.append(a)
                break
        else:
            eixos.append((a['centro'], a['normal'], [a]))

    saida = []
    for _, eixo, grupo in eixos:
        t = np.array([(c['centro'] - centro_corpo) @ eixo for c in grupo])
        extremos = {int(np.argmax(t))}
        if t.min() < 0:
            extremos.add(int(np.argmin(t)))
        saida.extend(grupo[i] for i in sorted(extremos))
    return sorted(saida, key=lambda x: -x['raio'])
