#!/usr/bin/env python3
"""
dedup.py — geometria expandida `{pos, col}` (ou já indexada) → indexada `{pos, col, idx}`.

A chave de um vértice é a sua posição **quantizada em float32** (a mesma precisão do
`Float32BufferAttribute` do Three.js) **mais a cor**, quando há cor. Dois efeitos deliberados:
a redução típica é de ~80 % dos vértices (arquivo 3–5× menor antes do gzip); e, como a cor
entra na chave, triângulos de cores diferentes nunca compartilham vértice — é isso que permite
ao editor re-segmentar uma malha em partes por componente conexo. O dedup **não** solda
costuras de malhas de fabricante (vértices a µm de distância continuam distintos).

A ordem dos vértices na saída é a da primeira ocorrência (estável); `-0.0` e `0.0` são chaves
distintas (bits diferentes em float32), como sempre foi.

Uso:
  python3 -m bim_pipeline.cli.dedup <input.json> [output.json]
  Se output não especificado, sobrescreve o input.
"""
import json
import os
import sys

import numpy as np


def dedup_arrays(pos, col=None):
    """
    `pos` (N, 3) e `col` (N, 3) ou None → `(pos_unicos, col_unicos | None, idx)` em numpy,
    na ordem da primeira ocorrência. É o miolo; `dedup()` é a forma do contrato JSON.
    """
    pos = np.asarray(pos, dtype=np.float64).reshape(-1, 3)
    chave = pos.astype(np.float32)
    if col is not None:
        col = np.asarray(col, dtype=np.float64).reshape(-1, 3)
        chave = np.concatenate([chave, col.astype(np.float32)], axis=1)
    # comparar os bytes (não os valores): -0.0 ≠ 0.0, e NaN não colapsa por acidente
    linhas = np.ascontiguousarray(chave).view(np.dtype((np.void, chave.dtype.itemsize * chave.shape[1]))).ravel()
    _, primeiro, inverso = np.unique(linhas, return_index=True, return_inverse=True)
    # np.unique devolve em ordem de chave; reordena pela primeira ocorrência
    ordem = np.argsort(primeiro, kind='stable')
    posicao = np.empty_like(ordem)
    posicao[ordem] = np.arange(len(ordem))
    idx = posicao[np.asarray(inverso).ravel()]
    primeiro = primeiro[ordem]
    return pos[primeiro], (col[primeiro] if col is not None else None), idx


def dedup(data):
    """
    Recebe dict `{pos, col}` ou `{pos, col, idx}` e retorna `(result, orig, dedup_n, pct)`,
    com `result = {pos, col, idx}` (col `[]` quando a entrada não tem cor).
    """
    pos = np.asarray(data['pos'], dtype=np.float64).reshape(-1, 3)
    col_in = data.get('col') or []
    col = np.asarray(col_in, dtype=np.float64).reshape(-1, 3) if len(col_in) else None
    existing_idx = data.get('idx')
    if existing_idx is not None and len(existing_idx):
        # já indexado — expande e re-deduplica para garantir consistência
        ii = np.asarray(existing_idx, dtype=np.int64)
        pos = pos[ii]
        if col is not None:
            col = col[ii]
    n = len(pos)
    if n == 0:
        return {'pos': [], 'col': [], 'idx': []}, 0, 0, 0
    pos_u, col_u, idx = dedup_arrays(pos, col)
    result = {'pos': pos_u.ravel().tolist(),
              'col': col_u.ravel().tolist() if col_u is not None else [],
              'idx': idx.astype(int).tolist()}
    dedup_n = len(pos_u)
    pct = 100 * (1 - dedup_n / n) if n else 0
    return result, n, dedup_n, pct


def main():
    if len(sys.argv) < 2:
        print('Uso: python3 -m bim_pipeline.cli.dedup <input.json> [output.json]')
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else in_path

    with open(in_path) as f:
        data = json.load(f)

    result, orig, dedup_n, pct = dedup(data)

    with open(out_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    in_mb = os.path.getsize(in_path) / 1e6
    out_mb = os.path.getsize(out_path) / 1e6
    print(f'{os.path.basename(in_path)}: {orig} → {dedup_n} vértices ({pct:.0f}% redução), {in_mb:.1f}MB → {out_mb:.1f}MB')


if __name__ == '__main__':
    main()
