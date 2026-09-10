#!/usr/bin/env python3
"""
preencher_entradas_aq.py — preenche `ENTRADA_3D`/`ENTRADA_PECA` num `.aq` JÁ EXPORTADO.

Para que existe: até 2026-09-09 os dois escritores gravavam a geometria sem ponto de
ligação nenhum, e uma peça assim não encaixa em tubulação e **não é desenhada em planta e
corte** — sai o símbolo padrão, um círculo com o triângulo. Os escritores já foram
corrigidos; esta ferramenta serve para as bibliotecas que já estão na mão de alguém, sem
repetir a importação.

Não inventa ponto de ligação: lê o OQ3D de cada simbologia e procura bocal na própria
malha (`bim_pipeline.geometria.bocais` — ponta de tubo ou face de flange). Simbologia sem
bocal reconhecível fica sem entrada, e a ferramenta diz quantas foram.

Também anula `PECA.SECAO`/`PECA.DIAMETRO_INTERNO` de toda peça com entrada — inclusive
num `.aq` que **já** tinha entradas, que é o caso das bibliotecas de 2026-09-09: elas
desenham os pontos de ligação no lugar certo e mesmo assim abrem com "Pontos de ligação
3D: Não", porque a seção ficou no cadastro da peça (ver
`bim_pipeline.aq.entradas_aq.secao_para_as_entradas`).

Depois de preencher, o Builder ainda precisa da opção "Bifiliar realista" diferente de
"Simbologia 2D" para desenhar a peça em planta (`PECA.OPCAO_RENDERIZACAO_PLANIFICADA`, que
os dois escritores gravam em 0 = Realista); o wireframe em si ele monta em tempo de
execução, não precisa estar no arquivo.

Uso:
    python3 -m bim_pipeline.cli.ferramentas.preencher_entradas_aq <arquivo.aq> [--saida copia.aq]
                                                                  [--refazer] [--quiet]

Sem `--saida` o arquivo é alterado no lugar. Depois, confira com
`python3 -m bim_pipeline.cli.ferramentas.validar_aq <arquivo.aq>`.
"""
import argparse
import os
import shutil
import sqlite3
import sys

from bim_pipeline.aq import entradas_aq
from bim_pipeline.aq import oq3d


class _Escritor:
    """O mínimo do `EscritorAq` que o `entradas_aq.gravar` usa, sobre uma conexão aberta."""

    def __init__(self, con):
        self.con = con
        self._proximo = {}

    def novo(self, tabela):
        if tabela not in self._proximo:
            chave = 'ID_ENTRADA' if tabela == 'ENTRADA_3D' else 'ID_ENTRADA_PECA'
            maximo = self.con.execute(f'SELECT MAX({chave}) FROM {tabela}').fetchone()[0]
            self._proximo[tabela] = (maximo or 0) + 1
        valor = self._proximo[tabela]
        self._proximo[tabela] = valor + 1
        return valor

    def ins(self, tabela, **campos):
        colunas = ', '.join(campos)
        marcas = ', '.join('?' for _ in campos)
        self.con.execute(f'INSERT INTO {tabela} ({colunas}) VALUES ({marcas})',
                         tuple(campos.values()))


