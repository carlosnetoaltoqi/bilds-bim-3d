#!/usr/bin/env python3
"""
pdf_akato.py — remonta o catálogo da Akato a partir das células com coordenadas.

Entrada: o JSON do `pdf_coords.py` (uma célula por operador de texto, com x, y,
corpo da fonte e ordem de desenho).
Saída: JSON com as famílias de produto e as suas linhas
       {codigo, descricao, embalagem, master}.

COMO A TABELA É RECONSTRUÍDA
----------------------------
O Illustrator desenha cada tabela por **blocos de coluna**, não por linhas: o
bloco dos códigos, depois o dos masters, depois o cabeçalho, depois o das
descrições, depois o das embalagens. Cada bloco é um objeto de texto com o seu
próprio entrelinhamento, e vários deles estão com o entrelinhamento corrompido
— na página 6 o código `21004` sai em `y = 381,8` e a sua descrição em
`y = 277,6`; uma embalagem cai em `y = −63`, fora da página.

Portanto **agrupar por `y` monta linhas erradas**. O que se preserva é a ordem
dentro de cada bloco, que espelha a ordem visual das linhas. Então:

1. A página é dividida em duas regiões, metade esquerda e metade direita — os
   painéis de produto vêm em duas colunas e as suas tabelas se intercalam na
   ordem de desenho.
2. Dentro de uma região, cada tabela vai do seu cabeçalho `CÓDIGO` até o
   `CÓDIGO` seguinte, com duas exceções para blocos desenhados antes do próprio
   cabeçalho (documentadas em `fatiar_em_tabelas`).
3. Cada célula é atribuída a uma coluna por `x`, pela fronteira entre os
   âncoras dos cabeçalhos (`coluna_de`), e o tipo do conteúdo confirma a
   coluna: código é `\\d{4,5}`, embalagem e master são inteiros — o master pode
   vir com separador de milhar —, descrição tem dígito e unidade.
4. As colunas são acumuladas em ordem de desenho e casadas por **ordinal**:
   o i-ésimo código com a i-ésima descrição, i-ésima embalagem, i-ésimo master.

TÍTULO DA FAMÍLIA
-----------------
O título é um bloco de linhas em CAIXA ALTA ao lado da foto do produto. O `y`
dele também está corrompido, e de forma que inverte a ordem: na página 18 o
SIFÃO EXTENSÍVEL SIMPLES BRANCO é desenhado em `y = 218` e o DUPLO BRANCO em
`y = 312`, enquanto as suas tabelas estão em `y = 459` e `y = 222`. Ordenar os
títulos por `y` troca os dois.

A **ordem de desenho** dos blocos de título, ao contrário, acompanha a ordem
visual dos painéis nas 24 páginas. Então o casamento é por posto na ordem de
desenho: dentro de cada região, o n-ésimo bloco de título desenhado pertence à
n-ésima tabela desenhada. Isso acerta inclusive as páginas em que o título vem
depois da sua própria tabela (17 e 18).

Uso:
    python3 pdf_akato.py <celulas.json> <saida.json>
"""
import json
import re
import sys
import unicodedata

# --- Classificação de conteúdo -------------------------------------------

CABECALHOS = {'CÓDIGO', 'DESCRIÇÃO', 'EMB.', 'MASTER', 'EMB', 'DESCRICAO'}

RE_CODIGO = re.compile(r'^\*?(\d{4,5})$')
RE_QTD = re.compile(r'^(\d{1,3}(?:\.\d{3})*)$')
# Descrição: um dígito seguido de unidade, ou uma polegada, ou um DN.
#
# SEM re.IGNORECASE, e a unidade tem de vir logo depois do número. As unidades
# do catálogo são minúsculas (`mm`, `cm`, `m`, `g`), e é isso que separa uma
# descrição de um pedaço de título: `NORMAL 6M` e `SOLDÁVEL 6M` — o `6M` do
# tubo de 6 metros — casam com um `m` insensível a caixa, e `NORMAL 6M` cai na
# faixa x da coluna DESCRIÇÃO. Entrava como uma descrição a mais na família de
# cima e desalinhava a tabela toda a partir dali.
RE_DESC = re.compile(r'\d\s*(?:mm|cm|m|g)\b|["”]|\bDN\b')

