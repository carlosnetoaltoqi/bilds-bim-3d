# O `.aq` do AltoQi Builder — ler (`biblioteca/bim_pipeline/aq/read_aq.py`)

> A escrita está em `aq-escrita.md`.

Um `.aq` é uma biblioteca BIM do AltoQi Builder: um banco **SQLite** com peças, grupos, dados
hidráulicos, curvas de bomba, propriedades personalizadas **e a malha 3D completa** (formato OQ3D,
ver `oq3d.md`). Não é preciso ter IFC para gerar visualização 3D — o `.aq` traz a mesma geometria,
com cor e miniatura, e lê-se ordens de grandeza mais rápido.

### ZIP ou SQLite direto

Versões recentes do Builder distribuem o `.aq` como SQLite puro; o ZIP contendo um SQLite é o caso
legado. `open_aq` tenta SQLite primeiro e cai para ZIP se falhar. Duas armadilhas do próprio
`sqlite3`:

- `sqlite3.connect(caminho)` **cria** um arquivo vazio se ele não existir — checar `os.path.isfile`
  antes e abrir somente-leitura (`file:…?mode=ro`, URI com `pathname2url`, porque os caminhos reais
  têm espaço e acento). A armadilha ficou dois meses documentada antes do código ser corrigido
  (skill 2.6.0): a tabela de armadilhas descreve o sintoma, não garante que o código ao lado já o evite.
- O `text_factory` tem de ser configurado **antes de qualquer query** — ver abaixo.

### Encoding: `PRAGMA encoding` mente — o texto é cp1252

O banco **declara** `PRAGMA encoding = UTF-8` e **guarda bytes cp1252**. O SQLite não valida a
codificação do que se manda gravar, e o `typeof()` continua `'text'`:

```
SELECT NOME_CP FROM CLASSE_PECA  →  b'Bomba de Combate a Inc\xeancio - Fabricante'
                                                           ^^^^ 'ê' em cp1252; UTF-8 inválido
```

O Builder é aplicação Windows, daí o cp1252. **Não é latin-1**: os dois codecs são idênticos em
toda a tabela **exceto na faixa 0x80–0x9F** — exatamente onde moram travessão (`0x96`), aspas
curvas (`0x93`/`0x94`) e reticências (`0x85`), caracteres comuns em nome de produto. Lido como
latin-1, `5U – 19” x 570mm` vira `5U \x96 19\x94 x 570mm`. **O erro é silencioso**: latin-1 nunca
lança exceção, então nada quebra — só sai errado, e chega à página pública. Latin-1 e Windows-1252
não são sinônimos.

```python
def _decode_texto(b):
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')   # cp1252 deixa 0x81, 0x8D, 0x8F, 0x90, 0x9D indefinidos

con.text_factory = _decode_texto
```

O fallback existe para que uma biblioteca com um desses cinco bytes continue abrindo em vez de
derrubar o build inteiro por causa de um caractere.

**Não troque o `text_factory` sem olhar as colunas binárias.** O latin-1 era byte-preserving, e
havia código que reconstruía o BLOB da geometria com `.encode('latin-1')` quando a coluna voltava
como `str`. Com cp1252 esse round-trip **não é reversível** — corromperia a malha em silêncio. Por
isso toda query de `SIMBOLOGIA_3D` usa `CAST(col AS BLOB)`: força bytes e elimina o re-encode.

**Literal acentuado dentro do SQL também tem de ir em cp1252.** O módulo `sqlite3` vincula um `str`
como UTF-8, então `WHERE NOME_GP = 'Joelho 90° Soldável'` **nunca casa** — no banco é
`b'...Sold\xe1vel'`, o parâmetro chega `b'...Sold\xc3\xa1vel'`, e a query volta vazia sem erro:

```python
con.execute('... WHERE g.NOME_GP = CAST(? AS TEXT)', (nome.encode('cp1252'),))
```

Quem varre a tabela inteira e filtra em Python (o `read_aq.py`) nunca encontra isso.

### Tabelas — catálogo de produto

