"""
miniaturas.py — pré-renderiza uma miniatura WebP por geometria no Chromium
(Playwright) com o MESMO Three.js, `buildScene()` e câmera do viewer, via
`thumbs.mjs` + `harness.html` deste diretório. (Era `build_thumbs` em
`scripts/build.py`; movido para o serviço de ingestão em 2026-09-05, E2.)

Por que existe: sem isso o browser do visitante baixa o JSON de geometria de
cada card visível (324 KB a 3,5 MB cada) e roda um render WebGL só para desenhar
o thumbnail. Medido em produção na página da Dancor: o elemento LCP É essa
miniatura, com 7.230 ms de render delay.

Quem usa: `scripts/build.py` (ZIP para a bilds.com) e `catalogo_de_aq.py --thumbs-dir`.
O serviço `apps/ingestao` chama o `thumbs.mjs` direto, do Node, com o mesmo cfg.
"""
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
THUMBS_MJS = os.path.join(AQUI, 'thumbs.mjs')

THUMB_W, THUMB_H = 448, 324
THUMB_MIME, THUMB_EXT, THUMB_QUALITY = 'image/webp', 'webp', 0.85

NODE_MINIMO = 20  # exigência do Playwright


def _node_versao(exe):
    """Major do Node em `exe`, ou None se não executar."""
    try:
        out = subprocess.run([exe, '--version'], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'v(\d+)\.', out.stdout.strip())
    return int(m.group(1)) if m else None


def _find_node():
    """
    Node com major >= NODE_MINIMO, ou None.

    Existe porque é comum a máquina ter dois Node: o do apt em /usr/bin (velho)
    e um do nvm (novo). O nvm só entra no PATH de shell interativo — um
    subprocess do Python normalmente pega o do apt. Sem esta busca, quem roda o
    build fora de um shell com nvm carregado recebe "Playwright requires
    Node.js 20 or higher" sem pista de que existe um Node bom instalado.

    Ordem: $BILDS_NODE > `node` do PATH > maior versão em ~/.nvm.
    """
    forcado = os.environ.get('BILDS_NODE')
    if forcado:
        return forcado if (_node_versao(forcado) or 0) >= NODE_MINIMO else None

    if (_node_versao('node') or 0) >= NODE_MINIMO:
        return 'node'

    nvm = os.path.expanduser('~/.nvm/versions/node')
    candidatos = []
    if os.path.isdir(nvm):
        for v in os.listdir(nvm):
            exe = os.path.join(nvm, v, 'bin', 'node')
            major = _node_versao(exe) if os.path.exists(exe) else None
            if major and major >= NODE_MINIMO:
                candidatos.append((major, exe))
    return max(candidatos)[1] if candidatos else None


class ThumbsError(RuntimeError):
    """O passo de miniaturas não conseguiu gerar tudo o que o catálogo pede."""


def vendor_dir_padrao():
    """
    Onde está o `three.module.js` que o harness importa: por padrão a `build/` do `three`
    instalado por `package.json` deste diretório (o `thumbs.mjs` resolve sozinho quando não
    recebe `vendorDir`); `$BILDS_THREE_DIR` sobrepõe. Devolve None quando é para o `thumbs.mjs`
    decidir.
    """
    forcado = os.environ.get('BILDS_THREE_DIR')
    if forcado:
        return forcado
    local = os.path.join(AQUI, 'node_modules', 'three', 'build')
    return local if os.path.isfile(os.path.join(local, 'three.module.js')) else None


