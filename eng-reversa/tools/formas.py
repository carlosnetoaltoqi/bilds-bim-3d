#!/usr/bin/env python3
"""
formas.py — geometria paramétrica REPRESENTATIVA para as peças do catálogo.

ATENÇÃO — LEIA ANTES DE USAR EM PROJETO
---------------------------------------
As malhas que este módulo gera **não são as cotas da Akato**. O catálogo
comercial não traz nenhuma cota de forma: dá o diâmetro nominal, o código e a
embalagem, e nada sobre raio de curva, profundidade de bolsa ou espessura de
colar. O que está aqui é uma forma plausível, montada a partir de:

- **diâmetro nominal** — do catálogo, é dado real;
- **espessura de parede** — das normas NBR 5648 (soldável) e NBR 5688
  (esgoto), é dado normativo;
- **todas as outras proporções** — inventadas, na tabela `PROPORCOES` abaixo,
  com a regra que gerou cada uma explícita.

Serve para visualizar, contar peça e detectar interferência grosseira. **Não
serve** para conferir encaixe, folga de instalação ou colisão fina — para isso
é preciso a cota do fabricante. Ver
`estudo/04-lacunas-do-catalogo-comercial.md`.

UNIDADES
--------
Tudo em **centímetros, Z-up**, que é o que o OQ3D guarda. Os diâmetros do
catálogo vêm em milímetro e são convertidos na entrada.

O QUE CADA GERADOR DEVOLVE
--------------------------
`[(verts, tris, rgba)]` — uma lista de malhas, não uma malha só. É como o
próprio AltoQi guarda: a `SIMBOLOGIA_3D` 169 da Amanco tem 4 malhas. Não há
união booleana; sobreposição de sólidos é aceitável e é o que o formato faz.
"""
import math

# --- Proporções -----------------------------------------------------------
#
# Cada linha diz de onde veio. As marcadas "aprox." são invenção deste módulo.
PROPORCOES = {
    # bolsa (profundidade do encaixe) — aprox., cresce com o diâmetro
    'bolsa':          lambda de: 0.60 * de + 4.0,
    # sobre-espessura do colar da bolsa — aprox.
    'colar':          lambda de: 3.0,
    # braço reto de um joelho, do centro à face — aprox.
    'braco':          lambda de: 0.60 * de + 4.0 + 0.35 * de,
    # raio do eixo de uma curva longa e de uma curta — aprox.
    'raio_longa':     lambda de: 1.50 * de,
    'raio_curta':     lambda de: 0.75 * de,
    # corpo de registro de esfera — aprox.
    'registro_diam':  lambda de: 1.70 * de,
    'registro_comp':  lambda de: 1.30 * de,
}

# Espessura de parede em milímetros, das normas. Fora destas bitolas, cai na
# regra aproximada `max(1.5, 0.055·DE)`.
PAREDE_NBR = {
    'ÁGUA FRIA':   {20: 1.5, 25: 1.7, 32: 2.1, 40: 2.4, 50: 3.0,
                    60: 3.3, 75: 4.2, 85: 4.7, 110: 6.1},
    'ESGOTO':      {40: 1.5, 50: 1.7, 75: 1.7, 100: 2.1, 150: 3.2, 200: 4.6},
}

# Polegada → milímetro que NÃO está na tabela de conversão da Akato (página 23
# do catálogo). O 3/8" e o 7/8" aparecem só na linha de polietileno e nas
# válvulas de pia, e a tabela da Akato não os cobre.
POLEGADA_EXTRA = {'3/8': 17, '7/8': 22}

# Cores. As de PVC seguem o que o catálogo afirma — marrom no soldável
# tradicional, azul nas conexões com bucha de latão, branca no roscável e no
# esgoto. As demais são escolha de visualização.
COR = {
    'marrom':  (150, 88, 55, 255),
    'azul':    (32, 92, 165, 255),
    'branca':  (238, 238, 234, 255),
    'preta':   (46, 46, 50, 255),
    'latao':   (181, 145, 60, 255),
    'borracha': (38, 38, 40, 255),
    'metal':   (176, 178, 182, 255),
    'cinza':   (140, 142, 146, 255),
}


def parede_mm(secao, de_mm):
    """Espessura de parede em mm — da norma quando há, senão aproximada."""
    tabela = PAREDE_NBR.get(secao, {})
    if de_mm in tabela:
        return tabela[de_mm]
    return max(1.5, 0.055 * de_mm)


