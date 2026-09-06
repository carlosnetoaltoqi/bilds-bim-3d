#!/usr/bin/env python3
"""
tupy_catalogo.py — dos arquivos baixados pelo `tupy_baixar.py` a uma biblioteca `.aq` do AltoQi
Builder, pelo pipeline do projeto:

    IGES (SolidWorks) ──step_to_geo.py──▶ geometria do viewer      (via catallog.catalogo_de_downloads)
    metadados da API + PartAtom do .rfa ──▶ specs por peça        (idem)
    catálogo ──▶ manifesto ──catalogo_to_aq.py──▶ Tupy-TupyGrooved.aq

Uma peça por IGES baixado; grupos sem IGES ficam fora (o `.rfa` é proprietário — ver
`rfa_partatom.py`) e são listados. O que cada peça leva no `.aq` está na docstring do
`catalogo_to_aq.py`; as specs (Código, tamanhos, dimensões, peso, material, normas, Tipos Revit,
Fonte 3D, URL) na do `catallog.py`.

SAÍDA em `--saida` (padrão `eng-reversa/tupy/saida/`): `geo/<código>.json`, `catalogo.json` (o
JSON do pipeline), `manifesto-aq.json` (o que foi para o gerador) e o `.aq`. A última linha do
stdout é o resumo JSON do gerador.

Uso:
    python3 eng-reversa/tupy/tools/tupy_catalogo.py [--downloads DIR] [--saida DIR] [--deflexao 0.2]
                                                     [--forcar] [--manter-prefixo-serie] [--aq NOME.aq]
"""
import argparse
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, '..', '..', '..'))
sys.path.insert(0, os.path.join(RAIZ, 'www', 'apps', 'ingestao', 'pipeline'))

import catallog          # noqa: E402
import catalogo_to_aq    # noqa: E402


def avisar(msg):
    print(msg, file=sys.stderr, flush=True)


def manifesto_aq(resultado, saida, origem):
    """O catálogo do pipeline → o manifesto que o `catalogo_to_aq.py` consome."""
    cfg = resultado['config']
    return {
        'catalogo': {'fabricante': cfg['fabricante'], 'titulo': cfg['titulo'], 'slug': cfg['slug'],
                     'descricao': cfg.get('descricao') or '', 'origem': origem},
        'geo_dir': saida,
        'produtos': [{
            'id': p['id'], 'nome': p['nome'], 'serie': p['serie'], 'conexoes': p['conexoes'],
            'codigo': p.get('codigo'), 'specs': p['specs'], 'curva': None, 'potencia': None,
            'geo': os.path.join('geo', p['geo']),
        } for p in resultado['catalog']['produtos']],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--downloads', default=os.path.join(AQUI, '..', 'downloads'))
    ap.add_argument('--saida', default=os.path.join(AQUI, '..', 'saida'))
    ap.add_argument('--aq', default='Tupy-TupyGrooved.aq')
    ap.add_argument('--titulo', default='TupyGrooved')
    ap.add_argument('--deflexao', type=float, default=0.2)
    ap.add_argument('--forcar', action='store_true')
    ap.add_argument('--manter-prefixo-serie', action='store_true')
    args = ap.parse_args()

    downloads, saida = os.path.abspath(args.downloads), os.path.abspath(args.saida)
    os.makedirs(saida, exist_ok=True)
    resultado = catallog.catalogo_de_downloads(downloads, os.path.join(saida, 'geo'), args.deflexao, args.forcar,
                                               titulo=args.titulo, origem={'ferramenta': 'eng-reversa/tupy/tools/tupy_catalogo.py'})
    with open(os.path.join(saida, 'catalogo.json'), 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    for a in resultado['diag']['avisos']:
        avisar(f'aviso: {a}')

    o = resultado['hints']['origem']
    origem = (f"Catálogo Eletrônico Tupy ({o.get('host')}), {o['grupos']} grupos, {resultado['n_geometrias']} peças com IGES; "
              f"gerado em {time.strftime('%Y-%m-%d')} por eng-reversa/tupy/tools/tupy_catalogo.py")
    manifesto = manifesto_aq(resultado, saida, origem)
    with open(os.path.join(saida, 'manifesto-aq.json'), 'w', encoding='utf-8') as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1)

    destino = os.path.join(saida, args.aq)
    if os.path.exists(destino):
        os.remove(destino)
    resumo = catalogo_to_aq.gerar(manifesto, destino, manter_prefixo=args.manter_prefixo_serie, progresso=avisar)
    avisar(f'→ {destino} ({os.path.getsize(destino) / 1e6:.1f} MB)')
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == '__main__':
    main()
