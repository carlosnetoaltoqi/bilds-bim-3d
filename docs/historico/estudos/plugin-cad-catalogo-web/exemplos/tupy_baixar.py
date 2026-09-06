#!/usr/bin/env python3
"""
tupy_baixar.py — baixa os arquivos (IGES 3D, Revit .rfa, DXF 2D) de uma categoria do Catálogo
Eletrônico Tupy (plataforma Catallog/Collabo, `conexoes.tupy.com.br`) para `downloads/`, com um
`manifesto.json` (grupo, produto, tipo, tamanho, SHA-256, URL) e um `grupos.json`.

É a linha de comando do ESTUDO (S7.17). A implementação — API do catálogo, formulário de
download, plano por grupo, manifesto idempotente — mora no pipeline do projeto,
`www/apps/ingestao/pipeline/catallog.py`, que é o que o serviço de ingestão usa no botão
"Importar plugin do AutoCAD". Este script só a chama; ver a docstring dela para o contrato.

O formulário de download do site é captura de lead (nome, e-mail, telefone, empresa, cargo) e é
enviado com os dados de UMA pessoa real, em `--lead` (`dados/lead.local.json` está no
`.gitignore`). Uso autorizado pelo usuário em 2026-09-05 para os 18 grupos da categoria
TupyGrooved, como empresa parceira em estudo. Não use para varrer o catálogo inteiro — os Termos
de Uso proíbem redistribuição, e o volume (≈930 IGES, ≈2 GB) não é "estudo".

Por grupo: os arquivos do próprio grupo (o `.rfa` da família) e o `.igs` de `--igs-por-grupo`
produtos (padrão 1; 0 nenhum; -1 todos). DXF só com `--dxf`. Idempotente sobre o manifesto.

Uso:
    python3 eng-reversa/tupy/tools/tupy_baixar.py --lead eng-reversa/tupy/dados/lead.local.json \
        [--host https://conexoes.tupy.com.br] [--categoria tupygrooved-173] [--destino eng-reversa/tupy/downloads] \
        [--igs-por-grupo 1] [--dxf] [--limite N] [--so-listar]
"""
import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, '..', '..', '..'))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))

from bim_pipeline.catalogo.fontes import plugin_catalogo_web as catallog   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--lead', required=True, help='JSON com full_name, email, mobile, company, position')
    ap.add_argument('--host', default='https://conexoes.tupy.com.br')
    ap.add_argument('--categoria', default='tupygrooved-173')
    ap.add_argument('--destino', default=os.path.join(AQUI, '..', 'downloads'))
    ap.add_argument('--igs-por-grupo', type=int, default=1)
    ap.add_argument('--dxf', action='store_true')
    ap.add_argument('--limite', type=int, default=0, help='pára após N arquivos novos (teste)')
    ap.add_argument('--so-listar', action='store_true')
    args = ap.parse_args()

    with open(args.lead, encoding='utf-8') as f:
        lead = catallog.validar_lead(json.load(f))
    destino = os.path.abspath(args.destino)
    cli = catallog.Catallog(args.host)
    form = (cli.settings().get('forms') or {}).get('download')
    grupos, plano = catallog.planejar(cli, args.categoria, args.igs_por_grupo, args.dxf)

    ja = set()
    man = os.path.join(destino, 'manifesto.json')
    if os.path.exists(man):
        with open(man, encoding='utf-8') as f:
            ja = {a['resource_id'] for a in json.load(f)['arquivos'] if os.path.exists(os.path.join(destino, a['arquivo']))}
    for g, p, r in plano:
        print(f"{'  ' if r['id'] in ja else '→ '}{g.get('code') or '':>7} {g['name']:<26} {(p or {}).get('code') or '-':>10} "
              f"{r['type_key']:5} {r['size_in_bytes'] / 1e6:6.2f} MB  {r['title']}", file=sys.stderr)
    if args.so_listar:
        return
    manifesto = catallog.baixar_plano(cli, plano, lead, destino, args.limite, form_padrao=form)
    catallog.gravar_grupos(grupos, destino)
    print(f"manifesto com {len(manifesto['arquivos'])} arquivo(s) em {man}", file=sys.stderr)


if __name__ == '__main__':
    main()
