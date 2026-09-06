#!/usr/bin/env python3
"""
catalogo_to_aq.py — o catálogo SALVO (o que a tela de edição mostra: produtos com nome, série,
specs, curva, conexões e a geometria em JSON no storage) vira uma biblioteca `.aq` NOVA do
AltoQi Builder, com todas as peças que restaram depois de editar, apagar ou acrescentar.

É o inverso do `catalogo_de_aq.py` e a generalização do `geo_to_aq.py` (uma peça) para N peças:
o `.aq` original não fica no servidor depois do import (A1), então o arquivo é GERADO DO ZERO
com o `aq_writer.py` (schema 607, cp1252, sentinelas, enums) e o `oq3d_writer.py`. Quem chama
é o serviço de ingestão (`GET /exportar/catalogo/:catalogId`), que monta o manifesto, serve o
arquivo como download e o apaga.

ENTRADA (JSON, o "manifesto"):

    {
      "catalogo": { "fabricante": "Amanco", "titulo": "Esgoto SN SR Silentium", "slug": "…",
                    "descricao": "…", "origem": "texto livre gravado em ITEM.TABELA_REFERENCIA" },
      "geo_dir": "/abs/storage",                  # base dos `geo` relativos (opcional)
      "produtos": [
        { "id": "cap-75mm", "nome": "Cap 75mm", "serie": "Cap", "conexoes": "Cap",
          "specs": { "Bolsa": "…" }, "curva": null | [[vazao, altura, potencia, rendimento]…],
          "potencia": null | 3.0, "codigo": "14808"?, "geo": "geo/<importId>/75mm.json" }
      ]
    }

O QUE O ARQUIVO GERADO TEM — e de onde vem cada coisa:

  CLASSE_PECA          uma, "Fabricante - Título"                    (catalogo)
  GRUPO_PECA           uma por `serie`, na ordem em que aparece; códigos IFC e tipo de aplicação
                       por `aq_writer.classificar_grupo(serie)` (189/192 grupos da Amanco);
                       `PROJETO_APLICACAO` por `aplicacao_de(título, séries)`; um grupo com
                       produto de curva Q-H vira bomba (2075)
  PECA                 uma por produto. NOME_PECA é o nome da tela SEM o prefixo da série que o
                       `catalogo.py` acrescenta quando o nome sozinho é ambíguo ('Cap 75mm' →
                       '75mm', como a Amanco grava) — `--manter-prefixo-serie` desliga isso.
                       Colunas como a Amanco grava numa peça com 3D (POSICIONAR_SIMBOLOGIA_3D=3,
                       INDICE_SIMBOLO3D_SELECIONADO=1, dimensões na sentinela -DBL_MAX)
  DADOS_HIDRAULICOS    uma por peça (TIPO_CURVA=2; com curva, aponta para o MODELO_BOMBA)
  MODELO_BOMBA +
  ITEM_CURVA_BOMBA     só para produto com `curva` (pontos [vazão, altura, potência, rendimento])
  CLASSE_ITEM/GRUPO_ITEM/ITEM/ITEM_ASSOCIADO
                       o insumo de orçamento de cada peça; `ITEM.CODIGO_ITEM` = `codigo`,
                       senão a spec "Código", senão o `id` (slug) do produto — o código comercial
                       original NÃO sobrevive ao import (o catálogo não o guarda)
  CLASSE_SIMBOLOGIA_3D uma, "Fabricante - Título" (é de onde o `read_aq.peek_metadata` tira o
                       fabricante ao reimportar); GRUPO_SIMBOLOGIA_3D por série
  SIMBOLOGIA_3D        UMA POR ARQUIVO DE GEOMETRIA DISTINTO — produtos que compartilham o
                       `geo` (o pipeline grava uma geometria por simbologia) compartilham a
                       simbologia também, via PECA_SIMBOLOGIA_3D, como no `.aq` de origem.
                       Geometria editada (copy-on-write) vira simbologia própria. O blob OQ3D
                       tem uma raiz por cor (o OQ3D só tem cor por malha): metros Y-up →
                       centímetros Z-up, `(x·100, −z·100, y·100)`
  PROPRIEDADE_PERSONALIZADA
                       UMA POR CHAVE DE SPEC distinta (12 na Amanco), num grupo "Fabricante:
                       Título"; VALOR_PROPRIEDADE_PERSONALIZADA por (produto, chave) não vazia

O QUE FICA DE FORA, porque o catálogo não tem de onde tirar: as peças sem simbologia 3D do
`.aq` original (tubos e kits — 312 das 1.168 da Amanco), `ENTRADA_PECA`/`ENTRADA_3D` (bocais e
conectividade), simbologia 2D, `IMAGEM`/`WIREFRAME`, os códigos comerciais originais.

ERROS — tudo acusa, nada é engolido: geometria ausente no storage, JSON de geometria inválido,
caractere fora do cp1252 num nome ou spec (o `.aq` não o representa), chave estrangeira órfã
(`PRAGMA foreign_key_check` no fim). Em qualquer falha o `.aq` parcial é apagado e a saída é 1.

SAÍDA: progresso no stderr (uma linha a cada 50 geometrias) e, no stdout, a última linha é um
JSON com o resumo: `{pecas, grupos, simbologias, triangulos, propriedades, valores, curvas,
bytes, segundos}`.

Uso:
    python3 -m bim_pipeline.cli.catalogo_para_aq manifesto.json saida.aq [--quiet] [--manter-prefixo-serie]
"""
import argparse
import contextlib
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))