| Tabela | Papel | Colunas que importam |
|---|---|---|
| `VERSAO_BANCO_CADASTRO` | 1 linha, cabeçalho | `VERSAO` (schema, ex.: 607), `TAG_IDIOMA`, `MODO_GRAVACAO` |
| `CLASSE_PECA` | classe/linha de produto | `NOME_CP` |
| `GRUPO_PECA` | série/família (`NOME_GP` = `"Cap"`, `"Pontos de comando"`, um modelo de bomba) | `ID_CLASSE_PECA`, `PROJETO_APLICACAO`, `ENTIDADE_IFC` (+3 colunas irmãs), `SUBTIPO_IFC`, `TIPO_SECAO_GP`, `RUGOSIDADE_GP`, `ATIVO` |
| `PECA` | variante individual | `ID_GRUPO_PECA`, `NOME_PECA`, `DESCRICAO_DADOS` (conexões, ex.: `2.1/2" x 2.1/2"`), `DIAMETRO_PECA` (**código**), `DIAMETRO_INTERNO` (mm de verdade), `COMPRIMENTO/ALTURA/LARGURA_PECA` (cm), `TIPO_APLICACAO_PECA`, `BIBLIOTECA`, `ATIVO` |
| `DADOS_HIDRAULICOS` | 1 por peça | `ID_PECA`, `ID_MODELO_BOMBA` (bombas), `TIPO_CURVA`, `FATOR_K`, comprimentos equivalentes |
| `ENTRADA_PECA` | bocais da peça | `DIAMETRO_EP` (código), `SECAO_EP` |
| `MODELO_BOMBA` | modelo comercial da bomba | `NOME_MB`, `POTENCIA_MB` (CV) |
| `ITEM_CURVA_BOMBA` | pontos Q-H do modelo | `VAZAO_ICB`, `ALTURA_ICB`, `POTENCIA_ICB`, `RENDIMENTO_ICB`, `NPSH` |
| `GRUPO_PROPRIEDADE_PERSONALIZADA` → `PROPRIEDADE_PERSONALIZADA` → `VALOR_PROPRIEDADE_PERSONALIZADA` | specs livres do fabricante | `NOME` do grupo e da propriedade, `TIPO_VALOR` (0 texto), `VALOR` por `ID_PECA` |
| `CLASSE_ITEM` → `GRUPO_ITEM` → `ITEM` ← `ITEM_ASSOCIADO` | insumo de orçamento | **`ITEM.CODIGO_ITEM` é o código comercial do fabricante** — não é propriedade personalizada |
| `DADOS_ELETRICOS` / `PONTO_ELETRICO` / `SUB_TIPO_PONTO` | bibliotecas elétricas | — |

A curva Q-H vem pelo caminho `PECA → DADOS_HIDRAULICOS.ID_MODELO_BOMBA → MODELO_BOMBA →
ITEM_CURVA_BOMBA`. Uma biblioteca sem bombas não tem `MODELO_BOMBA` preenchida — o `extract`
engole o `OperationalError` e devolve `curvas = []`.

