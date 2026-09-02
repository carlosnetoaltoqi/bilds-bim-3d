#!/usr/bin/env python3
"""
oq3d_roundtrip.py — prova que o `oq3d_writer.py` grava OQ3D que se lê de volta.

Escreve blobs com o escritor e lê com o `scripts/oq3d.py` DO PRÓPRIO PROJETO,
importado sem modificação, comparando vértice a vértice, triângulo a triângulo e
cor a cor. É a única aferição possível aqui: não há AltoQi Builder nesta
máquina, então o que se pode garantir é que o blob é consistente com o leitor
validado em 12 bibliotecas e 6 versões de schema.

Os casos cobrem o que separa um escritor certo de um quase certo:

1. **Uma malha, sem transform.** O caminho básico.
2. **Rotação não simétrica.** Se a rotação for gravada em linhas em vez de
   colunas, a matriz sai transposta: os pontos caem no lugar errado sem que a
   contagem de triângulos mude — o bug da sessão S5.1, que passou despercebido
   justamente porque não altera nenhuma contagem. Este caso falha se a
   transposição não estiver certa.
4. **Várias malhas com cores diferentes.** Confere o campo de contagem de
   raízes do cabeçalho e a cor por malha.
5. **Cores de bocal.** O leitor filtra verde `(1,154,63)` e azul `(10,84,152)`
   com `skip_markers=True`; o escritor tem de conseguir gravá-las.
6. **Comparação com um blob real.** Reescreve a geometria lida de uma
   `SIMBOLOGIA_3D` de verdade e confere que a releitura bate com o original.

Uso:
    python3 oq3d_roundtrip.py [--aq <arquivo.aq> --sid <id>]
"""
import argparse
import math
import os
import sqlite3
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, 'scripts'))   # o oq3d.py do projeto
sys.path.insert(0, AQUI)

import oq3d                      # noqa: E402  leitor do projeto, intocado
import oq3d_writer as w          # noqa: E402

TOL = 1e-9
falhas = []


def checar(nome, condicao, detalhe=''):
    marca = 'ok  ' if condicao else 'FALHA'
    print(f'  [{marca}] {nome}' + (f' — {detalhe}' if detalhe else ''))
    if not condicao:
        falhas.append(nome)


def comparar_malhas(esperado, obtido, nome):
    """Compara [(verts, tris, rgba)] com tolerância numérica."""
    if len(esperado) != len(obtido):
        checar(nome, False, f'{len(esperado)} malhas escritas, '
                            f'{len(obtido)} lidas')
        return
    for k, ((ve, te, ce), (vo, to, co)) in enumerate(zip(esperado, obtido)):
        vo = [tuple(v) for v in vo]
        to = [tuple(int(i) for i in t) for t in to]
        if len(ve) != len(vo) or len(te) != len(to):
            checar(f'{nome} malha {k}', False,
                   f'{len(ve)}v/{len(te)}t escritos, '
                   f'{len(vo)}v/{len(to)}t lidos')
            return
        pior = max((max(abs(a - b) for a, b in zip(p, q))
                    for p, q in zip(ve, vo)), default=0.0)
        if pior > TOL:
            checar(f'{nome} malha {k}', False, f'erro máx {pior:.3g} cm')
            return
        if to != te:
            checar(f'{nome} malha {k}', False, 'triângulos diferentes')
            return
        if tuple(co) != tuple(ce):
            checar(f'{nome} malha {k}', False, f'cor {ce} escrita, {co} lida')
            return
    checar(nome, True, f'{len(esperado)} malha(s), '
                       f'{sum(len(m[1]) for m in esperado)} triângulos')


def aplicar(xform, v):
    (r, t) = xform
    return (r[0] * v[0] + r[1] * v[1] + r[2] * v[2] + t[0],
            r[3] * v[0] + r[4] * v[1] + r[5] * v[2] + t[1],
            r[6] * v[0] + r[7] * v[1] + r[8] * v[2] + t[2])


def caso_simples():
    print('\n1. uma malha, sem transform')
    verts, tris = w.cilindro(raio=2.5, altura=10.0)
    blob = w.escrever([(verts, tris, (216, 203, 184, 255), None)])
    checar('assinatura OQ3D', oq3d.is_oq3d(blob), f'{len(blob)} bytes')
    lido = oq3d.extract(blob)
    comparar_malhas([(verts, tris, (216, 203, 184, 255))], lido, 'geometria')