# Polegada como aparece na tabela de conversão: 1/2", 1.1/4", 3".
RE_POLEGADA = re.compile(r'^\d+(?:\.\d+)?(?:/\d+)?["”]$')

# Quanto um valor pode começar à ESQUERDA do seu próprio cabeçalho. Acontece
# porque o valor é centralizado na coluna: `DN 100 x 100 x 50` na página 16
# começa 5,7 pt antes do `DESCRIÇÃO`.
FOLGA_ESQUERDA = 12.0

# Largura máxima que um valor pode avançar além do início da última coluna.
# O maior avanço legítimo observado é de 15 pt.
LARGURA_MAX_COLUNA = 40.0

# Faixa de corpo de fonte de um fragmento de título de família. Os títulos
# observados ficam entre 7,9 e 10,1 pt.
CORPO_TITULO_MIN = 7.5
CORPO_TITULO_MAX = 11.5

# Um título de família fica sempre bem à direita da coluna CÓDIGO da região —
# é o texto ao lado da foto. Isso separa o título do painel das legendas de
# margem ("SOLDÁVEL AKATO", "ROSCÁVEL AKATO"), que ficam colados na margem.
RECUO_MIN_TITULO = 90.0


def eh_caixa_alta(texto):
    """
    True se não há nenhuma letra minúscula — os títulos são todos assim.

    Testa a categoria Unicode `Ll`, não `str.islower()`: os indicadores
    ordinais `º` e `ª` respondem True a `islower()` mas são categoria `Lo`.
    Sem isso, `CURVA 90º` (páginas 12 a 15) é descartado como texto corrido e
    a família perde a primeira linha do título.
    """
    return not any(unicodedata.category(c) == 'Ll' for c in texto)


def tipo_conteudo(texto):
    """'codigo' | 'qtd' | 'desc' | 'titulo' | 'lixo'"""
    if texto in CABECALHOS:
        return 'cabecalho'
    if RE_CODIGO.match(texto):
        return 'codigo'
    if RE_QTD.match(texto):
        return 'qtd'
    if not eh_caixa_alta(texto):
        # Texto de marketing, notas, endereços, "Catálogo Construção Civil".
        # Descrições nunca têm minúscula exceto as poucas com "sem/com
        # registro" — tratadas antes, por casarem RE_DESC.
        return 'desc' if RE_DESC.search(texto) and len(texto) <= 24 else 'lixo'
    if RE_DESC.search(texto) and len(texto) <= 24:
        return 'desc'
    if len(texto) <= 24:
        return 'titulo'
    return 'lixo'


def numero(texto):
    return int(texto.replace('.', ''))


# --- Blocos (sequências de células com o mesmo x, em ordem de desenho) ----

def blocos(celulas, tol=1.0):
    """
    Agrupa células com o mesmo x que são vizinhas na ordem de desenho.

    A vizinhança em `ordem` é obrigatória. As linhas de um mesmo objeto de
    texto saem sempre em `ordem` consecutiva; sem essa checagem, dois títulos
    distantes que por acaso compartilham o x — `ADAPTADOR PARA CAIXA D´ÁGUA`
    na ordem 66-69 e `CURVA 90° CURTA` na 98-100, ambos em x = 475,9 — viram um
    bloco só, e a página fica com um título a menos que o número de tabelas.
    """
    saida = []
    for c in celulas:
        anterior = saida[-1][-1] if saida else None
        if (anterior and abs(anterior['x'] - c['x']) <= tol
                and c['ordem'] == anterior['ordem'] + 1):
            saida[-1].append(c)
        else:
            saida.append([c])
    return saida


GAP_CONTINUACAO = 8.0