`PECA.BIBLIOTECA` está **vazia em todas as bibliotecas reais** observadas; o fabricante vem do
prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` (abaixo).

### Tabelas — geometria 3D

| Tabela | Papel |
|---|---|
| **`SIMBOLOGIA_3D`** | a geometria. `SIMBOLOGIA_3D` (BLOB OQ3D — a malha), `IMAGEM` (BMP 100×100 24-bit pré-renderizado), `WIREFRAME` (arestas para planta/corte no CAD — **~70 % do arquivo, inútil para viewer**), `NOME` (muitas vezes só a dimensão: `'100MM'`), `USA_CORES_PECA`, `DESLOCAMENTO_X/Y/Z`, `ANGULO_PLANO_*`. `SIMBOLOGIA_3D_SIMPLIFICADA` e `IMAGEM_SIMPLIFICADA` nulas nas bibliotecas observadas |
| **`PECA_SIMBOLOGIA_3D`** | o vínculo peça → geometria (`ID_PECA`, `ID_SIMBOLOGIA_3D`). **É chave estrangeira: dispensa qualquer matching por nome** — a diferença central em relação ao caminho via IFC. Várias peças compartilham a mesma malha (numa biblioteca de conexões, ~2 peças por simbologia; as variantes "DESCE"/"COLUNA"/"SOBE" mudam a orientação de inserção, não a forma) |
| `GRUPO_SIMBOLOGIA_3D` | agrupa geometrias (`NOME_GRUPO`, `ID_CLASSE`) |
| **`CLASSE_SIMBOLOGIA_3D`** | `NOME_CLASSE` segue `"FABRICANTE - Linha de Produto"` (`'FABRICANTE - PVC Esgoto SN'`) — **a fonte confiável de fabricante** |
| `ENTRADA_3D` | pontos de conexão hidráulica: `POSICAO_X/Y/Z`, `DIAMETRO` (código; **só no schema 607**), `TIPO_SECAO`, `ID_SIMBOLOGIA_3D`. O IFC não carrega isso. Ainda não consumido pelo pipeline |
| `CLASSE_SIMBOLOGIA` → `GRUPO_SIMBOLOGIA` → `CONTEUDO_SIMBOLOGIA` → `SIMBOLOGIA` → `PECA_SIMBOLOGIA` | simbologia **2D** (planta e corte), formato binário próprio, distinto do OQ3D e não decifrado |
| `IMAGEM` | **ícones da interface do AltoQi**, não fotos de produto. Vazia nas bibliotecas hidráulicas; preenchida nas elétricas (onde há `SUB_TIPO_PONTO`) |
| `CLASSIFICACAO_IFC` / `CLASSIFICACAO_IFC_PECA` | vazias nas bibliotecas observadas |

> **Nunca `SELECT *` numa tabela de geometria.** Traz o `WIREFRAME` — centenas de MB. Selecione
> as colunas explicitamente, com `CAST(... AS BLOB)`.

> A imagem do produto é **sempre** `SIMBOLOGIA_3D.IMAGEM`, nunca a tabela `IMAGEM`.

### `DIAMETRO_PECA` é um CÓDIGO, não uma medida

> Tratar o valor como centímetro erra por ~2× nas peças de tubo e devolve `-1.8e308` em todo o resto.

É um índice na escala de diâmetros nominais do AltoQi. Pares observados:

| `NOME_PECA` | `DIAMETRO_PECA` |
|---|---|
| `40 mm - 1.1/2"` | 8 |
| `50 mm - 2"` | 9 |
| (60 mm) | 10 |
| `75 mm - 3"` | 11 |
| `100 mm - 4"` | 12 |
| `150 mm - 6"` | 14 |
| `200 mm - 8"` | 15 |

`ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO` usam a **mesma escala**: uma biblioteca de
bombas grava 7 a 11 nos bocais, cujas sucções e recalques vão de 1.1/4" a 3" — encaixa em 32, 40,
50, 60 e 75 mm e é de onde vem o 10 = 60 mm. Os códigos 1 a 7 (bitolas de água fria de 20, 25 e
32 mm) e o 13 (125 mm, por interpolação) **não são observáveis** nas bibliotecas disponíveis.

Quem traz código: numa biblioteca real de conexões, **~82 % das peças trazem a sentinela**
`-DBL_MAX`, ~8 % trazem zero e **~10 % trazem código** — só tubos, caixas sifonadas e ralos
(`TIPO_APLICACAO_PECA` 1, 9 e 10). **Nenhuma conexão (tipo 2) traz código**: o diâmetro de uma
conexão mora em `ENTRADA_PECA.DIAMETRO_EP`, não em `PECA.DIAMETRO_PECA`.

`PECA.DIAMETRO_INTERNO`, ao contrário, é milímetro de verdade (192,8 / 144,8 / 98,0 / 47,5).

### Sentinelas: o AltoQi não usa `NULL` para "não definido"

| Sentinela | Coluna | Onde aparece |
|---|---|---|
| `-2147483647` | inteira | `GRUPO_PECA.TIPO_CONFIGURACAO_GP` (todas as linhas), `ENTRADA_PECA.SECAO_EP` (~70 %) |
| `-1.7976931348623157e+308` (`-DBL_MAX`) | real | `PECA.DIAMETRO_PECA` e `COMPRIMENTO_PECA` (~82 % das peças numa biblioteca de conexões) |

Uma coluna com sentinela **não está vazia no sentido do SQL**: `IS NULL` não a encontra, um
`if peca['comprimento_cm']:` a considera verdadeira, e qualquer aritmética produz lixo.
`read_aq._sem_sentinela()` converte as duas para `None`; as quatro chaves numéricas do
`build_product_map` passam por ela.

### Enums do AltoQi — valores observados

Nada disto está documentado pelo fabricante do software; são correlações entre `NOME_GP` e os
códigos, em bibliotecas de conexões (schema 595), bombas (607), aquecedores e elétrica. Extraia
de uma biblioteca nova com `aq_referencia` antes de confiar.

`GRUPO_PECA.PROJETO_APLICACAO` — tipo de instalação:
**8** esgoto · **12** água fria · **22** incêndio · **36** gás · **64/76** elétrico.
Água quente, pluvial e ar condicionado não foram observados.