def build_thumbs(catalog, geo_dir, thumbs_dir, vendor_dir=None, node_modules_dir=None,
                 progresso=None):
    """
    Pré-renderiza uma miniatura por geometria e anota `thumb` nos produtos.

    Uma miniatura por GEOMETRIA, não por produto: 856 produtos da Amanco
    compartilham 448 geometrias.

    NÃO degrada em silêncio (desde 2026-09-03): sem Node >= 20, sem Playwright,
    sem browser, com timeout ou com qualquer geometria que falhou no render, lança
    `ThumbsError` — depois de anotar `thumb` nas que deram certo. Quem decide se
    o build segue é o chamador (`--allow-no-thumbs` no build.py).

    `node_modules_dir`: onde está o `playwright` (padrão: o da raiz do repositório,
    `pnpm install` na raiz). `vendor_dir`: onde está `three.module.js`.
    `progresso(mensagem)` recebe uma linha a cada 50 miniaturas.

    Retorna a quantidade de miniaturas geradas.
    """
    avisar = progresso or (lambda _m: None)
    geos = []
    for produto in catalog['produtos']:
        g = produto.get('geo')
        if g and g not in geos and os.path.exists(os.path.join(geo_dir, g)):
            geos.append(g)
    if not geos:
        return 0

    os.makedirs(thumbs_dir, exist_ok=True)
    vendor = vendor_dir or vendor_dir_padrao()
    cfg = {
        'harnessDir': AQUI,
        **({'vendorDir': os.path.abspath(vendor)} if vendor else {}),
        'geoDir': os.path.abspath(geo_dir),
        'outDir': os.path.abspath(thumbs_dir),
        'geos': geos,
        'width': THUMB_W, 'height': THUMB_H,
        'mime': THUMB_MIME, 'quality': THUMB_QUALITY, 'ext': THUMB_EXT,
    }
    cfg_path = os.path.join(thumbs_dir, '.thumbs-config.json')
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f)

    node = _find_node()
    if not node:
        os.remove(cfg_path)
        atual = _node_versao('node')
        raise ThumbsError(
            f'Playwright exige Node >= {NODE_MINIMO}'
            + (f', e o do PATH é v{atual}' if atual else ', e não há node no PATH')
            + '. Use `nvm use 20` (ou superior), ou aponte BILDS_NODE para um '
              'executável compatível.')

    env = dict(os.environ)
    # o thumbs.mjs faz `import('playwright')` e resolve `three` a partir do próprio arquivo
    # (node_modules deste diretório); `node_modules_dir` só existe para apontar outro lugar via NODE_PATH.
    if node_modules_dir:
        env['NODE_PATH'] = node_modules_dir
    ok, erros = {}, []
    try:
        proc = subprocess.Popen([node, THUMBS_MJS, cfg_path], cwd=AQUI,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            for linha in proc.stdout:
                try:
                    r = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if 'error' in r:
                    erros.append((r['geo'], r['error']))
                else:
                    ok[r['geo']] = r['bytes']
                    if len(ok) % 50 == 0:
                        avisar(f'{len(ok)}/{len(geos)} miniaturas')
            stderr = proc.stderr.read()
            proc.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise ThumbsError('render de miniaturas excedeu 30 min')
    except FileNotFoundError:
        raise ThumbsError(f'executável node não encontrado: {node}')
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)

    if proc.returncode == 1:
        # thumbs.mjs sai com 1 quando não consegue nem começar: playwright
        # ausente, Chromium não instalado, libs de sistema faltando.
        raise ThumbsError(stderr.strip()[:300] or 'thumbs.mjs falhou sem mensagem')

    for produto in catalog['produtos']:
        stem = os.path.splitext(produto.get('geo', ''))[0]
        if stem in ok:
            produto['thumb'] = f'{stem}.{THUMB_EXT}'

    if ok:
        media = sum(ok.values()) / len(ok) / 1024
        avisar(f'{len(ok)} miniaturas ({media:.0f} KB em média)')

    if erros:
        detalhe = '; '.join(f'{g}: {e[:70]}' for g, e in erros[:3])
        raise ThumbsError(f'{len(erros)} de {len(geos)} miniatura(s) falharam — {detalhe}')
    if not ok:
        raise ThumbsError(f'nenhuma das {len(geos)} miniaturas foi gerada '
                          f'(exit {proc.returncode}: {stderr.strip()[:200]})')
    return len(ok)