def juntar_partidas(celulas, tol=0.6):
    """
    Une células consecutivas que continuam a mesma célula na mesma linha base.

    O Illustrator parte células em vários operadores `Tj`, e isso aparece de
    duas formas:

    - **Mesmo x, mesmo y.** O pypdf reporta a mesma matriz de texto para `Tj`
      consecutivos dentro de um objeto — não acumula o avanço dos glifos. Foi
      assim que `21052` chegou como `'2105'` + `'2'` na página 6.
    - **x avançado alguns pontos.** Quando há reposicionamento explícito, o
      segundo pedaço vem com o x já adiantado: na página 10 a descrição `1"` do
      nípel 21283 chega como `'1'` em x = 161,7 e `'"'` em x = 166,2. Sem juntar,
      o `'1'` é classificado como quantidade, é recusado pela coluna DESCRIÇÃO
      e sobra só o `'"'`.

    O limite de 8 pt é seguro: as colunas da tabela estão a 50 pt ou mais uma
    da outra, então nunca há duas células distintas tão próximas na mesma linha.
    """
    saida = []
    for c in celulas:
        ant = saida[-1] if saida else None
        if (ant and abs(ant['y'] - c['y']) <= tol
                and abs(ant['corpo'] - c['corpo']) <= 0.5
                and 0 <= c['x'] - ant['x'] <= GAP_CONTINUACAO):
            saida[-1] = dict(ant, texto=ant['texto'] + c['texto'])
        else:
            saida.append(dict(c))
    return saida


# --- Montagem das tabelas -------------------------------------------------

def regiao(celula, meio):
    return 'esq' if celula['x'] < meio else 'dir'


CHAVE_CABECALHO = {'DESCRIÇÃO': 'descricao', 'EMB.': 'embalagem',
                   'EMB': 'embalagem', 'MASTER': 'master'}


def fatiar_em_tabelas(celulas, meio):
    """
    {regiao: [tabela]} onde tabela = {'y', 'cols', 'dados'}.

    Uma tabela começa no seu cabeçalho `CÓDIGO` e vai até o `CÓDIGO` seguinte
    **da mesma região**, na ordem de desenho. A ordem de desenho é o critério —
    não o `y` — porque o `y` de vários blocos está corrompido: na página 12 as
    duas últimas embalagens da CURVA 90º LONGA estão em `y = 312` e `y = 299`,
    dentro da faixa vertical da tabela de baixo, e por `y` iriam para a tabela
    errada.

    Exceção do olhar para trás: em algumas famílias o Illustrator desenha o
    bloco de códigos **antes** do cabeçalho `CÓDIGO` da própria tabela — uma
    célula só na página 12 (ordem 68) e na 16 (ordens 43 e 59), mas as seis do
    JOELHO 90° SOLDÁVEL na página 7 (ordens 50 a 55). O recuo cobre a corrida
    inteira de códigos imediatamente anterior ao cabeçalho, parando no
    cabeçalho anterior, e ela entra no começo da lista para preservar a ordem
    das linhas.
    """
    tabelas = {'esq': [], 'dir': []}
    for reg in ('esq', 'dir'):
        na_regiao = [c for c in celulas if regiao(c, meio) == reg]
        indices = [i for i, c in enumerate(na_regiao) if c['texto'] == 'CÓDIGO']

        # Quem olha para trás, e qual índice cada um reivindica.
        reivindicado = {}
        for k, i in enumerate(indices):
            limite = indices[k - 1] if k else -1
            x_cab = na_regiao[i]['x']
            j = i - 1
            while j > limite:
                anterior = na_regiao[j]
                if (tipo_conteudo(anterior['texto']) != 'codigo'
                        or not (-FOLGA_ESQUERDA <= anterior['x'] - x_cab <= 40)):
                    break
                reivindicado[j] = i
                j -= 1

        for k, i in enumerate(indices):
            fim = indices[k + 1] if k + 1 < len(indices) else len(na_regiao)
            # A primeira tabela da região também recolhe o que foi desenhado
            # antes do seu cabeçalho. Na página 11 o TÊ DE REDUÇÃO ROSCÁVEL tem
            # masters, descrições e embalagens nas ordens 42 a 50 e o `CÓDIGO`
            # só na 51 — sem isto a família sai com os dois códigos e mais nada.
            # É seguro porque, em todas as outras páginas, o que vem antes do
            # primeiro cabeçalho é título, texto de marketing ou o número da
            # página, e nenhum deles sobrevive à classificação de conteúdo.
            inicio = 0 if k == 0 else i + 1
            cabecalho = na_regiao[i]
            tab = {'y': cabecalho['y'],
                   'ordem': cabecalho['ordem'],
                   'cols': {'codigo': cabecalho['x']},
                   'dados': []}
            # sorted(): o recuo é percorrido de trás para frente, então as
            # chaves entram em ordem decrescente e precisam voltar à ordem
            # visual das linhas.
            meus = {j for j in range(inicio, fim) if j != i}
            for j, dono in reivindicado.items():
                if dono == i:
                    meus.add(j)
                else:
                    meus.discard(j)
            # sorted(): mantém a ordem visual das linhas, e os índices do recuo
            # — sempre menores que o do cabeçalho — entram na frente.
            fatia = [na_regiao[j] for j in sorted(meus)]
            for c in fatia:
                chave = CHAVE_CABECALHO.get(c['texto'])
                if chave:
                    tab['cols'][chave] = c['x']
                else:
                    tab['dados'].append(c)
            tabelas[reg].append(tab)
    return tabelas