# --- Primitivas -----------------------------------------------------------

def revolucao(perfil, lados=32):
    """
    Sólido de revolução de um perfil `[(r, z)]` em torno do eixo Z.

    O perfil é a seção meridiana, em centímetros. Fecha com tampa onde o raio
    é zero. É a primitiva que dá tubo, cap, luva, bucha de redução, nípel e
    anel de vedação — quase todo o catálogo é sólido de revolução.

    **Perfil fechado é soldado.** Quando o último ponto repete o primeiro — o
    caso de todo perfil de peça vazada, que sai pela parede externa e volta
    pela interna — o último anel é descartado e a última faixa costura de
    volta no anel 0. Sem isso os dois anéis coincidem mas são vértices
    distintos, e a malha fica com `2 × lados` arestas de borda: um sólido
    aparentemente fechado que no viewer mostra o interior pela costura.
    """
    fechado = (len(perfil) > 2
               and abs(perfil[0][0] - perfil[-1][0]) < 1e-9
               and abs(perfil[0][1] - perfil[-1][1]) < 1e-9)
    if fechado:
        perfil = perfil[:-1]

    verts, tris = [], []
    aneis = []
    for r, z in perfil:
        if abs(r) < 1e-9:
            aneis.append(('polo', len(verts)))
            verts.append((0.0, 0.0, z))
        else:
            aneis.append(('anel', len(verts)))
            for i in range(lados):
                a = 2 * math.pi * i / lados
                verts.append((r * math.cos(a), r * math.sin(a), z))

    faixas = list(range(len(aneis) - 1))
    for k in faixas + ([len(aneis) - 1] if fechado else []):
        (t0, b0) = aneis[k]
        (t1, b1) = aneis[(k + 1) % len(aneis)]
        if t0 == 'anel' and t1 == 'anel':
            for i in range(lados):
                j = (i + 1) % lados
                tris.append((b0 + i, b0 + j, b1 + j))
                tris.append((b0 + i, b1 + j, b1 + i))
        elif t0 == 'polo' and t1 == 'anel':
            for i in range(lados):
                tris.append((b0, b1 + (i + 1) % lados, b1 + i))
        elif t0 == 'anel' and t1 == 'polo':
            for i in range(lados):
                tris.append((b1, b0 + i, b0 + (i + 1) % lados))
    return verts, tris


