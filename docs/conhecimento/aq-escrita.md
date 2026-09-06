# Escrever um `.aq` do AltoQi Builder (`biblioteca/bim_pipeline/aq/aq_writer.py`)

> Escrita. O irmão `aq-formato.md` cobre o inverso — ler um `.aq` que já existe. Aqui o
> `.aq` **nasce** neste projeto: de uma malha qualquer (`geo_to_aq.py`, uma peça) ou de um
> catálogo inteiro salvo (`catalogo_to_aq.py`, N peças).

Para quem precisa gerar uma biblioteca que o AltoQi Builder aceite: a partir de uma
geometria isolada (um STEP tesselado, uma peça editada num viewer) ou a partir de um
catálogo com dezenas ou centenas de produtos. Não é um formato documentado pelo
fabricante — tudo abaixo foi extraído de bibliotecas reais e confirmado por aceitação no
Builder de verdade.

## O DDL não se escreve à mão

O `.aq` tem 77 tabelas e 84 índices. Uma coluna faltando faz o AltoQi recusar o arquivo —
não vale a pena arriscar um `CREATE TABLE` manual. O DDL do schema **607** (o mais novo
observado) está embarcado em `biblioteca/bim_pipeline/aq/schema-aq-607.sql`, extraído do
`sqlite_master` de um `.aq` real:

```sql
SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND type IN ('table', 'index');
```

`aq_writer.criar_schema(destino)` executa esse arquivo inteiro num banco novo. Sem o
arquivo (`schema_sql=None`), aceita um `modelo` — outro `.aq` real — e copia o DDL dele pela
mesma query, para quando se quiser gerar contra um schema diferente do embarcado.

## `EscritorAq`: o texto tem de ser gravado em cp1252

**É o erro que corrompe o arquivo em silêncio.** O `.aq` **declara** `PRAGMA encoding =
UTF-8` mas o Builder — aplicação Windows — **grava bytes cp1252** nas colunas de texto (ver
`aq-formato.md`, "Encoding"). O módulo `sqlite3` do Python vincula `str` como UTF-8 e
`bytes` como BLOB — nenhum dos dois produz o resultado certo. A saída é o `CAST`:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes sem converter: `typeof()` volta `'text'`, os
bytes ficam idênticos aos de uma biblioteca real, e o leitor do projeto devolve a string
original. Gravar em UTF-8 faz `'Soldável'` voltar `'SoldÃ¡vel'` **sem levantar exceção em
lugar nenhum** — passa no `integrity_check`, passa no `foreign_key_check`, e o nome errado
chega à ficha do produto na página pública. Esse erro já aconteceu do lado de quem lê; do lado
de quem escreve o risco é o mesmo.

`EscritorAq.ins(tabela, **campos)` faz esse `CAST` em toda coluna de texto automaticamente.
O encode é **estrito** — nunca `errors='replace'`. Um caractere fora das 256 posições do
cp1252 (um travessão longo, uma seta) não pode virar `?` dentro do nome de um produto sem
que ninguém note: `EscritorAq.cp1252` aborta com `tabela.coluna`, o valor e a posição do
caractere:

```
GRUPO_PECA.NOME_GP: 'Joelho 90° – Roscável' tem caractere fora do cp1252
na posição 10 ('–'). O .aq não representa esse caractere — troque-o na origem.
```

Essa é a checagem que se confere depois de gravar, também: os bytes altos das colunas de
texto **não podem** ser UTF-8 válido (um acento em cp1252 é um byte alto isolado; em UTF-8
são dois) — é o passo 7 do `validar_aq`, abaixo.

## Ordem de inserção

O SQLite **não** aplica chaves estrangeiras por padrão — um `ID_GRUPO_PECA` órfão passa
pelo `INSERT` sem erro e só aparece no AltoQi (ou no `PRAGMA foreign_key_check`, que os dois
escritores rodam no fim). A ordem que fecha as FKs:

