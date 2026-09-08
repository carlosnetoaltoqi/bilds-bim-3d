"""
entradas_aq.py — as `ENTRADA_3D`/`ENTRADA_PECA` do `.aq` a partir da malha.

Sem estas duas tabelas a peça abre no Cadastro com "Pontos de ligação 3D: Não", não
encaixa numa tubulação e o Builder **não gera o wireframe** que desenha a peça em planta
e corte (a geração é condicionada aos pontos de ligação e à opção "Bifiliar realista"
diferente de "Simbologia 2D" — `OPCAO_RENDERIZACAO_PLANIFICADA`, que os dois escritores
já gravam em 0 = Realista). Nenhuma fonte de geometria marca bocal, então a posição vem
da malha, por `bim_pipeline.geometria.bocais`.

O QUE CADA COLUNA RECEBE, e de onde vem o valor (medido nas 15 bibliotecas nativas
disponíveis, 634 linhas de `ENTRADA_3D` e 3.405 de `ENTRADA_PECA`):

| coluna | valor | por quê |
|---|---|---|
| `ENTRADA_3D.POSICAO_X/Y/Z` | centro do bocal, cm Z-up | frame da peça: malha com o *placement* da simbologia aplicado |
| `ENTRADA_3D.TIPO_SECAO` | 0 | 608 de 634 linhas nativas |
| `ENTRADA_3D.DIAMETRO` | código de bitola | só existe no schema 607; nativa que preenche usa o mesmo código de `DIAMETRO_EP` |
| `ENTRADA_3D.BASE`/`ALTURA` | 0 | 634 de 634 |
| `ENTRADA_PECA.LIGACAO_EP` | 0 | o enum vai de 0 a 3, `TIPO_LIGACAO` está vazia nas nativas e o significado **não está determinado**; 0 é o valor mais comum (1.675 de 3.405) |
| `ENTRADA_PECA.DIAMETRO_EP` | código de bitola | é aqui que mora o diâmetro de uma conexão, não em `PECA.DIAMETRO_PECA` |
| `ENTRADA_PECA.SECAO_EP` | 10 | valor das entradas com geometria na nativa de conexões; a sentinela aparece onde a seção não é definida |
| `ENTRADA_PECA.ANGULO_EP` | azimute do bocal em grau | derivado da normal do bocal; nas nativas é 0/90/180/270 nas conexões ortogonais |
| `ENTRADA_PECA.COMPRIMENTO_EP` | 0 | comprimento equivalente, que a malha não dá |
| `ENTRADA_PECA.BASE_EP`/`ALTURA_EP` | 0 | 2.887 de 3.405 |

O código de bitola é o índice da escala nominal do AltoQi (`aq_writer.CODIGO_DIAMETRO`),
não uma medida. O raio interno do bocal cai em cima do nominal nas nativas de conexão
(2,56 cm ↔ 50 mm, 5,08 ↔ 100, 10,00 ↔ 200), por isso a conversão é por nominal mais
próximo, com tolerância — bocal fora da escala fica **sem** código (sentinela), como as
conexões nativas cujo diâmetro só existe na entrada.
"""
import math

from bim_pipeline.aq.aq_writer import CODIGO_DIAMETRO, SENT_INT
from bim_pipeline.geometria.bocais import bocais

# Tolerância da conversão raio → nominal: o raio interno da malha nativa fica a menos de
# 3 % do nominal (2,56 cm para 50 mm é +2,4 %). 8 % dá folga para tesselação grosseira
# sem deixar um bocal de 60 mm virar 50.
TOLERANCIA_NOMINAL = 0.08

TIPO_SECAO_PADRAO = 0
SECAO_EP_PADRAO = 10
LIGACAO_EP_PADRAO = 0


def codigo_diametro(raio_cm):
    """Raio interno em cm → código de bitola do AltoQi, ou `None` fora da escala."""
    diametro_mm = 2.0 * float(raio_cm) * 10.0
    melhor, erro_melhor = None, None
    for nominal, codigo in CODIGO_DIAMETRO.items():
        erro = abs(diametro_mm - nominal) / nominal
        if erro <= TOLERANCIA_NOMINAL and (erro_melhor is None or erro < erro_melhor):
            melhor, erro_melhor = codigo, erro
    return melhor


def azimute(normal):
    """Normal do bocal → `ANGULO_EP` em grau, no intervalo [0, 360).

    É a direção do bocal no plano da planta. Um bocal vertical (normal em Z) não tem
    azimute definido e recebe 0, como as entradas verticais das nativas.
    """
    x, y = float(normal[0]), float(normal[1])
    if math.hypot(x, y) < 1e-6:
        return 0.0
    return math.degrees(math.atan2(y, x)) % 360.0


def derivar(malhas, **limites):
    """Malhas em cm Z-up (frame da peça) → `[{posicao, raio, codigo, angulo, normal}]`.

    Os `limites` vão para `bocais.bocais` (`raio_min`, `raio_max`, `folga_area`).
    """
    saida = []
    for bocal in bocais(malhas, **limites):
        saida.append({
            'posicao': tuple(float(c) for c in bocal['centro']),
            'raio': float(bocal['raio']),
            'codigo': codigo_diametro(bocal['raio']),
            'angulo': azimute(bocal['normal']),
            'normal': tuple(float(c) for c in bocal['normal']),
        })
    return saida


def gravar(g, entradas, id_simbologia=None, ids_peca=()):
    """Grava as entradas com o `EscritorAq` `g`. Devolve quantas linhas escreveu.

    `id_simbologia` recebe as `ENTRADA_3D` (a posição é da geometria); cada peça de
    `ids_peca` recebe uma `ENTRADA_PECA` por bocal (a bitola é da peça). Uma peça sem
    geometria não tem de onde tirar entrada e não entra aqui.
    """
    n = 0
    for entrada in entradas:
        codigo = entrada['codigo']
        if id_simbologia is not None:
            x, y, z = entrada['posicao']
            g.ins('ENTRADA_3D', ID_ENTRADA=g.novo('ENTRADA_3D'),
                  POSICAO_X=x, POSICAO_Y=y, POSICAO_Z=z,
                  TIPO_SECAO=TIPO_SECAO_PADRAO,
                  DIAMETRO=codigo if codigo is not None else 0,
                  BASE=0.0, ALTURA=0.0, ID_SIMBOLOGIA_3D=id_simbologia)
            n += 1
        for id_peca in ids_peca:
            g.ins('ENTRADA_PECA', ID_ENTRADA_PECA=g.novo('ENTRADA_PECA'),
                  LIGACAO_EP=LIGACAO_EP_PADRAO,
                  DIAMETRO_EP=codigo if codigo is not None else SENT_INT,
                  SECAO_EP=SECAO_EP_PADRAO, COMPRIMENTO_EP=0.0,
                  ANGULO_EP=entrada['angulo'], BASE_EP=0.0, ALTURA_EP=0.0,
                  ID_PECA=id_peca)
            n += 1
    return n