def _normaliza(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def varrer_tubo(caminho, r_ext, r_int, lados=24):
    """
    Varre uma coroa circular ao longo de um caminho PLANAR no plano XZ.

    `caminho` é `[(ponto, tangente)]`. A seção fica no plano perpendicular à
    tangente; como o caminho é planar em XZ, o eixo Y serve de referência fixa
    e a base da seção sai sem torção — não precisa de transporte paralelo.

    Devolve a parede externa, a interna e as duas coroas das pontas. É a
    primitiva do joelho, da curva, do sifão e da curva de transposição.
    """
    ext, inte = [], []
    for p, t in caminho:
        t = _normaliza(t)
        u = (0.0, 1.0, 0.0)
        v = _normaliza((t[1] * u[2] - t[2] * u[1],
                        t[2] * u[0] - t[0] * u[2],
                        t[0] * u[1] - t[1] * u[0]))
        for destino, raio in ((ext, r_ext), (inte, r_int)):
            for i in range(lados):
                a = 2 * math.pi * i / lados
                c, s = math.cos(a) * raio, math.sin(a) * raio
                destino.append((p[0] + c * u[0] + s * v[0],
                                p[1] + c * u[1] + s * v[1],
                                p[2] + c * u[2] + s * v[2]))

    n = len(caminho)
    verts = ext + inte
    base_i = len(ext)
    tris = []
    for k in range(n - 1):
        a0, a1 = k * lados, (k + 1) * lados
        for i in range(lados):
            j = (i + 1) % lados
            # parede externa, normal para fora
            tris.append((a0 + i, a0 + j, a1 + j))
            tris.append((a0 + i, a1 + j, a1 + i))
            # parede interna, normal para dentro
            tris.append((base_i + a0 + j, base_i + a0 + i, base_i + a1 + i))
            tris.append((base_i + a0 + j, base_i + a1 + i, base_i + a1 + j))
    # coroas das duas pontas
    for k, sinal in ((0, 1), (n - 1, -1)):
        a = k * lados
        for i in range(lados):
            j = (i + 1) % lados
            if sinal > 0:
                tris.append((a + i, base_i + a + i, base_i + a + j))
                tris.append((a + i, base_i + a + j, a + j))
            else:
                tris.append((base_i + a + i, a + i, a + j))
                tris.append((base_i + a + i, a + j, base_i + a + j))
    return verts, tris


def caminho_curva(braco, raio, angulo_graus, passos=10):
    """
    Caminho de um joelho: reto, arco, reto — do plano XZ, começando em +Z.

    Entra pela face inferior subindo em +Z e sai virado `angulo_graus` para +X.
    O eixo do arco tem raio `raio`; `braco` é o trecho reto de cada lado,
    medido do centro do arco à face.
    """
    ang = math.radians(angulo_graus)
    # centro do arco fica em (raio, 0, 0), o arco começa em (0,0,0) subindo
    reto = max(braco - raio, 0.05)
    pontos = [((0.0, 0.0, -reto), (0.0, 0.0, 1.0)), ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]
    cx, cz = raio, 0.0
    for k in range(1, passos + 1):
        a = ang * k / passos
        p = (cx - raio * math.cos(a), 0.0, cz + raio * math.sin(a))
        t = (math.sin(a), 0.0, math.cos(a))
        pontos.append((p, t))
    px, _, pz = pontos[-1][0]
    tx, _, tz = pontos[-1][1]
    pontos.append(((px + tx * reto, 0.0, pz + tz * reto), (tx, 0.0, tz)))
    return pontos


def caixa(dx, dy, dz, z0=0.0, cx=0.0, cy=0.0):
    """Paralelepípedo centrado em (cx, cy), de z0 a z0+dz."""
    x0, x1 = cx - dx / 2, cx + dx / 2
    y0, y1 = cy - dy / 2, cy + dy / 2
    z1 = z0 + dz
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    tris = [(0, 2, 1), (0, 3, 2),          # base
            (4, 5, 6), (4, 6, 7),          # topo
            (0, 1, 5), (0, 5, 4),
            (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6),
            (3, 0, 4), (3, 4, 7)]
    return verts, tris


def esfera(raio, cz=0.0, lados=20, aneis=12):
    perfil = []
    for k in range(aneis + 1):
        a = math.pi * k / aneis
        perfil.append((raio * math.sin(a), cz - raio * math.cos(a)))
    return revolucao(perfil, lados)


def rotacionar_z(verts, graus):
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c, z) for x, y, z in verts]


def rotacionar_y(verts, graus):
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    return [(x * c + z * s, y, -x * s + z * c) for x, y, z in verts]


def transladar(verts, dx=0.0, dy=0.0, dz=0.0):
    return [(x + dx, y + dy, z + dz) for x, y, z in verts]


# --- Peça: os parâmetros de que os geradores precisam ---------------------

class Peca:
    """
    Os parâmetros de uma peça, já em centímetros.

    `de1` é o diâmetro externo principal e `de2` o secundário, quando a
    descrição traz dois ("50 x 25mm", "DN 100 x 50", "20mm x 1/2\"").
    """

    def __init__(self, de1_mm, de2_mm, secao, titulo, comprimento_cm=None):
        self.secao = secao
        self.titulo = titulo
        self.de1 = de1_mm / 10.0
        self.de2 = (de2_mm or de1_mm) / 10.0
        self.e1 = parede_mm(secao, de1_mm) / 10.0
        self.e2 = parede_mm(secao, de2_mm or de1_mm) / 10.0
        self.comp = comprimento_cm
        alvo = titulo.upper()
        self.longa = 'LONGA' in alvo
        self.roscavel = 'ROSC' in alvo or 'INTERN' in alvo
        self.latao = 'LATÃO' in alvo or 'LATAO' in alvo

    # raios, em cm
    @property
    def r1(self): return self.de1 / 2
    @property
    def r1i(self): return self.de1 / 2 - self.e1
    @property
    def r2(self): return self.de2 / 2
    @property
    def r2i(self): return self.de2 / 2 - self.e2

    def bolsa(self, de=None):
        return PROPORCOES['bolsa'](10 * (de or self.de1)) / 10.0

    def colar(self, r):
        return r + PROPORCOES['colar'](0) / 10.0

    def cor_corpo(self):
        if self.secao == 'ESGOTO':
            return COR['branca']
        if self.secao == 'POLIETILENO':
            return COR['preta']
        if self.secao == 'ACESSÓRIOS':
            return COR['preta'] if 'PRETO' in self.titulo.upper() else COR['branca']
        if self.latao:
            return COR['azul']
        if self.roscavel:
            return COR['branca']
        return COR['marrom']


