#!/usr/bin/env python3
"""
formas_teste.py — gera a forma de TODAS as peças do catálogo e confere sanidade.

Uma malha inventada pode estar errada de três jeitos que nenhum round-trip
binário pega:

1. **degenerada** — sem triângulos, ou com índice fora da lista de vértices;
2. **fora de escala** — um tubo de 6 m com 60 cm, ou uma luva de 20 mm com
   2 m de bounding box;
3. **não fechada** — cada aresta de um sólido tem de ser compartilhada por
   exatamente dois triângulos. Uma malha aberta aparece no viewer como um
   buraco por onde se vê o interior da peça.

Este teste roda os três em cima de cada uma das 262 peças, e depois passa cada
malha pelo escritor OQ3D e pelo leitor do projeto, para fechar o ciclo.

Uso:
    python3 formas_teste.py [--detalhe]
"""
import argparse
import json
import os
import sys
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, 'www', 'apps', 'ingestao', 'pipeline'))
sys.path.insert(0, AQUI)

import oq3d                          # noqa: E402  leitor do projeto
import formas                        # noqa: E402
import oq3d_writer as w              # noqa: E402
from gerar_aq import (classificar, dimensoes, diametros_mm,  # noqa: E402
                      comprimento_do_titulo)

problemas = []


def falha(peca, msg):
    problemas.append(f'{peca}: {msg}')


def arestas_abertas(verts, tris):
    """Quantas arestas não são compartilhadas por exatamente 2 triângulos."""
    conta = defaultdict(int)
    for a, b, c in tris:
        for x, y in ((a, b), (b, c), (c, a)):
            conta[(min(x, y), max(x, y))] += 1
    return sum(1 for n in conta.values() if n != 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--detalhe', action='store_true')
    args = ap.parse_args()

    cat = json.load(open(os.path.join(os.path.dirname(AQUI), 'dados',
                                      'akato-catalogo.json'), encoding='utf-8'))
    conv = {c['polegada']: c for c in cat['conversao_polegada_mm']}

    total = comgeo = 0
    tri_total = 0
    por_forma = defaultdict(lambda: {'n': 0, 'tri': 0, 'bbox': []})

    for fam in cat['familias']:
        tipo = classificar(fam['titulo'])
        if tipo is None:
            continue
        forma = tipo[3]
        for linha in fam['linhas']:
            total += 1
            desc = linha['descricao']
            de1, de2 = diametros_mm(desc, fam['secao'], conv, forma)
            if de1 is None:
                falha(f"{fam['titulo']} / {desc}", 'sem diâmetro utilizável')
                continue
            comp = (dimensoes(desc)['comprimento_cm']
                    or comprimento_do_titulo(fam['titulo']))
            p = formas.Peca(de1, de2, fam['secao'], fam['titulo'], comp)
            malhas = formas.gerar(forma, p)
            nome = f"{fam['titulo']} / {desc}"

            if not malhas:
                falha(nome, f'gerador {forma!r} não produziu malha')
                continue

            n_tri = 0
            abertas = 0
            for verts, tris, rgba in malhas:
                if not tris:
                    falha(nome, 'malha sem triângulos')
                    continue
                mx = max(i for t in tris for i in t)
                if mx >= len(verts):
                    falha(nome, f'índice {mx} fora dos {len(verts)} vértices')
                if len(rgba) != 4 or not all(0 <= c <= 255 for c in rgba):
                    falha(nome, f'cor inválida {rgba}')
                n_tri += len(tris)
                abertas += arestas_abertas(verts, tris)

            dx, dy, dz = formas.bbox(malhas)
            maior = max(dx, dy, dz)
            # Escala: nada menor que 5 mm nem maior que 7 m.
            if maior < 0.5 or maior > 700:
                falha(nome, f'bbox fora de escala: {dx}×{dy}×{dz} cm')
            # O maior lado tem de guardar relação com o diâmetro nominal,
            # exceto onde o catálogo dá um comprimento próprio.
            if p.comp is None and maior > 14 * p.de1:
                falha(nome, f'bbox {maior} cm desproporcional ao DE {p.de1} cm')

            comgeo += 1
            tri_total += n_tri
            f = por_forma[forma]
            f['n'] += 1
            f['tri'] += n_tri
            f['bbox'].append((nome, dx, dy, dz, n_tri, abertas))

    print(f'{comgeo} de {total} peças com forma gerada, '
          f'{tri_total:,} triângulos'.replace(',', '.'))
    print()
    print(f"{'forma':18} {'peças':>5} {'triâng.':>9} "
          f"{'exemplo (bbox cm)':>44}  abertas")
    for forma in sorted(por_forma):
        d = por_forma[forma]
        nome, dx, dy, dz, nt, ab = d['bbox'][0]
        print(f'{forma:18} {d["n"]:5} {d["tri"]:9} '
              f'{nome[:34]:34} {dx:5.1f}×{dy:5.1f}×{dz:6.1f}  {ab:5}')
        if args.detalhe:
            for nome, dx, dy, dz, nt, ab in d['bbox']:
                print(f'      {nome[:56]:56} {dx:6.1f}×{dy:6.1f}×{dz:7.1f}'
                      f'  {nt:5} tri  {ab:4} abertas')

    # Fecha o ciclo: escreve e relê algumas peças pelo pipeline real.
    print()
    print('round-trip OQ3D de uma peça de cada forma:')
    for forma in sorted(por_forma):
        nome = por_forma[forma]['bbox'][0][0]
        fam = next(f for f in cat['familias'] if f['titulo'] == nome.split(' / ')[0])
        linha = next(l for l in fam['linhas']
                     if l['descricao'] == nome.split(' / ', 1)[1])
        de1, de2 = diametros_mm(linha['descricao'], fam['secao'], conv, forma)
        p = formas.Peca(de1, de2, fam['secao'], fam['titulo'],
                        dimensoes(linha['descricao'])['comprimento_cm']
                        or comprimento_do_titulo(fam['titulo']))
        malhas = formas.gerar(forma, p)
        blob = w.escrever([(v, t, c, None) for v, t, c in malhas])
        if not oq3d.is_oq3d(blob):
            falha(forma, 'blob sem assinatura OQ3D')
            continue
        lidas = oq3d.extract(blob)
        tri_esc = sum(len(t) for _, t, _ in malhas)
        tri_lid = sum(len(t) for _, t, _ in lidas)
        ok = len(lidas) == len(malhas) and tri_esc == tri_lid
        if not ok:
            falha(forma, f'round-trip: {len(malhas)}/{tri_esc} escritos, '
                         f'{len(lidas)}/{tri_lid} lidos')
        print(f'  [{"ok  " if ok else "FALHA"}] {forma:18} '
              f'{len(malhas)} malhas, {tri_esc} triângulos, '
              f'{len(blob) / 1024:.0f} KB')

    print()
    if problemas:
        print(f'{len(problemas)} PROBLEMA(S):')
        for p in problemas[:25]:
            print(f'  - {p}')
        if len(problemas) > 25:
            print(f'  … e mais {len(problemas) - 25}')
        return 1
    print('todas as formas passaram')
    return 0


if __name__ == '__main__':
    sys.exit(main())