```
VERSAO_BANCO_CADASTRO
CLASSE_PECA → GRUPO_PECA → PECA → (DADOS_HIDRAULICOS, ENTRADA_PECA, ITEM_ASSOCIADO)
CLASSE_SIMBOLOGIA_3D → GRUPO_SIMBOLOGIA_3D → SIMBOLOGIA_3D
                                              → (ENTRADA_3D, PECA_SIMBOLOGIA_3D)
GRUPO_PROPRIEDADE_PERSONALIZADA → PROPRIEDADE_PERSONALIZADA
                                   → VALOR_PROPRIEDADE_PERSONALIZADA
CLASSE_ITEM → GRUPO_ITEM → ITEM
MODELO_BOMBA → ITEM_CURVA_BOMBA        (só bibliotecas de bomba)
```

Uma biblioteca de fabricante preenche 16 a 25 das 77 tabelas — o resto é cadastro do
projeto, não do produto. Uma peça **com 3D**, o mínimo que o Builder aceita, usa estas
colunas (as que não aparecem ficam no `DEFAULT` do DDL):

| Tabela | Colunas que o escritor preenche |
|---|---|
| `CLASSE_PECA` | `ID_CLASSE_PECA`, `NOME_CP`, `INDICACAO_CP`, `CODIGO_ELLO`, `ATIVO` |
| `GRUPO_PECA` | `ID_GRUPO_PECA`, `NOME_GP`, `ID_CLASSE_PECA`, `TIPO_SECAO_GP`, `RUGOSIDADE_GP`, `RUGOSIDADE_EQUIVALENTE`, `TIPO_FWH`, `COEFICIENTE_MANNING`, `TIPO_MATERIAL`, `PROJETO_APLICACAO`, `ELEMENTO_APLICACAO`, `TIPO_CONFIGURACAO_GP` (sentinela), `REPRESENTACAO_GP`, `ENTIDADE_IFC`/`TIPO_ENTIDADE_IFC`/`ENTIDADE_IFC_2X3`, `SUBTIPO_IFC`/`SUBTIPO_IFC_2X3`/`TIPO_ENTIDADE_IFC_2X3`, `CODIGO_ELLO`, `ATIVO` |
| `PECA` | `ID_PECA`, `NOME_PECA`, `ID_GRUPO_PECA`, `BIBLIOTECA`, `DESCRICAO_DADOS`, `DESCRICAO_DADOS_SIMBOLOGIA`, `INDICACAO_DADOS`, `TIPO_APLICACAO_PECA`, `DIAMETRO_PECA`/`COMPRIMENTO_PECA`/`ESPESSURA_PECA`/`LARGURA_PECA`/`ALTURA_PECA`/`PROFUNDIDADE_PECA` (sentinela), `POSICIONAR_SIMBOLOGIA_3D`, `INDICE_SIMBOLO3D_SELECIONADO`, `SIMBOLO_SELECIONADO`, `POSICIONAR_SIMBOLOGIA`, `POSICAO_DADOS`, `POSICIONA_CAMPOS`, `DESENHA_SIMBOLOGIA`, `FORMATO_PECA`, `OPCAO_RENDERIZACAO_PLANIFICADA`, `INCLUIR_REPRESENTACAO3D_PARAMETRICA`, `CONEXAO_VOLUMETRICA`, `CODIGO_ELLO`, `ATIVO` |
| `PECA_SIMBOLOGIA_3D` | `ID_PECA_SIMBOLOGIA_3D`, `ID_PECA`, `ID_SIMBOLOGIA_3D` — o vínculo; sem ela a peça não tem forma |
| `SIMBOLOGIA_3D` | `ID_SIMBOLOGIA_3D`, `ID_GRUPO_SIMBOLOGIA_3D`, `NOME`, `SIMBOLOGIA_3D` (o BLOB OQ3D, `sqlite3.Binary`), `USA_CORES_PECA`, `REFERENCIA_CORTE`, `EMBUTIMENTO`, `DESLOCAMENTO_X/Y/Z`, `ANGULO_PLANO_XY/XZ/YZ`, `CODIGO_ELLO`, `ATIVO` |
| `CLASSE_SIMBOLOGIA_3D` / `GRUPO_SIMBOLOGIA_3D` | `NOME_CLASSE` / `NOME_GRUPO`, `ID_CLASSE`/`ID_CLASSE_SIMBOLOGIA_3D`, `CODIGO_ELLO`, `ATIVO` |
| `PROPRIEDADE_PERSONALIZADA` | `ID_PROPRIEDADE_PERSONALIZADA`, `ID_GRUPO_PROPRIEDADE_PERSONALIZADA`, `NOME`, `TIPO_VALOR=0` (texto, mesmo para número) |
| `VALOR_PROPRIEDADE_PERSONALIZADA` | `ID_VALOR_PROPRIEDADE_PERSONALIZADA`, `ID_PROPRIEDADE_PERSONALIZADA`, `ID_PECA`, `VALOR` |