def preencher(caminho, refazer=False, progresso=None):
    """
    Devolve `(entradas, simbologias_com_bocal, simbologias_sem_bocal, falhas, secao)`,
    onde `secao` é `{'com_entrada': …, 'corrigidas': …}` — quantas peças ficaram com a
    seção nas entradas e quantas delas precisaram da varredura de conserto.

    Um `.aq` que é ZIP não é aceito: a escrita exige o SQLite direto, que é o que os dois
    escritores produzem.
    """
    if not os.path.isfile(caminho):
        raise FileNotFoundError(caminho)
    con = sqlite3.connect(caminho)
    try:
        ja_tem = {r[0] for r in con.execute('SELECT DISTINCT ID_SIMBOLOGIA_3D FROM ENTRADA_3D')}
        if refazer and ja_tem:
            con.execute('DELETE FROM ENTRADA_3D')
            con.execute('DELETE FROM ENTRADA_PECA')
            ja_tem = set()
        alvos = [r[0] for r in con.execute(
            'SELECT ID_SIMBOLOGIA_3D FROM SIMBOLOGIA_3D ORDER BY ID_SIMBOLOGIA_3D')
            if r[0] not in ja_tem]

        g = _Escritor(con)
        n_entradas = com_bocal = 0
        sem_bocal, falhas = [], []
        for i, sid in enumerate(alvos, start=1):
            blob = con.execute('SELECT CAST(SIMBOLOGIA_3D AS BLOB) FROM SIMBOLOGIA_3D'
                               ' WHERE ID_SIMBOLOGIA_3D = ?', (sid,)).fetchone()[0]
            if blob is None or not oq3d.is_oq3d(bytes(blob)):
                falhas.append((sid, 'blob não é OQ3D'))
                continue
            # A simbologia exportada por este projeto tem DESLOCAMENTO e ANGULO_PLANO em
            # zero, então a malha do OQ3D já está no frame da peça, que é o da ENTRADA_3D.
            malhas = [(v, t, rgba, None) for v, t, rgba in oq3d.extract(bytes(blob))]
            try:
                entradas = entradas_aq.derivar(malhas)
            except Exception as e:                     # noqa: BLE001 — a malha é de terceiro
                falhas.append((sid, f'{type(e).__name__}: {e}'))
                continue
            if not entradas:
                sem_bocal.append(sid)
                continue
            if not entradas_aq.plausivel(entradas):
                falhas.append((sid, f'{len(entradas)} bocais na malha — fora do que uma peça '
                                    f'tem (projeto inteiro numa simbologia?); nada gravado'))
                continue
            pecas = [r[0] for r in con.execute(
                'SELECT ID_PECA FROM PECA_SIMBOLOGIA_3D WHERE ID_SIMBOLOGIA_3D = ?', (sid,))]
            n_entradas += entradas_aq.gravar(g, entradas, id_simbologia=sid, ids_peca=pecas)
            com_bocal += 1
            if progresso and (i % 25 == 0 or i == len(alvos)):
                progresso(f'{i}/{len(alvos)} simbologias, {n_entradas} entradas')

        # Uma varredura sobre TODAS as peças com entrada, não só as desta rodada: o `.aq`
        # que já saiu com entradas (as bibliotecas de 2026-09-09) tem a seção no cadastro
        # da peça e por isso abre com "Pontos de ligação 3D: Não" mesmo com os pontos
        # certos. Sem isto, `ja_tem` faria a ferramenta pular justamente esses arquivos.
        pendentes = [r[0] for r in con.execute(
            'SELECT ID_PECA FROM PECA p WHERE EXISTS'
            ' (SELECT 1 FROM ENTRADA_PECA e WHERE e.ID_PECA = p.ID_PECA)'
            ' AND (p.SECAO IS NOT NULL OR p.DIAMETRO_INTERNO IS NOT NULL)')]
        entradas_aq.secao_para_as_entradas(con, pendentes)
        com_entrada = con.execute('SELECT COUNT(DISTINCT ID_PECA) FROM ENTRADA_PECA').fetchone()[0]
        con.commit()
    finally:
        con.close()
    secao = {'com_entrada': com_entrada, 'corrigidas': len(pendentes)}
    return n_entradas, com_bocal, sem_bocal, falhas, secao


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='preenche ENTRADA_3D/ENTRADA_PECA num .aq já exportado, achando os bocais na malha')
    ap.add_argument('aq')
    ap.add_argument('--saida', default=None, help='grava numa cópia em vez de alterar no lugar')
    ap.add_argument('--refazer', action='store_true',
                    help='apaga as entradas existentes e detecta tudo de novo')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)

    destino = args.saida or args.aq
    if args.saida:
        shutil.copy(args.aq, args.saida)

    def progresso(msg):
        if not args.quiet:
            print(f'  {msg}', flush=True)

    entradas, com_bocal, sem_bocal, falhas, secao = preencher(destino, refazer=args.refazer,
                                                              progresso=progresso)
    if not args.quiet:
        print(f'{destino}: {entradas} entradas em {com_bocal} simbologias; '
              f'{len(sem_bocal)} sem bocal reconhecível, {len(falhas)} falhas; '
              f"{secao['com_entrada']} peças com a seção nas entradas"
              + (f" ({secao['corrigidas']} corrigidas agora)" if secao['corrigidas'] else ''))
        for sid, motivo in falhas[:10]:
            print(f'  FALHA simbologia {sid}: {motivo}')
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
