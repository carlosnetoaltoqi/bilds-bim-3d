#!/usr/bin/env python3
"""
geo_to_aq.py — embala uma geometria do viewer (`{ pos, col, idx }` em metros,
Y-up, ou uma lista de `partes`) num `.aq` mínimo do AltoQi Builder: uma
biblioteca com UMA peça, sua simbologia 3D em OQ3D e as propriedades
personalizadas que vierem junto.

É o inverso de `read_aq.py` + `oq3d.py`, para geometria que NÃO nasceu no
AltoQi — um STEP tesselado pelo `step_to_geo.py`, ou uma peça editada no editor
3D da POC (`www/apps/web/src/components/bim-editor/`). Reaproveita, sem
modificar, o que a engenharia reversa da Akato deixou pronto em
`eng-reversa/tools/`: o schema 607 completo (`dados/schema-aq-607.sql`), o
escritor OQ3D (`oq3d_writer.py`) e o `Gerador` do `gerar_aq.py`, que grava
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

O QUE FICA DE FORA. `ENTRADA_PECA` (bocais e comprimentos equivalentes),
`ITEM` (insumo de orçamento) e simbologia 2D: não há de onde tirar isso de uma
malha. A peça entra como equipamento genérico (`TIPO_APLICACAO_PECA = 2`,
conexão), sem código de diâmetro (sentinela `-DBL_MAX`, como as 700 conexões
da Amanco). A origem fica gravada numa propriedade personalizada "Geometria
3D", como o `eng-reversa` faz com a forma representativa.

Uso:
    python3 www/apps/ingestao/pipeline/geo_to_aq.py entrada.json saida.aq
    python3 www/apps/ingestao/pipeline/geo_to_aq.py entrada.json saida.aq --fabricante Dancor --linha "Bombas" --nome "2831A09"
    (os argumentos de linha de comando sobrepõem `info` do JSON)
"""
import argparse
import json
import os
import sqlite3
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
# raiz do repositório: www/apps/ingestao/pipeline → quatro níveis acima. Enquanto o gerador de
# `.aq` viver em eng-reversa/ (fora do serviço), este é o único módulo do pipeline que sai daqui.
RAIZ = os.path.abspath(os.path.join(AQUI, '..', '..', '..', '..'))
ENG = os.path.join(RAIZ, 'eng-reversa', 'tools')
sys.path.insert(0, ENG)

import gerar_aq       # noqa: E402  Gerador (cp1252), criar_schema, constantes do AltoQi
import oq3d_writer    # noqa: E402  o escritor OQ3D

SCHEMA_SQL = os.path.join(RAIZ, 'eng-reversa', 'dados', 'schema-aq-607.sql')
M_TO_CM = 100.0
COR_PADRAO = (0.533, 0.588, 0.667)


def _rgba(rgb):
    return tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb) + (255,)


def _para_oq3d(pos, idx):
    """metros Y-up → centímetros Z-up: (x, y, z) → (x·100, −z·100, y·100)."""
    verts = [(pos[i] * M_TO_CM, -pos[i + 2] * M_TO_CM, pos[i + 1] * M_TO_CM)
             for i in range(0, len(pos), 3)]
    tris = [(idx[t], idx[t + 1], idx[t + 2]) for t in range(0, len(idx), 3)]
    return verts, tris


def malhas_de_partes(partes):
    """[(verts_cm, tris, rgba, None)] — uma por parte, cor do primeiro vértice."""
    malhas = []
    for p in partes:
        pos, idx, col = p['pos'], p['idx'], p.get('col')
        if not idx:
            continue
        cor = tuple(col[:3]) if col else COR_PADRAO
        verts, tris = _para_oq3d(pos, idx)
        malhas.append((verts, tris, _rgba(cor), None))
    return malhas


def malhas_por_cor(pos, col, idx):
    """Divide uma malha única em malhas de cor uniforme (o OQ3D só tem cor por malha)."""
    if not col:
        verts, tris = _para_oq3d(pos, idx)
        return [(verts, tris, _rgba(COR_PADRAO), None)]
    grupos = {}
    for t in range(0, len(idx), 3):
        a = idx[t]
        chave = (round(col[a * 3], 4), round(col[a * 3 + 1], 4), round(col[a * 3 + 2], 4))
        grupos.setdefault(chave, []).append((idx[t], idx[t + 1], idx[t + 2]))
    malhas = []
    for cor, tris in grupos.items():
        remap, p2, t2 = {}, [], []
        for tri in tris:
            novo = []
            for vi in tri:
                if vi not in remap:
                    remap[vi] = len(p2) // 3
                    p2.extend(pos[vi * 3:vi * 3 + 3])
                novo.append(remap[vi])
            t2.extend(novo)
        verts, tris_cm = _para_oq3d(p2, t2)
        malhas.append((verts, tris_cm, _rgba(cor), None))
    return malhas


