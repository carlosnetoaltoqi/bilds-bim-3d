# Achados para a documentação do projeto

Cinco coisas que este estudo descobriu e que contradizem ou completam o
`CLAUDE.md` e a skill `docs/skills/leitor-biblioteca-aq/SKILL.md`.

**Aplicados na documentação em 2026-09-02.** Os achados 1, 2 e 3 estão agora no
`CLAUDE.md` e na skill `leitor-biblioteca-aq` (2.3.0), como manda a regra do
`CLAUDE.md`: "ao descobrir qualquer coisa nova sobre ler `.aq`, registre nos dois
lugares". O 4 entrou como recomendação nos dois. O 5 é defeito de código e segue
**pendente** — a correção está descrita abaixo.

Este documento continua sendo o registro de onde cada coisa foi descoberta e por quê.

---

## Achado 1 — `DIAMETRO_PECA` é um código, não um centímetro

**Onde está errado:** `docs/skills/leitor-biblioteca-aq/SKILL.md` 2.2.0, tabela
da tabela `PECA`:

> | `DIAMETRO_PECA` | REAL | Diâmetro nominal (cm) |

**O que é:** um índice numa escala de diâmetros nominais do AltoQi. Na Amanco,
a peça `50 mm - 2"` tem `DIAMETRO_PECA = 9` e a `100 mm - 4"` tem 12 — não 5,0
e 10,0.

| `NOME_PECA` | `DIAMETRO_PECA` |
|---|---|
| `40 mm - 1.1/2"` | 8 |
| `50 mm - 2"` | 9 |
| `75 mm - 3"` | 11 |
| `100 mm - 4"` | 12 |
| `150 mm - 6"` | 14 |
| `200 mm - 8"` | 15 |

`ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO` usam a mesma escala. A
Dancor grava 7 a 11 nos bocais das suas bombas, cujas sucções e recalques vão
de 1.1/4" a 3", o que encaixa em 32, 40, 50, 60 e 75 mm — e confirma o código
10 como 60 mm, que a Amanco não mostra.

**Também:** das 1.168 peças da Amanco, 963 (82%) trazem
`-1.7976931348623157e+308` (`-DBL_MAX`), a sentinela de "não definido", 93 trazem zero e
112 trazem código — 48 de tubo, 52 de caixa sifonada e afins, 12 de ralo. **Nenhuma das
700 conexões traz código:** o diâmetro de uma conexão mora em `ENTRADA_PECA`.

**Por que importa para quem lê:** o `build_product_map` do `read_aq.py` expõe o
campo como `'diametro_cm'`. Qualquer consumidor que trate esse número como
centímetro erra por um fator de ~2 nas peças de tubo e recebe `-1.8e308` nas
outras.

**Onde corrigir:** a tabela da `PECA` na skill (bump para 2.3.0 e nota no
histórico), a seção "Conhecimento crítico: read_aq.py" do `CLAUDE.md`, e o nome
da chave `diametro_cm` no `build_product_map`.

> `PECA.DIAMETRO_INTERNO`, ao contrário, é milímetro de verdade: 192,8 / 144,8 /
> 98,0 / 47,5.

---

## Achado 2 — o `.aq` grava cp1252 num banco declarado UTF-8, e isso vale para quem escreve

**O que já está documentado:** a skill 2.1.0 e o `CLAUDE.md` cobrem bem o lado
da leitura — `text_factory` cp1252, a faixa 0x80–0x9F, o `CAST(col AS BLOB)`
nas colunas binárias.

**O que falta:** o mecanismo, e o que ele implica para escrever.

```
PRAGMA encoding                   → UTF-8
SELECT typeof(NOME_CP) …          → text
SELECT NOME_CP FROM CLASSE_PECA   → b'Bomba de Combate a Inc\xeancio - Dancor'
```

O banco **declara UTF-8** e guarda bytes cp1252. O SQLite não valida a
codificação do que se manda gravar, e o valor continua tipado como `text`.

**A consequência para escrever** é que o padrão do módulo `sqlite3` do Python
está errado: ele vincula `str` como UTF-8. Gravar assim produz mojibake na
leitura — `'Soldável'` volta `'SoldÃ¡vel'` — sem levantar exceção em lugar
nenhum. Aconteceu na primeira versão do gerador deste estudo. É o mesmo bug de
produção de 2026-08-28 registrado no `CLAUDE.md`, do outro lado.

O jeito de gravar certo:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes sem converter. Verificado: `typeof()`
volta `'text'`, os bytes ficam idênticos aos de uma biblioteca real, e o
`_decode_texto` do projeto devolve a string original.

**A checagem que pega:** os bytes altos das colunas de texto não podem ser
UTF-8 válido. Em cp1252 um acento é um byte alto isolado, que é UTF-8
inválido; em UTF-8 são dois bytes. Implementada em `tools/validar_aq.py`,
passo 7.

**Onde registrar:** um bloco "Escrever `.aq`" na skill, e na seção de encoding
do `CLAUDE.md`.

---

## Achado 3 — o parser de OQ3D promove nós a raiz em duas bibliotecas

