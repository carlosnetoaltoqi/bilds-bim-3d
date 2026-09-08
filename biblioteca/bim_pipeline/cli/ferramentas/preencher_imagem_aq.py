#!/usr/bin/env python3
"""
preencher_imagem_aq.py — preenche `SIMBOLOGIA_3D.IMAGEM` num `.aq` JÁ EXPORTADO.

Para que existe: até 2026-09-08 os dois escritores do projeto gravavam a geometria e
deixavam a `IMAGEM` nula, e o AltoQi Builder **não desenha a peça** sem esse BMP (o
experimento que isolou o campo está em `bim_pipeline.aq.imagem_aq`). Os escritores já
foram corrigidos — quem for exportar de novo não precisa desta ferramenta. Ela serve
para as bibliotecas que já estão na mão de alguém: em vez de repetir a importação (que
depende de serviços e banco de pé), lê o OQ3D de cada simbologia, rasteriza e grava.

Não inventa nada: a imagem sai da mesma malha que está no arquivo, pelo mesmo módulo
que os escritores usam. Simbologia que já tem `IMAGEM` é preservada, a não ser com
`--refazer`.

Uso:
    python3 -m bim_pipeline.cli.ferramentas.preencher_imagem_aq <arquivo.aq> [--saida copia.aq]
                                                                [--refazer] [--quiet]

Sem `--saida` o arquivo é alterado no lugar. Depois, confira com
`python3 -m bim_pipeline.cli.ferramentas.validar_aq <arquivo.aq>`.
"""
import argparse
import os
import shutil
import sqlite3
import sys

from bim_pipeline.aq import imagem_aq
from bim_pipeline.aq import oq3d


def preencher(caminho, refazer=False, progresso=None):
    """
    Devolve `(preenchidas, puladas, falhas)`. Um `.aq` que é ZIP não é aceito: a
    escrita exige o SQLite direto, que é o que os dois escritores produzem.
    """
    if not os.path.isfile(caminho):
        raise FileNotFoundError(caminho)
    con = sqlite3.connect(caminho)
    try:
        alvos = con.execute(
            'SELECT ID_SIMBOLOGIA_3D FROM SIMBOLOGIA_3D'
            + ('' if refazer else ' WHERE IMAGEM IS NULL')
            + ' ORDER BY ID_SIMBOLOGIA_3D').fetchall()
        total = con.execute('SELECT COUNT(*) FROM SIMBOLOGIA_3D').fetchone()[0]
        preenchidas, falhas = 0, []
        for i, (sid,) in enumerate(alvos, start=1):
            blob = con.execute('SELECT CAST(SIMBOLOGIA_3D AS BLOB) FROM SIMBOLOGIA_3D '
                               'WHERE ID_SIMBOLOGIA_3D = ?', (sid,)).fetchone()[0]
            if blob is None or not oq3d.is_oq3d(bytes(blob)):
                falhas.append((sid, 'blob não é OQ3D'))
                continue
            # `oq3d.extract` já resolve instâncias e transforms; o rasterizador recebe
            # a mesma tupla que `oq3d_writer.escrever` consome.
            malhas = [(v, t, rgba, None) for v, t, rgba in oq3d.extract(bytes(blob))]
            bmp = imagem_aq.render(malhas)
            if bmp is None:
                falhas.append((sid, 'nenhum triângulo na malha'))
                continue
            con.execute('UPDATE SIMBOLOGIA_3D SET IMAGEM = ? WHERE ID_SIMBOLOGIA_3D = ?',
                        (sqlite3.Binary(bmp), sid))
            preenchidas += 1
            if progresso and (i % 25 == 0 or i == len(alvos)):
                progresso(f'{i}/{len(alvos)} simbologias')
        con.commit()
    finally:
        con.close()
    return preenchidas, total - len(alvos), falhas


def main(argv=None):
    ap = argparse.ArgumentParser(description='preenche SIMBOLOGIA_3D.IMAGEM num .aq já exportado')
    ap.add_argument('aq')
    ap.add_argument('--saida', default=None, help='grava numa cópia em vez de alterar no lugar')
    ap.add_argument('--refazer', action='store_true', help='refaz também as que já têm IMAGEM')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)

    destino = args.saida or args.aq
    if args.saida:
        shutil.copy(args.aq, args.saida)

    def progresso(msg):
        if not args.quiet:
            print(f'  {msg}', flush=True)

    preenchidas, puladas, falhas = preencher(destino, refazer=args.refazer, progresso=progresso)
    if not args.quiet:
        print(f'{destino}: {preenchidas} imagens gravadas, {puladas} já tinham, {len(falhas)} falhas')
        for sid, motivo in falhas[:10]:
            print(f'  FALHA simbologia {sid}: {motivo}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
