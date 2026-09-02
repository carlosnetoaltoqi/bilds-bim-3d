# Escrever um `.aq` — o que a documentação de leitura não cobre

O `CLAUDE.md` e a skill `leitor-biblioteca-aq` documentam o schema para
**ler**. Para escrever falta outra coisa: os valores concretos que o AltoQi
Builder põe nas colunas de enum, quais tabelas ficam de fato preenchidas numa
biblioteca de fabricante, em que ordem inserir, e — o mais importante — como o
texto é codificado.

Todo valor citado aqui foi observado numa das 12 bibliotecas de `input/`. O que
é inferência está marcado como inferência.

---

## 1. A armadilha que corrompe o arquivo em silêncio: o encoding

**Um `.aq` declara `PRAGMA encoding = UTF-8` e guarda bytes cp1252.**

```
sqlite> PRAGMA encoding;                         → UTF-8
sqlite> SELECT typeof(NOME_CP) FROM CLASSE_PECA; → text
```

E os bytes, na biblioteca da Dancor:

```python
b'Bomba de Combate a Inc\xeancio - Dancor'
#                        ^^^^ 'ê' em cp1252; não é UTF-8 válido
```

O SQLite não valida a codificação do que se manda gravar. O AltoQi Builder é
aplicação Windows, grava cp1252, e o valor continua tipado como `text`.

O `scripts/read_aq.py` do projeto sabe disso e lê com
`con.text_factory = _decode_texto` (cp1252 com fallback latin-1). **Consequência
para quem escreve:** gravar em UTF-8, que é o comportamento padrão do módulo
`sqlite3` do Python, produz mojibake na leitura.

Foi o que aconteceu na primeira versão do gerador:

```
'Tubo De Pvc Soldável 6M'   →  'Tubo De Pvc SoldÃ¡vel 6M'
```

**O erro não levanta exceção em lugar nenhum.** O arquivo abre, passa no
`integrity_check`, passa no `foreign_key_check`, o `extract` devolve todas as
peças — e o nome errado chega ao nome do produto na página publicada. É o mesmo
bug de produção de 2026-08-28 registrado no `CLAUDE.md`, agora do lado de quem
escreve em vez do lado de quem lê.

### Como gravar certo

O `sqlite3` do Python vincula `str` como UTF-8 e `bytes` como BLOB. Nenhum dos
dois serve: o primeiro grava a codificação errada, o segundo grava o tipo
errado. A saída é o `CAST`:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes como texto sem converter nada.
Verificado: `typeof()` volta `'text'`, os bytes gravados são idênticos aos de
uma biblioteca real, e o `_decode_texto` do projeto devolve a string original.

E **encode estrito, nunca `errors='replace'`**: o cp1252 tem 256 posições e um
caractere fora da tabela viraria `?` dentro do nome do produto sem ninguém
notar. O catálogo da Akato usa `°`, `º`, `²`, `´` e `’`, todos representáveis;
um `–` ou um `→` vindo de outra fonte não seria, e tem de estourar.

### Como conferir

A checagem que pega o erro: os bytes altos das colunas de texto **não podem**
ser UTF-8 válido.

```python
# 'Soldável' é b'Sold\xe1vel' em cp1252 e b'Sold\xc3\xa1vel' em UTF-8.
# Em cp1252 o acento é um byte alto isolado, que é UTF-8 inválido.
for v in bytes_das_colunas_de_texto:
    if any(b > 0x7F for b in v):
        assert nao_decodifica_utf8(v)
```

Está implementada em `tools/validar_aq.py`, passo 7. No arquivo gerado: 406
textos acentuados, 0 deles UTF-8 válido.

---

## 2. As tabelas que uma biblioteca de fabricante usa

De 77 tabelas no schema, uma biblioteca de fabricante preenche entre 16 e 25.
As demais são cadastros do projeto, não do produto.

