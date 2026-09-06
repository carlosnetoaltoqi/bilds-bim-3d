"""
zip_bilds.py — o ÚNICO escritor do pacote ZIP que a bilds.com consome (`docs/conhecimento/zip-bilds-formato.md`):

    manifest.json      slug, title, manufacturer, description, layout, filters, productCount, thumbCount
    catalog.json       o catálogo inteiro (campos em português)
    geo/<stem>.json    uma geometria por simbologia (produtos que compartilham entram uma vez)
    thumbs/<stem>.webp uma miniatura por geometria, quando houver

`thumbCount == 0` num catálogo com produtos é o sinal de que as miniaturas foram puladas ou
falharam — a página renderiza no browser. Geometria referenciada e ausente em disco fica fora do
ZIP e é avisada (quem chama decide se isso é erro).

`gerar_zip()` faz o caminho inteiro a partir de um `.aq`/`.zip` num diretório temporário: é o que o
serviço gerador de ZIP e o modo lote da CLI (`bim_pipeline.cli.zip_bilds`) consomem — as mesmas
funções do criador de catálogos (`catalogo.build_catalog_from_aq`, `miniaturas.render.build_thumbs`),
sem gravar nada além do ZIP pedido (ADR-012).
"""
import datetime
import json
import os
import shutil
import tempfile
import zipfile

from bim_pipeline.catalogo.catalogo import build_catalog_from_aq, resumo_diag
from bim_pipeline.catalogo.inferencia import auto_config
from bim_pipeline.miniaturas.render import ThumbsError, build_thumbs


class CatalogoVazio(RuntimeError):
    """O `.aq` não tem nenhuma peça com geometria 3D — não há o que publicar."""


def nome_zip(slug, quando=None):
    """`<slug>-AAAAMMDDHHMM.zip` — o nome que o modo lote grava em `output/`."""
    quando = quando or datetime.datetime.now()
    return f"{slug}-{quando.strftime('%Y%m%d%H%M')}.zip"


def build_zip_bilds(catalog, zip_path, geo_dir, thumbs_dir=None, avisar=None):
    """
    Monta o ZIP. Devolve `{'geometrias': n incluídas, 'ausentes': [stems], 'thumbs': n}`.
    `avisar(msg)` recebe um aviso por geometria ausente (até 5, depois um resumo).
    """
    thumbs = []
    if thumbs_dir and os.path.isdir(thumbs_dir):
        for produto in catalog['produtos']:
            nome = produto.get('thumb')
            if nome and nome not in thumbs and os.path.exists(os.path.join(thumbs_dir, nome)):
                thumbs.append(nome)

    incluidos, ausentes = set(), []
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)) or '.', exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            'slug':         catalog['slug'],
            'title':        catalog['titulo'],
            'manufacturer': catalog['fabricante'],
            'description':  catalog.get('descricao', ''),
            'layout':       catalog['layout'],
            'filters':      catalog['filtros'],
            'productCount': len(catalog['produtos']),
            'thumbCount':   len(thumbs),
        }
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr('catalog.json', json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))

        for produto in catalog['produtos']:
            geo_nome = produto.get('geo', '')
            if not geo_nome or geo_nome in incluidos or geo_nome in ausentes:
                continue
            geo_path = os.path.join(geo_dir, geo_nome)
            if os.path.exists(geo_path):
                zf.write(geo_path, f'geo/{geo_nome}')
                incluidos.add(geo_nome)
            else:
                ausentes.append(geo_nome)
                if avisar and len(ausentes) <= 5:
                    avisar(f'AVISO: geo/{geo_nome} não encontrado — fora do ZIP')

        for nome in thumbs:
            zf.write(os.path.join(thumbs_dir, nome), f'thumbs/{nome}')
    if avisar and len(ausentes) > 5:
        avisar(f'AVISO: +{len(ausentes) - 5} geometrias ausentes')
    return {'geometrias': len(incluidos), 'ausentes': ausentes, 'thumbs': len(thumbs)}


def gerar_zip(entrada, saida, nome_original=None, miniaturas='obrigatorias', progresso=None,
              config=None, work_dir=None):
    """
    `.aq`/`.zip` → ZIP em `saida`. Tudo o mais fica num diretório temporário apagado no fim
    (ou em `work_dir`, se quem chama quiser guardar geometria e miniaturas).

    `miniaturas`: 'obrigatorias' (falha de render → `ThumbsError`, sem ZIP), 'opcionais'
    (falha → aviso, ZIP sem `thumbs/`), 'nao' (nem tenta).
    Devolve `{'catalog', 'n_geometrias', 'diag', 'zip', 'thumbs', 'bytes'}`.
    Lança `CatalogoVazio` se não há peça com geometria; erros de leitura sobem como vieram.
    """
    avisar = progresso or (lambda m: None)
    config = config or auto_config(entrada, nome_original=nome_original or os.path.basename(entrada))[0]
    work = work_dir or tempfile.mkdtemp(prefix='bilds-zip-')
    try:
        geo_dir = os.path.join(work, 'geo')
        thumbs_dir = os.path.join(work, 'thumbs')
        os.makedirs(geo_dir, exist_ok=True)

        catalog, n_geo, diag = build_catalog_from_aq(config, entrada, geo_dir, progresso=avisar)
        resumo_diag(diag, indent='', out=avisar)
        if not catalog['produtos']:
            raise CatalogoVazio('catálogo vazio — nenhuma peça com geometria 3D')
        avisar(f'catálogo: {len(catalog["produtos"])} produto(s), {n_geo} geometria(s)')

        thumbs_dir_real, n_thumbs = None, 0
        if miniaturas == 'nao':
            avisar('miniaturas puladas: a página renderiza no browser')
        else:
            try:
                n_thumbs = build_thumbs(catalog, geo_dir, thumbs_dir, progresso=avisar)
                thumbs_dir_real = thumbs_dir if n_thumbs > 0 else None
                avisar(f'miniaturas: {n_thumbs} gerada(s)')
            except ThumbsError as e:
                if miniaturas == 'obrigatorias':
                    raise
                avisar(f'AVISO: miniaturas não geradas — {e}')

        r = build_zip_bilds(catalog, saida, geo_dir, thumbs_dir_real, avisar=avisar)
        kb = os.path.getsize(saida) / 1024
        avisar(f'zip: {kb:.0f} KB')
        return {'catalog': catalog, 'n_geometrias': n_geo, 'diag': diag, 'zip': saida,
                'thumbs': r['thumbs'], 'bytes': os.path.getsize(saida)}
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
