"""
entradas_aq.py — as `ENTRADA_3D`/`ENTRADA_PECA` do `.aq` a partir da malha.

Sem estas duas tabelas a peça não encaixa numa tubulação e o Builder **não desenha a
peça em planta e corte** — sai o símbolo padrão. Com elas, e com "Bifiliar realista"
diferente de "Simbologia 2D" (`OPCAO_RENDERIZACAO_PLANIFICADA`, que os dois escritores
gravam em 0 = Realista), o Builder monta o wireframe **em tempo de execução** e a peça
sai em planta na representação unifiliar — confirmado no Builder em 2026-09-10 e pela
própria equipe do Builder; o `WIREFRAME` gravado no `.aq` não é requisito. Nenhuma fonte
de geometria marca bocal, então a posição vem da malha, por `bim_pipeline.geometria.bocais`.

O rótulo **"Pontos de ligação 3D: Sim/Não"** do Cadastro **não** vem destas tabelas: vem
de `PECA.SECAO`/`PECA.DIAMETRO_INTERNO` estarem nulas — ver `secao_para_as_entradas`.

O QUE CADA COLUNA RECEBE, e de onde vem o valor (medido nas 15 bibliotecas nativas
disponíveis, 634 linhas de `ENTRADA_3D` e 3.405 de `ENTRADA_PECA`):

| coluna | valor | por quê |
|---|---|---|
| `ENTRADA_3D.POSICAO_X/Y/Z` | centro do bocal, cm Z-up | frame da peça: malha com o *placement* da simbologia aplicado |
| `ENTRADA_3D.TIPO_SECAO` | 0 | 608 de 634 linhas nativas |
| `ENTRADA_3D.DIAMETRO` | código de bitola | só existe no schema 607; nativa que preenche usa o mesmo código de `DIAMETRO_EP` |
| `ENTRADA_3D.BASE`/`ALTURA` | 0 | 634 de 634 |
| `ENTRADA_PECA.LIGACAO_EP` | 0 | o enum vai de 0 a 3, `TIPO_LIGACAO` está vazia nas nativas e o significado **não está determinado**; 0 é o valor mais comum (1.675 de 3.405). Não é índice da entrada: dentro da mesma peça aparecem `(0,0,0)`, `(1,1)`, `(2,1)` e `(0,3)` |
| `ENTRADA_PECA.DIAMETRO_EP` | código de bitola | é aqui que mora o diâmetro de uma conexão, não em `PECA.DIAMETRO_PECA` |
| `ENTRADA_PECA.SECAO_EP` | 10 | valor das entradas com geometria na nativa de conexões; a sentinela aparece onde a seção não é definida |
| `ENTRADA_PECA.ANGULO_EP` | azimute do bocal em grau | derivado da normal do bocal; nas nativas é 0/90/180/270 nas conexões ortogonais |
| `ENTRADA_PECA.COMPRIMENTO_EP` | 0 | comprimento equivalente, que a malha não dá |
| `ENTRADA_PECA.BASE_EP`/`ALTURA_EP` | 0 | 2.887 de 3.405 |
| `PECA.SECAO` e `PECA.DIAMETRO_INTERNO` | **NULL** | 1.441 de 1.441 peças nativas com entrada; é o que acende "Pontos de ligação 3D: Sim" |

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

# Máximo de bocais que uma simbologia nativa tem: 38 (as 634 linhas nativas se distribuem em
# 2 na metade dos casos, 4 em dois terços, e a cauda vai até 38). Acima disso a "peça" não é
# peça conectável — é um projeto inteiro virando uma simbologia, e a malha tem dezenas de pontas
# de tubo que não são ponto de ligação de nada.
LIMITE_POR_SIMBOLOGIA = 38

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


def plausivel(entradas, limite=LIMITE_POR_SIMBOLOGIA):
    """A quantidade de bocais cabe no que uma peça de verdade tem?

    Quem chama **reporta** o descarte em vez de gravar, e não trunca: escolher 38 de 107
    bocais seria inventar quais deles são ponto de ligação.
    """
    return len(entradas) <= limite


def secao_para_as_entradas(con, ids_peca):
    """Anula `PECA.SECAO` e `PECA.DIAMETRO_INTERNO` das peças que ganharam entrada.

    Peça com ponto de ligação 3D tira seção e diâmetro **das entradas**, não do cadastro
    da peça: nas 14 bibliotecas nativas, as duas colunas estão nulas em **1.441 de 1.441**
    peças com `ENTRADA_PECA`, e valem 10 (o *default* do schema) só em peças sem entrada
    nenhuma — e isso dentro da mesma biblioteca, não por convenção de fabricante (na de
    esgoto, 1.115 peças com entrada têm as duas nulas e 48 sem entrada têm 10; na de
    barramento, 220 contra 32). Os dois escritores não nomeavam as colunas, então o
    *default* entrava, e a peça abria no Cadastro com **"Pontos de ligação 3D: Não"**
    mesmo com as entradas gravadas e desenhadas (os pontos vermelhos apareciam no lugar
    certo) — medido no Builder em 2026-09-10, nas bibliotecas de conexões, de válvulas e
    de esgoto.

    Que anular as duas **acenda** o "Sim" é hipótese até o próximo teste no Builder: o que
    está medido é a correlação (1.441/1.441, dentro da mesma biblioteca) e que as entradas
    já são lidas, porque os pontos vermelhos saem no lugar certo. Depois de anular não
    sobra diferença sistemática entre peça nossa com entrada e peça nativa com entrada.
    """
    con.executemany('UPDATE PECA SET SECAO = NULL, DIAMETRO_INTERNO = NULL WHERE ID_PECA = ?',
                    [(int(i),) for i in ids_peca])


def gravar(g, entradas, id_simbologia=None, ids_peca=()):
    """Grava as entradas com o `EscritorAq` `g`. Devolve quantas linhas escreveu.

    `id_simbologia` recebe as `ENTRADA_3D` (a posição é da geometria); cada peça de
    `ids_peca` recebe uma `ENTRADA_PECA` por bocal (a bitola é da peça). Uma peça sem
    geometria não tem de onde tirar entrada e não entra aqui. Quem recebe entrada tem a
    seção anulada na `PECA` — ver `secao_para_as_entradas`.
    """
    n = 0
    if entradas and ids_peca:
        secao_para_as_entradas(g.con, ids_peca)
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
