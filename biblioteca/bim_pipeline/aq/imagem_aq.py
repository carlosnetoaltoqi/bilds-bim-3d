#!/usr/bin/env python3
"""
imagem_aq.py — o BMP de preview de `SIMBOLOGIA_3D.IMAGEM`.

POR QUE ISTO EXISTE. Sem este BMP o AltoQi Builder **não desenha a peça** — nem
no ambiente 3D, nem na planta. A peça entra no Cadastro, mostra nome, código,
descrição e propriedades, e não tem forma nenhuma. O `.aq` fica com megabytes de
OQ3D válido que ninguém vê.

COMO SE SABE. Experimento de 2026-09-08 no Builder, com uma biblioteca nativa de
fabricante que funciona (aquecedores, schema 582) e uma nossa (conexões, schema 607):

    A  nativa intocada                                     desenha
    B  nativa SEM IMAGEM, SEM WIREFRAME e sem entradas     NÃO desenha
    C  nosso cadastro + geometria nativa (blob+wire+img)   desenha (só a peça transplantada)
    D  o C com a IMAGEM apagada, WIREFRAME mantido         NÃO desenha
    E  o C com o WIREFRAME apagado, IMAGEM mantida         desenha
    F  nossa geometria + IMAGEM gerada por este módulo     desenha e lança no projeto

D contra E isola o campo: o que destrava é a `IMAGEM`, não o `WIREFRAME`. O
`WIREFRAME` (arestas para planta/corte) e as `ENTRADA_PECA`/`ENTRADA_3D`
(bocais) seguem fora do escopo — a peça desenha sem eles.

O FORMATO. Nas 16 bibliotecas nativas medidas a `IMAGEM` é sempre o mesmo BMP:
100×100, 24 bits, sem paleta e sem compressão — 54 bytes de cabeçalho + 100
linhas de 300 bytes = 30.054 bytes exatos. A linha tem 300 bytes, múltiplo de 4,
então **não há padding** (é a única resolução em que dá essa sorte; mudar `LADO`
reintroduz o padding do BMP).

O RASTERIZADOR. É software puro, em numpy: sem Playwright, sem Chromium, sem
WebGL. Não é o harness de miniaturas de `bim_pipeline.miniaturas` — aquele existe
para a imagem do site, roda o mesmo Three.js do viewer e depende de Node. Aqui a
imagem é um requisito do formato do arquivo, gerado no mesmo processo que escreve
o `.aq`, e o `.aq` tem que sair no CI, onde não há navegador. Um catálogo de
1.399 simbologias não pode pagar 2 s de Chromium por peça.
"""
import math
import struct

import numpy as np

LADO = 100                      # 0x64 nas 16 bibliotecas nativas medidas
MARGEM = 4                       # px de folga de cada lado, para a peça não encostar na borda
FUNDO = (255, 255, 255)          # os nativos começam em branco (ff ff ff no primeiro pixel)
AZIMUTE, ELEVACAO = 35.0, 20.0   # vista isométrica suave: mostra volume em 100 px
AMBIENTE, DIFUSA = 0.35, 0.65    # sombreamento plano — só para dar relevo à malha
TETO_TRABALHO = 4_000_000        # pixels-candidatos por lote (limita a memória do rasterizador)


def _base_da_camera(azimute=AZIMUTE, elevacao=ELEVACAO):
    """
    Base ortonormal da câmera para geometria em Z-up (a do OQ3D).

    Devolve `(direita, cima, frente)`: `frente` aponta do objeto para a câmera,
    então a profundidade de um ponto é `v · frente` — maior é mais perto.
    """
    az, el = math.radians(azimute), math.radians(elevacao)
    frente = np.array([math.cos(el) * math.cos(az),
                       math.cos(el) * math.sin(az),
                       math.sin(el)])
    direita = np.cross([0.0, 0.0, 1.0], frente)
    direita /= np.linalg.norm(direita)
    cima = np.cross(frente, direita)
    return direita, cima, frente