from bim_pipeline.aq import aq_writer
from bim_pipeline.aq import oq3d_writer

from bim_pipeline.geometria.malhas import GeometriaInvalida, malhas_por_cor

RE_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


class ExportacaoError(SystemExit):
    """Falha que o operador precisa ler — sai com 1 e a mensagem no stderr."""

    def __init__(self, mensagem):
        super().__init__(f'catalogo_to_aq: {mensagem}')


def avisar(msg):
    print(msg, file=sys.stderr, flush=True)


# ─── Geometria ────────────────────────────────────────────────────────────────

def malhas_de_geometria(geo, onde='geometria'):
    """`{pos, col, idx}` do viewer → malhas por cor em cm Z-up (`geometria.malhas`); erro vira `ExportacaoError`."""
    try:
        return malhas_por_cor(geo, onde)
    except GeometriaInvalida as e:
        raise ExportacaoError(str(e))


def carregar_geometria(caminho, onde):
    if not os.path.isfile(caminho):
        raise ExportacaoError(f'{onde}: geometria ausente no storage — {caminho}')
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ExportacaoError(f'{onde}: não li a geometria {caminho} ({e})')


# ─── Nomes ────────────────────────────────────────────────────────────────────

def nome_da_peca(nome, serie, manter_prefixo=False):
    """
    Desfaz o prefixo de série que o `catalogo.py` acrescenta ao nome exibido quando o nome da
    peça sozinho é curto ou se repete entre grupos ('50mm' aparece em Cap, Luva, Joelho…):
    'Cap 50mm' com série 'Cap' volta a '50mm', que é como a Amanco grava `NOME_PECA`.
    Se o que sobra é vazio, ou `manter_prefixo`, fica o nome da tela.
    """
    n = (nome or '').strip()
    s = (serie or '').strip()
    if not manter_prefixo and s and n.lower().startswith(s.lower() + ' '):
        resto = n[len(s):].strip()
        if resto:
            return resto
    return n or s or 'Peça'


def nome_da_simbologia(caminho_geo, nome_peca):
    """Stem do arquivo de geometria ('75mm', 'cap-75mm'); cópia copy-on-write (uuid) usa o nome da peça."""
    stem = os.path.splitext(os.path.basename(caminho_geo))[0]
    return nome_peca if RE_UUID.match(stem) else stem