`ENTIDADE_IFC` / `TIPO_ENTIDADE_IFC` / `ENTIDADE_IFC_2X3` andam sempre juntos, em combinações fixas:

| IFC4 | tipo | 2×3 | O que é |
|---|---|---|---|
| 2071 | 4099 | 2088 | `IfcPipeFitting` — curva, luva, cap, tê, redução, ramal |
| 2072 | 4096 | 2086 | `IfcPipeSegment` — tubo |
| 2075 | 4118 | 2093 | bomba |
| 2076 | 4122 | 2092 | aparelho sanitário |
| 2079 | 4121 | 2092 | terminal de ventilação |
| 2084 | 4103 | 2091 | válvula |
| 2085 | 4123 | 2092 | terminal de descarte — ralo, caixa sifonada |
| 2090 | 4138 | 2090 | aquecedor a gás |

`SUBTIPO_IFC` dentro de `IfcPipeFitting`: **0** curva/joelho · **1** luva · **3** cap · **4**
tê/junção · **6** redução · **7** ramal. Em `IfcPipeSegment` só o 3; em bomba só o 5; em válvula
só o 22. `SUBTIPO_IFC_2X3` é sempre igual a `SUBTIPO_IFC`.

`PECA.TIPO_APLICACAO_PECA`: **1** tubo · **2** conexão · **6** bomba · **8** aparelho sanitário ·
**9** caixa sifonada / ralo com grelha · **10** ralo · **55** ramal de ventilação.

Colunas de grupo fixas por material, numa biblioteca de PVC: `RUGOSIDADE_GP = 135.0`
(Hazen-Williams C), `RUGOSIDADE_EQUIVALENTE = 6e-05`, `COEFICIENTE_MANNING = 0.01`, `TIPO_FWH = 1`,
`TIPO_SECAO_GP = 0` (circular), `TIPO_MATERIAL = 0`; `ELEMENTO_APLICACAO` e `REPRESENTACAO_GP` são
0, exceto 1 e 2 nos grupos de tubo. `DADOS_HIDRAULICOS.TIPO_CURVA = 2` em todas as conexões.

Propriedades personalizadas observadas — bombas: Tensão, Corrente, Grau de Proteção, Isolamento,
Sucção x Recalque, Altura Máxima, Motor, Rotor, Rotação. Conexões: Bolsa, Classe de rigidez,
Encaixe, Fecho Hídrico, Vazão, Inclinação. Elétrica: Corrente máxima, Conectividade, Touch,
Temperatura de cor, Dimerizável. `TIPO_VALOR = 0` (texto) mesmo para números — converter com `float`.

### Versões de schema — indexadas por número

| `VERSAO` | Diferença notada |
|---|---|
| 552–582 | `ENTRADA_3D` **não tem** a coluna `DIAMETRO` |
| 595 | — |
| 607 | `ENTRADA_3D.DIAMETRO` existe; é a versão que o escritor emite |

Uma query com `ENTRADA_3D.DIAMETRO` quebra com `no such column` nas bibliotecas antigas — testar
`VERSAO_BANCO_CADASTRO.VERSAO` ou `PRAGMA table_info` antes. O leitor OQ3D foi validado em seis
versões (552, 562, 572, 582, 595, 607) sem falha de parse; o formato do BLOB não mudou com o schema.

### Peças sem geometria são esperadas

Peça sem linha em `PECA_SIMBOLOGIA_3D` não tem forma fixa: **tubos** (o Builder gera o cilindro
por diâmetro × comprimento) e **kits de aparelho sanitário** (ramal de ventilação, tanque, vaso com
tê) — entradas de projeto. Numa biblioteca de conexões são **cerca de um quarto das peças**. Pular
é o correto; o build informa quantas.

Mas "sem 3D" tem dois significados, e o build os separa: `build_catalog_from_aq` devolve
`(catalog, n_geo, diag)` e `resumo_diag(diag)` separa:

| Categoria em `diag` | Significado | Como sai |
|---|---|---|
| `pecas_sem_simbologia` | tubo/kit — sem linha em `PECA_SIMBOLOGIA_3D` | linha informativa "— esperado" |
| `sim_sem_blob`, `sim_nao_oq3d` | simbologia existe mas o BLOB é nulo ou não é OQ3D | `AVISO: N simbologia(s) descartada(s)` |
| `sim_ilegivel` | `OQ3DError` (truncado/corrompido), com id, nome e erro | idem, uma linha por simbologia |
| `sim_vazia` | parse ok, nenhuma malha (era o sintoma da malha versão 3 antes da correção) | idem |
| `pecas_sim_descartada` | peças que ficaram sem 3D **por causa** dos itens acima | contagem no mesmo AVISO |
| `avisos` | `OQ3DAvisoParse` por simbologia (raízes divergentes do cabeçalho) | `AVISO: N simbologia(s) com aviso de parse` |

**Descartada × aviso de parse:** descartada é geometria perdida; aviso é geometria completa com
hierarquia suspeita (transforms de nós promovidos podem deslocar a peça numa biblioteca de
conexões). Nenhum dos dois pode ficar só em `warnings.warn` — foi colhendo o aviso por simbologia
que a malha versão 3 apareceu. Teste:
`tests/biblioteca/test_catalogo.py::test_diag_separa_tubos_de_simbologia_descartada`.

### Como o pipeline lê

| Função (`read_aq.py`) | O que devolve | Toca a geometria? |
|---|---|---|
| `open_aq(path)` | `(con, tmp_dir)` — SQLite direto ou extraído do ZIP; `text_factory` cp1252 já configurado | não |
| `extract(path)` | `{grupos, pecas, curvas, propriedades}` — `SELECT *` em `GRUPO_PECA` e `PECA` (`ATIVO = 1`), joins de curva e de propriedade | não |
| `extract_simbologias(path)` | `simbologias {id → {nome, grupo, classe, blob, imagem}}` e `por_peca {id_peca → id_simbologia}` — colunas explícitas com `CAST AS BLOB`; sem `WIREFRAME` | sim |
| `peek_metadata(path)` | `fabricante` (prefixo comum das classes, Title Case; `PECA.BIBLIOTECA` como reforço), `linhas`, `grupos`, `has_curves`, `n_pecas`, `n_simbologias`, `schema` | não |
| `build_product_map(data)` | `{nome_gp → {serie, pecas: [{id, nome, conexoes, diametro_codigo, comprimento_cm, …, specs, curva_pts}]}}` — usado por `ferramentas.validar_aq` | não |

`peek_metadata` deixa `FileNotFoundError` subir (caminho errado é erro do operador) e engole só
"arquivo existe mas não é `.aq` legível". Do lado do catálogo, `catalogo.inferencia.peek_aq` monta
fabricante e título a partir disso; o nome do produto ganha o prefixo do grupo **por grupo**, quando
algum `NOME_PECA` do grupo tem menos de 4 caracteres ou se repete em outro grupo (`'100mm'` → `'Cap
100mm'`; um nome já completo fica como está).

## Onde está no código

- `biblioteca/bim_pipeline/aq/read_aq.py` — `_decode_texto`, `open_aq`, `extract`, `_sem_sentinela`,
  `build_product_map`, `read_classes`, `peek_metadata`, `extract_simbologias`.
  CLI: `python3 -m bim_pipeline.cli.read_aq <arquivo.aq> [saida.json] [--meta]`.
- `biblioteca/bim_pipeline/aq/oq3d.py` — o BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D` (ver `oq3d.md`).
- `biblioteca/bim_pipeline/catalogo/catalogo.py` — `build_catalog_from_aq`, `resumo_diag`, regra de prefixo por grupo.
- `biblioteca/bim_pipeline/catalogo/inferencia.py` — `peek_aq`, cascata de fabricante/título.
- `biblioteca/bim_pipeline/cli/ferramentas/aq_referencia.py` — somente leitura: imprime os valores de enum e as tabelas preenchidas de um `.aq` real.
- `tests/biblioteca/test_catalogo.py` — separação tubo/kit × simbologia descartada.

## Ver também

- `aq-escrita.md` — o inverso: gerar um `.aq` que o Builder aceita.
- `oq3d.md` — o formato binário da malha dentro de `SIMBOLOGIA_3D`.
- `geometria.md` — `{pos, col, idx}`, dedup, unidades e eixos do viewer.
- `catalogo-modelo.md` — o que o catálogo salvo guarda de cada peça (e o que não guarda).
- `diagnostico.md` — sintoma → causa, incluindo as linhas de encoding, sentinela e `no such column`.
- Skill `docs/skills/leitor-biblioteca-aq/` — a mesma matéria para uso fora deste repositório, com as queries de extração.
