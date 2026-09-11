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

A ajuda **guarda páginas abandonadas** de versões antigas ao lado das atuais, com nomes
quase iguais (`Angulo_rotacao.htm` × `Angulo_de_rotacao.htm`) — citar uma delas é citar o
programa de outra época. O índice por isso classifica cada página pelo alcance a partir do
sumário (`contents_data.js`): `toc` (está no sumário), `link` (só chega por link de página
alcançável, típico de janela de propriedades) e `orfa` (não chega de lugar nenhum). A busca
**pula as órfãs** a menos que se peça `--incluir-orfas`, e marca as que não estão no sumário.

Páginas que já se mostraram úteis, todas no sumário: `peca.htm` (as propriedades da peça, e
a tabela Projeto × Aplicações), `entradas_3d.htm`, `representacao_simbologia_3d.htm`,
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


ARQUIVO_SUMARIO = 'contents_data.js'
RX_HTM = re.compile(r"""[\w%.()\-]+\.htm""", re.I)
RX_HREF = re.compile(rb"""href\s*=\s*["']([^"'#?>]+\.htm)""", re.I)   # o HTML é lido em bytes


def alcance(dir_ajuda, paginas):
    """Classifica cada página por alcance: 'toc', 'link' ou 'orfa'.

    O sumário da ajuda (`contents_data.js`) lista as páginas da versão corrente; o resto do
    diretório mistura janelas de propriedades (que só abrem por link) com páginas de versões
    passadas que ninguém mais referencia. Quem não é alcançável a partir do sumário, nem
    direta nem transitivamente, é sucata — e citar sucata como fonte já é errar de versão.

    Sem `contents_data.js` não há como julgar: todas voltam como 'toc' (nada é descartado).
    """
    nomes = {os.path.basename(p) for p in paginas}
    sumario = os.path.join(dir_ajuda, ARQUIVO_SUMARIO)
    try:
        with open(sumario, 'rb') as f:
            bruto = f.read().decode('utf8', 'replace')
    except OSError:
        return {n: 'toc' for n in nomes}
    toc = {m.group(0) for m in RX_HTM.finditer(bruto)} & nomes

    saidas = {}
    for caminho in paginas:
        try:
            with open(caminho, 'rb') as f:
                bruto = f.read()
        except OSError:
            continue
        nome = os.path.basename(caminho)
        saidas[nome] = {os.path.basename(m.group(1).decode('latin-1'))
                        for m in RX_HREF.finditer(bruto)} & nomes

    vistos = set(toc)
    fila = list(toc)
    while fila:
        for alvo in saidas.get(fila.pop(), ()):
            if alvo not in vistos:
                vistos.add(alvo)
                fila.append(alvo)
    return {n: ('toc' if n in toc else 'link' if n in vistos else 'orfa') for n in nomes}


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
    estados = alcance(dir_ajuda, paginas)
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
            nome = os.path.basename(caminho)
            saida.write(json.dumps({'arquivo': nome, 'titulo': titulo, 'trilha': trilha,
                                    'estado': estados.get(nome, 'toc'), 'texto': t},
                                   ensure_ascii=False) + '\n')
            n += 1
            bytes_ += len(t)
    orfas = sum(1 for e in estados.values() if e == 'orfa')
    return n, bytes_, orfas


def buscar(indice, padrao, antes=2, depois=4, limite=20, so_paginas=False, pagina=None,
           incluir_orfas=False):
    """Percorre o JSONL e imprime os trechos que casam. Devolve o número de páginas com acerto.

    Páginas órfãs (inalcançáveis a partir do sumário — ver `alcance`) ficam de fora por
    padrão: são de versões passadas do programa. As que entram por link, não pelo sumário,
    saem marcadas `[link]`, porque valem menos como citação.
    """
    rx = re.compile(padrao, re.I)
    achados = pulados = 0
    with open(indice, encoding='utf8') as f:
        for linha in f:
            d = json.loads(linha)
            if pagina and pagina.lower() not in d['arquivo'].lower():
                continue
            estado = d.get('estado', 'toc')
            if estado == 'orfa' and not incluir_orfas:
                if rx.search(d['texto']):
                    pulados += 1
                continue
            linhas = d['texto'].splitlines()
            hits = [i for i, l in enumerate(linhas) if rx.search(l)]
            if not hits:
                continue
            achados += 1
            marca = '' if estado == 'toc' else f' [{estado}]'
            if so_paginas:
                print(f"{d['arquivo'] + marca:48s} {len(hits):3d}x  {d['trilha'][:70]}")
            else:
                print(f"\n===== {d['arquivo']}{marca} — {d['titulo'][:60]}\n      {d['trilha'][:110]}")
                vistos = set()
                for i in hits:
                    for j in range(max(0, i - antes), min(len(linhas), i + depois + 1)):
                        if j in vistos:
                            continue
                        vistos.add(j)
                        print(('>> ' if rx.search(linhas[j]) else '   ') + linhas[j][:200])
            if achados >= limite:
                break
    if pulados:
        print(f'({pulados} página(s) órfã(s) de versão antiga fora da conta; '
              f'--incluir-orfas para vê-las)', file=sys.stderr)
    return achados


def main(argv=None):
    ap = argparse.ArgumentParser(description='busca na ajuda em HTML do AltoQi Builder')
    ap.add_argument('padrao', nargs='?', help='expressão regular a procurar')
    ap.add_argument('--ajuda', default=None, help='diretório da ajuda (só para indexar)')
    ap.add_argument('--indice', default=PADRAO_INDICE, help=f'JSONL do índice (padrão {PADRAO_INDICE})')
    ap.add_argument('--indexar', action='store_true', help='refaz o índice antes de buscar')
    ap.add_argument('--paginas', action='store_true', help='lista só os arquivos que casam')
    ap.add_argument('--pagina', default=None, help='restringe a páginas cujo nome casa com isto')
    ap.add_argument('--incluir-orfas', action='store_true',
                    help='inclui as páginas inalcançáveis pelo sumário (versões antigas)')
    ap.add_argument('--antes', type=int, default=2)
    ap.add_argument('--depois', type=int, default=4)
    ap.add_argument('--limite', type=int, default=20)
    args = ap.parse_args(argv)

    if args.indexar or not os.path.isfile(args.indice):
        if not args.ajuda:
            print(f'índice ausente em {args.indice}: rode com --ajuda <dir da ajuda> --indexar',
                  file=sys.stderr)
            return 2
        n, b, orfas = indexar(args.ajuda, args.indice)
        print(f'{n} páginas ({orfas} órfãs de versão antiga), {b/1e6:.1f} MB de texto '
              f'→ {args.indice}', file=sys.stderr)

    if not args.padrao:
        return 0
    if buscar(args.indice, args.padrao, args.antes, args.depois, args.limite,
              args.paginas, args.pagina, args.incluir_orfas) == 0:
        print('(nada)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