def coluna_de(celula, cols):
    """
    A coluna a que a célula pertence, ou None se está fora de todas.

    A decisão é por **fronteira entre âncoras**, não por uma banda de largura
    fixa em volta de cada cabeçalho: a coluna vai do seu próprio cabeçalho até
    o cabeçalho seguinte. Uma banda estreita perderia as descrições curtas, que
    são centralizadas e por isso ficam bem à direita do cabeçalho — na página
    21, `1"` sai em x = 161,2 com o `DESCRIÇÃO` em x = 137,0, 24 pt de
    distância, enquanto `1.1/4"` sai em x = 154,1.
    """
    ordenadas = sorted(cols.items(), key=lambda kv: kv[1])
    # À direita da última coluna a tabela acaba, e o que vem depois não é dado.
    # O número da página fica em x = 601,2, contra o `MASTER` em x = 546,9 — e
    # sendo `05` um inteiro, sem este corte ele entra como um master a mais.
    if celula['x'] > ordenadas[-1][1] + LARGURA_MAX_COLUNA:
        return None
    melhor = None
    for nome, x in ordenadas:
        if celula['x'] + FOLGA_ESQUERDA >= x:
            melhor = nome
        else:
            break
    return melhor


def blocos_de_titulo(celulas, meio, cols_por_regiao):
    """
    {regiao: [{'ordem':..., 'texto':...}]} — os títulos de família.

    Um bloco é uma sequência de fragmentos de título consecutivos na ordem de
    desenho e com o mesmo x. Dois cortes descartam o que não é título de
    família:

    - **recuo** — o título fica ao lado da foto, bem à direita da coluna
      CÓDIGO. Isso remove as legendas de margem (`SOLDÁVEL AKATO`,
      `ROSCÁVEL AKATO`) e os títulos de seção em x = 74.
    - **corpo** — entre 7,5 e 11,5 pt. Acima é título de seção (`ÁGUA FRIA` em
      19,2; `NOTAS` em 48,6); abaixo são os rótulos do infográfico da luva de
      correr na página 11, em 6,4 e 6,5 pt, que passam pelo recuo e senão
      contariam como um título a mais na região.
    """
    titulos = {'esq': [], 'dir': []}
    for bloco in blocos([c for c in celulas
                         if tipo_conteudo(c['texto']) == 'titulo'
                         and CORPO_TITULO_MIN <= c['corpo'] <= CORPO_TITULO_MAX]):
        reg = regiao(bloco[0], meio)
        x_codigo = cols_por_regiao.get(reg)
        if x_codigo is None or bloco[0]['x'] - x_codigo < RECUO_MIN_TITULO:
            continue
        titulos[reg].append({
            'ordem': bloco[0]['ordem'],
            'texto': ' '.join(c['texto'] for c in bloco),
        })
    return titulos