def caso_rotacao():
    print('\n2. rotação não simétrica (pega o bug de column-major)')
    verts, tris = w.tubo(raio_ext=5.5, raio_int=5.0, altura=20.0)
    # 90° em Z composto com 90° em X: nenhuma simetria que perdoe a transposta.
    c, s = math.cos(math.pi / 2), math.sin(math.pi / 2)
    rz = (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)
    rx = (1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c)
    rot = tuple(sum(rz[i * 3 + k] * rx[k * 3 + j] for k in range(3))
                for i in range(3) for j in range(3))
    xform = (rot, (12.0, -3.0, 7.5))
    blob = w.escrever([(verts, tris, (10, 84, 152, 255), xform)])
    esperado = [aplicar(xform, v) for v in verts]
    lido = oq3d.extract(blob)
    comparar_malhas([(esperado, tris, (10, 84, 152, 255))], lido,
                    'pontos com rotação aplicada')

    # A prova de que a convenção importa: gravar a transposta dá outro
    # resultado. Se as duas leituras coincidissem, o teste acima não provaria
    # nada — a rotação escolhida seria simétrica demais.
    transposta = tuple(rot[j * 3 + i] for i in range(3) for j in range(3))
    outro = oq3d.extract(w.escrever(
        [(verts, tris, (10, 84, 152, 255), (transposta, xform[1]))]))
    difere = any(abs(a - b) > 1e-6
                 for p, q in zip(lido[0][0], outro[0][0])
                 for a, b in zip(p, q))
    checar('a rotação escolhida distingue linhas de colunas', difere)


def caso_varias():
    print('\n3. várias malhas, cores diferentes')
    entradas = []
    for i, cor in enumerate([(216, 203, 184, 255), (1, 154, 63, 255),
                             (10, 84, 152, 255), (90, 90, 90, 255)]):
        verts, tris = w.cilindro(raio=1.0 + i, altura=4.0, z0=6.0 * i,
                                 lados=12)
        entradas.append((verts, tris, cor, None))
    blob = w.escrever(entradas)
    import struct
    n_raizes = struct.unpack_from('<I', blob, 29)[0]
    checar('campo de contagem de raízes', n_raizes == 4, f'N={n_raizes}')
    comparar_malhas([(v, t, c) for v, t, c, _ in entradas],
                    oq3d.extract(blob), 'geometria e cores')

    print('\n4. filtro de bocais do leitor')
    corpo = oq3d.extract(blob, skip_markers=True)
    checar('skip_markers descarta verde e azul', len(corpo) == 2,
           f'{len(corpo)} de 4 malhas mantidas')


def caso_bbox():
    print('\n5. bbox e stats do leitor sobre o que escrevemos')
    verts, tris = w.tubo(raio_ext=8.0, raio_int=7.5, altura=600.0, lados=48)
    blob = w.escrever([(verts, tris, (255, 255, 255, 255), None)])
    dx, dy, dz = oq3d.bbox(blob)
    checar('bbox do tubo DN160 de 6 m',
           abs(dz - 600.0) < 1e-6 and abs(dx - 16.0) < 0.1,
           f'{dx:.2f} × {dy:.2f} × {dz:.2f} cm')
    st = oq3d.stats(blob)
    checar('stats consistente',
           st['triangulos'] == len(tris) and st['malhas'] == 1,
           f"{st['malhas']} malha, {st['triangulos']} triângulos")


def caso_real(aq, sid):
    print(f'\n6. reescrita de geometria real ({os.path.basename(aq)} sid={sid})')

    def dec(b):
        try:
            return b.decode('cp1252')
        except UnicodeDecodeError:
            return b.decode('latin-1')

    con = sqlite3.connect(f'file:{aq}?mode=ro', uri=True)
    con.text_factory = dec
    row = con.execute('SELECT NOME, CAST(SIMBOLOGIA_3D AS BLOB) '
                      'FROM SIMBOLOGIA_3D WHERE ID_SIMBOLOGIA_3D = ?',
                      (sid,)).fetchone()
    con.close()
    if row is None:
        checar('simbologia existe', False, f'sid {sid} não encontrado')
        return

    original = oq3d.extract(row[1])
    # Reescreve cada malha do original como uma raiz, já em coordenadas de
    # mundo (os transforms do original foram aplicados na leitura).
    entradas = [([tuple(float(c) for c in v) for v in verts],
                 [tuple(int(i) for i in t) for t in tris],
                 tuple(rgba), None)
                for verts, tris, rgba in original]
    blob = w.escrever(entradas)
    relido = oq3d.extract(blob)
    comparar_malhas([(v, t, c) for v, t, c, _ in entradas], relido,
                    f'{row[0]!r} reescrita')
    print(f'       original {len(row[1])} bytes → reescrito {len(blob)} bytes '
          f'({len(blob) / len(row[1]):.2f}×, sem WIREFRAME nem instâncias '
          f'por referência)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aq', default=os.path.join(
        RAIZ, 'input', 'Amanco', 'PVC Esgoto SN, SR e Silentium',
        'pecas_Amanco_Esgoto_SN_SR_Silentium.aq'))
    ap.add_argument('--sid', type=int, default=169)
    args = ap.parse_args()

    print('oq3d_roundtrip — escritor OQ3D contra o leitor do projeto')
    print(f'leitor: {oq3d.__file__}')
    caso_simples()
    caso_rotacao()
    caso_varias()
    caso_bbox()
    if os.path.exists(args.aq):
        caso_real(args.aq, args.sid)
    else:
        print(f'\n6. pulado — {args.aq} não existe')

    print()
    if falhas:
        print(f'{len(falhas)} FALHA(S): ' + ', '.join(falhas))
        return 1
    print('todos os casos passaram')
    return 0


if __name__ == '__main__':
    sys.exit(main())
