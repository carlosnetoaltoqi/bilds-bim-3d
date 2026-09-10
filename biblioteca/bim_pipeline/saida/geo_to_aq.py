#!/usr/bin/env python3
"""
geo_to_aq.py — embala uma geometria do viewer (`{ pos, col, idx }` em metros,
Y-up, ou uma lista de `partes`) num `.aq` mínimo do AltoQi Builder: uma
biblioteca com UMA peça, sua simbologia 3D em OQ3D e as propriedades
personalizadas que vierem junto.

É o inverso de `read_aq.py` + `oq3d.py`, para geometria que NÃO nasceu no
AltoQi — um STEP tesselado pelo `step_to_geo.py`, ou uma peça editada no editor
3D da POC (`web/src/components/bim-editor/`). Reaproveita, sem
modificar, o que o estudo de escrita de `.aq` deixou pronto em
este diretório: o schema 607 completo (`schema-aq-607.sql`), o
escritor OQ3D (`oq3d_writer.py`) e o `Gerador` do `aq_writer.py`, que grava
texto em cp1252 via `CAST(? AS TEXT)` — a armadilha que corrompe nomes em
silêncio se for esquecida.

ENTRADA (JSON):

    {
      "info": { "fabricante": "…", "linha": "…", "nome": "…", "descricao": "…",
                "codigo": "…", "specs": { "chave": "valor" } },
      "pos": [...], "col": [...], "idx": [...]            # uma malha, OU
      "partes": [ { "nome": "…", "pos": [...], "col": [...] | null, "idx": [...] } ]
    }

Cada parte vira um objeto-raiz do OQ3D (uma `TQi3DTriangleMesh` com cor
uniforme). Sem `partes`, a malha única é dividida por cor: o OQ3D só tem cor
por malha, e é assim que o `oq3d.py` a lê de volta.

UNIDADES E EIXOS. O OQ3D é centímetros, Z-up. Do viewer (metros, Y-up):
`oq3d = (x·100, −z·100, y·100)` — a conversão documentada no CLAUDE.md,
seção "Unidades" do OQ3D.

O QUE FICA DE FORA. `WIREFRAME` (arestas para planta/corte) e a simbologia 2D: o Builder
gera o primeiro sozinho, desde que a peça tenha pontos de ligação 3D. A `IMAGEM` **entra**:
é o BMP de preview sem o qual o Builder não desenha nada (experimento em
`bim_pipeline.aq.imagem_aq`). As `ENTRADA_3D`/`ENTRADA_PECA` também entram, quando a malha
tem bocal reconhecível — ponta de tubo ou face de flange (`bim_pipeline.aq.entradas_aq`);
malha sem bocal sai sem entrada, e aí a peça não encaixa em tubulação. (`ITEM`/`ITEM_ASSOCIADO` entram, com o código
comercial de `info.codigo` ou o nome da peça.) A peça entra como equipamento genérico (`TIPO_APLICACAO_PECA = 2`,
conexão), sem código de diâmetro (sentinela `-DBL_MAX`, como as 700 conexões
de uma biblioteca real). A origem fica gravada numa propriedade personalizada "Geometria
3D", como se faz com uma forma representativa (`docs/conhecimento/formas-representativas.md`).

Uso:
    python3 -m bim_pipeline.cli.gerar_aq entrada.json saida.aq
    python3 -m bim_pipeline.cli.gerar_aq entrada.json saida.aq --fabricante "Fabricante" --linha "Bombas" --nome "B-100"
    (os argumentos de linha de comando sobrepõem `info` do JSON)
"""
import argparse
import json
import os
import sqlite3
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

from bim_pipeline.aq import aq_writer
from bim_pipeline.aq import cadastro
from bim_pipeline.aq import entradas_aq
from bim_pipeline.aq import imagem_aq
from bim_pipeline.aq import oq3d_writer

from bim_pipeline.geometria.malhas import GeometriaInvalida, malhas_de_partes, malhas_por_cor

SCHEMA_SQL = aq_writer.SCHEMA_SQL