## Os enums do AltoQi — valores observados

Nada disto está documentado pelo fabricante; são correlações entre o nome do grupo e os
códigos, confirmadas em bibliotecas de conexões, bombas, aquecedores e elétrica reais.
`aq_referencia` (abaixo) extrai os mesmos valores de um `.aq` novo antes de confiar neles.

`GRUPO_PECA.PROJETO_APLICACAO` — tipo de instalação: **8** esgoto · **12** água fria ·
**22** incêndio · **36** gás · **64/76** elétrico. `aq_writer.aplicacao_de(*textos)` infere
isso do título e das séries do catálogo por palavra: `ESGOTO`/`PLUVIAL` → 8,
`INCENDIO`/`SPRINKLER`/`HIDRANTE` → 22, `GAS`/`GLP` → 36, senão 12 (água fria é o padrão).

`ENTIDADE_IFC`/`TIPO_ENTIDADE_IFC`/`ENTIDADE_IFC_2X3` andam sempre juntos:

| IFC4 | tipo | 2×3 | O que é |
|---|---|---|---|
| 2071 | 4099 | 2088 | `IfcPipeFitting` — curva, luva, cap, tê, redução, ramal |
| 2072 | 4096 | 2086 | `IfcPipeSegment` — tubo |
| 2075 | 4118 | 2093 | bomba |
| 2076 | 4122 | 2092 | aparelho sanitário |
| 2079 | 4121 | 2092 | terminal de ventilação |
| 2084 | 4103 | 2091 | válvula |
| 2085 | 4123 | 2092 | terminal de descarte — ralo, caixa sifonada |

`SUBTIPO_IFC` dentro de `IfcPipeFitting`: **0** curva/joelho · **1** luva · **3** cap ·
**4** tê/junção · **6** redução · **7** ramal; em tubo só o 3, em bomba só o 5, em válvula
só o 22. `SUBTIPO_IFC_2X3` é sempre igual ao `SUBTIPO_IFC`.

`PECA.TIPO_APLICACAO_PECA`: **1** tubo · **2** conexão · **6** bomba · **8** aparelho
sanitário · **9** caixa sifonada/ralo com grelha · **10** ralo · **55** ramal de
ventilação.

`aq_writer.classificar_grupo(nome)` decide os três códigos acima **a partir do nome do
grupo**, para quando não se tem os códigos originais (é o caso do catálogo salvo — ver
abaixo). Regras **por palavra inteira** (`\b palavra \b` sobre o nome sem acento, em
maiúsculas), na ordem em que aparecem — a primeira que casa vence: `TUBO` antes de mais
nada, depois `BOMBA`/`PRESSURIZADOR`, `CAIXA SIFONADA`, `RALO`, `VALVULA`/`REGISTRO`,
`JUNCAO`/`TE` (tê — casa antes de `CURVA`/`JOELHO`, porque "Junção com Joelho" é tê, não
curva), `CURVA`/`JOELHO`, `CAP`/`PLUG`/`TAMPAO`, `REDUCAO`/`BUCHA`, e por fim
`LUVA`/`UNIAO`/`NIPEL`/`ADAPTADOR`. **Sem nenhuma regra casando, a peça vira conexão
genérica (luva)** — `IFC_CONEXAO, SUB_LUVA, APL_CONEXAO` — o enquadramento mais comum e o
mais inofensivo para um grupo que o vocabulário não reconheceu. Ajustadas contra os grupos
com 3D de uma biblioteca real de conexões: reproduz cerca de 98% deles (189 de 192) — os
que não batem têm códigos diferentes dos irmãos no próprio arquivo original.