def tabelas_da_pagina(pagina):
    """[{pagina, regiao, titulo, linhas:[{codigo,descricao,embalagem,master}]}]"""
    meio = pagina['largura'] / 2
    celulas = juntar_partidas(pagina['celulas'])

    tabelas = fatiar_em_tabelas(celulas, meio)
    if not tabelas['esq'] and not tabelas['dir']:
        return [], []

    # x da coluna CÓDIGO por região, para o recuo dos títulos.
    x_codigo = {r: min((t['cols']['codigo'] for t in ts), default=None)
                for r, ts in tabelas.items()}

    avisos = []
    saida = []
    for reg in ('esq', 'dir'):
        # Casamento título ↔ tabela por POSTO NA ORDEM DE DESENHO, não por y.
        # O y do bloco de título está corrompido em várias páginas: na 18 o
        # título SIFÃO EXTENSÍVEL SIMPLES BRANCO é desenhado em y = 218 e o
        # DUPLO BRANCO em y = 312, invertidos em relação às suas tabelas
        # (y = 459 e y = 222). Já a ordem de desenho segue a ordem visual dos
        # painéis nas 24 páginas.
        ordenadas = sorted(tabelas[reg], key=lambda t: t['ordem'])
        titulos = blocos_de_titulo(celulas, meio, x_codigo)[reg]
        titulos.sort(key=lambda t: t['ordem'])

        for i, tab in enumerate(ordenadas):
            colunas = {'codigo': [], 'descricao': [], 'embalagem': [],
                       'master': []}
            for c in tab['dados']:
                tipo = tipo_conteudo(c['texto'])
                if tipo in ('titulo', 'lixo'):
                    continue
                col = coluna_de(c, tab['cols'])
                if col is None:
                    continue
                # O tipo do conteúdo tem de bater com a coluna: assim uma
                # legenda que caia na banda de EMB. não vira quantidade.
                if col == 'codigo' and tipo != 'codigo':
                    continue
                if col in ('embalagem', 'master') and tipo != 'qtd':
                    continue
                if col == 'descricao' and tipo != 'desc':
                    continue
                colunas[col].append(c['texto'])

            n = len(colunas['codigo'])
            if not n:
                continue
            titulo = titulos[i]['texto'] if i < len(titulos) else ''
            if not titulo:
                avisos.append(f"p{pagina['pagina']} {reg}: tabela sem título "
                              f"(códigos {colunas['codigo'][:3]})")
            for nome in ('descricao', 'embalagem', 'master'):
                if colunas[nome] and len(colunas[nome]) != n:
                    avisos.append(
                        f"p{pagina['pagina']} {reg} {titulo!r}: {n} códigos "
                        f"mas {len(colunas[nome])} valores em {nome}")

            linhas = []
            for j, codigo in enumerate(colunas['codigo']):
                emb = colunas['embalagem'][j] if j < len(colunas['embalagem']) else None
                mst = colunas['master'][j] if j < len(colunas['master']) else None
                emb = numero(emb) if emb else None
                mst = numero(mst) if mst else None
                # Invariante do catálogo: a caixa master nunca é menor que a
                # embalagem. Quando as duas colunas chegam trocadas por um
                # bloco fora de ordem, isto corrige — e o aviso registra.
                if emb is not None and mst is not None and mst < emb:
                    avisos.append(f"p{pagina['pagina']} {titulo!r} {codigo}: "
                                  f"emb={emb} > master={mst}, invertidos")
                    emb, mst = mst, emb
                linhas.append({
                    'codigo': codigo.lstrip('*'),
                    'descricao': (colunas['descricao'][j]
                                  if j < len(colunas['descricao']) else ''),
                    'embalagem': emb,
                    'master': mst,
                })
            saida.append({
                'pagina': pagina['pagina'],
                'regiao': reg,
                'titulo': titulo,
                'linhas': linhas,
            })
    return saida, avisos


# --- Seção (Linha Água Fria / Esgoto / Acessórios / Polietileno) ----------

SECOES = ['ÁGUA FRIA', 'ESGOTO', 'ACESSÓRIOS', 'POLIETILENO']


def secao_da_pagina(pagina, corrente):
    """A seção anunciada nesta página, ou a que vinha valendo."""
    for c in pagina['celulas']:
        if c['corpo'] < 13:
            continue
        alvo = _sem_acento(c['texto']).upper()
        for s in SECOES:
            if _sem_acento(s) in alvo:
                return s
    return corrente


def _sem_acento(s):
    return ''.join(ch for ch in unicodedata.normalize('NFD', s)
                   if unicodedata.category(ch) != 'Mn')


