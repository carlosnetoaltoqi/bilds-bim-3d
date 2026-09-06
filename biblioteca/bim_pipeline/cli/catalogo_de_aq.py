#!/usr/bin/env python3
"""
catalogo_de_aq.py — a linha de comando do pipeline: um `.aq` (ou `.zip` com o
SQLite dentro) vira JSONs de geometria em `--geo-dir` e um catálogo em JSON.

    python3 catalogo_de_aq.py <biblioteca.aq> --geo-dir <dir> --saida <catalogo.json>
                              [--nome-original pecas_dancor.aq] [--thumbs-dir <dir>]
                              [--vendor-dir <dir>] [--sair-com-stdin]

É o que o serviço de ingestão (`apps/ingestao`) executa como processo filho para
cada upload: o Node lê o JSON de saída, grava catálogo e produtos no Mongo e depois
roda o `thumbs.mjs` (ou passa `--thumbs-dir` para fazer tudo aqui). O `scripts/build.py`
usa as mesmas funções (`catalogo.py`, `inferencia.py`, `miniaturas.py`) para o ZIP.

Progresso e diagnóstico vão para o **stderr**, uma linha por vez (o serviço mostra a
última ao usuário). O stdout fica vazio; o resultado é o arquivo `--saida`:

    {
      "config":       {slug, titulo, fabricante, descricao, layout},
      "catalog":      {slug, titulo, fabricante, descricao, layout, filtros, produtos[]},
      "n_geometrias": 448,
      "diag":         {pecas_sem_simbologia, pecas_sim_descartada, sim_sem_blob, sim_nao_oq3d,
                       sim_ilegivel[], sim_vazia[], avisos[]},
      "hints":        {n_pecas, n_simbologias, schema, grupos[], linhas[], has_curves},
      "thumbs":       {"geradas": N, "erro": null | "mensagem"}      (só com --thumbs-dir)
    }

Cada produto: {id, nome, serie, geo: "<stem>.json", potencia, conexoes, specs, curva[, thumb]}.

Códigos de saída: 0 ok (mesmo com produtos = 0 — o chamador decide o que é "vazio");
1 erro de leitura/parse (mensagem no stderr); 2 stdin fechou (pai morreu).
"""
import argparse
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))

from bim_pipeline.catalogo.catalogo import build_catalog_from_aq, montar_resultado, resumo_diag   # noqa: E402
from bim_pipeline.catalogo.inferencia import auto_config                                          # noqa: E402
from bim_pipeline.processo import vigiar_stdin                                           # noqa: E402


def _log(msg):
    sys.stderr.write(msg.rstrip('\n') + '\n')
    sys.stderr.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('aq', help='biblioteca .aq (SQLite) ou .zip com o SQLite dentro')
    ap.add_argument('--geo-dir', required=True, help='onde gravar <geo>.json, um por simbologia')
    ap.add_argument('--saida', required=True, help='arquivo JSON com o catálogo e o diagnóstico')
    ap.add_argument('--nome-original', default=None,
                    help='nome que o usuário deu ao arquivo (o upload chega como bim-<uuid>.aq)')
    ap.add_argument('--thumbs-dir', default=None, help='também renderiza as miniaturas aqui (Chromium)')
    ap.add_argument('--vendor-dir', default=None, help='pasta com three.module.js (padrão: ver miniaturas.py)')
    ap.add_argument('--sair-com-stdin', action='store_true',
                    help='sair com 2 quando o stdin fechar (o serviço usa para não deixar órfãos)')
    args = ap.parse_args(argv)

    if args.sair_com_stdin:
        vigiar_stdin()

    t0 = time.time()
    lap = lambda m: _log(f'[{time.time() - t0:6.1f}s] {m}')   # noqa: E731

    try:
        config, hints = auto_config(args.aq, args.nome_original)
        lap(f'{config["fabricante"]} · {config["titulo"]} — {hints.get("n_pecas", 0)} peças, '
            f'{hints.get("n_simbologias", 0)} simbologias, schema {hints.get("schema")}')
        catalog, n_geo, diag = build_catalog_from_aq(config, args.aq, args.geo_dir, progresso=lap)
    except Exception as e:   # erro de leitura/parse: o serviço mostra a mensagem
        _log(f'ERRO: {type(e).__name__}: {e}')
        return 1

    resumo_diag(diag, indent='', out=_log)

    thumbs = None
    if args.thumbs_dir:
        from bim_pipeline.miniaturas.render import ThumbsError, build_thumbs
        try:
            geradas = build_thumbs(catalog, args.geo_dir, args.thumbs_dir,
                                   vendor_dir=args.vendor_dir, progresso=lap)
            thumbs = {'geradas': geradas, 'erro': None}
        except ThumbsError as e:
            geradas = sum(1 for p in catalog['produtos'] if p.get('thumb'))
            thumbs = {'geradas': geradas, 'erro': str(e)}
            _log(f'AVISO: miniaturas — {e}')

    resultado = montar_resultado(config, catalog, n_geo, diag, hints, thumbs)
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False)
    lap(f'pronto — {len(catalog["produtos"])} produtos, {n_geo} geometrias → {args.saida}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