## `geo_to_aq.py` — uma peça a partir de qualquer malha

Quando a geometria não nasceu no AltoQi — um STEP tesselado, uma peça editada num viewer
— `geo_to_aq.gerar()` embala `{pos, col, idx}` (ou uma lista de `partes`) numa biblioteca
de uma peça só. Conversão do viewer (metros, Y-up) para o OQ3D (centímetros, Z-up):

```
oq3d = (x·100, −z·100, y·100)
```

**Malhas por cor:** o OQ3D só tem cor por malha (`TCoatingColor`), então uma malha do
viewer com várias cores é dividida por cor antes de escrever — cada cor vira um objeto-raiz
OQ3D próprio. Se a entrada já traz `partes` com `pos` cada uma (o editor grava assim), cada
parte vira uma raiz, sem dividir por cor de novo.

A peça entra como equipamento genérico: `TIPO_APLICACAO_PECA = 2` (conexão),
`ENTIDADE_IFC = IfcPipeFitting`, sem código de diâmetro (`DIAMETRO_PECA` na sentinela
`-DBL_MAX`, como a maioria das conexões numa biblioteca real). A origem fica registrada
numa propriedade personalizada própria, não inventada: `specs['Geometria 3D'] = 'malha
importada — <origem>; N malha(s), T triângulos'`.

**O que fica de fora:** `ENTRADA_PECA` (bocais, comprimentos equivalentes) e a simbologia
2D — não há de onde tirar isso de uma malha solta. **O código comercial (`ITEM.CODIGO_ITEM`)
não fica de fora**: `CLASSE_ITEM → GRUPO_ITEM → ITEM → ITEM_ASSOCIADO` são gravados também
para a peça única, com `CODIGO_ITEM` vindo de `info['codigo']` ou, na falta dele, do nome da
peça — é o mesmo lugar onde o catálogo inteiro grava o código (abaixo).

## `catalogo_to_aq.py` — o catálogo inteiro

Generalizar a receita acima para um catálogo com centenas de produtos exige cinco regras
que só aparecem escrevendo N peças em vez de uma — todas conferidas contra uma biblioteca
real de conexões reconstruída (cerca de 850 peças exportadas, 450 simbologias, `NOME_PECA`
igual ao original em 100% das peças, bbox e triângulos iguais em todas as geometrias) e
**aceita pelo AltoQi Builder**.

**1. Uma `SIMBOLOGIA_3D` por arquivo de geometria, não por peça.** O pipeline já grava uma
geometria por simbologia e várias peças apontam para ela (compartilhamento entre variantes,
p. ex. peças que só mudam a orientação de inserção). Escrever preserva isso: o mesmo caminho
de arquivo vira a mesma linha de `SIMBOLOGIA_3D`, e cada peça que o usa ganha sua própria
linha em `PECA_SIMBOLOGIA_3D`. Uma geometria editada (copy-on-write, arquivo próprio) vira
simbologia própria — deixa de ser compartilhada.

**2. Uma `PROPRIEDADE_PERSONALIZADA` por chave de spec, não por peça.** Um catálogo real
tem uma dúzia de chaves de spec e milhares de valores (peça × chave). Escrever uma
`PROPRIEDADE_PERSONALIZADA` por (peça, chave) multiplicaria a tabela por ~400 e o Builder
mostraria milhares de "propriedades" em vez de uma dúzia. Um único
`GRUPO_PROPRIEDADE_PERSONALIZADA` ("Fabricante: Título"), uma `PROPRIEDADE_PERSONALIZADA`
por chave distinta, e um `VALOR_PROPRIEDADE_PERSONALIZADA` por (peça, chave) não vazia.

**3. `NOME_PECA` sem o prefixo da série.** O catálogo salvo pode exibir "Cap 50mm" porque
"50mm" sozinho é ambíguo entre grupos (Cap, Luva, Joelho todos têm um "50mm"); no `.aq` o
fabricante grava só `NOME_PECA = '50mm'` no grupo `Cap`. `nome_da_peca()` tira o prefixo
`"<série> "` do nome da tela antes de gravar — devolve o nome original na íntegra numa
reconstrução completa. **Uma reconstrução com menos peças pode mostrar nomes diferentes da
tela original, e isso é esperado**: a regra de quando prefixar depende do conjunto de
nomes do arquivo inteiro (é ambíguo *dentro daquele arquivo*), e um export com menos peças
(sem tubos, sem kits) tem um conjunto menor — o que era ambíguo lá pode deixar de ser aqui.
`--manter-prefixo-serie` desliga a remoção, para quem quer o nome da tela literal.