# --- Tabela de conversão polegada × milímetro (página 23) -----------------

def tabela_conversao(paginas):
    """
    [{polegada, pvc_soldavel_mm, pvc_esgoto_mm}] — a tabela de NOTAS.

    Vale para preencher DIAMETRO_PECA: o catálogo descreve as peças roscáveis
    em polegada e as soldáveis/esgoto em milímetro, e é esta tabela que liga as
    duas escalas.
    """
    for pag in paginas:
        celulas = [c for c in pag['celulas'] if c['corpo'] > 9.0]
        cabs = {c['texto'] for c in celulas}
        if 'POLEGADA' not in cabs or 'PVC SOLDÁVEL' not in cabs:
            continue
        x_pol = min(c['x'] for c in celulas if c['texto'] == 'POLEGADA')
        x_sol = min(c['x'] for c in celulas if c['texto'] == 'PVC SOLDÁVEL')
        x_esg = min(c['x'] for c in celulas if c['texto'] == 'PVC ESGOTO')
        linhas = {}
        for c in celulas:
            if c['texto'] in ('POLEGADA', 'PVC SOLDÁVEL', 'PVC ESGOTO',
                              'TABELA DE CONVERSÃO'):
                continue
            y = round(c['y'], 0)
            d = {abs(c['x'] - x_pol): 'polegada',
                 abs(c['x'] - x_sol): 'pvc_soldavel_mm',
                 abs(c['x'] - x_esg): 'pvc_esgoto_mm'}
            col = d[min(d)]
            linhas.setdefault(y, {})[col] = c['texto']
        saida = []
        for y in sorted(linhas, reverse=True):
            linha = linhas[y]
            # Só linhas cuja primeira coluna é de fato uma polegada: os títulos
            # `NOTAS` e `POLEGADAS X MILÍMETROS` também têm corpo grande e caem
            # na faixa x da coluna POLEGADA.
            if not RE_POLEGADA.match(linha.get('polegada', '')):
                continue
            saida.append({
                'polegada': linha['polegada'].replace('”', '"'),
                'pvc_soldavel_mm': _mm(linha.get('pvc_soldavel_mm')),
                'pvc_esgoto_mm': _mm(linha.get('pvc_esgoto_mm')),
            })
        return saida
    return []


def _mm(texto):
    if not texto or texto.strip() == '-':
        return None
    m = re.search(r'(\d+)', texto)
    return int(m.group(1)) if m else None


# --- Programa -------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        sys.exit('Uso: pdf_akato.py <celulas.json> <saida.json>')
    dados = json.load(open(sys.argv[1], encoding='utf-8'))

    familias, avisos = [], []
    secao = None
    for pag in dados['paginas']:
        secao = secao_da_pagina(pag, secao)
        tabs, avs = tabelas_da_pagina(pag)
        for t in tabs:
            t['secao'] = secao
        familias.extend(tabs)
        avisos.extend(avs)

    conversao = tabela_conversao(dados['paginas'])

    codigos = [l['codigo'] for f in familias for l in f['linhas']]
    repetidos = sorted({c for c in codigos if codigos.count(c) > 1})

    resultado = {
        'origem': dados['origem'],
        'conversao_polegada_mm': conversao,
        'familias': familias,
        'avisos': avisos,
        'resumo': {
            'familias': len(familias),
            'produtos': len(codigos),
            'codigos_repetidos': repetidos,
            'sem_descricao': sum(1 for f in familias for l in f['linhas']
                                 if not l['descricao']),
            'sem_embalagem': sum(1 for f in familias for l in f['linhas']
                                 if l['embalagem'] is None),
        },
    }
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)

    r = resultado['resumo']
    print(f"{r['familias']} famílias, {r['produtos']} produtos")
    print(f"  sem descrição: {r['sem_descricao']}   "
          f"sem embalagem: {r['sem_embalagem']}")
    print(f"  códigos repetidos: {r['codigos_repetidos'] or 'nenhum'}")
    print(f"  conversão polegada×mm: {len(conversao)} linhas")
    if avisos:
        print(f'  {len(avisos)} avisos:')
        for a in avisos:
            print(f'    - {a}')


if __name__ == '__main__':
    main()
