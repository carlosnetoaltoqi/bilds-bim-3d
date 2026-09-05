# O `.aq` do AltoQi Builder — schema, encoding, sentinelas (`www/apps/ingestao/pipeline/read_aq.py`)

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo.

### Encoding é cp1252, não latin-1

O AltoQi Builder é aplicação Windows: o texto no SQLite é **cp1252**. Latin-1 e cp1252
são idênticos em toda a tabela **exceto na faixa 0x80–0x9F** — que é exatamente onde
moram travessão (0x96), aspas curvas (0x93/0x94) e reticências (0x85).

Lido como latin-1, `5U – 19” x 570mm MRD 557` vira `5U \x96 19\x94 x 570mm MRD 557` e
chega assim na página pública. O erro é silencioso: latin-1 nunca lança exceção, então
nada quebra — só sai errado.

`_decode_texto()` decodifica cp1252 com fallback para latin-1. O fallback existe porque
cp1252 deixa cinco bytes indefinidos (0x81, 0x8D, 0x8F, 0x90, 0x9D) e falha neles; sem o
fallback, uma biblioteca com esses bytes derrubaria o build inteiro.

⚠️ **Não troque o `text_factory` sem olhar as colunas binárias.** O latin-1 era
byte-preserving, e o código dependia disso para reconstruir o BLOB da geometria quando
ele voltava como `str`. Com cp1252 esse round-trip **não é reversível** — corromperia a
malha 3D em silêncio. Por isso as queries de `SIMBOLOGIA_3D` usam `CAST(... AS BLOB)`:
força bytes e elimina a ambiguidade.

### Literal acentuado numa query também tem de ir em cp1252

O banco **declara** `PRAGMA encoding = UTF-8` e guarda **bytes cp1252**. O SQLite não
valida a codificação do que se manda gravar, e o `typeof()` continua `'text'`:

```
SELECT NOME_CP FROM CLASSE_PECA  →  b'Bomba de Combate a Inc\xeancio - Dancor'
```

Consequência para quem consulta: o módulo `sqlite3` do Python vincula um `str` como
UTF-8, então `WHERE NOME_GP = 'Joelho 90° Soldável'` **nunca casa** — no banco é
`b'...Sold\xe1vel'` e o parâmetro chega como `b'...Sold\xc3\xa1vel'`. A query volta
vazia, sem erro. O jeito certo:

```python
con.execute('... WHERE g.NOME_GP = CAST(? AS TEXT)', (nome.encode('cp1252'),))
```

O `read_aq.py` nunca precisou disso porque varre tabelas inteiras e decodifica em
Python — só aparece quando se compara literal acentuado dentro do SQL.

### .aq pode ser ZIP ou SQLite direto

Sempre tentar SQLite direto primeiro (alguns .aq são extraídos de outro ZIP).
O `text_factory` cp1252 tem de ser configurado antes de qualquer query — ver a
seção de encoding acima.

### Tabelas — catálogo de produto

- `GRUPO_PECA` — séries/famílias (`NOME_GP` = "CAM-W10", "Cap", "Pontos de comando")
- `PECA` — variantes individuais (`NOME_PECA`, `DESCRICAO_DADOS`, dimensões em cm —
  **exceto `DIAMETRO_PECA`, que é um código**, ver abaixo)
- `DADOS_HIDRAULICOS` — parâmetros hidráulicos por peça
- `MODELO_BOMBA` — nome e potência nominal do modelo
- `ITEM_CURVA_BOMBA` — pontos Q-H (`VAZAO_ICB`, `ALTURA_ICB`, `POTENCIA_ICB`, `RENDIMENTO_ICB`)
- `PROPRIEDADE_PERSONALIZADA` / `VALOR_PROPRIEDADE_PERSONALIZADA` — specs livres
- `DADOS_ELETRICOS` / `PONTO_ELETRICO` / `SUB_TIPO_PONTO` — bibliotecas elétricas

### ⚠️ `DIAMETRO_PECA` é um CÓDIGO, não um centímetro

Corrigido em 2026-09-02. A skill `leitor-biblioteca-aq` 2.2.0 dizia "diâmetro nominal
(cm)" e **está errado**. É um índice numa escala de diâmetros nominais do AltoQi:

| `NOME_PECA` (Amanco) | `DIAMETRO_PECA` |
|---|---|
| `40 mm - 1.1/2"` | 8 |
| `50 mm - 2"` | 9 |
| `75 mm - 3"` | 11 |
| `100 mm - 4"` | 12 |
| `150 mm - 6"` | 14 |
| `200 mm - 8"` | 15 |

`ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO` usam a mesma escala: a Dancor grava
7 a 11 nos bocais das suas bombas, cujas sucções e recalques vão de 1.1/4" a 3" — o que
encaixa em 32, 40, 50, 60 e 75 mm, e confirma o código 10 como 60 mm.

**Os códigos 1 a 7 não são observáveis** nas 12 bibliotecas de `input/`. As bitolas de
água fria de 20, 25 e 32 mm não aparecem em nenhuma delas.

**A distribuição real na Amanco, nas 1.168 peças:** 963 (82%) trazem a sentinela
`-1.7976931348623157e+308` (`-DBL_MAX`), 93 trazem zero e **112 trazem código** — as 48
de tubo, 52 de caixa sifonada e afins (`TIPO_APLICACAO_PECA=9`) e 12 de ralo (tipo 10).

**Nenhuma das 700 conexões (tipo 2) tem código.** É isso que sustenta a regra: o diâmetro
de uma conexão mora em `ENTRADA_PECA.DIAMETRO_EP`, não aqui.

> **Corrigido no pipeline em 2026-09-02:** a chave do `build_product_map` passou de
> `'diametro_cm'` para `'diametro_codigo'`, e as quatro chaves numéricas passam por
> `_sem_sentinela()` — antes o mapa entregava `-1.8e308` como se fosse medida.

`PECA.DIAMETRO_INTERNO`, ao contrário, é milímetro de verdade: 192,8 / 144,8 / 98,0 /
47,5.

### As sentinelas: o AltoQi não usa `NULL` para "não definido"

| Sentinela | Onde aparece |
|---|---|
| `-2147483647` | `GRUPO_PECA.TIPO_CONFIGURACAO_GP` (265 de 265 na Amanco), `ENTRADA_PECA.SECAO_EP` (1.871 de 2.627) |
| `-1.7976931348623157e+308` (`-DBL_MAX`) | `PECA.DIAMETRO_PECA` em 963 de 1.168 na Amanco (82%) |

Ler essas colunas como número útil sem testar a sentinela produz lixo. E ao escrever um
`.aq`, gravar `NULL` onde a biblioteca real grava a sentinela é uma divergência
silenciosa — não se sabe se o Builder trata as duas igual.

### Tabelas — geometria 3D (as que importam para o caminho padrão)

| Tabela | Papel |
|---|---|
| **`SIMBOLOGIA_3D`** | a geometria. Colunas: `SIMBOLOGIA_3D` (BLOB OQ3D — a malha), `IMAGEM` (BMP 100×100 pré-renderizado), `WIREFRAME` (arestas p/ CAD — **69–71% do arquivo, descartável**), `NOME`, `USA_CORES_PECA` |
| **`PECA_SIMBOLOGIA_3D`** | o vínculo peça → geometria (`ID_PECA`, `ID_SIMBOLOGIA_3D`). Chave estrangeira: dispensa qualquer matching por nome. Várias peças compartilham a mesma malha |
| `GRUPO_SIMBOLOGIA_3D` | agrupa geometrias (`NOME_GRUPO`, `ID_CLASSE`) |
| **`CLASSE_SIMBOLOGIA_3D`** | `NOME_CLASSE` segue o padrão `"FABRICANTE - Linha"` (`'AMANCO - PVC Esgoto SN'`) — **a fonte confiável de fabricante** |
| `ENTRADA_3D` | pontos de conexão hidráulica: `POSICAO_X/Y/Z`, `DIAMETRO`, `TIPO_SECAO`, `ID_SIMBOLOGIA_3D`. **O IFC não carrega isso.** Ainda não consumido pelo pipeline — oportunidade para conectividade BIM |
| `CONTEUDO_SIMBOLOGIA` | símbolo 2D de planta baixa, formato proprietário distinto do OQ3D |
| `IMAGEM` | **ícones da interface do AltoQi**, não fotos de produto. Vazia nas bibliotecas hidráulicas; preenchida nas elétricas, onde há `SUB_TIPO_PONTO` |