**4. Um grupo por série, com os códigos IFC inferidos do nome.** O catálogo não guarda os
códigos originais de grupo, então `classificar_grupo()` (acima) os infere do nome da série
— por palavra inteira, ~98% dos grupos de uma biblioteca real de conexões reproduzidos.
**Uma série com curva Q-H promove o grupo inteiro a bomba** (`IFC_BOMBA`, `SUB_BOMBA`,
`APL_BOMBA`), independente do que `classificar_grupo` teria dito pelo nome — a presença de
curva é um sinal mais forte que o vocabulário.

**5. As colunas exatas de uma peça com 3D**, como um fabricante real grava:
`POSICIONAR_SIMBOLOGIA_3D = 3`, `INDICE_SIMBOLO3D_SELECIONADO = 1`, `INDICACAO_DADOS` =
nome, `DESCRICAO_DADOS_SIMBOLOGIA` = série, as seis dimensões (`COMPRIMENTO`/`ESPESSURA`/
`LARGURA`/`ALTURA`/`PROFUNDIDADE_PECA`) na sentinela `-DBL_MAX`, `INDICACAO_PLANTA` e
`INDICACAO_DETALHE` nulos. (`geo_to_aq.py`, a peça única, usa `0`/`-1` em algumas dessas
colunas em vez da sentinela e preenche as indicações — os dois conjuntos, verificados
separadamente, abriram no Builder.)

**O que um catálogo salvo não guarda, e portanto o `.aq` gerado não tem:** as peças sem
simbologia 3D do arquivo original (tubos e kits — cerca de um quarto das peças numa
biblioteca real de conexões), `ENTRADA_PECA`/`ENTRADA_3D` (bocais e conectividade
hidráulica), simbologia 2D, `IMAGEM`, `WIREFRAME`, e o **código comercial original**
(`ITEM.CODIGO_ITEM` sai preenchido, mas com a spec "Código" se existir, senão o slug do
produto — nunca o código de catálogo de origem, que o catálogo salvo não guarda).

### Erros que abortam a exportação

Nada é engolido — tudo acusa com `exit 1` e apaga o arquivo `.aq` parcial (um `.aq` que
"quase" abriu é pior que nenhum):

| Erro | Onde é pego |
|---|---|
| Geometria ausente no storage | antes de ler o JSON, com o caminho e o nome do produto |
| JSON de geometria inválido ou malha vazia | `malhas_por_cor` / `malhas_de_partes` |
| Caractere fora do cp1252 em nome, série ou spec | `EscritorAq.cp1252`, com `tabela.coluna` e a posição do caractere |
| Catálogo sem produtos | antes de criar o schema |
| Chave estrangeira órfã | `PRAGMA foreign_key_check`, rodado no fim, antes do `commit` final |

A última linha do `stdout` de `catalogo_to_aq` é sempre um resumo em JSON —
`{pecas, grupos, simbologias, triangulos, propriedades, valores, curvas, bytes, segundos}`
— para quem chama de outro processo (o serviço de ingestão) parsear sem depender do texto
de progresso, que vai no `stderr`.

## O que só o Builder pode dizer

O leitor do projeto (`read_aq.py`/`oq3d.py`) confere que o arquivo é consistente consigo
mesmo; só o AltoQi Builder confirma que ele é aceito de verdade. Duas aceitações manuais
registradas até aqui: um `.aq` de uma peça só, gerado do zero — árvore de
classes/grupos/peças correta, propriedades personalizadas visíveis, acentos íntegros; e um
catálogo inteiro reconstruído a partir do que estava salvo — aberto e conferido pelo usuário. Nenhum dos dois testes tem registro detalhado do que foi olhado na janela 3D ou do
lançamento da peça numa rede — só o veredito de abertura.

## Ferramentas

