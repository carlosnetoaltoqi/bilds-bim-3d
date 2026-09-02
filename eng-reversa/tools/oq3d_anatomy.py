#!/usr/bin/env python3
"""
oq3d_anatomy.py — dissecação byte a byte de um blob OQ3D.

O `scripts/oq3d.py` do projeto é um leitor TOLERANTE: ele varre à procura de
0x5B/0x5D e consome por inteiro apenas os três blocos de tamanho conhecido
(malha, cor, transform). Tudo o que fica entre um bloco e o próximo marcador é
ignorado — e é exatamente esse resto que um ESCRITOR precisa reproduzir.

Esta ferramenta imprime, em ordem de documento:

  - a assinatura e os bytes que a cercam;
  - cada marcador de abertura (0x5B + u32 len + nome de classe);
  - o payload consumido, quando o tamanho é conhecido;
  - o GAP: os bytes entre o fim do payload conhecido e o próximo marcador,
    em hexadecimal. É o que falta documentar para escrever OQ3D.

Uso:
    python3 oq3d_anatomy.py <arquivo.aq> <ID_SIMBOLOGIA_3D> [--max-nos N]

Somente leitura. Não escreve nada e não toca no projeto.
"""
import argparse
import sqlite3
import struct
import sys

MAGIC = b'OQ3D 3D Objects File'
OPEN, CLOSE = 0x5B, 0x5D

CLASSES = {
    'TQi3DReusedObject', 'TQi3DReusableObject', 'TQi3DObjectGroup',
    'TQi3DTriangleMesh', 'TCoatingColor', 'TQi3DIndexedTriangleMeshData',
    'TCoordinateTransformation3D',
}


def _decode_texto(b):
    """cp1252, não latin-1 — ver a skill leitor-biblioteca-aq."""
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')


def carregar_blob(aq_path, sid):
    con = sqlite3.connect(aq_path)
    con.text_factory = _decode_texto
    row = con.execute(
        'SELECT NOME, CAST(SIMBOLOGIA_3D AS BLOB) FROM SIMBOLOGIA_3D '
        'WHERE ID_SIMBOLOGIA_3D = ?', (sid,)).fetchone()
    con.close()
    if row is None:
        sys.exit(f'ID_SIMBOLOGIA_3D {sid} não existe em {aq_path}')
    return row[0], row[1]


def classe_em(buf, p):
    """(nome, offset_do_payload) se há marcador de classe em p, senão None."""
    if p + 5 > len(buf):
        return None
    length = struct.unpack_from('<I', buf, p + 1)[0]
    if not (3 <= length <= 60) or p + 5 + length > len(buf):
        return None
    try:
        name = buf[p + 5:p + 5 + length].decode('ascii')
    except UnicodeDecodeError:
        return None
    return (name, p + 5 + length) if name in CLASSES else None


def fim_do_payload(buf, name, off):
    """Fim do payload de tamanho conhecido, ou None se a classe é container."""
    n = len(buf)
    if name == 'TCoatingColor':
        return off + 12
    if name == 'TCoordinateTransformation3D':
        return off + 4 + 12 * 8
    if name == 'TQi3DIndexedTriangleMeshData':
        ver, n_coord, _ = struct.unpack_from('<3I', buf, off)
        idx_off = off + 12 + n_coord * 8
        n_idx = struct.unpack_from('<I', buf, idx_off)[0]
        return idx_off + 8 + n_idx * 4
    return None


def hexdump(buf, ini, fim, largura=16, limite=256):
    """Hex + ASCII de buf[ini:fim], truncado em `limite` bytes."""
    dados = buf[ini:fim]
    truncado = len(dados) > limite
    if truncado:
        dados = dados[:limite]
    linhas = []
    for i in range(0, len(dados), largura):
        pedaco = dados[i:i + largura]
        hx = ' '.join(f'{b:02x}' for b in pedaco)
        txt = ''.join(chr(b) if 32 <= b < 127 else '.' for b in pedaco)
        linhas.append(f'      {ini + i:08x}  {hx:<{largura * 3}} |{txt}|')
    if truncado:
        linhas.append(f'      ... (+{fim - ini - limite} bytes)')
    return '\n'.join(linhas)