> **Nunca use `SELECT *` em `SIMBOLOGIA_3D`** — traz o `WIREFRAME` (285 MB dos 412 MB
> da Amanco). Selecione as colunas explicitamente.

> A imagem do produto é **sempre** `SIMBOLOGIA_3D.IMAGEM`, nunca a tabela `IMAGEM`.

### Propriedades personalizadas observadas

**Bombas:** Tensão, Corrente, Grau de Proteção, Isolamento, Sucção x Recalque,
Altura Máxima, Temperatura máxima, Motor, Rotor, Rotação.

**Conexões:** Bolsa, Classe de rigidez, Temperatura máxima de operação, Encaixe,
Distância máxima entre apoios, Fecho Hídrico, Vazão, Inclinação.

**Elétrica:** Corrente máxima, Potência máxima da carga, Conectividade,
Aplicativo compatível, Material do painel, Touch, Tensão de alimentação,
Temperatura de cor, Vida útil, Dimerizável.

### Peças sem geometria — comportamento correto

Peças sem linha em `PECA_SIMBOLOGIA_3D` não têm forma fixa: **tubos** (o AltoQi gera
o cilindro a partir de diâmetro × comprimento) e **kits de aparelho sanitário**
(ramal de ventilação, tanque de lavar, vaso com tê) — entradas de projeto. Na Amanco
são 312 de 1.168 (27%). Pular é o esperado; o build informa quantas.

**Mas "sem 3D" tinha dois significados, e até a S7.6 o build somava os dois (I2).**
`build_catalog_from_aq` devolve agora `(catalog, n_geo, diag)` e `resumo_diag(diag)`
imprime cada categoria separada:

| Categoria em `diag` | Significado | Como sai |
|---|---|---|
| `pecas_sem_simbologia` | tubo/kit — sem linha em `PECA_SIMBOLOGIA_3D` | linha informativa "— esperado" |
| `sim_sem_blob`, `sim_nao_oq3d` | simbologia existe mas o BLOB é nulo ou não é OQ3D | `AVISO: N simbologia(s) descartada(s)` |
| `sim_ilegivel` | `OQ3DError` (truncado/corrompido), com id, nome e erro | idem, uma linha por simbologia |
| `sim_vazia` | parse ok, nenhuma malha (era o sintoma da versão 3 na Maxbar) | idem |
| `pecas_sim_descartada` | peças que ficaram sem 3D **por causa** dos itens acima | contagem no mesmo AVISO |
| `avisos` | `OQ3DAvisoParse` por simbologia (I3) | `AVISO: N simbologia(s) com aviso de parse` |

Nas 15 bibliotecas de `input/` (2026-09-03) só a Intelbras produz avisos (23 simbologias,
raízes divergentes) e nenhuma produz simbologia descartada — a Maxbar produzia 31 `sim_vazia`
até a correção da versão 3. Teste: `tests/test_build.py::test_diag_separa_tubos_de_simbologia_descartada`.

### Escrever um `.aq` — o inverso do `read_aq.py`

Estudado em 2026-09-02. O corpo completo está em `eng-reversa/estudo/01-escrever-um-aq.md`;
o essencial:

> **O `.aq` gerado abre no AltoQi Builder de verdade** — testado pelo usuário em 2026-09-02
> com a biblioteca da Akato (variante paramétrica), registrado em 2026-09-03: árvore de
> classes/grupos/peças correta e **propriedades personalizadas visíveis com acentos
> íntegros** (`Água`, `Redução`, `kgf/cm²`). Print em
> `eng-reversa/estudo/img/builder-akato-aberto-2026-09-02.png`. Versões anteriores deste
> arquivo e do `eng-reversa/README.md` diziam que isso faltava provar. O que **ainda** não
> foi visto no Builder: a malha OQ3D na janela 3D e a peça lançada numa rede.