| Tabela | Amanco (1.168 peças) | Dancor (13 bombas) | O `.aq` gerado |
|---|---|---|---|
| `VERSAO_BANCO_CADASTRO` | 1 | 1 | 1 |
| `CLASSE_PECA` | 3 | 1 | 5 |
| `GRUPO_PECA` | 265 | 11 | 83 |
| `PECA` | 1.168 | 13 | 262 |
| `DADOS_HIDRAULICOS` | 958 | 13 | 262 |
| `ENTRADA_PECA` | 2.627 | 26 | — |
| `CLASSE_SIMBOLOGIA_3D` | 4 | 1 | 2 |
| `GRUPO_SIMBOLOGIA_3D` | 63 | 11 | 2 |
| `SIMBOLOGIA_3D` | 457 | 13 | 12 |
| `PECA_SIMBOLOGIA_3D` | 869 | 13 | 12 |
| `ENTRADA_3D` | 83 | 26 | — |
| `GRUPO_PROPRIEDADE_PERSONALIZADA` | 1 | 3 | 1 |
| `PROPRIEDADE_PERSONALIZADA` | 12 | 34 | 8 |
| `VALOR_PROPRIEDADE_PERSONALIZADA` | 4.925 | 113 | 1.494 |
| `CLASSE_ITEM` / `GRUPO_ITEM` / `ITEM` | 5 / 78 / 263 | 1 / 11 / 13 | 5 / 87 / 269 |
| `ITEM_ASSOCIADO` | 3.491 | 13 | 262 |
| `MODELO_BOMBA` / `ITEM_CURVA_BOMBA` | — | 12 / 122 | — |
| `CLASSE_SIMBOLOGIA` … `PECA_SIMBOLOGIA` | 8 / 71 / 469 / 469 / 1.749 | 2 / 11 / 13 / 13 / 13 | — |

As cinco últimas (`CLASSE_SIMBOLOGIA`, `GRUPO_SIMBOLOGIA`,
`CONTEUDO_SIMBOLOGIA`, `SIMBOLOGIA`, `PECA_SIMBOLOGIA`) são a **simbologia 2D**
— o símbolo de planta e de corte, num formato binário próprio dentro de
`CONTEUDO_SIMBOLOGIA.SIMBOLOGIA` que **este estudo não decifrou**. Uma
biblioteca sem elas é utilizável; as peças aparecem em 3D e em lista, e a
representação em planta cai no símbolo genérico do AltoQi.

### Ordem de inserção

As chaves estrangeiras exigem esta ordem:

```
VERSAO_BANCO_CADASTRO
CLASSE_PECA  →  GRUPO_PECA  →  PECA
                                 ├─ DADOS_HIDRAULICOS
                                 ├─ ENTRADA_PECA
                                 └─ ITEM_ASSOCIADO ─┐
CLASSE_SIMBOLOGIA_3D → GRUPO_SIMBOLOGIA_3D → SIMBOLOGIA_3D             │
                                               ├─ ENTRADA_3D           │
                                               └─ PECA_SIMBOLOGIA_3D   │
GRUPO_PROPRIEDADE_PERSONALIZADA → PROPRIEDADE_PERSONALIZADA            │
                                    → VALOR_PROPRIEDADE_PERSONALIZADA  │
CLASSE_ITEM → GRUPO_ITEM → ITEM ───────────────────────────────────────┘
MODELO_BOMBA → ITEM_CURVA_BOMBA        (só bibliotecas de bomba)
```

Vale rodar `PRAGMA foreign_key_check` no fim: o SQLite **não** aplica chaves
estrangeiras por padrão, então um `ID_GRUPO_PECA` órfão passa pelo `INSERT`
sem erro e só aparece no AltoQi.

---

## 3. As sentinelas: o AltoQi não usa `NULL` para "não definido"

| Sentinela | Onde aparece |
|---|---|
| `-2147483647` | `GRUPO_PECA.TIPO_CONFIGURACAO_GP` (265 de 265 na Amanco), `ENTRADA_PECA.SECAO_EP` (1.871 de 2.627) |
| `-1.7976931348623157e+308` (`-DBL_MAX`) | `PECA.DIAMETRO_PECA` em 963 das 1.168 peças da Amanco (82%) |

Gravar `NULL` onde a biblioteca real grava a sentinela é uma divergência
silenciosa. Não sabemos se o Builder trata os dois igual.