def _juntar(malhas):
    """
    Concatena as malhas de uma simbologia num só par (vértices, triângulos).

    Mesmo contrato de `oq3d_writer.escrever`: `(verts, tris, rgba, xform)`, com
    `verts` em centímetros Z-up, `rgba` uniforme por malha e `xform` em LINHAS
    (`((r0..r8), (tx, ty, tz))`) ou `None` para identidade. O `xform` é aplicado
    aqui pelo mesmo caminho do escritor — se a imagem ignorasse o transform, a
    peça sairia montada errado no preview e certa no 3D.
    """
    vs, ts, cores, base = [], [], [], 0
    for verts, tris, rgba, xform in malhas:
        v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
        t = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
        if len(v) == 0 or len(t) == 0:
            continue
        if xform is not None:
            rot, trans = xform
            v = v @ np.asarray(rot, dtype=np.float64).reshape(3, 3).T + np.asarray(trans, dtype=np.float64)
        vs.append(v)
        ts.append(t + base)
        cores.append(np.tile(np.asarray(rgba[:3], dtype=np.float64) / 255.0, (len(t), 1)))
        base += len(v)
    if not vs:
        return None, None, None
    return np.concatenate(vs), np.concatenate(ts), np.concatenate(cores)


def _cor_por_triangulo(v, t, cor_malha, frente):
    """Sombreamento plano: cor da malha modulada pelo ângulo entre a face e a luz."""
    n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    norma = np.linalg.norm(n, axis=1, keepdims=True)
    norma[norma == 0] = 1.0
    # luz na direção da câmera, deslocada para o alto: destaca a silhueta e o topo
    luz = frente + np.array([0.0, 0.0, 0.45])
    luz /= np.linalg.norm(luz)
    brilho = AMBIENTE + DIFUSA * np.abs((n / norma) @ luz)
    return np.clip(cor_malha * brilho[:, None], 0.0, 1.0) * 255.0


def _rasterizar(xy, prof, t, cor_t, lado):
    """
    Z-buffer por lista de trabalho, vetorizado.

    Numa imagem de 100×100 quase todo triângulo de uma malha de fabricante cobre
    um punhado de pixels, então o custo real é a soma das áreas das *bounding
    boxes*, não o número de triângulos — o que permite tratar 111 mil triângulos
    sem laço em Python. Para cada triângulo se enumeram os pixels da sua bbox, se
    testa a coordenada baricêntrica e se resolve a profundidade empacotando
    `(profundidade, índice do triângulo)` num int64: ordenar por esse valor faz o
    vencedor de cada pixel ser o último da sua posição.
    """
    n_tri = len(t)
    if n_tri >= 1 << 31:                          # o empacotamento reserva 32 bits ao índice
        raise ValueError(f'malha com {n_tri} triângulos excede o rasterizador')
    a, b, c = xy[t[:, 0]], xy[t[:, 1]], xy[t[:, 2]]
    za, zb, zc = prof[t[:, 0]], prof[t[:, 1]], prof[t[:, 2]]

    xmin = np.clip(np.floor(np.minimum.reduce([a[:, 0], b[:, 0], c[:, 0]])), 0, lado - 1).astype(np.int64)
    xmax = np.clip(np.ceil(np.maximum.reduce([a[:, 0], b[:, 0], c[:, 0]])), 0, lado - 1).astype(np.int64)
    ymin = np.clip(np.floor(np.minimum.reduce([a[:, 1], b[:, 1], c[:, 1]])), 0, lado - 1).astype(np.int64)
    ymax = np.clip(np.ceil(np.maximum.reduce([a[:, 1], b[:, 1], c[:, 1]])), 0, lado - 1).astype(np.int64)
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])

    larg, alt = xmax - xmin + 1, ymax - ymin + 1
    vale = (larg > 0) & (alt > 0) & (np.abs(det) > 1e-12)
    if not vale.any():
        return None
    idx_tri = np.nonzero(vale)[0]
    area = (larg[vale] * alt[vale]).astype(np.int64)

    # profundidade em inteiro, para caber no empacotamento junto do índice
    lo, hi = prof.min(), prof.max()
    escala_z = (1 << 30) / max(hi - lo, 1e-12)

    buffer_chave = np.full(lado * lado, -1, dtype=np.int64)

    # lotes por orçamento de trabalho, para a memória não depender da malha
    acumulado = np.cumsum(area)
    inicio_lote = 0
    while inicio_lote < len(area):
        gasto = acumulado[inicio_lote:] - (acumulado[inicio_lote - 1] if inicio_lote else 0)
        fim_lote = inicio_lote + max(int(np.searchsorted(gasto, TETO_TRABALHO)), 1)
        fatia = slice(inicio_lote, fim_lote)
        tri = np.repeat(idx_tri[fatia], area[fatia])
        deslocamento = np.arange(len(tri)) - np.repeat(
            np.cumsum(area[fatia]) - area[fatia], area[fatia])
        lg = larg[tri]
        px = xmin[tri] + deslocamento % lg
        py = ymin[tri] + deslocamento // lg

        fx, fy = px + 0.5, py + 0.5
        w0 = ((b[tri, 0] - fx) * (c[tri, 1] - fy) - (c[tri, 0] - fx) * (b[tri, 1] - fy)) / det[tri]
        w1 = ((c[tri, 0] - fx) * (a[tri, 1] - fy) - (a[tri, 0] - fx) * (c[tri, 1] - fy)) / det[tri]
        w2 = 1.0 - w0 - w1
        dentro = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if dentro.any():
            tri, px, py = tri[dentro], px[dentro], py[dentro]
            z = w0[dentro] * za[tri] + w1[dentro] * zb[tri] + w2[dentro] * zc[tri]
            chave = (np.rint((z - lo) * escala_z).astype(np.int64) << 32) | tri
            pixel = py * lado + px
            # vence o maior (profundidade, índice) de cada pixel: ordena e pega o último
            ordem = np.lexsort((chave, pixel))
            pixel, chave = pixel[ordem], chave[ordem]
            ultimo = np.ones(len(pixel), dtype=bool)
            ultimo[:-1] = pixel[1:] != pixel[:-1]
            pixel, chave = pixel[ultimo], chave[ultimo]
            melhor = chave > buffer_chave[pixel]
            buffer_chave[pixel[melhor]] = chave[melhor]
        inicio_lote = fim_lote

    img = np.empty((lado, lado, 3), dtype=np.uint8)
    img[:] = FUNDO
    pintado = np.nonzero(buffer_chave >= 0)[0]
    if len(pintado):
        vencedor = (buffer_chave[pintado] & 0xFFFFFFFF).astype(np.int64)
        img.reshape(-1, 3)[pintado] = cor_t[vencedor].astype(np.uint8)
    return img