**O texto tem de ser gravado em cp1252, e errar isso corrompe o arquivo em silêncio.**
O módulo `sqlite3` do Python vincula `str` como UTF-8 e `bytes` como BLOB — nenhum dos
dois serve. A saída é o `CAST`:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes sem converter: `typeof()` volta `'text'`, os
bytes ficam idênticos aos de uma biblioteca real, e o `_decode_texto` devolve a string
original. Gravar em UTF-8 faz `'Soldável'` voltar `'SoldÃ¡vel'` — **sem levantar exceção
em lugar nenhum**, passando no `integrity_check` e chegando ao nome do produto na página
pública. É o bug de 2026-08-28, do lado de quem escreve. Encode **estrito**, nunca
`errors='replace'`.

**Uma biblioteca de fabricante preenche 16 a 25 das 77 tabelas.** A ordem de inserção
que fecha as chaves estrangeiras: `VERSAO_BANCO_CADASTRO` → `CLASSE_PECA` → `GRUPO_PECA`
→ `PECA` → (`DADOS_HIDRAULICOS`, `ENTRADA_PECA`, `ITEM_ASSOCIADO`);
`CLASSE_SIMBOLOGIA_3D` → `GRUPO_SIMBOLOGIA_3D` → `SIMBOLOGIA_3D` → `PECA_SIMBOLOGIA_3D`;
`GRUPO_PROPRIEDADE_PERSONALIZADA` → `PROPRIEDADE_PERSONALIZADA` →
`VALOR_PROPRIEDADE_PERSONALIZADA`; `CLASSE_ITEM` → `GRUPO_ITEM` → `ITEM`.

> O SQLite **não** aplica chaves estrangeiras por padrão: um `ID_GRUPO_PECA` órfão passa
> pelo `INSERT` sem erro e só aparece no AltoQi. Rodar `PRAGMA foreign_key_check` no fim.

**O DDL não se escreve à mão** — são 77 tabelas e 84 índices, e uma coluna faltando faz o
AltoQi recusar o arquivo. Está versionado em `eng-reversa/dados/schema-aq-607.sql`,
extraído do `sqlite_master` da Dancor.

**`ITEM.CODIGO_ITEM` é onde vive o código comercial do fabricante** — `'14808'` na
Amanco, `'10652511'` na Dancor, `'KO 16D GLP'` na Komeco. Não é propriedade
personalizada.

**Enums, com os valores observados.** `GRUPO_PECA.PROJETO_APLICACAO`: 8 esgoto, 12 água
fria, 22 incêndio, 36 gás, 64/76 elétrico. `ENTIDADE_IFC` (com `TIPO_ENTIDADE_IFC` e
`ENTIDADE_IFC_2X3`, que andam juntos): 2071 `IfcPipeFitting`, 2072 `IfcPipeSegment`,
2075 bomba, 2076 aparelho sanitário, 2084 válvula, 2085 terminal de descarte, 2090
aquecedor. `SUBTIPO_IFC` dentro de 2071: 0 curva/joelho, 1 luva, 3 cap, 4 tê, 6 redução.
`PECA.TIPO_APLICACAO_PECA`: 1 tubo, 2 conexão, 6 bomba, 8 aparelho, 9 caixa sifonada,
10 ralo, 55 ramal.

**Preencha `PECA.BIBLIOTECA`.** É o passo 2 da cascata de inferência de fabricante do
`build.py`, está vazio nas 12 bibliotecas reais, e é a **única fonte que sobrevive a uma
biblioteca sem geometria** — sem `CLASSE_SIMBOLOGIA_3D` o passo 1 não existe e a cascata
cai no nome da pasta.

### Escrever um catálogo inteiro — `www/apps/ingestao/pipeline/catalogo_to_aq.py` (S7.16, 2026-09-05)

O `geo_to_aq.py` grava UMA peça. Para N peças (o "baixar .aq" da edição do catálogo, que gera
uma biblioteca nova a partir do que está salvo no Mongo e no storage) valem mais cinco regras,
todas conferidas contra a Amanco (854 peças exportadas, 448 simbologias, `NOME_PECA` idêntico
ao original em 100 % das peças, bbox e nº de triângulos iguais em 448/448 geometrias):