# --- Geradores por tipo de forma -----------------------------------------

def f_tubo(p):
    """Trecho de tubo. O comprimento vem do título da família ("6M")."""
    L = p.comp
    if L is None:
        raise ValueError(f'tubo sem comprimento: {p.titulo}')
    return [(*revolucao([(p.r1i, 0), (p.r1, 0), (p.r1, L), (p.r1i, L),
                         (p.r1i, 0)]), p.cor_corpo())]


def _bolsa_dupla(p, r, ri, corpo, cor):
    """Corpo cilíndrico com um colar de bolsa em cada ponta."""
    b = p.bolsa(2 * r * 10 / 10)
    rc = p.colar(r)
    perfil = [(ri, 0), (rc, 0), (rc, b), (r, b), (r, corpo - b),
              (rc, corpo - b), (rc, corpo), (ri, corpo), (ri, 0)]
    return [(*revolucao(perfil), cor)]


def f_luva(p):
    """Luva, união, luva de correr — corpo curto com bolsa nas duas pontas."""
    b = p.bolsa()
    corpo = 2 * b + 0.4 * p.de1
    return _bolsa_dupla(p, p.r1, p.r1i, corpo, p.cor_corpo())


def f_nipel(p):
    """Nípel: tubo curto com rosca externa, sem colar."""
    L = 1.6 * p.de1
    return [(*revolucao([(p.r1i, 0), (p.r1, 0), (p.r1, L), (p.r1i, L),
                         (p.r1i, 0)]), p.cor_corpo())]


def f_cap(p):
    """Cap: bolsa numa ponta, fundo fechado na outra."""
    b = p.bolsa()
    rc = p.colar(p.r1)
    L = b + 0.35 * p.de1
    perfil = [(0, L), (rc, L), (rc, b * 0.15), (rc, 0), (p.r1i, 0), (p.r1i, b),
              (0, b)]
    return [(*revolucao(perfil), p.cor_corpo())]


def f_plug(p):
    """Plug/espude: tampão maciço com sextavado de aperto."""
    L = 1.2 * p.de1
    corpo = revolucao([(0, 0), (p.r1, 0), (p.r1, L * 0.75), (0, L * 0.75)])
    cabeca = revolucao([(0, L * 0.75), (p.r1 * 1.25, L * 0.75),
                        (p.r1 * 1.25, L), (0, L)], lados=6)
    return [(*corpo, p.cor_corpo()), (*cabeca, p.cor_corpo())]


def f_anel(p):
    """Anel de vedação: toro de borracha na boca do tubo."""
    r_sec = max(0.25, 0.055 * p.de1)
    r_eixo = p.r1 + r_sec
    perfil = [(r_eixo + r_sec * math.cos(2 * math.pi * k / 16),
               r_sec * math.sin(2 * math.pi * k / 16)) for k in range(17)]
    return [(*revolucao(perfil), COR['borracha'])]


def f_reducao(p):
    """
    Bucha de redução, luva de redução, adaptador — tronco de cone entre os
    dois diâmetros, com bolsa no maior e ponta no menor.
    """
    b1, b2 = p.bolsa(p.de1 * 10 / 10), p.bolsa(p.de2 * 10 / 10)
    rc1, rc2 = p.colar(p.r1), p.colar(p.r2)
    z = 0.0
    perfil = [(p.r1i, z), (rc1, z)]
    z += b1
    perfil += [(rc1, z), (p.r1, z)]
    z += 0.35 * p.de1
    perfil += [(rc2, z)]
    z += b2
    perfil += [(rc2, z), (p.r2i, z)]
    perfil += [(p.r2i, 0), (p.r1i, 0)]
    excentrica = 'EXCÊNTRICA' in p.titulo.upper()
    malhas = [(*revolucao(perfil), p.cor_corpo())]
    if excentrica:
        # a redução excêntrica alinha as geratrizes inferiores em vez dos eixos
        v, t = malhas[0][0], malhas[0][1]
        desl = p.r1 - p.r2
        v = [(x, y, z_) if z_ < b1 + 0.2 else (x + desl, y, z_)
             for x, y, z_ in v]
        malhas = [(v, t, p.cor_corpo())]
    if p.latao:
        malhas.append((*revolucao([(p.r2i * 0.75, 0), (p.r2i, 0),
                                   (p.r2i, b2 * 0.8), (p.r2i * 0.75, b2 * 0.8),
                                   (p.r2i * 0.75, 0)]), COR['latao']))
    return malhas