def codigo_do_produto(p):
    specs = p.get('specs') or {}
    for cand in (p.get('codigo'), specs.get('Código'), specs.get('Codigo'), specs.get('Código comercial'), p.get('id')):
        if cand is not None and str(cand).strip():
            return str(cand).strip()
    return nome_da_peca(p.get('nome'), p.get('serie'))


# ─── O gerador ────────────────────────────────────────────────────────────────

def gerar(manifesto, saida, manter_prefixo=False, progresso=avisar):
    """Grava `saida` e devolve o resumo. `progresso(linha)` recebe o andamento (None = silencioso)."""
    t0 = time.time()
    silencioso = progresso is None
    progresso = progresso or (lambda _m: None)
    cat = manifesto.get('catalogo') or {}
    produtos = manifesto.get('produtos') or []
    if not produtos:
        raise ExportacaoError('catálogo sem produtos — nada a exportar')
    fabricante = (cat.get('fabricante') or '').strip() or 'Sem fabricante'
    titulo = (cat.get('titulo') or '').strip() or 'Catálogo'
    origem = (cat.get('origem') or '').strip() or 'bilds-bim-3d catalogo_to_aq.py'
    base_geo = manifesto.get('geo_dir') or ''

    def caminho_geo(p):
        g = p.get('geo') or ''
        if not g:
            raise ExportacaoError(f"produto {p.get('nome')!r}: sem geometria ('geo' vazio)")
        return g if os.path.isabs(g) else os.path.join(base_geo, g)

    series = []
    for p in produtos:
        s = (p.get('serie') or '').strip() or 'Outros'
        if s not in series:
            series.append(s)
    aplicacao = aq_writer.aplicacao_de(titulo, cat.get('descricao'), *series)
    series_com_curva = {(p.get('serie') or '').strip() or 'Outros' for p in produtos if p.get('curva')}

    # `criar_schema` imprime no stdout; o stdout deste script é o resumo JSON
    with open(os.devnull, 'w') as nulo, contextlib.redirect_stdout(nulo if silencioso else sys.stderr):
        con = aq_writer.criar_schema(saida)
    g = aq_writer.EscritorAq(con)
    try:
        g.versao()

        # ── classes (uma de cada) ─────────────────────────────────────────────
        nome_classe = f'{fabricante} - {titulo}'
        id_classe = g.novo('CLASSE_PECA')
        g.ins('CLASSE_PECA', ID_CLASSE_PECA=id_classe, NOME_CP=nome_classe, INDICACAO_CP=origem,
              CODIGO_ELLO=0, ATIVO=1)
        id_ci = g.novo('CLASSE_ITEM')
        g.ins('CLASSE_ITEM', ID_CLASSE_ITEM=id_ci, NOME_CI=nome_classe, CODIGO_ELLO=0, ATIVO=1)
        id_cs = g.novo('CLASSE_SIMBOLOGIA_3D')
        g.ins('CLASSE_SIMBOLOGIA_3D', ID_CLASSE_SIMBOLOGIA_3D=id_cs, NOME_CLASSE=nome_classe,
              CODIGO_ELLO=0, ATIVO=1)
        id_gprop = g.novo('GRUPO_PROPRIEDADE_PERSONALIZADA')
        g.ins('GRUPO_PROPRIEDADE_PERSONALIZADA', ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_gprop,
              NOME=f'{fabricante}: {titulo}')

        # ── grupos: um por série ──────────────────────────────────────────────
        grupos = {}
        for serie in series:
            (ifc, tipo_ent, ifc2x3), sub, apl = aq_writer.classificar_grupo(serie)
            if serie in series_com_curva:
                (ifc, tipo_ent, ifc2x3), sub, apl = aq_writer.IFC_BOMBA, aq_writer.SUB_BOMBA, aq_writer.APL_BOMBA
            tubo = apl == aq_writer.APL_TUBO
            id_gp = g.novo('GRUPO_PECA')
            g.ins('GRUPO_PECA', ID_GRUPO_PECA=id_gp, NOME_GP=serie, TIPO_SECAO_GP=0,
                  RUGOSIDADE_GP=aq_writer.RUGOSIDADE_PVC, RUGOSIDADE_EQUIVALENTE=aq_writer.RUGOSIDADE_EQUIV_PVC,
                  TIPO_FWH=aq_writer.TIPO_FWH_PVC, COEFICIENTE_MANNING=aq_writer.MANNING_PVC,
                  TIPO_MATERIAL=0, PROJETO_APLICACAO=aplicacao,
                  ELEMENTO_APLICACAO=1 if tubo else 0, TIPO_CONFIGURACAO_GP=aq_writer.SENT_INT,
                  REPRESENTACAO_GP=2 if tubo else 0, ID_CLASSE_PECA=id_classe, CODIGO_ELLO=0, ATIVO=1,
                  ENTIDADE_IFC=ifc, SUBTIPO_IFC=sub, TIPO_ENTIDADE_IFC=tipo_ent,
                  ENTIDADE_IFC_2X3=ifc2x3, SUBTIPO_IFC_2X3=sub, TIPO_ENTIDADE_IFC_2X3=tipo_ent)
            id_gi = g.novo('GRUPO_ITEM')
            g.ins('GRUPO_ITEM', ID_GRUPO_ITEM=id_gi, ID_CLASSE_ITEM=id_ci, NOME_GI=serie,
                  UNIDADE_GI=aq_writer.UNIDADE_METRO if tubo else aq_writer.UNIDADE_PECA, CODIGO_ELLO=0, ATIVO=1)
            id_gs = g.novo('GRUPO_SIMBOLOGIA_3D')
            g.ins('GRUPO_SIMBOLOGIA_3D', ID_GRUPO_SIMBOLOGIA_3D=id_gs, NOME_GRUPO=serie,
                  CODIGO_ELLO=0, ATIVO=1, ID_CLASSE=id_cs)
            grupos[serie] = dict(id_gp=id_gp, id_gi=id_gi, id_gs=id_gs, apl=apl, tubo=tubo)

        # ── peças ─────────────────────────────────────────────────────────────
        simb_por_geo = {}          # caminho absoluto da geometria → id da simbologia
        props = {}                 # chave de spec → id da propriedade
        n_valores = n_curvas = n_tri = 0
        for i, p in enumerate(produtos, 1):
            serie = (p.get('serie') or '').strip() or 'Outros'
            grp = grupos[serie]
            nome = nome_da_peca(p.get('nome'), serie, manter_prefixo)
            onde = f"produto {i}/{len(produtos)} {p.get('nome')!r}"
            geo_abs = caminho_geo(p)

            id_peca = g.novo('PECA')
            g.ins('PECA', ID_PECA=id_peca, NOME_PECA=nome, BIBLIOTECA=fabricante, SIMBOLO_SELECIONADO=1,
                  DESCRICAO_DADOS=(p.get('conexoes') or '').strip() or serie, POSICIONAR_SIMBOLOGIA=0,
                  POSICAO_DADOS=0, INDICACAO_DADOS=nome, POSICIONA_CAMPOS=1, DESENHA_SIMBOLOGIA=2,
                  DIAMETRO_PECA=aq_writer.SENT_REAL, COMPRIMENTO_PECA=aq_writer.SENT_REAL,
                  ID_GRUPO_PECA=grp['id_gp'], TIPO_APLICACAO_PECA=grp['apl'], CODIGO_ELLO=0, ATIVO=1,
                  DESCRICAO_DADOS_SIMBOLOGIA=serie, POSICIONAR_SIMBOLOGIA_3D=3,
                  ESPESSURA_PECA=aq_writer.SENT_REAL, LARGURA_PECA=aq_writer.SENT_REAL,
                  ALTURA_PECA=aq_writer.SENT_REAL, PROFUNDIDADE_PECA=aq_writer.SENT_REAL,
                  FORMATO_PECA=-1, OPCAO_RENDERIZACAO_PLANIFICADA=0, INCLUIR_REPRESENTACAO3D_PARAMETRICA=0,
                  CONEXAO_VOLUMETRICA=0, INDICE_SIMBOLO3D_SELECIONADO=1)

            # curva Q-H → MODELO_BOMBA + pontos; a DADOS_HIDRAULICOS aponta para ele
            curva = p.get('curva') or []
            id_mb = None
            if curva:
                id_mb = g.novo('MODELO_BOMBA')
                potencia = p.get('potencia')
                g.ins('MODELO_BOMBA', ID_MODELO_BOMBA=id_mb, NOME_MB=f'{fabricante} - {serie} - {nome}',
                      POTENCIA_MB=float(potencia) if potencia is not None else None, CODIGO_ELLO=0, ATIVO=1)
                for pt in curva:
                    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                        raise ExportacaoError(f'{onde}: ponto de curva inválido {pt!r}')
                    vaz, alt = float(pt[0]), float(pt[1])
                    pot = float(pt[2]) if len(pt) > 2 and pt[2] is not None else None
                    rend = float(pt[3]) if len(pt) > 3 and pt[3] is not None else None
                    g.ins('ITEM_CURVA_BOMBA', ID_ITEM_CURVA_BOMBA=g.novo('ITEM_CURVA_BOMBA'),
                          VAZAO_ICB=vaz, ALTURA_ICB=alt, POTENCIA_ICB=pot, RENDIMENTO_ICB=rend,
                          ID_MODELO_BOMBA=id_mb)
                    n_curvas += 1
            if id_mb:
                g.ins('DADOS_HIDRAULICOS', ID_DADOS_HIDRAULICOS=g.novo('DADOS_HIDRAULICOS'),
                      ID_MODELO_BOMBA=id_mb, ID_PECA=id_peca)
            else:
                g.ins('DADOS_HIDRAULICOS', ID_DADOS_HIDRAULICOS=g.novo('DADOS_HIDRAULICOS'),
                      TIPO_CURVA=aq_writer.TIPO_CURVA_CONEXAO, ID_PECA=id_peca)

            # insumo de orçamento
            id_item = g.novo('ITEM')
            g.ins('ITEM', ID_ITEM=id_item, ID_GRUPO_ITEM=grp['id_gi'], NOME_ITEM=nome, CODIGO_ELLO=0, ATIVO=1,
                  FABRICANTE=fabricante, TABELA_REFERENCIA=origem, CATEGORIA='Insumo',
                  CODIGO_ITEM=codigo_do_produto(p), OBSERVACAO='')
            g.ins('ITEM_ASSOCIADO', ID_ITEM_ASSOCIADO=g.novo('ITEM_ASSOCIADO'), QUANTIDADE_IA=1.0,
                  MEDICAO_PECA=aq_writer.MEDICAO_TUBO if grp['tubo'] else aq_writer.MEDICAO_CONEXAO,
                  ID_PECA=id_peca, ID_ITEM=id_item)

            # geometria — uma simbologia por arquivo, compartilhada entre as peças que a usam
            id_simb = simb_por_geo.get(geo_abs)
            if id_simb is None:
                malhas = malhas_de_geometria(carregar_geometria(geo_abs, onde), onde)
                blob = oq3d_writer.escrever(malhas)
                n_tri += sum(len(t) for _, t, _, _ in malhas)
                id_simb = g.novo('SIMBOLOGIA_3D')
                g.ins('SIMBOLOGIA_3D', ID_SIMBOLOGIA_3D=id_simb, ID_GRUPO_SIMBOLOGIA_3D=grp['id_gs'],
                      NOME=nome_da_simbologia(geo_abs, nome), CODIGO_ELLO=0, ATIVO=1,
                      SIMBOLOGIA_3D=sqlite3.Binary(blob), REFERENCIA_CORTE=0, EMBUTIMENTO=1.0, USA_CORES_PECA=1,
                      DESLOCAMENTO_X=0.0, DESLOCAMENTO_Y=0.0, DESLOCAMENTO_Z=0.0,
                      ANGULO_PLANO_XY=0.0, ANGULO_PLANO_XZ=0.0, ANGULO_PLANO_YZ=0.0)
                simb_por_geo[geo_abs] = id_simb
                if len(simb_por_geo) % 50 == 0:
                    progresso(f'{len(simb_por_geo)} geometrias gravadas ({i}/{len(produtos)} produtos)')
            g.ins('PECA_SIMBOLOGIA_3D', ID_PECA_SIMBOLOGIA_3D=g.novo('PECA_SIMBOLOGIA_3D'),
                  ID_PECA=id_peca, ID_SIMBOLOGIA_3D=id_simb)

            # propriedades personalizadas — uma PROPRIEDADE por chave, um VALOR por (peça, chave)
            for chave, valor in (p.get('specs') or {}).items():
                if valor is None or str(valor).strip() == '':
                    continue
                chave = str(chave).strip()
                id_prop = props.get(chave)
                if id_prop is None:
                    id_prop = g.novo('PROPRIEDADE_PERSONALIZADA')
                    g.ins('PROPRIEDADE_PERSONALIZADA', ID_PROPRIEDADE_PERSONALIZADA=id_prop,
                          ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_gprop, NOME=chave, TIPO_VALOR=0)
                    props[chave] = id_prop
                g.ins('VALOR_PROPRIEDADE_PERSONALIZADA',
                      ID_VALOR_PROPRIEDADE_PERSONALIZADA=g.novo('VALOR_PROPRIEDADE_PERSONALIZADA'),
                      ID_PROPRIEDADE_PERSONALIZADA=id_prop, ID_PECA=id_peca, VALOR=str(valor))
                n_valores += 1

        con.commit()
        violacoes = con.execute('PRAGMA foreign_key_check').fetchall()
        if violacoes:
            raise ExportacaoError(f'{len(violacoes)} chave(s) estrangeira(s) órfã(s): {violacoes[:5]}')
        con.close()
    except BaseException:
        con.close()
        if os.path.exists(saida):
            os.remove(saida)
        raise

    resumo = {
        'fabricante': fabricante, 'titulo': titulo,
        'pecas': len(produtos), 'grupos': len(grupos), 'simbologias': len(simb_por_geo),
        'triangulos': n_tri, 'propriedades': len(props), 'valores': n_valores, 'curvas': n_curvas,
        'bytes': os.path.getsize(saida), 'segundos': round(time.time() - t0, 1),
    }
    progresso(f"{resumo['pecas']} peças, {resumo['grupos']} grupos, {resumo['simbologias']} simbologias, "
              f"{resumo['triangulos']} triângulos, {resumo['bytes'] / 1024 / 1024:.1f} MB em {resumo['segundos']}s")
    return resumo


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('manifesto', help='JSON com catalogo, geo_dir e produtos')
    ap.add_argument('saida', help='caminho do .aq a gravar (sobrescreve)')
    ap.add_argument('--manter-prefixo-serie', action='store_true',
                    help='NOME_PECA igual ao nome da tela, sem tirar o prefixo da série')
    ap.add_argument('--quiet', action='store_true', help='sem progresso no stderr')
    args = ap.parse_args()
    with open(args.manifesto, encoding='utf-8') as f:
        manifesto = json.load(f)
    resumo = gerar(manifesto, args.saida, manter_prefixo=args.manter_prefixo_serie,
                   progresso=None if args.quiet else avisar)
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == '__main__':
    main()