- **Uma `SIMBOLOGIA_3D` por arquivo de geometria, não por peça.** O pipeline grava uma geometria
  por simbologia e várias peças apontam para ela; ao escrever, o mesmo arquivo vira a mesma
  simbologia e cada peça ganha a sua linha em `PECA_SIMBOLOGIA_3D` (856 peças → 457 na Amanco
  original; 854 → 448 no export). Uma geometria editada (copy-on-write) vira simbologia própria.
- **Uma `PROPRIEDADE_PERSONALIZADA` por chave de spec, não por peça.** A Amanco tem 12
  propriedades para 4.925 valores; escrever uma propriedade por (peça, chave) multiplicaria a
  tabela por 400 e o Builder mostraria 4.000 "propriedades". Um único
  `GRUPO_PROPRIEDADE_PERSONALIZADA` ("Fabricante: Título").
- **`NOME_PECA` é o nome sem o prefixo da série.** O `catalogo.py` exibe "Cap 50mm" porque "50mm"
  se repete entre Cap, Luva e Joelho; no `.aq` a Amanco grava `NOME_PECA = '50mm'` no grupo
  `Cap`. Tirar o prefixo `"<série> "` do nome da tela devolve o original em 100 % das 854 peças.
  A reconstrução pelo `catalogo.py` pode mostrar 52 nomes sem o prefixo que a tela tinha — a regra
  de prefixo depende do conjunto de nomes do arquivo, e o export tem menos peças (sem tubos/kits).
- **Grupo por série, com os códigos IFC inferidos do nome** (`aq_writer.classificar_grupo`): regras
  por palavra inteira, ajustadas contra os 192 grupos com 3D da Amanco — 189 batem; os 3 que não
  batem têm códigos diferentes dos irmãos no próprio arquivo ("Caixa Sifonada" 2076/3/9 ao lado de
  "Caixa Sifonada 3 Entradas" 2085/1/9). Um grupo com produto de curva Q-H vira bomba
  (`2075/4118/2093`, `SUBTIPO_IFC 5`, `TIPO_APLICACAO_PECA 6`, como a Dancor). `PROJETO_APLICACAO`
  por palavra do título/série (`aplicacao_de`: esgoto 8, incêndio 22, gás 36, senão água fria 12).
- **Colunas de uma peça com 3D, como a Amanco grava:** `POSICIONAR_SIMBOLOGIA_3D = 3`,
  `INDICE_SIMBOLO3D_SELECIONADO = 1`, `INDICACAO_DADOS = nome`, `DESCRICAO_DADOS_SIMBOLOGIA =
  grupo`, `COMPRIMENTO/ESPESSURA/LARGURA/ALTURA/PROFUNDIDADE_PECA = -DBL_MAX`, `INDICACAO_PLANTA`
  e `INDICACAO_DETALHE` nulos. (O `geo_to_aq.py` usa `0`/`-1` e preenche as indicações — os dois
  abrem no leitor do projeto; no Builder só a Akato, gerada como o `geo_to_aq.py`, foi vista.)

**O que o catálogo não guarda e portanto não volta:** as peças sem simbologia 3D (312 tubos e kits
da Amanco), `ENTRADA_PECA`/`ENTRADA_3D` (bocais, conectividade), simbologia 2D, `IMAGEM`,
`WIREFRAME` e o **código comercial** (`ITEM.CODIGO_ITEM` sai com a spec "Código" se houver, senão o
slug do produto). Guardar o `.aq` original no import resolveria isso por um caminho diferente
(copiar e aplicar deltas) — não foi feito.

**Erros que a geração acusa** (exit 1, `.aq` parcial apagado): geometria ausente ou inválida no
storage (com o nome do produto), caractere fora do cp1252 em nome/série/spec (com tabela.coluna e
posição), catálogo sem produtos, chave estrangeira órfã no `PRAGMA foreign_key_check` final.

### Diferenças entre versões de schema

| Versão | Bibliotecas | Diferença notada |
|---|---|---|
| 552–582 | Komeco, Intelbras | `ENTRADA_3D` **não tem** a coluna `DIAMETRO` |
| 595 | Amanco | — |
| 607 | Dancor | `ENTRADA_3D.DIAMETRO` existe |

Uma query que use `ENTRADA_3D.DIAMETRO` quebra com `no such column` nas bibliotecas
antigas.