def f_joelho(p):
    """Joelho e curva. O ângulo e o raio saem do título."""
    alvo = p.titulo.upper()
    ang = 45 if '45' in alvo else 90
    raio = (PROPORCOES['raio_longa' if p.longa else 'raio_curta'](p.de1 * 10)
            / 10.0)
    braco = PROPORCOES['braco'](p.de1 * 10) / 10.0
    cam = caminho_curva(braco, raio, ang)
    corpo = varrer_tubo(cam, p.r1, p.r1i)
    malhas = [(*corpo, p.cor_corpo())]
    # colares nas duas bocas
    rc = p.colar(p.r1)
    b = p.bolsa()
    malhas.append((*revolucao([(p.r1, -braco), (rc, -braco), (rc, -braco + b),
                               (p.r1, -braco + b), (p.r1, -braco)]),
                   p.cor_corpo()))
    if p.de2 != p.de1:
        # joelho com visita ou saída reduzida: um ramo menor no meio do arco
        ramo = revolucao([(p.r2i, 0), (p.r2, 0), (p.r2, braco * 0.9),
                          (p.r2i, braco * 0.9), (p.r2i, 0)])
        malhas.append((transladar(rotacionar_y(ramo[0], 90), 0, 0, raio * 0.4),
                       ramo[1], p.cor_corpo()))
    return malhas


def f_transposicao(p):
    """Curva de transposição: dois arcos opostos, o desvio em S."""
    raio = PROPORCOES['raio_longa'](p.de1 * 10) / 10.0
    passos = 8
    cam = [((0.0, 0.0, -0.6 * p.de1), (0.0, 0.0, 1.0))]
    for k in range(passos + 1):
        a = math.radians(30) * k / passos
        cam.append(((raio - raio * math.cos(a), 0.0, raio * math.sin(a)),
                    (math.sin(a), 0.0, math.cos(a))))
    px, _, pz = cam[-1][0]
    for k in range(1, passos + 1):
        a = math.radians(30) * (1 - k / passos)
        dx = (raio - raio * math.cos(math.radians(30))) - (raio - raio * math.cos(a))
        cam.append(((px - dx, 0.0, pz + raio * (math.sin(math.radians(30)) - math.sin(a)) + 0.0),
                    (math.sin(a), 0.0, math.cos(a))))
    px, _, pz = cam[-1][0]
    cam.append(((px, 0.0, pz + 0.6 * p.de1), (0.0, 0.0, 1.0)))
    return [(*varrer_tubo(cam, p.r1, p.r1i), p.cor_corpo())]


def f_te(p):
    """Tê: corpo passante com bolsa nas pontas e um ramo a 90°."""
    b = p.bolsa()
    corpo_L = 2 * b + 0.9 * p.de1
    malhas = _bolsa_dupla(p, p.r1, p.r1i, corpo_L, p.cor_corpo())
    # o ramo, na direção +X, saindo do meio
    rb, rbi = p.r2, p.r2i
    b2 = p.bolsa(p.de2 * 10 / 10)
    rc2 = p.colar(rb)
    L = 0.5 * p.de1 + b2 + 0.3 * p.de2
    perfil = [(rbi, 0), (rb, 0), (rb, L - b2), (rc2, L - b2), (rc2, L),
              (rbi, L), (rbi, 0)]
    ramo = revolucao(perfil)
    malhas.append((transladar(rotacionar_y(ramo[0], 90), 0, 0, corpo_L / 2),
                   ramo[1], p.cor_corpo()))
    if p.latao:
        luva = revolucao([(rbi * 0.75, L - b2), (rbi, L - b2), (rbi, L),
                          (rbi * 0.75, L), (rbi * 0.75, L - b2)])
        malhas.append((transladar(rotacionar_y(luva[0], 90), 0, 0, corpo_L / 2),
                       luva[1], COR['latao']))
    return malhas


