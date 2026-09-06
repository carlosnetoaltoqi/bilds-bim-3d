#!/usr/bin/env python3
"""
validar_aq.py — valida um `.aq` gerado usando o LEITOR DO PRÓPRIO PROJETO.

A prova de que a engenharia reversa fechou não é o arquivo abrir no SQLite: é
o `www/apps/ingestao/pipeline/read_aq.py` e o `www/apps/ingestao/pipeline/oq3d.py` do bilds-bim-3d — escritos para
ler bibliotecas do AltoQi, validados em 12 bibliotecas e 6 versões de schema —
lerem o arquivo gerado sem saber que ele não veio do AltoQi.

Os dois módulos são importados sem modificação nenhuma. O que se confere:

1. `open_aq` abre e a versão do schema está declarada
2. integridade do SQLite e das chaves estrangeiras
3. `extract` devolve grupos, peças, propriedades
4. `peek_metadata` infere fabricante e título — a cascata que alimenta o
   cabeçalho da página publicada, e que **não pode** sair vazia nem em forma
   de slug
5. `build_product_map` monta o mapa que o `build.py` consome
6. `extract_simbologias` lê as geometrias, e o `oq3d.py` parseia cada blob,
   confere unidades e bounding box
7. o texto acentuado está em cp1252, não em UTF-8 — o erro de escrita mais
   perigoso, porque não levanta exceção em lugar nenhum
8. o código comercial chegou a `ITEM.CODIGO_ITEM`, e nenhum texto tem byte de
   controle

Uso:
    python3 validar_aq.py <arquivo.aq>
"""
import os
import sqlite3
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))

from bim_pipeline.aq import oq3d        # noqa: E402   leitor do projeto, intocado
from bim_pipeline.aq import read_aq     # noqa: E402   leitor do projeto, intocado

falhas = []


def checar(nome, ok, detalhe=''):
    print(f"  [{'ok  ' if ok else 'FALHA'}] {nome}"
          + (f' — {detalhe}' if detalhe else ''))
    if not ok:
        falhas.append(nome)