def gerar(entrada, saida, info):
    fabricante = info.get('fabricante') or 'Sem fabricante'
    linha = info.get('linha') or 'Peças importadas'
    nome = info.get('nome') or os.path.splitext(os.path.basename(saida))[0]
    descricao = info.get('descricao') or nome
    specs = dict(info.get('specs') or {})
    origem = info.get('origem') or 'geo_to_aq.py'

    partes = entrada.get('partes') or []
    # `step_to_geo.py` também grava `partes`, mas só como metadados (nome, cor,
    # contagem) — sem buffers. Só é lista de malhas se cada parte traz `pos`.
    if partes and all('pos' in p for p in partes):
        malhas = malhas_de_partes(partes)
    else:
        malhas = malhas_por_cor(entrada['pos'], entrada.get('col') or [], entrada['idx'])
    if not malhas:
        raise SystemExit('nenhuma malha para gravar')

    con = gerar_aq.criar_schema(saida, SCHEMA_SQL)
    g = gerar_aq.Gerador(con, {})
    g.versao()

    # -- cadastro da peça ------------------------------------------------
    id_classe = g.novo('CLASSE_PECA')
    g.ins('CLASSE_PECA', ID_CLASSE_PECA=id_classe, NOME_CP=f'{fabricante} - {linha}',
          INDICACAO_CP='', CODIGO_ELLO=0, ATIVO=1)
    ifc, tipo_ent, ifc2x3 = gerar_aq.IFC_CONEXAO
    id_grupo = g.novo('GRUPO_PECA')
    g.ins('GRUPO_PECA', ID_GRUPO_PECA=id_grupo, NOME_GP=linha, TIPO_SECAO_GP=0,
          RUGOSIDADE_GP=gerar_aq.RUGOSIDADE_PVC, RUGOSIDADE_EQUIVALENTE=gerar_aq.RUGOSIDADE_EQUIV_PVC,
          TIPO_FWH=gerar_aq.TIPO_FWH_PVC, COEFICIENTE_MANNING=gerar_aq.MANNING_PVC,
          TIPO_MATERIAL=0, PROJETO_APLICACAO=gerar_aq.APLICACAO_AGUA_FRIA, ELEMENTO_APLICACAO=0,
          TIPO_CONFIGURACAO_GP=gerar_aq.SENT_INT, REPRESENTACAO_GP=0, ID_CLASSE_PECA=id_classe,
          CODIGO_ELLO=0, ATIVO=1, ENTIDADE_IFC=ifc, SUBTIPO_IFC=gerar_aq.SUB_LUVA,
          TIPO_ENTIDADE_IFC=tipo_ent, ENTIDADE_IFC_2X3=ifc2x3, SUBTIPO_IFC_2X3=gerar_aq.SUB_LUVA,
          TIPO_ENTIDADE_IFC_2X3=tipo_ent)
    id_peca = g.novo('PECA')
    g.ins('PECA', ID_PECA=id_peca, NOME_PECA=nome, BIBLIOTECA=fabricante, SIMBOLO_SELECIONADO=1,
          DESCRICAO_DADOS=descricao, POSICIONAR_SIMBOLOGIA=0, POSICAO_DADOS=0, POSICIONA_CAMPOS=1,
          DESENHA_SIMBOLOGIA=2, DIAMETRO_PECA=gerar_aq.SENT_REAL, INDICACAO_PLANTA=nome,
          INDICACAO_DETALHE=nome, COMPRIMENTO_PECA=0, ID_GRUPO_PECA=id_grupo,
          TIPO_APLICACAO_PECA=gerar_aq.APL_CONEXAO, CODIGO_ELLO=0, ATIVO=1,
          POSICIONAR_SIMBOLOGIA_3D=0, FORMATO_PECA=-1, OPCAO_RENDERIZACAO_PLANIFICADA=0,
          INCLUIR_REPRESENTACAO3D_PARAMETRICA=0, CONEXAO_VOLUMETRICA=0, INDICE_SIMBOLO3D_SELECIONADO=-1)
    g.ins('DADOS_HIDRAULICOS', ID_DADOS_HIDRAULICOS=g.novo('DADOS_HIDRAULICOS'),
          TIPO_CURVA=gerar_aq.TIPO_CURVA_CONEXAO, ID_PECA=id_peca)

    # -- insumo de orçamento: é em ITEM.CODIGO_ITEM que o AltoQi guarda o código
    #    comercial (o 14808 da Amanco, o 21011 da Akato) ------------------------
    codigo = str(info.get('codigo') or nome)
    id_ci = g.novo('CLASSE_ITEM')
    g.ins('CLASSE_ITEM', ID_CLASSE_ITEM=id_ci, NOME_CI=f'{fabricante} - {linha}', CODIGO_ELLO=0, ATIVO=1)
    id_gi = g.novo('GRUPO_ITEM')
    g.ins('GRUPO_ITEM', ID_GRUPO_ITEM=id_gi, ID_CLASSE_ITEM=id_ci, NOME_GI=linha,
          UNIDADE_GI=gerar_aq.UNIDADE_PECA, CODIGO_ELLO=0, ATIVO=1)
    id_item = g.novo('ITEM')
    g.ins('ITEM', ID_ITEM=id_item, ID_GRUPO_ITEM=id_gi, NOME_ITEM=descricao, CODIGO_ELLO=0, ATIVO=1,
          FABRICANTE=fabricante, TABELA_REFERENCIA=origem, CATEGORIA='Insumo', CODIGO_ITEM=codigo, OBSERVACAO='')
    g.ins('ITEM_ASSOCIADO', ID_ITEM_ASSOCIADO=g.novo('ITEM_ASSOCIADO'), QUANTIDADE_IA=1.0,
          MEDICAO_PECA=gerar_aq.MEDICAO_CONEXAO, ID_PECA=id_peca, ID_ITEM=id_item)

    # -- geometria: OQ3D, uma raiz por malha ------------------------------
    id_cs = g.novo('CLASSE_SIMBOLOGIA_3D')
    g.ins('CLASSE_SIMBOLOGIA_3D', ID_CLASSE_SIMBOLOGIA_3D=id_cs,
          NOME_CLASSE=f'{fabricante} - {linha}', CODIGO_ELLO=0, ATIVO=1)
    id_gs = g.novo('GRUPO_SIMBOLOGIA_3D')
    g.ins('GRUPO_SIMBOLOGIA_3D', ID_GRUPO_SIMBOLOGIA_3D=id_gs, NOME_GRUPO=linha,
          CODIGO_ELLO=0, ATIVO=1, ID_CLASSE=id_cs)
    blob = oq3d_writer.escrever(malhas)
    id_simb = g.novo('SIMBOLOGIA_3D')
    g.ins('SIMBOLOGIA_3D', ID_SIMBOLOGIA_3D=id_simb, ID_GRUPO_SIMBOLOGIA_3D=id_gs, NOME=nome,
          CODIGO_ELLO=0, ATIVO=1, SIMBOLOGIA_3D=sqlite3.Binary(blob), REFERENCIA_CORTE=0,
          EMBUTIMENTO=1.0, USA_CORES_PECA=1, DESLOCAMENTO_X=0.0, DESLOCAMENTO_Y=0.0,
          DESLOCAMENTO_Z=0.0, ANGULO_PLANO_XY=0.0, ANGULO_PLANO_XZ=0.0, ANGULO_PLANO_YZ=0.0)
    g.ins('PECA_SIMBOLOGIA_3D', ID_PECA_SIMBOLOGIA_3D=g.novo('PECA_SIMBOLOGIA_3D'),
          ID_PECA=id_peca, ID_SIMBOLOGIA_3D=id_simb)

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
        'malhas': len(malhas),
        'triangulos': sum(len(t) for _, t, _, _ in malhas),
        'oq3d_bytes': len(blob),
        'bytes': os.path.getsize(saida),
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
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    with open(args.entrada, encoding='utf-8') as f:
        entrada = json.load(f)
    info = dict(entrada.get('info') or {})
    for k in ('fabricante', 'linha', 'nome', 'descricao', 'codigo'):
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
    print(json.dumps(r))


if __name__ == '__main__':
    main()