def f_juncao(p):
    """Junção: como o tê, mas o ramo entra a 45°."""
    b = p.bolsa()
    corpo_L = 2 * b + 1.1 * p.de1
    malhas = _bolsa_dupla(p, p.r1, p.r1i, corpo_L, p.cor_corpo())
    rb, rbi = p.r2, p.r2i
    L = 0.9 * p.de1 + p.bolsa(p.de2 * 10 / 10)
    ramo = revolucao([(rbi, 0), (rb, 0), (rb, L), (rbi, L), (rbi, 0)])
    malhas.append((transladar(rotacionar_y(ramo[0], 45), 0, 0, corpo_L * 0.45),
                   ramo[1], p.cor_corpo()))
    return malhas


def f_registro(p):
    """Registro de esfera: corpo, duas pontas e alavanca."""
    dr = PROPORCOES['registro_diam'](p.de1 * 10) / 10.0
    lr = PROPORCOES['registro_comp'](p.de1 * 10) / 10.0
    b = p.bolsa()
    z = 0.0
    perfil = [(p.r1i, z), (p.r1, z)]
    z += b
    perfil += [(p.r1, z), (dr / 2, z), (dr / 2, z + lr)]
    z += lr
    perfil += [(p.r1, z), (p.r1, z + b), (p.r1i, z + b), (p.r1i, 0)]
    malhas = [(*revolucao(perfil), p.cor_corpo())]
    # haste e alavanca, na direção +X
    haste = revolucao([(0, 0), (dr * 0.10, 0), (dr * 0.10, dr * 0.35), (0, dr * 0.35)])
    malhas.append((transladar(rotacionar_y(haste[0], 90), dr / 2, 0, b + lr / 2),
                   haste[1], COR['azul']))
    alav = caixa(dr * 0.12, dr * 0.9, dr * 0.16)
    malhas.append((transladar(rotacionar_y(alav[0], 90),
                              dr / 2 + dr * 0.35, 0, b + lr / 2),
                   alav[1], COR['azul']))
    return malhas


def f_valvula_retencao(p):
    """Válvula de retenção: corpo abaulado entre duas bolsas."""
    b = p.bolsa()
    dr = 1.5 * p.de1
    z = 0.0
    perfil = [(p.r1i, 0), (p.r1, 0), (p.r1, b), (dr / 2, b + 0.15 * p.de1),
              (dr / 2, b + 0.75 * p.de1), (p.r1, b + 0.9 * p.de1),
              (p.r1, 2 * b + 0.9 * p.de1), (p.r1i, 2 * b + 0.9 * p.de1),
              (p.r1i, 0)]
    tampa = revolucao([(0, b + 0.78 * p.de1), (dr / 2 * 0.8, b + 0.78 * p.de1),
                       (dr / 2 * 0.8, b + 0.9 * p.de1), (0, b + 0.9 * p.de1)])
    return [(*revolucao(perfil), p.cor_corpo()), (*tampa, COR['cinza'])]


def f_torneira_boia(p):
    """Torneira de boia: corpo roscado, braço e flutuador."""
    corpo = revolucao([(p.r1i, 0), (p.r1, 0), (p.r1, 1.6 * p.de1),
                       (p.r1i, 1.6 * p.de1), (p.r1i, 0)])
    braco = revolucao([(0, 0), (p.r1 * 0.22, 0), (p.r1 * 0.22, 7.0), (0, 7.0)])
    bola = esfera(2.8)
    return [(*corpo, COR['branca']),
            (transladar(rotacionar_y(braco[0], 90), 0, 0, 1.5 * p.de1),
             braco[1], COR['metal']),
            (transladar(bola[0], 7.0 + 2.8, 0, 1.5 * p.de1), bola[1],
             COR['branca'])]


def f_engate(p):
    """Engate flexível: mangueira corrugada com duas porcas."""
    L = p.comp or 30.0
    r = max(0.55, p.r1 * 0.55)
    n = max(12, int(L / 1.2))
    perfil = [(0.0, 0.0)]          # tampa inferior
    for k in range(n + 1):
        z = L * k / n
        perfil.append((r * (1.0 + 0.14 * (k % 2)), z))
    perfil.append((0.0, L))        # tampa superior
    corpo = revolucao(perfil, lados=16)
    malhas = [(*corpo, COR['metal'])]
    for z0 in (0.0, L - 1.6):
        porca = revolucao([(0, z0), (r * 1.9, z0), (r * 1.9, z0 + 1.6),
                           (0, z0 + 1.6)], lados=6)
        malhas.append((*porca, COR['latao']))
    return malhas