def integridade(caminho):
    print('\n2. integridade do banco')
    con = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    checar('integrity_check',
           con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    con.execute('PRAGMA foreign_keys = ON')
    violacoes = con.execute('PRAGMA foreign_key_check').fetchall()
    checar('foreign_key_check', not violacoes,
           f'{len(violacoes)} violações' if violacoes
           else 'nenhuma chave órfã')
    if violacoes:
        for v in violacoes[:5]:
            print('        ', v)
    con.close()


def encoding_cp1252(caminho):
    """
    O texto acentuado está em cp1252, e não em UTF-8?

    Esta é a checagem que pega o erro mais perigoso de um escritor de `.aq`.
    O `.aq` declara `PRAGMA encoding = UTF-8` mas o AltoQi grava bytes cp1252,
    e o `read_aq.py` decodifica com cp1252. Um arquivo gravado em UTF-8 abre
    normalmente, passa no `integrity_check`, não levanta exceção em lugar
    nenhum — e chega ao nome do produto como `SoldÃ¡vel`.
    """
    print('\n7. codificação do texto acentuado')
    con = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    con.text_factory = bytes
    acentuados = [v for (v,) in con.execute(
        'SELECT NOME_GP FROM GRUPO_PECA UNION ALL '
        'SELECT NOME_CP FROM CLASSE_PECA UNION ALL '
        'SELECT VALOR FROM VALOR_PROPRIEDADE_PERSONALIZADA')
        if v and any(b > 0x7F for b in v)]
    con.close()

    if not acentuados:
        checar('há texto acentuado para conferir', False)
        return

    # Em cp1252 um acento é UM byte alto isolado; em UTF-8 são dois bytes, o
    # primeiro na faixa 0xC0–0xDF. `Soldável` é b'Sold\xe1vel' em cp1252 e
    # b'Sold\xc3\xa1vel' em UTF-8.
    como_utf8 = 0
    for v in acentuados:
        try:
            v.decode('utf-8')
            como_utf8 += 1
        except UnicodeDecodeError:
            pass
    checar('bytes altos NÃO são UTF-8 válido (logo, são cp1252)',
           como_utf8 == 0,
           f'{len(acentuados)} textos acentuados, {como_utf8} em UTF-8')

    todos_cp1252 = all(_decodifica_cp1252(v) for v in acentuados)
    checar('todos decodificam em cp1252', todos_cp1252)
    exemplo = acentuados[0]
    print(f'         ex.: {exemplo!r} → '
          f'{read_aq._decode_texto(exemplo)!r}')


def _decodifica_cp1252(b):
    try:
        b.decode('cp1252')
        return True
    except UnicodeDecodeError:
        return False


def texto_limpo(caminho):
    print('\n8. limpeza do texto e código comercial')
    con = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    con.text_factory = read_aq._decode_texto
    sujos = []
    for tabela, coluna in [('PECA', 'NOME_PECA'), ('GRUPO_PECA', 'NOME_GP'),
                           ('CLASSE_PECA', 'NOME_CP'), ('ITEM', 'NOME_ITEM'),
                           ('VALOR_PROPRIEDADE_PERSONALIZADA', 'VALOR')]:
        for (v,) in con.execute(f'SELECT "{coluna}" FROM "{tabela}"'):
            if v and any(ord(c) < 32 and c not in '\n\t' for c in v):
                sujos.append((tabela, v))
    checar('nenhum byte de controle nos textos', not sujos,
           f'{len(sujos)} suspeitos' if sujos else
           'sintoma de cp1252 lido como latin-1 ausente')

    codigos = con.execute(
        'SELECT COUNT(*), COUNT(DISTINCT CODIGO_ITEM) FROM ITEM '
        "WHERE CODIGO_ITEM <> ''").fetchone()
    checar('ITEM.CODIGO_ITEM preenchido e único',
           codigos[0] == codigos[1] and codigos[0] > 0,
           f'{codigos[0]} itens, {codigos[1]} códigos distintos')

    amostra = con.execute(
        'SELECT i.CODIGO_ITEM, i.NOME_ITEM, g.NOME_GI '
        'FROM ITEM i JOIN GRUPO_ITEM g ON g.ID_GRUPO_ITEM = i.ID_GRUPO_ITEM '
        'LIMIT 3').fetchall()
    for a in amostra:
        print(f'         {a[0]}  {a[1]!r}  em {a[2]!r}')
    con.close()


def main():
    if len(sys.argv) < 2:
        sys.exit('Uso: validar_aq.py <arquivo.aq>')
    caminho = sys.argv[1]

    print(f'validar_aq — {caminho}')
    print(f'leitores: {read_aq.__file__}')
    print(f'          {oq3d.__file__}')

    print('\n1. abertura pelo open_aq do projeto')
    con, tmp = read_aq.open_aq(caminho)
    ver = con.execute('SELECT VERSAO, TAG_IDIOMA FROM '
                      'VERSAO_BANCO_CADASTRO').fetchone()
    checar('open_aq abriu', True, f'schema {ver[0]}, idioma {ver[1]}')
    classes = read_aq.read_classes(con)
    con.close()
    if tmp:
        import shutil
        shutil.rmtree(tmp)

    integridade(caminho)

    print('\n3. extract')
    dados = read_aq.extract(caminho)
    checar('grupos', len(dados['grupos']) > 0, f"{len(dados['grupos'])}")
    checar('peças', len(dados['pecas']) > 0, f"{len(dados['pecas'])}")
    checar('propriedades', len(dados['propriedades']) > 0,
           f"{len(dados['propriedades'])} valores")
    checar('curvas de bomba ausentes (correto: não é bomba)',
           len(dados['curvas']) == 0, f"{len(dados['curvas'])}")

    print('\n4. cascata de fabricante e título (peek_aq do build.py)')
    # A inferência de fabricante e título é do `build.py`, não do
    # `read_aq.peek_metadata` — este último só devolve as classes crus.
    import build
    hints = build.peek_aq(caminho)
    fab, tit = hints.get('fabricante'), hints.get('titulo')
    checar('fabricante inferido', bool(fab), repr(fab))
    checar('fabricante não é slug',
           bool(fab) and fab == fab.strip() and ' - ' not in fab, repr(fab))
    checar('título inferido', bool(tit), repr(tit))
    checar('título diferente do fabricante',
           bool(tit) and tit.lower() != (fab or '').lower(), repr(tit))
    print(f'         classes de simbologia 3D: {classes}')
    print(f"         linhas: {hints.get('linhas')}")
    print(f"         {hints.get('n_pecas')} peças, "
          f"{hints.get('n_simbologias')} simbologias, "
          f"schema {hints.get('schema')}")

    print('\n5. build_product_map')
    mapa = read_aq.build_product_map(dados)
    total = sum(len(v['pecas']) for v in mapa.values())
    checar('mapa de produtos', total == len(dados['pecas']),
           f'{len(mapa)} grupos, {total} peças')
    exemplo = next(iter(mapa.values()))
    checar('peça do mapa tem specs',
           bool(exemplo['pecas'][0]['specs']),
           f"{len(exemplo['pecas'][0]['specs'])} propriedades em "
           f"{exemplo['pecas'][0]['nome']!r}")

    print('\n6. geometria pelo extract_simbologias + oq3d')
    # extract_simbologias devolve uma TUPLA (simbologias, por_peca).
    simbs, por_peca = read_aq.extract_simbologias(caminho)
    if not simbs:
        print('         nenhuma geometria — esperado sem geometria pedida')
    else:
        ok_blobs = tri_total = 0
        tubos, outras = [], []
        detalhado = len(simbs) <= 20
        for sid, s in sorted(simbs.items()):
            blob = s['blob']
            if blob is None or not oq3d.is_oq3d(blob):
                checar(f"assinatura de {s['nome']!r}", False)
                continue
            st = oq3d.stats(blob)
            tri_total += st['triangulos']
            ok_blobs += 1
            # O grupo diz se é tubo; o nome da peça é só a bitola.
            eh_tubo = 'TUBO' in read_aq._decode_texto(
                s['grupo'].encode('cp1252', 'replace')).upper()
            (tubos if eh_tubo else outras).append(
                (s['nome'], st['bbox_cm']))
            if detalhado:
                print(f"         {s['nome']:>8}  {st['triangulos']:5} "
                      f"triângulos  bbox {st['bbox_cm'][0]:.2f} × "
                      f"{st['bbox_cm'][1]:.2f} × {st['bbox_cm'][2]:.2f} cm  "
                      f"cores {st['cores']}")
        checar('todos os blobs são OQ3D válidos', ok_blobs == len(simbs),
               f'{ok_blobs}/{len(simbs)} blobs, {tri_total} triângulos')
        checar('vínculo peça → simbologia é chave estrangeira',
               len(por_peca) == len(simbs),
               f'{len(por_peca)} peças ligadas a {len(simbs)} simbologias')
        # As duas famílias de tubo do catálogo são de 6 m: 600 cm no eixo Z.
        checar('barras de tubo com 600 cm no eixo Z',
               bool(tubos) and all(abs(b[2] - 600.0) < 0.01 for _, b in tubos),
               f'{len(tubos)} tubos')
        # Conexão nenhuma passa de 1,2 m — o maior é o sifão extensível.
        grandes = [(n, b) for n, b in outras if max(b) > 120]
        checar('nenhuma conexão maior que 120 cm', not grandes,
               '; '.join(f'{n} {b}' for n, b in grandes[:3]) if grandes
               else f'{len(outras)} conexões, maior '
                    f'{max((max(b) for _, b in outras), default=0):.1f} cm')

    encoding_cp1252(caminho)
    texto_limpo(caminho)

    print()
    if falhas:
        print(f'{len(falhas)} FALHA(S): ' + ', '.join(falhas))
        return 1
    print('o .aq gerado é lido pelo pipeline do projeto sem ressalvas')
    return 0


if __name__ == '__main__':
    sys.exit(main())
