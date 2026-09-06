#!/usr/bin/env python3
"""
zip_bilds.py — .aq ou .zip → ZIP para upload em bilds.com

Usado pelo serviço de ingestão em POST /exportar/zip-bilds.
Geometria e miniaturas ficam num diretório temporário apagado no final.
Nada fica no servidor: o arquivo de entrada é responsabilidade de quem chama;
o ZIP de saída é servido como download e apagado pelo controlador.

Uso:
  python3 zip_bilds.py <input.aq|input.zip> --saida <saida.zip> [--nome-original <nome>]
                       [--skip-thumbs] [--sair-com-stdin]
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))

from bim_pipeline.catalogo.catalogo import build_catalog_from_aq  # noqa: E402
from bim_pipeline.catalogo.inferencia import auto_config           # noqa: E402
from bim_pipeline.miniaturas.render import ThumbsError, build_thumbs  # noqa: E402
from bim_pipeline.processo import vigiar_stdin  # noqa: E402


def build_zip_bilds(catalog, zip_path, geo_dir, thumbs_dir=None):
    """Monta o ZIP no formato bilds.com (manifest.json + catalog.json + geo/ + thumbs/)."""
    thumbs = []
    if thumbs_dir and os.path.isdir(thumbs_dir):
        for produto in catalog['produtos']:
            nome = produto.get('thumb')
            if nome and nome not in thumbs and os.path.exists(os.path.join(thumbs_dir, nome)):
                thumbs.append(nome)

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

        incluidos = set()
        for produto in catalog['produtos']:
            geo_nome = produto.get('geo', '')
            if not geo_nome or geo_nome in incluidos:
                continue
            geo_path = os.path.join(geo_dir, geo_nome)
            if os.path.exists(geo_path):
                zf.write(geo_path, f'geo/{geo_nome}')
                incluidos.add(geo_nome)

        for nome in thumbs:
            zf.write(os.path.join(thumbs_dir, nome), f'thumbs/{nome}')


def main():
    ap = argparse.ArgumentParser(description='zip_bilds.py — .aq/.zip → ZIP bilds.com')
    ap.add_argument('input', help='arquivo .aq ou .zip de entrada')
    ap.add_argument('--saida', required=True, help='caminho do ZIP gerado')
    ap.add_argument('--nome-original', help='nome exibido nos logs (padrão: basename do input)')
    ap.add_argument('--skip-thumbs', action='store_true', help='não gerar miniaturas')
    ap.add_argument('--sair-com-stdin', action='store_true',
                    help='encerra quando stdin fechar (serviço de ingestão)')
    args = ap.parse_args()

    if args.sair_com_stdin:
        vigiar_stdin()

    nome_original = args.nome_original or os.path.basename(args.input)
    config, _hints = auto_config(args.input, nome_original=nome_original)

    def progresso(msg):
        print(msg, file=sys.stderr, flush=True)

    work = tempfile.mkdtemp(prefix='bilds-zip-')
    try:
        geo_dir = os.path.join(work, 'geo')
        thumbs_dir = os.path.join(work, 'thumbs')
        os.makedirs(geo_dir)

        catalog, n_geo, _diag = build_catalog_from_aq(config, args.input, geo_dir, progresso=progresso)

        if not catalog['produtos']:
            print('ERRO: catálogo vazio — nenhuma peça com geometria 3D', file=sys.stderr)
            sys.exit(1)

        print(f'catálogo: {len(catalog["produtos"])} produto(s), {n_geo} geometria(s)', file=sys.stderr, flush=True)

        thumbs_dir_real = None
        if not args.skip_thumbs:
            try:
                n = build_thumbs(catalog, geo_dir, thumbs_dir, progresso=progresso)
                thumbs_dir_real = thumbs_dir if n > 0 else None
                print(f'miniaturas: {n} gerada(s)', file=sys.stderr, flush=True)
            except ThumbsError as e:
                print(f'AVISO: miniaturas não geradas — {e}', file=sys.stderr, flush=True)

        build_zip_bilds(catalog, args.saida, geo_dir, thumbs_dir_real)
        kb = os.path.getsize(args.saida) / 1024
        print(f'zip: {kb:.0f} KB', file=sys.stderr, flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
