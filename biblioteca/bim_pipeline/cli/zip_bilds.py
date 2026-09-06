#!/usr/bin/env python3
"""
zip_bilds — `.aq`/`.zip` → ZIP da bilds.com. Nada fica persistido além do ZIP (ADR-012).

Um arquivo (é o que o serviço gerador de ZIP chama):
    python3 -m bim_pipeline.cli.zip_bilds <biblioteca.aq|.zip> --saida <saida.zip>
            [--nome-original <nome>] [--skip-thumbs | --allow-no-thumbs] [--sair-com-stdin]

Lote — todas as bibliotecas de uma pasta, um ZIP por `.aq`, espelhando as subpastas
(era o `scripts/build.py --all` até 2026-09-06):
    python3 -m bim_pipeline.cli.zip_bilds --all [--input-dir input] [--output-dir output]
            [--force] [--layout series-rows|catalog-grid] [--skip-thumbs | --allow-no-thumbs]

Miniaturas: por padrão são **obrigatórias** — sem Node/Playwright/Chromium a geração FALHA
(exit 1), porque um ZIP sem `thumbs/` paga o render no browser (dezenas de segundos de LCP).
`--allow-no-thumbs` avisa e segue; `--skip-thumbs` nem tenta. Catálogo sem nenhuma peça com
geometria → exit 1. No lote, qualquer falha → exit 1 no fim, depois de tentar todas.
"""
import argparse
import json
import os
import sys

from bim_pipeline.catalogo.inferencia import auto_config, find_aq_paths
from bim_pipeline.miniaturas.render import ThumbsError
from bim_pipeline.processo import vigiar_stdin
from bim_pipeline.saida.zip_bilds import CatalogoVazio, gerar_zip, nome_zip


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def _modo_miniaturas(args):
    return 'nao' if args.skip_thumbs else ('opcionais' if args.allow_no_thumbs else 'obrigatorias')


def aq_rel_dir(aq_path, input_dir):
    """Pasta do `.aq` relativa à entrada, para espelhar a estrutura na saída ('' na raiz)."""
    rel = os.path.relpath(os.path.dirname(os.path.abspath(aq_path)), os.path.abspath(input_dir))
    return '' if rel in ('.', os.curdir) else rel


def find_existing_zip(out_dir, slug):
    """ZIP mais recente já gerado para este slug, se houver."""
    if not os.path.isdir(out_dir):
        return None
    hits = sorted(f for f in os.listdir(out_dir) if f.startswith(slug + '-') and f.endswith('.zip'))
    return os.path.join(out_dir, hits[-1]) if hits else None


def um_arquivo(args):
    if args.sair_com_stdin:
        vigiar_stdin()
    try:
        gerar_zip(args.input, args.saida, nome_original=args.nome_original,
                  miniaturas=_modo_miniaturas(args), progresso=_log)
    except CatalogoVazio as e:
        _log(f'ERRO: {e}')
        return 1
    except ThumbsError as e:
        _log(f'ERRO: miniaturas — {e}')
        _log('       Sem miniaturas o ZIP sairia sem thumbs/ e a página pagaria o render no browser. '
             'Para aceitar isso de propósito: --allow-no-thumbs; para nem tentar: --skip-thumbs.')
        return 1
    return 0


def lote(args):
    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)
    aq_paths = find_aq_paths(input_dir)
    if not aq_paths:
        _log(f'Nenhuma biblioteca .aq encontrada em {input_dir}')
        return 1
    _log(f'=== lote: {len(aq_paths)} biblioteca(s) .aq ===')
    feitos, pulados, falhas = [], [], []
    for i, aq_path in enumerate(aq_paths, 1):
        rel_dir = aq_rel_dir(aq_path, input_dir)
        nome = os.path.basename(aq_path)
        _log(f'[{i}/{len(aq_paths)}] {os.path.join(rel_dir, nome) if rel_dir else nome}')
        try:
            config, hints = auto_config(aq_path)
        except Exception as e:
            _log(f'    ERRO ao ler metadados: {e}')
            falhas.append((aq_path, str(e)))
            continue
        if args.layout:
            config['layout'] = args.layout
        zip_dir = os.path.join(output_dir, rel_dir) if rel_dir else output_dir
        ja = find_existing_zip(zip_dir, config['slug'])
        if ja and not args.force:
            _log(f'    já processado: {ja} — pulando (use --force para refazer)')
            pulados.append(aq_path)
            continue
        _log(f'    {config["fabricante"]} · {config["titulo"]} '
             f'({hints.get("n_pecas", 0)} peças, {hints.get("n_simbologias", 0)} geometrias)')
        saida = os.path.join(zip_dir, nome_zip(config['slug']))
        try:
            r = gerar_zip(aq_path, saida, config=config, miniaturas=_modo_miniaturas(args),
                          progresso=lambda m: _log(f'    {m}'))
        except (CatalogoVazio, ThumbsError) as e:
            _log(f'    ERRO: {e}')
            falhas.append((aq_path, str(e)))
            continue
        except Exception as e:
            _log(f'    ERRO no build: {type(e).__name__}: {e}')
            falhas.append((aq_path, str(e)))
            continue
        # catalog.json solto acompanha o ZIP, para inspeção
        with open(os.path.join(zip_dir, f'{config["slug"]}-catalog.json'), 'w', encoding='utf-8') as f:
            json.dump(r['catalog'], f, ensure_ascii=False, indent=2)
        feitos.append(saida)
        _log(f'    ZIP: {saida}')
    _log('=== lote concluído ===')
    _log(f'  gerados : {len(feitos)}')
    if pulados:
        _log(f'  pulados : {len(pulados)} (já tinham ZIP)')
    if falhas:
        _log(f'  falhas  : {len(falhas)}')
        for p, e in falhas:
            _log(f'      {os.path.basename(p)}: {e[:90]}')
    return 1 if falhas else 0


def build_parser():
    ap = argparse.ArgumentParser(prog='python3 -m bim_pipeline.cli.zip_bilds',
                                 description='.aq/.zip → ZIP da bilds.com (um arquivo ou lote)')
    ap.add_argument('input', nargs='?', help='arquivo .aq ou .zip de entrada (omitido com --all)')
    ap.add_argument('--saida', help='caminho do ZIP gerado (modo um arquivo)')
    ap.add_argument('--nome-original', help='nome exibido nos logs (padrão: basename do input)')
    ap.add_argument('--all', '-a', action='store_true', help='lote: todos os .aq de --input-dir')
    ap.add_argument('--input-dir', default='input', help='lote: pasta com os .aq (padrão input/)')
    ap.add_argument('--output-dir', default='output', help='lote: onde gravar os ZIPs (padrão output/)')
    ap.add_argument('--force', action='store_true', help='lote: refaz também as que já têm ZIP')
    ap.add_argument('--layout', choices=['series-rows', 'catalog-grid'], help='lote: força o layout')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--skip-thumbs', action='store_true', help='nem tenta renderizar miniaturas')
    g.add_argument('--allow-no-thumbs', action='store_true',
                   help='tenta; se falhar, avisa e segue em vez de falhar')
    ap.add_argument('--sair-com-stdin', action='store_true',
                    help='sair com 2 quando o stdin fechar (o serviço usa para não deixar órfãos)')
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.all:
        return lote(args)
    if not args.input or not args.saida:
        ap.error('informe <input> e --saida, ou --all')
    return um_arquivo(args)


if __name__ == '__main__':
    sys.exit(main())