def anatomia(buf, max_nos=None):
    n = len(buf)
    print(f'tamanho total: {n} bytes')

    pos_magic = buf.find(MAGIC)
    print(f'\n=== ASSINATURA (offset {pos_magic}) ===')
    print(hexdump(buf, 0, min(pos_magic + len(MAGIC) + 32, n)))

    print('\n=== ÁRVORE ===')
    p = 0
    prof = 0
    nos = 0
    gaps = {}          # (classe, tamanho_do_gap) -> contagem
    prefixos = {}      # bytes antes do 0x5B, por classe
    while p < n:
        b = buf[p]
        if b == OPEN:
            hit = classe_em(buf, p)
            if hit is None:
                p += 1
                continue
            name, off = hit
            nos += 1
            if max_nos and nos > max_nos:
                print(f'\n... interrompido em {max_nos} nós')
                break
            pre = bytes(buf[max(0, p - 4):p])
            prefixos.setdefault(name, set()).add(pre.hex(' '))
            ind = '  ' * prof
            print(f'{ind}[{nos:04d}] @{p:08x} 0x5B len={off - p - 5} '
                  f'{name}  (antes: {pre.hex(" ")})')

            fim = fim_do_payload(buf, name, off)
            if fim is None:
                print(f'{ind}      payload: CONTAINER (tamanho desconhecido)')
                q = off
            else:
                if name == 'TCoatingColor':
                    ver, flag = struct.unpack_from('<2I', buf, off)
                    rgba = struct.unpack_from('<4B', buf, off + 8)
                    print(f'{ind}      versao={ver} flag={flag} rgba={rgba}')
                elif name == 'TCoordinateTransformation3D':
                    ver = struct.unpack_from('<I', buf, off)[0]
                    m = struct.unpack_from('<12d', buf, off + 4)
                    ident = all(abs(m[i] - (1.0 if i in (0, 4, 8) else 0.0)) < 1e-12
                                for i in range(9))
                    print(f'{ind}      versao={ver} rot_identidade={ident} '
                          f'trans={tuple(round(x, 4) for x in m[9:12])}')
                elif name == 'TQi3DIndexedTriangleMeshData':
                    ver, n_coord, res1 = struct.unpack_from('<3I', buf, off)
                    idx_off = off + 12 + n_coord * 8
                    n_idx, res2 = struct.unpack_from('<2I', buf, idx_off)
                    print(f'{ind}      versao={ver} nCoords={n_coord} '
                          f'({n_coord // 3} vértices) res1={res1} '
                          f'nIdx={n_idx} ({n_idx // 3} triângulos) res2={res2}')
                q = fim

            # GAP: do fim do payload conhecido até o próximo marcador válido
            r = q
            while r < n and buf[r] not in (OPEN, CLOSE):
                r += 1
            while r < n and buf[r] == OPEN and classe_em(buf, r) is None:
                r += 1
                while r < n and buf[r] not in (OPEN, CLOSE):
                    r += 1
            if r > q:
                gaps.setdefault((name, r - q), 0)
                gaps[(name, r - q)] += 1
                print(f'{ind}      GAP {r - q} bytes até @{r:08x}:')
                print(hexdump(buf, q, r, limite=96))
            p = q
            prof += 1
            continue

        if b == CLOSE:
            prof = max(0, prof - 1)
            p += 1
            continue
        p += 1

    print(f'\n=== RESUMO ===')
    print(f'nós: {nos}')
    print('\nGAPs observados (classe, tamanho) -> ocorrências:')
    for (cls, tam), qtd in sorted(gaps.items()):
        print(f'  {cls:32} gap={tam:5}  x{qtd}')
    print('\nBytes que precedem o 0x5B, por classe:')
    for cls, pres in sorted(prefixos.items()):
        print(f'  {cls:32} {sorted(pres)[:6]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('aq')
    ap.add_argument('sid', type=int)
    ap.add_argument('--max-nos', type=int, default=None)
    args = ap.parse_args()
    nome, blob = carregar_blob(args.aq, args.sid)
    print(f'SIMBOLOGIA_3D {args.sid}: {nome!r}')
    anatomia(blob, args.max_nos)


if __name__ == '__main__':
    main()