def render(malhas, lado=LADO):
    """
    `malhas` (o mesmo argumento de `oq3d_writer.escrever`) → BMP pronto para
    `SIMBOLOGIA_3D.IMAGEM`, ou `None` se não houver triângulo nenhum.
    """
    v, t, cor_malha = _juntar(malhas)
    if v is None:
        return None
    direita, cima, frente = _base_da_camera()
    xy = np.column_stack((v @ direita, v @ cima))
    prof = v @ frente

    lo, hi = xy.min(axis=0), xy.max(axis=0)
    vao = max((hi - lo).max(), 1e-9)
    escala = (lado - 2 * MARGEM) / vao
    xy = (xy - (lo + hi) / 2) * escala + lado / 2

    img = _rasterizar(xy, prof, t, _cor_por_triangulo(v, t, cor_malha, frente), lado)
    if img is None:
        return None
    return bmp24(img)


def bmp24(img):
    """
    BMP 24 bits sem compressão, no layout dos nativos: linhas de baixo para cima
    e canais em BGR. Com `LADO = 100` a linha tem 300 bytes (múltiplo de 4) e
    dispensa padding — o arquivo dá 30.054 bytes, igual ao dos nativos.
    """
    altura, largura = img.shape[:2]
    if (largura * 3) % 4:
        raise ValueError(f'largura {largura} exige padding de linha, não implementado')
    dados = np.ascontiguousarray(img[::-1, :, ::-1]).tobytes()
    cabecalho = struct.pack('<2sIHHI', b'BM', 54 + len(dados), 0, 0, 54)
    dib = struct.pack('<IiiHHIIiiII', 40, largura, altura, 1, 24, 0, len(dados), 0, 0, 0, 0)
    return cabecalho + dib + dados