def f_sifao(p):
    """Sifão extensível: copo, curva em U e saída, no comprimento do catálogo."""
    L = p.comp or 62.0
    r, ri = 1.9, 1.6
    ramos = 1
    alvo = p.titulo.upper()
    if 'DUPLO' in alvo:
        ramos = 2
    elif 'TRIPLO' in alvo:
        ramos = 3
    cor = COR['preta'] if 'PRETO' in alvo else COR['branca']
    malhas = []
    for k in range(ramos):
        dx = k * 6.5
        # o perfil volta ao eixo em (0, 0): sem esse ponto o último anel
        # fica de borda e o copo aparece aberto por baixo
        copo = revolucao([(0, 0), (3.4, 0), (3.4, 5.0), (r, 6.0), (r, 9.0),
                          (ri, 9.0), (ri, 0), (0, 0)])
        malhas.append((transladar(copo[0], dx, 0, L * 0.55), copo[1], cor))
        cam = caminho_curva(4.5, 3.0, 180, passos=12)
        u = varrer_tubo(cam, r, ri, lados=16)
        malhas.append((transladar(u[0], dx, 0, 6.0), u[1], cor))
    saida = revolucao([(ri, 0), (r, 0), (r, L * 0.45), (ri, L * 0.45), (ri, 0)])
    malhas.append((transladar(saida[0], (ramos - 1) * 6.5 + 9.0, 0, 0),
                   saida[1], cor))
    return malhas


def f_valvula_pia(p):
    """Válvula de pia/lavatório, tampa, unho: grelha circular e corpo roscado."""
    alvo = p.titulo.upper()
    if 'TAMPA' in alvo:
        d = p.de1 * 1.6
        return [(*revolucao([(0, 0), (d / 2, 0), (d / 2, 0.6), (0, 0.8)]),
                 COR['metal'])]
    if 'UNHO' in alvo:
        return [(*revolucao([(0, 0), (p.r1 * 0.5, 0), (p.r1 * 0.5, 4.0),
                             (0, 4.0)]), COR['latao'])]
    grelha = revolucao([(0, 0), (p.de1 * 0.9, 0), (p.de1 * 0.9, 0.5),
                        (p.r1, 0.6), (0, 0.6)])
    corpo = revolucao([(p.r1i, -3.5), (p.r1, -3.5), (p.r1, 0), (p.r1i, 0),
                       (p.r1i, -3.5)])
    malhas = [(*grelha, COR['metal']), (*corpo, COR['metal'])]
    if 'LADRÃO' in alvo or 'LADRAO' in alvo:
        # o ladrão é o furo lateral de extravasão
        lad = revolucao([(0, 0), (p.r1 * 0.35, 0), (p.r1 * 0.35, p.r1 * 1.2),
                         (0, p.r1 * 1.2)])
        malhas.append((transladar(rotacionar_y(lad[0], 90), 0, 0, -1.8),
                       lad[1], COR['metal']))
    return malhas


def f_chuveiro(p):
    """Kit chuveiro: pinha, braço e, quando há, o registro."""
    d = p.de1 * 1.0
    pinha = revolucao([(0, 0), (d / 2, 1.2), (d / 2 * 0.96, 1.6), (0, 1.8)])
    braco = revolucao([(0, 0), (0.8, 0), (0.8, 22.0), (0, 22.0)])
    malhas = [(*pinha, COR['branca']),
              (transladar(rotacionar_y(braco[0], 65), 0, 0, 1.6),
               braco[1], COR['branca'])]
    if 'COM REGISTRO' in p.titulo.upper():
        reg = revolucao([(0, 0), (1.6, 0), (1.6, 2.2), (0, 2.2)])
        malhas.append((transladar(reg[0], 6.0, 0, 10.0), reg[1], COR['branca']))
    return malhas