---

## 4. `DIAMETRO_PECA` é um CÓDIGO, não um centímetro

A skill `leitor-biblioteca-aq` 2.2.0 documenta `PECA.DIAMETRO_PECA` como
"diâmetro nominal (cm)". **Não é.** Na Amanco:

| `NOME_PECA` | `DIAMETRO_PECA` |
|---|---|
| `40 mm - 1.1/2"` | 8 |
| `50 mm - 2"` | 9 |
| `75 mm - 3"` | 11 |
| `100 mm - 4"` | 12 |
| `150 mm - 6"` | 14 |
| `200 mm - 8"` | 15 |

É um índice numa escala de diâmetros nominais do AltoQi. `ENTRADA_PECA.DIAMETRO_EP`
e `ENTRADA_3D.DIAMETRO` usam a mesma escala: a Dancor grava 7, 8, 9, 10 e 11
nos bocais das suas bombas, cujas sucções e recalques vão de 1.1/4" a 3" — o
que encaixa em 32, 40, 50, 60 e 75 mm.

**A escala completa não é observável nestas 12 bibliotecas.** Os códigos 10 e
13 não aparecem na Amanco (que salta de 9 para 11 e de 12 para 14), e a
interpolação sugere 60 mm e 125 mm — o 60 confirmado pela Dancor. Os códigos
das bitolas de água fria abaixo de 40 mm (20, 25 e 32 mm) **não aparecem em
nenhuma biblioteca**, e por isso o gerador deixa a sentinela nessas peças em
vez de adivinhar 5, 6 e 7.

**A quem põe o código:** das 1.168 peças da Amanco, 112 trazem código — as 48 de tubo,
52 de caixa sifonada e afins (`TIPO_APLICACAO_PECA=9`) e 12 de ralo (tipo 10). 963 trazem
a sentinela e 93 trazem zero. **Nenhuma das 700 conexões traz código:** o diâmetro de uma
conexão mora em `ENTRADA_PECA.DIAMETRO_EP`, não em `PECA.DIAMETRO_PECA`. O gerador segue
isso e põe código só no tubo, que é a única dessas três categorias que ele produz.

`PECA.DIAMETRO_INTERNO`, ao contrário, é milímetro de verdade: 192,8 / 144,8 /
98,0 / 47,5.

---

## 5. Os enums, com os valores observados

### `GRUPO_PECA.PROJETO_APLICACAO` — o tipo de instalação

| Valor | Instalação | Onde |
|---|---|---|
| 8 | esgoto | Amanco, PVC esgoto |
| 12 | água fria | Komeco, bombas e pressurizadores |
| 22 | incêndio | Dancor, bombas de combate a incêndio |
| 36 | gás | Komeco, aquecedor de passagem a gás |
| 64, 76 | elétrico | Maxbar, barramento blindado |

Água quente, drenagem pluvial e ar condicionado não aparecem — não há
biblioteca desses domínios em `input/`.

### `ENTIDADE_IFC` e companhia

As quatro colunas andam juntas e vêm em combinações fixas:

| `ENTIDADE_IFC` | `TIPO_ENTIDADE_IFC` | `ENTIDADE_IFC_2X3` | Significado | Grupos que usam |
|---|---|---|---|---|
| 2071 | 4099 | 2088 | `IfcPipeFitting` | curva, joelho, luva, cap, tê, redução, ramal |
| 2072 | 4096 | 2086 | `IfcPipeSegment` | tubo |
| 2075 | 4118 | 2093 | bomba | Dancor, Komeco |
| 2076 | 4122 | 2092 | aparelho sanitário | pia, chuveiro, vaso, lavatório |
| 2079 | 4121 | 2092 | terminal | terminal de ventilação |
| 2084 | 4103 | 2091 | válvula | válvula de retenção |
| 2085 | 4123 | 2092 | terminal de descarte | ralo, caixa sifonada |
| 2090 | 4138 | 2090 | aquecedor | Komeco, aquecedor a gás |

### `SUBTIPO_IFC` — o tipo predefinido dentro da entidade

Dentro de `IfcPipeFitting` (2071), pela correlação com os 156 grupos da Amanco:

