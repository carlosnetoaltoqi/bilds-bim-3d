#!/usr/bin/env python3
"""
ajuda_builder.py — busca na ajuda em HTML do AltoQi Builder.

Para que existe: a ajuda do programa é a **única fonte que diz o que um campo do `.aq`
significa**. Medir a distribuição de uma coluna nas bibliotecas nativas responde "que valor
ela costuma ter"; só a ajuda responde "o que ela é" — e a diferença entre as duas perguntas
já custou uma hipótese com correlação perfeita (ADR-022 × ADR-023).

São ~2.500 páginas `.htm` (123 MB com as imagens, ~4 MB só de texto). Ler página a página
não cabe em sessão nenhuma, então esta ferramenta extrai o texto **uma vez** para um índice
JSONL ao lado do diretório de saída e busca por expressão regular sobre ele, imprimindo só
as linhas que casam mais o contexto.

O diretório da ajuda **não é do repositório**: é uma instalação do Builder na máquina de
quem opera (ADR-016 — o caminho concreto fica na memória do agente ou no `--ajuda`).

Uso:
    python3 -m bim_pipeline.cli.ferramentas.ajuda_builder --ajuda <dir> --indexar
    python3 -m bim_pipeline.cli.ferramentas.ajuda_builder "pontos de liga" [--paginas]
                                                          [--antes 2] [--depois 4] [--pagina peca]

O índice fica em `<dir do índice>/ajuda-builder.jsonl` (padrão: `output/`, que é gitignored)
e é reusado enquanto existir; `--indexar` refaz.

Páginas que já se mostraram úteis: `peca.htm` (as propriedades da peça, e a tabela
Projeto × Aplicações), `entradas_3d.htm`, `representacao_simbologia_3d.htm`,
`editar_simbologia_3d.htm`.
"""
import argparse
import html
import json
import os
import re
import sys

PADRAO_INDICE = os.path.join('output', 'ajuda-builder.jsonl')


def texto_de_htm(caminho):
    """HTML da ajuda → texto legível, preservando a quebra de linha dos blocos.

    A ajuda mistura UTF-8 (com BOM) e cp1252 entre páginas, por isso a cascata de
    decodificação: latin-1 nunca falha e fecha a lista.
    """
    with open(caminho, 'rb') as f:
        bruto = f.read()
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            s = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    s = re.sub(r'(?is)<(script|style|head)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|li|h\d)>', '\n', s)
    s = re.sub(r'(?i)</t[dh]>', ' | ', s)          # célula de tabela vira separador
    s = html.unescape(re.sub(r'<[^>]+>', '', s))
    s = re.sub(r'[ \t\xa0]+', ' ', s)
    return '\n'.join(l.strip() for l in s.splitlines() if l.strip())


def indexar(dir_ajuda, destino):
    """Extrai o texto de todo `.htm` de `dir_ajuda` para um JSONL. Devolve (páginas, bytes)."""
    if not os.path.isdir(dir_ajuda):
        raise NotADirectoryError(dir_ajuda)
    paginas = sorted(os.path.join(r, n) for r, _, ns in os.walk(dir_ajuda)
                     for n in ns if n.lower().endswith('.htm'))
    if not paginas:
        raise FileNotFoundError(f'nenhum .htm em {dir_ajuda}')
    pasta = os.path.dirname(destino)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    n = bytes_ = 0
    with open(destino, 'w', encoding='utf8') as saida:
        for caminho in paginas:
            try:
                t = texto_de_htm(caminho)
            except OSError:
                continue
            # A trilha ("Home > Cadastro > Peças > …") é o que situa a página na ajuda; o
            # título é a primeira linha que não é a trilha nem o BOM.
            linhas = [l for l in t.splitlines() if l and l != '﻿']
            trilha = next((l for l in linhas if l.startswith('Home >')), '')
            titulo = next((l for l in linhas if not l.startswith('Home >')), '')
            saida.write(json.dumps({'arquivo': os.path.basename(caminho), 'titulo': titulo,
                                    'trilha': trilha, 'texto': t}, ensure_ascii=False) + '\n')
            n += 1
            bytes_ += len(t)
    return n, bytes_


def buscar(indice, padrao, antes=2, depois=4, limite=20, so_paginas=False, pagina=None):
    """Percorre o JSONL e imprime os trechos que casam. Devolve o número de páginas com acerto."""
    rx = re.compile(padrao, re.I)
    achados = 0
    with open(indice, encoding='utf8') as f:
        for linha in f:
            d = json.loads(linha)
            if pagina and pagina.lower() not in d['arquivo'].lower():
                continue
            linhas = d['texto'].splitlines()
            hits = [i for i, l in enumerate(linhas) if rx.search(l)]
            if not hits:
                continue
            achados += 1
            if so_paginas:
                print(f"{d['arquivo']:48s} {len(hits):3d}x  {d['trilha'][:70]}")
            else:
                print(f"\n===== {d['arquivo']} — {d['titulo'][:60]}\n      {d['trilha'][:110]}")
                vistos = set()
                for i in hits:
                    for j in range(max(0, i - antes), min(len(linhas), i + depois + 1)):
                        if j in vistos:
                            continue
                        vistos.add(j)
                        print(('>> ' if rx.search(linhas[j]) else '   ') + linhas[j][:200])
            if achados >= limite:
                break
    return achados


def main(argv=None):
    ap = argparse.ArgumentParser(description='busca na ajuda em HTML do AltoQi Builder')
    ap.add_argument('padrao', nargs='?', help='expressão regular a procurar')
    ap.add_argument('--ajuda', default=None, help='diretório da ajuda (só para indexar)')
    ap.add_argument('--indice', default=PADRAO_INDICE, help=f'JSONL do índice (padrão {PADRAO_INDICE})')
    ap.add_argument('--indexar', action='store_true', help='refaz o índice antes de buscar')
    ap.add_argument('--paginas', action='store_true', help='lista só os arquivos que casam')
    ap.add_argument('--pagina', default=None, help='restringe a páginas cujo nome casa com isto')
    ap.add_argument('--antes', type=int, default=2)
    ap.add_argument('--depois', type=int, default=4)
    ap.add_argument('--limite', type=int, default=20)
    args = ap.parse_args(argv)

    if args.indexar or not os.path.isfile(args.indice):
        if not args.ajuda:
            print(f'índice ausente em {args.indice}: rode com --ajuda <dir da ajuda> --indexar',
                  file=sys.stderr)
            return 2
        n, b = indexar(args.ajuda, args.indice)
        print(f'{n} páginas, {b/1e6:.1f} MB de texto → {args.indice}', file=sys.stderr)

    if not args.padrao:
        return 0
    if buscar(args.indice, args.padrao, args.antes, args.depois, args.limite,
              args.paginas, args.pagina) == 0:
        print('(nada)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