def f_caixa_sifonada(p):
    """
    Caixa sifonada: corpo (quadrado ou redondo), grelha e saída.

    A descrição dá as três medidas — `DN 100 x 100 x 50` é corpo 100, altura
    de referência 100 e saída 50.
    """
    lado = p.de1
    saida = p.de2
    h = lado * 0.75
    redonda = 'REDONDA' in p.titulo.upper()
    if redonda:
        corpo = revolucao([(0, 0), (lado / 2, 0), (lado / 2, h), (0, h)])
    else:
        corpo = caixa(lado, lado, h)
    grelha = (caixa(lado * 1.06, lado * 1.06, 0.6, z0=h)
              if not redonda else
              revolucao([(0, h), (lado / 2 * 1.06, h),
                         (lado / 2 * 1.06, h + 0.6), (0, h + 0.6)]))
    tubo_saida = revolucao([(saida / 2 - 0.2, 0), (saida / 2, 0),
                            (saida / 2, lado * 0.5), (saida / 2 - 0.2, lado * 0.5),
                            (saida / 2 - 0.2, 0)])
    malhas = [(*corpo, COR['branca']), (*grelha, COR['branca']),
              (transladar(rotacionar_y(tubo_saida[0], 90), lado / 2, 0, h * 0.35),
               tubo_saida[1], COR['branca'])]
    # entradas laterais
    n_ent = 5 if 'CINCO' in p.titulo.upper() else 3
    r_ent = 2.0
    for k in range(n_ent):
        ang = 360 * k / n_ent
        ent = revolucao([(r_ent - 0.2, 0), (r_ent, 0), (r_ent, lado * 0.35),
                         (r_ent - 0.2, lado * 0.35), (r_ent - 0.2, 0)])
        v = rotacionar_z(transladar(rotacionar_y(ent[0], 90), lado / 2, 0,
                                    h * 0.7), ang)
        malhas.append((v, ent[1], COR['branca']))
    return malhas


def f_ralo(p):
    """Ralo sifonado: corpo baixo com grelha."""
    lado = max(10.0, p.de1 * 2.5)
    h = lado * 0.55
    redondo = 'REDONDO' in p.titulo.upper()
    corpo = (revolucao([(0, 0), (lado / 2, 0), (lado / 2, h), (0, h)])
             if redondo else caixa(lado, lado, h))
    grelha = (revolucao([(0, h), (lado / 2 * 1.05, h),
                         (lado / 2 * 1.05, h + 0.6), (0, h + 0.6)])
              if redondo else caixa(lado * 1.05, lado * 1.05, 0.6, z0=h))
    saida = revolucao([(p.r1i, -p.de1 * 1.2), (p.r1, -p.de1 * 1.2), (p.r1, 0),
                       (p.r1i, 0), (p.r1i, -p.de1 * 1.2)])
    return [(*corpo, COR['branca']), (*grelha, COR['branca']),
            (*saida, COR['branca'])]


def f_grelha(p):
    """Grelha e porta-grelha: moldura e placa vazada."""
    lado = p.de1 * 1.15
    moldura = caixa(lado * 1.12, lado * 1.12, 1.2)
    malhas = [(*moldura, COR['branca'])]
    n = 7
    for k in range(n):
        y = -lado / 2 + lado * (k + 0.5) / n
        barra = caixa(lado * 0.94, lado / n * 0.55, 0.5, z0=1.2, cy=y)
        malhas.append((*barra, COR['branca']))
    return malhas


GERADORES = {
    'tubo': f_tubo, 'luva': f_luva, 'nipel': f_nipel, 'cap': f_cap,
    'plug': f_plug, 'anel': f_anel, 'reducao': f_reducao, 'joelho': f_joelho,
    'transposicao': f_transposicao, 'te': f_te, 'juncao': f_juncao,
    'registro': f_registro, 'valvula_retencao': f_valvula_retencao,
    'torneira_boia': f_torneira_boia, 'engate': f_engate, 'sifao': f_sifao,
    'valvula_pia': f_valvula_pia, 'chuveiro': f_chuveiro,
    'caixa_sifonada': f_caixa_sifonada, 'ralo': f_ralo, 'grelha': f_grelha,
}


def gerar(forma, peca):
    """`[(verts, tris, rgba)]` para a peça, ou `[]` se não há gerador."""
    fn = GERADORES.get(forma)
    return fn(peca) if fn else []


def bbox(malhas):
    """(dx, dy, dz) em cm — para conferência."""
    pts = [v for m in malhas for v in m[0]]
    if not pts:
        return (0.0, 0.0, 0.0)
    return tuple(round(max(p[i] for p in pts) - min(p[i] for p in pts), 2)
                 for i in range(3))
