#!/usr/bin/env python3
"""
pipeline_ponta_a_ponta.py — roda o pipeline do projeto sobre o `.aq` gerado.

O `validar_aq.py` prova que os leitores do projeto entendem o arquivo. Este
script vai um passo além: chama `build_catalog_from_aq` e `build_preview` do
`scripts/build.py`, que são o pipeline de verdade, e produz o `catalog.json`,
os JSONs de geometria e a página de preview com viewer 3D — os mesmos
artefatos que a Dancor e a Amanco produzem.

Se isto funciona, a engenharia reversa fechou o ciclo: PDF → `.aq` → catálogo
publicável, com a geometria saindo do `.aq` que nós mesmos escrevemos.

**Nada fica fora de `eng-reversa/`.** O `build.py` é importado como módulo, o
`config` é montado em memória — sem tocar no `config.json` da raiz — e o
`catalog.json` e a geometria são gravados em `eng-reversa/saida/catalogo/`.

Com uma ressalva que o código trata: o `build_preview` grava em
`output/preview/{slug}/`, um caminho fixo no módulo (`PREVIEW_DIR`, linha 85 do
`build.py`), que não é parametrizável. Então ele escreve lá e este script move
o diretório para `eng-reversa/saida/preview/` em seguida, deixando o `output/`
do projeto como estava. O `build_preview` não atualiza o
`output/preview/catalogs.json` — esse registro é mexido pelo `run_build`, que
não é chamado aqui.

Com `--zip`, gera também as miniaturas e o pacote `.zip` que a API da
bilds.com consome, e **este sai em `output/`** — o lugar padrão dos ZIPs do
projeto, junto com os que o `build.py --all` produz. É a única coisa que este
estudo escreve fora de `eng-reversa/`, e só quando pedida explicitamente.

As miniaturas importam: o `CLAUDE.md` registra que um ZIP sem `thumbs/` faz o
catálogo na bilds.com voltar ao render dinâmico, que é o comportamento de
39,9 s de LCP que motivou toda a mudança de 2026-08-27.

Uso:
    python3 pipeline_ponta_a_ponta.py <arquivo.aq> [--zip]
"""
import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, 'www', 'apps', 'ingestao', 'pipeline'))

import build      # noqa: E402   pipeline do projeto, intocado

SAIDA = os.path.join(os.path.dirname(AQUI), 'saida', 'catalogo')


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    fazer_zip = '--zip' in sys.argv
    if not argv:
        sys.exit('Uso: pipeline_ponta_a_ponta.py <arquivo.aq> [--zip]')
    aq = argv[0]

    hints = build.peek_aq(aq)
    config = {
        'slug': os.environ.get('SLUG', 'akato-construcao-civil'),
        'titulo': hints['titulo'],
        'fabricante': hints['fabricante'],
        'descricao': 'Catálogo Construção Civil da Akato, gerado a partir do '
                     'PDF comercial por engenharia reversa do formato .aq.',
        # `catalog-grid` é o layout de catálogo de conexões — o mesmo que a
        # Amanco usa. `series-rows` é para famílias com poucas variantes.
        'layout': 'catalog-grid',
    }

    geo_dir = os.path.join(SAIDA, 'data')
    os.makedirs(geo_dir, exist_ok=True)

    catalog, n_geo, diag = build.build_catalog_from_aq(config, aq, geo_dir)
    sem_3d = diag['pecas_sem_simbologia'] + diag['pecas_sim_descartada']

    print(f'build_catalog_from_aq:')
    print(f"  fabricante {catalog['fabricante']!r}  "
          f"título {catalog['titulo']!r}  layout {catalog['layout']!r}")
    print(f"  {len(catalog['produtos'])} produtos publicáveis, "
          f'{n_geo} geometrias, {sem_3d} peças sem forma 3D')
    print(f"  filtros: {catalog['filtros']}")
    build.resumo_diag(diag, indent='  ')

    caminho_catalog = os.path.join(SAIDA, 'catalog.json')
    with open(caminho_catalog, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)

    for p in catalog['produtos']:
        arq = os.path.join(geo_dir, p['geo'])
        with open(arq, encoding='utf-8') as f:
            g = json.load(f)
        print(f"  {p['id']:34} {len(g['idx']) // 3:5} triângulos  "
              f"{len(g['pos']) // 3:5} vértices  "
              f"{os.path.getsize(arq) / 1024:7.1f} KB  série {p['serie']!r}")

    thumbs_dir = os.path.join(SAIDA, 'thumbs')
    if fazer_zip:
        print()
        print('build_thumbs (Chromium + Three.js, uma miniatura por geometria):')
        os.makedirs(thumbs_dir, exist_ok=True)
        try:
            n_thumbs = build.build_thumbs(catalog, geo_dir, thumbs_dir)
        except build.ThumbsError as e:
            # Este script é de estudo: segue sem miniaturas, mas diz por quê.
            print(f'  AVISO: miniaturas — {e}')
            n_thumbs = sum(1 for p in catalog['produtos'] if p.get('thumb'))
        com_thumb = sum(1 for p in catalog['produtos'] if p.get('thumb'))
        print(f'  {n_thumbs} miniaturas, {com_thumb} de '
              f"{len(catalog['produtos'])} produtos com `thumb`")
        if not n_thumbs:
            print('  AVISO: sem miniaturas o catálogo cai no render dinâmico '
                  'na bilds.com')

        # O catalog.json gravado antes não tinha o campo `thumb`; reescreve.
        with open(caminho_catalog, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=1)

        print()
        print('build_zip:')
        zip_path = build.build_zip(catalog, out_dir=build.OUTPUT_DIR,
                                   geo_dir=geo_dir, thumbs_dir=thumbs_dir)
        print(f'  {zip_path}')

    try:
        build.build_preview(catalog, catalog['layout'], geo_dir=geo_dir)
    except Exception as e:
        print(f'\nbuild_preview falhou: {type(e).__name__}: {e}')
        return 1

    # O build_preview grava em output/preview/{slug}/ — caminho fixo do módulo.
    # Trazer para cá mantém a promessa de não deixar nada no projeto.
    gerado = os.path.join(build.PREVIEW_DIR, config['slug'])
    destino = os.path.join(os.path.dirname(AQUI), 'saida', 'preview',
                           config['slug'])
    if os.path.isdir(gerado):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        if os.path.isdir(destino):
            shutil.rmtree(destino)
        shutil.move(gerado, destino)
        print(f'\nbuild_preview: ok — movido de output/preview/ para {destino}')
        print(f"  {os.path.getsize(os.path.join(destino, 'index.html')):,} "
              f'bytes de index.html'.replace(',', '.'))

        # O template referencia o Three.js em caminho ABSOLUTO
        # (`/vendor/three.module.js`, via importmap), então a página só funciona
        # servida a partir da raiz do diretório de preview. Copiar o vendor
        # para cá reproduz a estrutura que o `output/preview/` tem.
        vendor_src = os.path.join(build.TEMPLATES_DIR, 'vendor')
        vendor_dst = os.path.join(os.path.dirname(destino), 'vendor')
        if os.path.isdir(vendor_src) and not os.path.isdir(vendor_dst):
            shutil.copytree(vendor_src, vendor_dst)
        raiz_web = os.path.dirname(destino)
        print(f'  para abrir, sirva {raiz_web} como raiz:')
        print(f'    python3 -m http.server -d "{raiz_web}" 8080')
        print(f"    → http://localhost:8080/{config['slug']}/")
    else:
        print('\nbuild_preview: ok, mas não achei o diretório para mover')

    print(f'\nsaída em {SAIDA}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