def gerar(entrada, saida, info):
    fabricante = info.get('fabricante') or 'Sem fabricante'
    linha = info.get('linha') or 'Peças importadas'
    nome = info.get('nome') or os.path.splitext(os.path.basename(saida))[0]
    descricao = info.get('descricao') or nome
    specs = dict(info.get('specs') or {})
    origem = info.get('origem') or 'geo_to_aq.py'
    # A disciplina é obrigatória e vem de quem importa (ADR-024): sem ela a peça entrava
    # como hidráulica calada, que é como uma válvula de HVAC virou "conexão de água fria".
    disciplina = info.get('disciplina')
    if not disciplina:
        raise SystemExit(
            'falta a disciplina da peça (ADR-024). Passe --disciplina com uma de: '
            + ', '.join(sorted(cadastro.DISCIPLINAS)))
    cadastro.mascara_da_disciplina(disciplina)
    diag = cadastro.Diagnostico()
    serie = cadastro.serie_do_titulo(linha, fabricante, nome)

    partes = entrada.get('partes') or []
    # `step_to_geo.py` também grava `partes`, mas só como metadados (nome, cor,
    # contagem) — sem buffers. Só é lista de malhas se cada parte traz `pos`.
    if partes and all('pos' in p for p in partes):
        malhas = malhas_de_partes(partes)
    else:
        try:
            malhas = malhas_por_cor(entrada, onde='entrada')
        except GeometriaInvalida as e:
            raise SystemExit(str(e))
    if not malhas:
        raise SystemExit('nenhuma malha para gravar')

    con = aq_writer.criar_schema(saida, SCHEMA_SQL)
    g = aq_writer.EscritorAq(con)
    g.versao()

    # -- cadastro da peça ------------------------------------------------
    id_classe = g.novo('CLASSE_PECA')
    g.ins('CLASSE_PECA', ID_CLASSE_PECA=id_classe, NOME_CP=f'{fabricante} - {linha}',
          INDICACAO_CP='', CODIGO_ELLO=0, ATIVO=1)
    id_grupo = g.novo('GRUPO_PECA')
    campos_grupo, aplicacao = cadastro.linha_grupo(
        id_grupo=id_grupo, nome=linha, disciplina=disciplina, id_classe=id_classe,
        entidade_ifc=info.get('entidadeIfc'), diag=diag)
    g.ins('GRUPO_PECA', **campos_grupo)
    id_peca = g.novo('PECA')
    campos_peca = cadastro.linha_peca(
        id_peca=id_peca, nome=nome, id_grupo=id_grupo, aplicacao=aplicacao,
        fabricante=fabricante, descricao=descricao, comprimento=0)
    campos_peca.update(INDICACAO_PLANTA=nome, INDICACAO_DETALHE=nome)
    g.ins('PECA', **campos_peca)
    g.ins('DADOS_HIDRAULICOS', ID_DADOS_HIDRAULICOS=g.novo('DADOS_HIDRAULICOS'),
          TIPO_CURVA=aq_writer.TIPO_CURVA_CONEXAO, ID_PECA=id_peca)

    # -- insumo de orçamento: é em ITEM.CODIGO_ITEM que o AltoQi guarda o código
    #    comercial (o código de catálogo do fabricante) --------------------------
    codigo = str(info.get('codigo') or nome)
    id_ci = g.novo('CLASSE_ITEM')
    g.ins('CLASSE_ITEM', ID_CLASSE_ITEM=id_ci, NOME_CI=f'{fabricante} - {linha}', CODIGO_ELLO=0, ATIVO=1)
    id_gi = g.novo('GRUPO_ITEM')
    g.ins('GRUPO_ITEM', ID_GRUPO_ITEM=id_gi, ID_CLASSE_ITEM=id_ci, NOME_GI=linha,
          UNIDADE_GI=aq_writer.UNIDADE_PECA, CODIGO_ELLO=0, ATIVO=1)
    id_item = g.novo('ITEM')
    g.ins('ITEM', ID_ITEM=id_item, ID_GRUPO_ITEM=id_gi, NOME_ITEM=descricao, CODIGO_ELLO=0, ATIVO=1,
          FABRICANTE=fabricante, TABELA_REFERENCIA=origem, CATEGORIA='Insumo', CODIGO_ITEM=codigo, OBSERVACAO='')
    g.ins('ITEM_ASSOCIADO', ID_ITEM_ASSOCIADO=g.novo('ITEM_ASSOCIADO'), QUANTIDADE_IA=1.0,
          MEDICAO_PECA=aq_writer.MEDICAO_CONEXAO, ID_PECA=id_peca, ID_ITEM=id_item)

    # -- geometria: OQ3D, uma raiz por malha ------------------------------
    id_cs = g.novo('CLASSE_SIMBOLOGIA_3D')
    g.ins('CLASSE_SIMBOLOGIA_3D', ID_CLASSE_SIMBOLOGIA_3D=id_cs,
          NOME_CLASSE=f'{fabricante} - {linha}', CODIGO_ELLO=0, ATIVO=1)
    id_gs = g.novo('GRUPO_SIMBOLOGIA_3D')
    g.ins('GRUPO_SIMBOLOGIA_3D', ID_GRUPO_SIMBOLOGIA_3D=id_gs, NOME_GRUPO=linha,
          CODIGO_ELLO=0, ATIVO=1, ID_CLASSE=id_cs)
    blob = oq3d_writer.escrever(malhas)
    # o BMP de preview NÃO é enfeite: sem ele o Builder não desenha a peça (ver imagem_aq)
    imagem = imagem_aq.render(malhas)
    id_simb = g.novo('SIMBOLOGIA_3D')
    g.ins('SIMBOLOGIA_3D', ID_SIMBOLOGIA_3D=id_simb, ID_GRUPO_SIMBOLOGIA_3D=id_gs, NOME=nome,
          CODIGO_ELLO=0, ATIVO=1, SIMBOLOGIA_3D=sqlite3.Binary(blob),
          IMAGEM=sqlite3.Binary(imagem) if imagem else None, REFERENCIA_CORTE=0,
          EMBUTIMENTO=1.0, USA_CORES_PECA=1, DESLOCAMENTO_X=0.0, DESLOCAMENTO_Y=0.0,
          DESLOCAMENTO_Z=0.0, ANGULO_PLANO_XY=0.0, ANGULO_PLANO_XZ=0.0, ANGULO_PLANO_YZ=0.0)
    g.ins('PECA_SIMBOLOGIA_3D', ID_PECA_SIMBOLOGIA_3D=g.novo('PECA_SIMBOLOGIA_3D'),
          ID_PECA=id_peca, ID_SIMBOLOGIA_3D=id_simb)

    # -- pontos de ligação: sem eles a peça não encaixa em tubulação e o Builder não
    #    gera o wireframe de planta/corte ---------------------------------
    entradas = entradas_aq.derivar(malhas, serie=serie, diag=diag, onde=nome)
    if not entradas_aq.plausivel(entradas):
        # malha de projeto inteiro, não de peça: dezenas de pontas de tubo que não são
        # ponto de ligação de nada. Melhor sem entrada nenhuma que com 107 inventadas.
        print(f'  {len(entradas)} bocais na malha — fora do que uma peça tem; '
              f'entradas não gravadas', file=sys.stderr)
        entradas = []
    entradas_aq.gravar(g, entradas, id_simbologia=id_simb, ids_peca=(id_peca,))

    # -- propriedades personalizadas --------------------------------------
    id_gp = g.novo('GRUPO_PROPRIEDADE_PERSONALIZADA')
    g.ins('GRUPO_PROPRIEDADE_PERSONALIZADA', ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_gp,
          NOME=f'{fabricante}: {linha}')
    specs['Geometria 3D'] = f'malha importada — {origem}; {len(malhas)} malha(s), ' \
                            f'{sum(len(t) for _, t, _, _ in malhas)} triângulos'
    if info.get('codigo'):
        specs.setdefault('Código', str(info['codigo']))
    for chave, valor in specs.items():
        if valor is None or str(valor).strip() == '':
            continue
        id_prop = g.novo('PROPRIEDADE_PERSONALIZADA')
        g.ins('PROPRIEDADE_PERSONALIZADA', ID_PROPRIEDADE_PERSONALIZADA=id_prop,
              ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_gp, NOME=str(chave), TIPO_VALOR=0)
        g.ins('VALOR_PROPRIEDADE_PERSONALIZADA',
              ID_VALOR_PROPRIEDADE_PERSONALIZADA=g.novo('VALOR_PROPRIEDADE_PERSONALIZADA'),
              ID_PROPRIEDADE_PERSONALIZADA=id_prop, ID_PECA=id_peca, VALOR=str(valor))

    con.commit()
    con.close()
    return {
        'peca': nome, 'fabricante': fabricante, 'linha': linha,
        'malhas': len(malhas), 'entradas': len(entradas),
        'triangulos': sum(len(t) for _, t, _, _ in malhas),
        'oq3d_bytes': len(blob),
        'bytes': os.path.getsize(saida),
        'disciplina': disciplina,
        'avisos': diag.linhas(),
        **diag.resumo(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('entrada', help='JSON com pos/col/idx ou partes, e opcionalmente info')
    ap.add_argument('saida', help='caminho do .aq a gravar (sobrescreve)')
    ap.add_argument('--fabricante')
    ap.add_argument('--linha')
    ap.add_argument('--nome')
    ap.add_argument('--descricao')
    ap.add_argument('--codigo')
    ap.add_argument('--disciplina', choices=sorted(cadastro.DISCIPLINAS),
                    help='disciplina da peça (ADR-024); obrigatória se não vier no info do JSON')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    with open(args.entrada, encoding='utf-8') as f:
        entrada = json.load(f)
    info = dict(entrada.get('info') or {})
    for k in ('fabricante', 'linha', 'nome', 'descricao', 'codigo', 'disciplina'):
        v = getattr(args, k)
        if v:
            info[k] = v
    if not info.get('origem') and entrada.get('fonte'):
        info['origem'] = f"STEP {entrada['fonte']}"

    r = gerar(entrada, args.saida, info)
    if not args.quiet:
        print(f"{args.saida}: peça '{r['peca']}' ({r['fabricante']} / {r['linha']}), "
              f"{r['malhas']} malha(s), {r['triangulos']:,} triângulos, "
              f"OQ3D {r['oq3d_bytes'] / 1024:.0f} KB, arquivo {r['bytes'] / 1024:.0f} KB".replace(',', '.'))
        for aviso in r['avisos']:
            print(f'  {aviso}', file=sys.stderr)
    print(json.dumps(r))


if __name__ == '__main__':
    main()