| Ferramenta | Para que serve |
|---|---|
| `python3 -m bim_pipeline.cli.ferramentas.validar_aq <arquivo.aq> [--tubo-cm N] [--max-conexao-cm N]` | Valida um `.aq` gerado **com o leitor do próprio projeto** — não é uma checagem de SQLite genérica, é a prova de que `read_aq`/`oq3d` leem o arquivo sem saber que ele não veio do AltoQi: abre e confere a versão do schema, integridade e FKs, `extract`, a cascata de fabricante/título (não pode sair vazia nem em slug), o mapa peça→grupo, a geometria parseada, o cp1252 (nunca UTF-8, nenhum byte de controle) e o código comercial em `ITEM.CODIGO_ITEM`. As duas flags ligam checagens de tamanho que dependem do catálogo (comprimento de barra de tubo, maior conexão plausível) — sem elas não rodam |
| `python3 -m bim_pipeline.cli.ferramentas.aq_referencia <arquivo.aq> [--tabela NOME] [--limite N]` | Só leitura: extrai de um `.aq` real os valores concretos que um gerador precisa — os enums (`PROJETO_APLICACAO`, `TIPO_APLICACAO_PECA`, `ENTIDADE_IFC`, `TIPO_SECAO_GP`...) e quais das 77 tabelas ficam de fato preenchidas. Usar antes de confiar nos valores observados acima numa biblioteca nova |
| `oq3d_roundtrip` (`biblioteca/bim_pipeline/cli/ferramentas/oq3d_roundtrip.py`) | Prova que `oq3d_writer.py` grava um blob que o próprio `oq3d.py` lê de volta idêntico — vértice a vértice, triângulo a triângulo, cor a cor — inclusive o caso de rotação não simétrica, que pega o bug de gravar a matriz transposta sem mudar nenhuma contagem |

## Onde está no código

- `biblioteca/bim_pipeline/aq/aq_writer.py` — `SCHEMA_SQL`, `criar_schema`, `EscritorAq`
  (`ins`, `cp1252`, `versao`), as constantes de enum, `classificar_grupo`, `aplicacao_de`.
- `biblioteca/bim_pipeline/aq/schema-aq-607.sql` — o DDL das 77 tabelas e 84 índices.
- `biblioteca/bim_pipeline/aq/oq3d_writer.py` — o escritor do BLOB binário (ver `oq3d.md`).
- `biblioteca/bim_pipeline/saida/geo_to_aq.py` — `gerar()`, uma peça. CLI:
  `python3 -m bim_pipeline.cli.gerar_aq entrada.json saida.aq [--fabricante] [--linha] [--nome] [--codigo]`.
- `biblioteca/bim_pipeline/saida/catalogo_to_aq.py` — `gerar()`, o catálogo inteiro. CLI:
  `python3 -m bim_pipeline.cli.catalogo_para_aq manifesto.json saida.aq [--manter-prefixo-serie] [--quiet]`.
- `biblioteca/bim_pipeline/cli/ferramentas/validar_aq.py` — validação com o leitor do projeto.
- `biblioteca/bim_pipeline/cli/ferramentas/aq_referencia.py` — extração de enums de um `.aq` real.
- `biblioteca/bim_pipeline/cli/ferramentas/oq3d_roundtrip.py` — prova do escritor OQ3D.
- `tests/biblioteca/test_geo_to_aq.py`, `test_catalogo_to_aq.py`, `test_ferramentas.py` — a
  suíte que cobre os três escritores e as duas ferramentas de validação.

## Ver também

- `aq-formato.md` — o inverso: ler um `.aq` que já existe, schema, cp1252, sentinelas.
- `oq3d.md` — o formato binário da malha gravada em `SIMBOLOGIA_3D.SIMBOLOGIA_3D`.
- `geometria.md` — `{pos, col, idx}`, dedup, unidades e eixos do viewer (a entrada de
  `geo_to_aq` e `catalogo_to_aq`).
- `formas-representativas.md` — quando a geometria não vem de malha nenhuma, mas de
  parâmetros.
- Skill `docs/skills/leitor-biblioteca-aq/` — a mesma matéria para uso fora deste
  repositório.
