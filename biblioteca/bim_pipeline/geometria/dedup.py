#!/usr/bin/env python3
"""
dedup.py — Converte geometria expandida { pos, col } em indexada { pos, col, idx }.

Redução típica: 80% menos vértices, arquivo 3–5× menor antes do gzip.
Para 14 modelos Dancor: ~80MB expandido → ~25MB indexado → ~4.5MB gzip total.

Uso:
  python3 -m bim_pipeline.cli.dedup <input.json> [output.json]
  Se output não especificado, sobrescreve o input.
"""
import json
import struct
import sys
import os


def dedup(data):
    """
    Recebe dict { pos, col } ou { pos, col, idx } e retorna { pos, col, idx }.
    Usa quantização float32 como chave para identificar vértices duplicados
    (mesma precisão que Float32BufferAttribute no Three.js).
    """
    pos = data['pos']
    col = data.get('col', [])
    existing_idx = data.get('idx')

    if existing_idx is not None:
        # Já está indexado — re-dedup para garantir consistência
        expanded_pos = []
        expanded_col = []
        for i in existing_idx:
            expanded_pos += pos[i * 3:i * 3 + 3]
            if col:
                expanded_col += col[i * 3:i * 3 + 3]
        pos = expanded_pos
        col = expanded_col

    n = len(pos) // 3

    def q(v):
        return struct.pack('f', v)

    seen = {}
    new_pos = []
    new_col = []
    new_idx = []

    for i in range(n):
        px, py, pz = pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]
        if col:
            cr, cg, cb = col[i * 3], col[i * 3 + 1], col[i * 3 + 2]
            key = (q(px), q(py), q(pz), q(cr), q(cg), q(cb))
        else:
            key = (q(px), q(py), q(pz))

        if key not in seen:
            seen[key] = len(new_pos) // 3
            new_pos += [px, py, pz]
            if col:
                new_col += [cr, cg, cb]
        new_idx.append(seen[key])

    result = {'pos': new_pos, 'col': new_col if col else [], 'idx': new_idx}
    orig = n
    dedup_n = len(new_pos) // 3
    pct = 100 * (1 - dedup_n / orig) if orig else 0
    return result, orig, dedup_n, pct


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