| Valor | Grupos | Leitura |
|---|---|---|
| 0 | Curva Curta 90º, Curva 45º, Joelho (68 grupos) | curva / joelho |
| 1 | Luva Simples (8) | luva / conector |
| 3 | Cap, Sifão Expert (9) | terminação |
| 4 | Tê, Tê vertical, Tê superior (53) | tê / junção |
| 6 | Redução Excêntrica, Bucha de Redução (15) | redução |
| 7 | Ramal de Ventilação (3) | ramal |

Em `IfcPipeSegment` (2072) só o 3 aparece. Em válvula (2084), só o 22.

> O `SUBTIPO_IFC_2X3` é sempre igual ao `SUBTIPO_IFC` nas 265 linhas da Amanco.

### `PECA.TIPO_APLICACAO_PECA` — o que a peça é, para a paleta

| Valor | O que é | Onde |
|---|---|---|
| 1 | tubo | as 48 peças de tubo da Amanco |
| 2 | conexão | 700 peças da Amanco, 212 da Maxbar |
| 6 | bomba | as 13 da Dancor |
| 8 | aparelho sanitário | 206 da Amanco |
| 9 | caixa sifonada, chuveiro, ralo com grelha | 52 |
| 10 | ralo | 59 |
| 55 | ramal de ventilação | 103 |

### Colunas de grupo com valor fixo por material

Na Amanco (PVC), as 265 linhas de `GRUPO_PECA` trazem:

```
RUGOSIDADE_GP          = 135.0       Hazen-Williams C
RUGOSIDADE_EQUIVALENTE = 6e-05       metros
COEFICIENTE_MANNING    = 0.01
TIPO_FWH               = 1           Fair-Whipple-Hsiao ligado
TIPO_SECAO_GP          = 0           circular
TIPO_MATERIAL          = 0
TIPO_CONFIGURACAO_GP   = -2147483647 sentinela
ELEMENTO_APLICACAO     = 0, exceto 1 nos 9 grupos de tubo
REPRESENTACAO_GP       = 0, exceto 2 nos 9 grupos de tubo
ATIVO                  = 1
CODIGO_ELLO            = 0
```

A Dancor usa `RUGOSIDADE_GP = 135.0` e `TIPO_FWH = 0`; a Komeco, 130 e 125.

### `DADOS_HIDRAULICOS`

Nas 700 conexões da Amanco só `TIPO_CURVA = 2` e `ID_PECA` estão preenchidos —
o resto é `NULL`. Nas outras 258 linhas nem o `TIPO_CURVA`.

### `ITEM` — onde vive o código comercial

`ITEM.CODIGO_ITEM` é o código do fabricante:

| Biblioteca | `CODIGO_ITEM` | `NOME_ITEM` |
|---|---|---|
| Amanco | `14808` | `50mm` |
| Dancor | `10652511` | `3,0CV T 220/380V INC FLG IR3 - 10652511` |
| Komeco | `KO 16D GLP` | `GLP KO 16D` |

`FABRICANTE` e `TABELA_REFERENCIA` repetem o nome do fabricante, `CATEGORIA` é
`'Insumo'` nas três. `GRUPO_ITEM.UNIDADE_GI` é 1 nos grupos de tubo (medidos
por metro) e 0 no resto; `ITEM_ASSOCIADO.MEDICAO_PECA` é 1 nas peças de tubo e
2 nas conexões.

**É aqui que o código de catálogo pertence** — não numa propriedade
personalizada. O gerador põe nos dois lugares: em `CODIGO_ITEM`, que é o
canônico, e como propriedade `Código Akato`, que é o que aparece na ficha do
produto na página publicada.

---

## 6. Fabricante e título: a cascata precisa de uma âncora

O `build.py` infere fabricante e título, e nunca podem sair vazios nem em forma
de slug — são o cabeçalho da página publicada. A cascata:

1. prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE`, no padrão
   `"FABRICANTE - Linha de Produto"`
2. `PECA.BIBLIOTECA`
3. pasta avô, se descritiva
4. pasta pai, se coincidir com o primeiro token do nome do arquivo
5. primeiro token do nome do arquivo

**Uma biblioteca sem geometria não tem passo 1** — não há
`CLASSE_SIMBOLOGIA_3D`. E o passo 2, `PECA.BIBLIOTECA`, está **vazio nas 12
bibliotecas reais**. Sobra depender do nome da pasta.

Daí duas recomendações para quem gera um `.aq`:

- **Preencher `PECA.BIBLIOTECA`.** É uma coluna que existe, que a cascata já
  consulta e que nenhum fabricante usa. Custa nada e é a única fonte de
  fabricante que sobrevive a um arquivo sem geometria.
- **Nomear `CLASSE_SIMBOLOGIA_3D` no padrão `"FABRICANTE - Linha"`**, com a
  linha de produto de verdade. Se a classe se chamar
  `"AKATO - Tubos PVC (demonstração)"`, o pipeline publica "Tubos PVC
  (demonstração)" como a linha do catálogo. A ressalva vai no nome do
  `GRUPO_SIMBOLOGIA_3D`, que é o que aparece na árvore do AltoQi.

O arquivo gerado declara duas classes — `AKATO - PVC Água Fria Soldável` e
`AKATO - PVC Esgoto Série Normal` — e o `build.py` extrai fabricante `Akato` e
linhas `['PVC Água Fria Soldável', 'PVC Esgoto Série Normal']`.

---

## 7. Diferenças entre versões de schema

O schema mudou entre as versões observadas, e um gerador precisa escolher uma.

| Versão | Bibliotecas | Diferença notada |
|---|---|---|
| 552–582 | Komeco, Intelbras | `ENTRADA_3D` **não tem** a coluna `DIAMETRO` |
| 595 | Amanco | — |
| 607 | Dancor | `ENTRADA_3D.DIAMETRO` existe |

O gerador emite **607**, a mais nova disponível, e copia o DDL de um `.aq`
real (`dados/schema-aq-607.sql`: 77 tabelas, 84 índices) em vez de escrever
`CREATE TABLE` à mão. Uma coluna faltando é o tipo de erro que o AltoQi
rejeita, e são 77 tabelas.

O `open_aq` do projeto tenta SQLite direto e cai para ZIP se falhar. As 12
bibliotecas de `input/` são SQLite puro, e é o que o gerador produz — o ZIP é o
caso legado.

---

## 8. O que só o Builder pode dizer

Não há AltoQi Builder nesta máquina. O arquivo gerado passa nas 20 checagens do
`validar_aq.py` e atravessa o `build.py` até uma página com viewer 3D, mas isso
prova compatibilidade com o **leitor do projeto**, não com o Builder. Os riscos
concretos, em ordem de probabilidade:

1. **A simbologia 2D ausente.** As cinco tabelas de `CONTEUDO_SIMBOLOGIA` estão
   vazias. É o item mais provável de o Builder reclamar, ou de degradar para um
   símbolo genérico em planta.
2. **Os 5 bytes opacos do cabeçalho OQ3D** e os blocos que o leitor tolerante do
   projeto ignora. Foram copiados byte a byte de uma subárvore real, então o
   risco é baixo, mas não é zero — ver `02-escrever-oq3d.md`.
3. **A escala de `CODIGO_DIAMETRO`.** Os códigos que o gerador usa foram
   observados; os que faltavam ficaram como sentinela. Se o Builder exigir
   código em toda peça, faltam 3 bitolas.
4. **`ENTRADA_PECA` e `ENTRADA_3D` vazias.** Sem pontos de conexão, o Builder
   provavelmente não consegue encaixar a peça numa rede automaticamente. É a
   limitação funcional mais séria, e é do catálogo, não do formato — ver
   `04-lacunas-do-catalogo-comercial.md`.
5. **As sentinelas em colunas que não foram observadas.** Onde a biblioteca real
   não mostrou valor, o gerador omitiu a coluna e deixou o `DEFAULT` do DDL
   agir. Pode não ser o que o Builder espera.

O teste que resolve os cinco de uma vez: abrir o `.aq` gerado no AltoQi Builder
e lançar uma peça num projeto.