O cabeçalho OQ3D tem, no offset 29, um `u32` com o **número de objetos-raiz**.
Comparando esse campo com o que o `scripts/oq3d.py` conta, em **todas** as 783
geometrias das 12 bibliotecas de fabricante:

| | |
|---|---|
| geometrias conferidas | 783 |
| divergem | **54 (6,9%)** |
| bibliotecas afetadas | **6 de 12** |

As seis: as cinco da Intelbras que têm geometria (CFTV 4/55, Cont_Acesso 4/10,
PPCI 4/11, SDAI 6/25, Sensor_Alarme 5/16) e a **Maxbar, com 31 de 135**.

O parse encontra **sempre mais** raízes, nunca menos, e a diferença vai de
**+2 a +10**. Não é sempre par — `+7` aparece 3 vezes e `+9` seis —, o que
**descarta** a explicação simples de "um `0x5D` desempilha um nível e promove
dois filhos" como regra única: o desempilhamento espúrio acontece em
quantidade variável dentro do mesmo blob.

> Vale registrar como o número mudou. Medindo duas geometrias por biblioteca, o
> resultado parecia "2 de 24, sempre +2" — pequeno e com explicação limpa.
> Medindo todas, virou "54 de 783, de +2 a +10, com valores ímpares". A amostra
> não estava só imprecisa: ela sugeria um mecanismo que os dados completos
> refutam.

**Impacto prático:** a geometria emitida é a mesma — o `_collect` desce a árvore
inteira de qualquer jeito. O que muda é a hierarquia, e com ela a composição
dos transforms dos nós promovidos. Nas seis bibliotecas afetadas (Intelbras e
Maxbar, ambas de equipamento) as malhas já vêm em coordenadas de mundo, então
não aparece. Numa biblioteca de conexões, apareceria.

**Aplicado em 2026-09-02:** `oq3d.n_raizes_declarado()` lê o campo e o
`parse()` avisa com `OQ3DAvisoParse` quando divergem — troca o erro silencioso
por algo visível. O cabeçalho inteiro está documentado no `CLAUDE.md` e na
skill 2.3.0.

---

## Achado 4 — a cascata de fabricante não tem âncora numa biblioteca sem geometria

O `peek_aq` do `build.py` infere o fabricante em cinco passos. Os dois
primeiros são dados do banco:

1. prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE`
2. `PECA.BIBLIOTECA`

**Uma biblioteca sem geometria não tem o passo 1** — não existe
`CLASSE_SIMBOLOGIA_3D`. E o passo 2 está **vazio nas 12 bibliotecas reais**,
como a própria skill avisa ("não confie nela"). Sobram os três passos que
dependem do nome da pasta e do arquivo.

Isso é um risco real para o pipeline: um `.aq` legítimo de fabricante cujas
peças não tenham forma fixa — tubos e kits, que a Amanco tem em 27% das peças —
publicaria com o fabricante vindo do nome de uma pasta.

**Recomendação para quem gera `.aq`:** preencher `PECA.BIBLIOTECA`. É uma
coluna que existe, que a cascata já consulta e que nenhum fabricante usa. O
gerador deste estudo preenche com `'Akato'`, e é por isso que a variante sem
geometria ainda infere o fabricante certo.

---

## Achado 5 — `saida` e `output` faltam em `_GENERIC_DIRS`

`scripts/build.py:922`:

```python
_GENERIC_DIRS = {'input', 'biblioteca', 'bibliotecas', 'bim', 'ifc', 'aq',
                 'downloads', 'arquivos', 'temp', 'tmp', '.', ''}
```

O título do catálogo vem da pasta pai do `.aq` quando ela é "descritiva", e a
lista acima é o que define não-descritiva. `saida`, `output`, `out`, `dist` e
`build` não estão nela.

**Sintoma observado:** um `.aq` em `eng-reversa/saida/` saiu com o título
`'Saida'` — e a checagem "título diferente do fabricante" passou, porque
`'Saida'` de fato é diferente de `'Akato'`. O valor é lixo e nenhuma validação
acusa.

**Correção:** acrescentar `'saida'`, `'output'`, `'out'`, `'dist'` e `'build'`
ao conjunto. Uma linha.

**Contorno usado aqui:** o `.aq` gerado mora em
`saida/Akato/PVC Construção Civil/`, e o título sai `'PVC Construção Civil'`.

---

## Nota sobre modificações no repositório

Durante esta sessão, três arquivos do projeto apareceram modificados **sem que
este estudo os tocasse**:

```
 M scripts/build.py
 M templates/layouts/catalog-grid.html
 M templates/layouts/series-rows.html
```

O diff é coerente e deliberado: um parâmetro `thumbs_dir` no `build_preview` e
o uso do WebP pré-gerado nos dois layouts, em vez do render dinâmico via
Three.js. Os três foram alterados às 12:15 e o `output/preview/` foi
regenerado às 12:17, num padrão de edição-e-teste.

Todas as escritas deste estudo foram em `eng-reversa/`. Os três arquivos foram
deixados como estão — descartar trabalho não commitado de outra pessoa seria
destrutivo.
