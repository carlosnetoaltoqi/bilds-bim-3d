---
name: leitor-biblioteca-aq
description: Lê E ESCREVE arquivos de biblioteca BIM do AltoQi Builder (.aq) — SQLite com geometria 3D embutida. Extrai peças, dados hidráulicos, curvas de bomba, propriedades, miniaturas e a malha 3D completa (formato OQ3D), dispensando os IFCs; e gera um .aq do zero, com o schema, os enums, o encoding cp1252 e o binário OQ3D corretos.
version: 2.8.1
author: Bilds / carlosnetoaltoqi
---

# Skill: leitor-biblioteca-aq

Você é especialista em abrir e extrair dados de arquivos de biblioteca BIM do AltoQi Builder (`.aq`). Ao ser invocada, pergunte ao usuário o caminho do arquivo `.aq`. Não assuma nenhum diretório padrão.

---

## O mais importante: o .aq contém a geometria 3D

**O `.aq` não é só o banco de dados de produto — ele carrega a malha 3D completa, com cor e miniatura.** É a mesma geometria que o AltoQi exporta como IFC. Isso significa que **não é preciso ter os arquivos IFC** para gerar visualização 3D.

A geometria está no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, num formato binário proprietário chamado **OQ3D** — documentado na íntegra mais abaixo, na seção "Formato OQ3D".

Validado em **nove bibliotecas** e **seis versões de schema** (552, 562, 572, 582, 595, 607), sem uma falha de parse. As três de referência:

| Biblioteca | Schema | Peças | Geometrias | Domínio | IFCs de contraprova |
|---|---|---|---|---|---|
| Dancor | 607 | 13 | 13 | bombas de incêndio | 14 (tessellated) |
| Amanco | 595 | 1.168 | 457 | conexões PVC esgoto | 502 (`IFCADVANCEDBREP`) |
| Intelbras | 572 | 32 | 18 | dispositivos elétricos | nenhum (teste cego) |

Onde o IFC é tessellated (Dancor), os triângulos batem **exatamente**. Onde é B-rep (Amanco), a forma converge a menos de 1 mm mas a tesselação é independente — o IFC guarda o sólido exato e é retessellizado a cada leitura; o `.aq` traz a malha que o AltoQi fixou.

Ler a geometria do `.aq` é **85× a 421× mais rápido** que parsear os IFCs equivalentes.

---

## O que é um arquivo .aq

Um `.aq` é um arquivo ZIP renomeado. Dentro há um banco de dados SQLite com toda a biblioteca BIM: peças, grupos, dados hidráulicos, curvas de bomba, propriedades personalizadas e imagens.

Para abrir — tenta SQLite direto primeiro, cai para ZIP se falhar:

```python
import zipfile, sqlite3, os, shutil, tempfile

def _decode_texto(b):
    """
    Texto do .aq é cp1252 (AltoQi Builder é app Windows), não latin-1.
    Fallback porque cp1252 deixa cinco bytes indefinidos e falharia neles.
    """
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')


def open_aq(aq_path):
    """
    Abre um .aq como SQLite. Tenta direto primeiro (caso mais comum),
    cai para extração de ZIP se falhar.
    Retorna (connection, tmp_dir_ou_None).
    Caller deve fechar a connection; se tmp_dir não for None, remover com shutil.rmtree.
    """
    # `sqlite3.connect(caminho)` CRIA um arquivo vazio se ele não existir — e o erro
    # que sobra é o do fallback ("não é ZIP"), não "arquivo não encontrado".
    # Checar antes e abrir somente-leitura (URI com percent-encoding: os caminhos
    # de biblioteca têm espaço e acento).
    if not os.path.isfile(aq_path):
        raise FileNotFoundError(f'biblioteca .aq não encontrada: {aq_path}')

    # Tentativa 1: SQLite direto (alguns .aq são SQLite com extensão .aq)
    try:
        uri = 'file:' + pathname2url(os.path.abspath(aq_path)) + '?mode=ro'
        con = sqlite3.connect(uri, uri=True)        # from urllib.request import pathname2url
        con.text_factory = _decode_texto
        con.row_factory = sqlite3.Row
        con.execute('SELECT 1 FROM GRUPO_PECA LIMIT 1')
        return con, None
    except Exception:
        pass

    # Tentativa 2: ZIP contendo SQLite
    tmp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(aq_path, 'r') as z:
        z.extractall(tmp_dir)
    db_files = [f for f in os.listdir(tmp_dir)
                if os.path.isfile(os.path.join(tmp_dir, f)) and not f.endswith('.xml')]
    if not db_files:
        shutil.rmtree(tmp_dir)
        raise FileNotFoundError('Nenhum SQLite encontrado dentro do .aq')
    dest = os.path.join(tmp_dir, '_extracted.db')
    shutil.copy(os.path.join(tmp_dir, db_files[0]), dest)
    con = sqlite3.connect(dest)
    con.text_factory = _decode_texto
    con.row_factory = sqlite3.Row
    return con, tmp_dir
```

> ### ⚠️ Encoding: cp1252, **não** latin-1
>
> O AltoQi Builder é aplicação Windows — o texto no SQLite é **cp1252**. Os dois codecs
> são idênticos em toda a tabela **exceto na faixa 0x80–0x9F**, que é exatamente onde
> moram travessão (`0x96`), aspas curvas (`0x93`/`0x94`) e reticências (`0x85`) — os
> caracteres que aparecem em nome de produto.
>
> Lido como latin-1, `5U – 19” x 570mm MRD 557` vira `5U \x96 19\x94 x 570mm MRD 557`.
> **O erro é silencioso:** latin-1 decodifica qualquer byte sem lançar, então nada quebra
> — só sai errado, e vai parar na página pública.
>
> ```python
> def _decode_texto(b):
>     """cp1252 com fallback: os cinco bytes indefinidos do cp1252
>     (0x81, 0x8D, 0x8F, 0x90, 0x9D) fariam o build inteiro falhar."""
>     try:
>         return b.decode('cp1252')
>     except UnicodeDecodeError:
>         return b.decode('latin-1')
>
> con.text_factory = _decode_texto
> ```
>
> **Não troque o `text_factory` sem olhar as colunas binárias.** O latin-1 é
> byte-preserving, e é comum o código reconstruir o BLOB da geometria com
> `.encode('latin-1')` quando a coluna volta como `str`. Com cp1252 esse round-trip
> **não é reversível** — corromperia a malha 3D em silêncio. Use `CAST(col AS BLOB)` na
> query para forçar bytes e eliminar o re-encode.
>
> **Por que tentar SQLite direto primeiro:** versões recentes do AltoQi Builder distribuem o .aq como SQLite puro (sem ZIP). O ZIP é o caso legado. Tentar SQLite primeiro evita `zipfile.BadZipFile` desnecessário.

> ### ⚠️ Literal acentuado numa query também tem de ir em cp1252
>
> O mecanismo, documentado na 2.3.0: o `.aq` **declara** `PRAGMA encoding = UTF-8` e
> **guarda bytes cp1252**. O SQLite não valida a codificação do que se manda gravar, e o
> `typeof()` continua `'text'`:
>
> ```
> SELECT NOME_CP FROM CLASSE_PECA  →  b'Bomba de Combate a Inc\xeancio - Dancor'
> ```
>
> O módulo `sqlite3` do Python vincula um `str` como UTF-8, então
> `WHERE NOME_GP = 'Joelho 90° Soldável'` **nunca casa** — no banco é
> `b'...Sold\xe1vel'` e o parâmetro chega `b'...Sold\xc3\xa1vel'`. A query volta vazia,
> sem erro nenhum.
>
> ```python
> con.execute('... WHERE g.NOME_GP = CAST(? AS TEXT)', (nome.encode('cp1252'),))
> ```
>
> Só aparece quando se compara literal acentuado dentro do SQL — quem varre a tabela
> inteira e filtra em Python nunca encontra isso.

---

## Estrutura do banco — tabelas principais

### Metadados

**`VERSAO_BANCO_CADASTRO`** (1 linha)
| Coluna | Tipo | Descrição |
|---|---|---|
| `VERSAO` | INTEGER | Versão do schema do banco (ex: 607) |
| `TAG_IDIOMA` | TEXT | Idioma (`'pt-BR'`) |
| `MODO_GRAVACAO` | INTEGER | Modo de gravação interno |

---

### Hierarquia de peças

**`GRUPO_PECA`** — agrupa peças por família/série
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_GRUPO_PECA` | INTEGER PK | |
| `NOME_GP` | TEXT | Nome do grupo/série (ex: `'CAM-W21'`) |
| `PROJETO_APLICACAO` | INTEGER | Tipo de instalação (22 = incêndio, outros = hidráulico, elétrico…) |
| `RUGOSIDADE_GP` | REAL | Rugosidade interna em μm |
| `ENTIDADE_IFC` | INTEGER | Tipo de entidade IFC4 associado |
| `ENTIDADE_IFC_2X3` | INTEGER | Tipo de entidade IFC2×3 associado |
| `ATIVO` | INTEGER | 1 = ativo, 0 = inativo |

**`PECA`** — cada variante de produto dentro de um grupo
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_PECA` | INTEGER PK | |
| `NOME_PECA` | TEXT | Nome da variante (ex: `'2CV T 220/380V INC FLG IR3'`) |
| `ID_GRUPO_PECA` | INTEGER FK | Referência ao grupo |
| `DESCRICAO_DADOS` | TEXT | Descrição resumida (ex: `'2.1/2" x 2.1/2"'`) |
| `DIAMETRO_PECA` | REAL | **CÓDIGO de diâmetro, não centímetro** — ver o aviso abaixo |
| `DIAMETRO_INTERNO` | REAL | Diâmetro interno em **milímetro** (192,8 / 98,0 / 47,5) |
| `COMPRIMENTO_PECA` | REAL | Comprimento (cm) |
| `ALTURA_PECA` | REAL | Altura (cm) |
| `LARGURA_PECA` | REAL | Largura (cm) |
| `BIBLIOTECA` | TEXT | Nome da biblioteca de origem — **vazia nas 12 bibliotecas testadas** |
| `ATIVO` | INTEGER | 1 = ativo |

> ### ⚠️ `DIAMETRO_PECA` é um CÓDIGO de diâmetro, não um centímetro
>
> Corrigido na 2.3.0. As versões anteriores desta skill diziam "diâmetro nominal (cm)".
> É um índice numa escala de diâmetros nominais do AltoQi:
>
> | `NOME_PECA` (Amanco) | `DIAMETRO_PECA` |
> |---|---|
> | `40 mm - 1.1/2"` | 8 |
> | `50 mm - 2"` | 9 |
> | `75 mm - 3"` | 11 |
> | `100 mm - 4"` | 12 |
> | `150 mm - 6"` | 14 |
> | `200 mm - 8"` | 15 |
>
> `ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO` usam a mesma escala — a Dancor grava
> 7 a 11 nos bocais das bombas, cujas sucções e recalques vão de 1.1/4" a 3", o que
> encaixa em 32, 40, 50, 60 e 75 mm e confirma o código 10 como 60 mm. Os códigos 1 a 7
> não são observáveis nas 12 bibliotecas.
>
> **A distribuição real na Amanco, nas 1.168 peças:** 963 (82%) trazem a sentinela
> `-1.7976931348623157e+308` (`-DBL_MAX`), 93 trazem zero e **112 trazem código** — as 48
> de tubo, 52 de caixa sifonada e afins (`TIPO_APLICACAO_PECA=9`) e 12 de ralo (tipo 10).
>
> **Nenhuma das 700 conexões (tipo 2) tem código**: o diâmetro de uma conexão mora em
> `ENTRADA_PECA.DIAMETRO_EP`.
>
> Tratar esse número como centímetro erra por ~2× nas peças de tubo e devolve
> `-1.8e308` em todo o resto.

> ### As sentinelas: o AltoQi não usa `NULL` para "não definido"
>
> | Sentinela | Onde aparece |
> |---|---|
> | `-2147483647` | `GRUPO_PECA.TIPO_CONFIGURACAO_GP` (265 de 265 na Amanco), `ENTRADA_PECA.SECAO_EP` (1.871 de 2.627) |
> | `-1.7976931348623157e+308` | `PECA.DIAMETRO_PECA` em 963 de 1.168 na Amanco (82%) |

---

### Dados hidráulicos

**`DADOS_HIDRAULICOS`** — parâmetros hidráulicos por peça (1:1 com PECA para bombas)
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_DADOS_HIDRAULICOS` | INTEGER PK | |
| `ID_PECA` | INTEGER FK | Peça associada |
| `ID_MODELO_BOMBA` | INTEGER FK | Modelo de bomba (NULL para não-bombas) |
| `VAZAO_DH` | REAL | Vazão de projeto (L/min ou m³/h) |
| `PRESSAO_MINIMA` | REAL | Pressão mínima (m.c.a) |
| `PRESSAO_MAXIMA` | REAL | Pressão máxima (m.c.a) |
| `POTENCIA_DH` | REAL | Potência (CV ou kW) |
| `RENDIMENTO_DH` | REAL | Rendimento (%) |
| `FATOR_K` | REAL | Coeficiente K de perda de carga |
| `TIPO_CURVA` | INTEGER | Tipo de curva Q-H (0 = bomba centrífuga) |
| `DIAMETRO_ESGUICHO` | REAL | Diâmetro do esguicho (mm) |
| `COMPRIMENTO_EQUIVALENTE_LATERAL` | REAL | Comprimento equivalente lateral (m) |
| `COMPRIMENTO_EQUIVALENTE_DIRETO` | REAL | Comprimento equivalente direto (m) |

---

### Curva Q-H de bomba

**`MODELO_BOMBA`** — agrupa pontos de curva por modelo comercial
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_MODELO_BOMBA` | INTEGER PK | |
| `NOME_MB` | TEXT | Nome completo do modelo (encoding cp1252 — ver aviso acima) |
| `POTENCIA_MB` | REAL | Potência nominal (CV) |
| `ATIVO` | INTEGER | 1 = ativo |

**`ITEM_CURVA_BOMBA`** — pontos da curva Q-H (N pontos por modelo)
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_ITEM_CURVA_BOMBA` | INTEGER PK | |
| `ID_MODELO_BOMBA` | INTEGER FK | Modelo de bomba |
| `VAZAO_ICB` | REAL | Vazão (m³/h) |
| `ALTURA_ICB` | REAL | Altura manométrica (m.c.a) |
| `POTENCIA_ICB` | REAL | Potência no ponto (CV ou kW) |
| `RENDIMENTO_ICB` | REAL | Rendimento no ponto (%) |
| `NPSH` | REAL | NPSH requerido (m) |

---

### Propriedades personalizadas

Propriedades livres definidas pelo fabricante — chave/valor por peça.

**`GRUPO_PROPRIEDADE_PERSONALIZADA`** — categorias de propriedades
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_GRUPO_PROPRIEDADE_PERSONALIZADA` | INTEGER PK | |
| `NOME` | TEXT | Nome do grupo (ex: `'DANCOR'`, `'Dados Elétricos'`) |

**`PROPRIEDADE_PERSONALIZADA`** — definição de cada propriedade
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_PROPRIEDADE_PERSONALIZADA` | INTEGER PK | |
| `ID_GRUPO_PROPRIEDADE_PERSONALIZADA` | INTEGER FK | |
| `NOME` | TEXT | Nome da propriedade (ex: `'Tensão'`, `'Grau de Proteção'`) |
| `TIPO_VALOR` | INTEGER | 0 = texto, 1 = numérico, 2 = booleano |

**`VALOR_PROPRIEDADE_PERSONALIZADA`** — valor por peça
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_VALOR_PROPRIEDADE_PERSONALIZADA` | INTEGER PK | |
| `ID_PROPRIEDADE_PERSONALIZADA` | INTEGER FK | |
| `ID_PECA` | INTEGER FK | |
| `VALOR` | TEXT | Valor da propriedade |

Propriedades observadas em bibliotecas de bombas:
- `Tensão` — ex: `'Trifásico - 220/380V'`
- `Corrente` — ex: `'5,55A'`
- `Grau de Proteção` — ex: `'IP21'`, `'IP55-TFVE'`
- `Isolamento` — ex: `'Classe F'`
- `Sucção x Recalque` — ex: `'2.1/2" x 2.1/2"'`
- `Altura Máxima` — ex: `'30 m.c.a'`
- `Temperatura máxima de trabalho do líquido`
- `Motor` — norma técnica do motor
- `Rotor` — diâmetro e tipo
- `Rotação` — ex: `'3.500 rpm · 60Hz'`

---

### Geometria 3D e miniaturas

**`SIMBOLOGIA_3D`** — a tabela mais importante: carrega a malha, a cor e a imagem.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_SIMBOLOGIA_3D` | INTEGER PK | |
| `ID_GRUPO_SIMBOLOGIA_3D` | INTEGER FK | → `GRUPO_SIMBOLOGIA_3D` |
| `NOME` | TEXT | Nome da geometria (muitas vezes só a dimensão: `'100MM'`) |
| **`SIMBOLOGIA_3D`** | **BLOB** | **malha 3D no formato OQ3D** — a geometria completa |
| **`IMAGEM`** | **BLOB** | **miniatura BMP 100×100 24-bit** pré-renderizada pelo AltoQi |
| `SIMBOLOGIA_3D_SIMPLIFICADA` | BLOB | versão de baixa resolução — **nula** nas três bibliotecas testadas |
| `IMAGEM_SIMPLIFICADA` | BLOB | idem — nula |
| `WIREFRAME` | BLOB | arestas (`T3DWireframeGenerator::TEdge`) para planta/corte no CAD |
| `USA_CORES_PECA` | INTEGER | 1 em todas as bibliotecas testadas |
| `DESLOCAMENTO_X/Y/Z` | REAL | deslocamento de inserção |
| `ANGULO_PLANO_XY/XZ/YZ` | REAL | ângulos de inserção |

> **`WIREFRAME` é 69–71% do tamanho do arquivo e é inútil para viewer web.** Na Amanco são 285 MB de 412 MB; na Dancor, 114 MB de 160 MB. Nunca carregue essa coluna em `SELECT *`.

**`GRUPO_SIMBOLOGIA_3D`** — agrupa geometrias (`NOME_GRUPO`, `ID_CLASSE`).

**`CLASSE_SIMBOLOGIA_3D`** — **a melhor fonte de fabricante**. `NOME_CLASSE` segue o padrão `"FABRICANTE - Linha de Produto"`:

```
'DANCOR - Bomba de Combate a Incêncio'      (sic — typo do fabricante)
'AMANCO - PVC Esgoto SN'
'INTELBRAS - Dispositivos smart'
```

**`PECA_SIMBOLOGIA_3D`** — o vínculo peça → geometria (`ID_PECA`, `ID_SIMBOLOGIA_3D`).

> **Este vínculo é uma chave estrangeira e dispensa qualquer matching por nome.** É a diferença central em relação ao caminho via IFC, onde é preciso casar nome de arquivo com nome de peça por heurística. Várias peças compartilham a mesma geometria: na Amanco, 457 malhas servem 856 peças (as variantes "DESCE", "COLUNA" e "SOBE" mudam a orientação de inserção, não a forma — uma única malha atende 22 peças).

**`ENTRADA_3D`** — pontos de conexão hidráulica: `POSICAO_X/Y/Z`, `DIAMETRO`, `TIPO_SECAO`, `ID_SIMBOLOGIA_3D`. **O IFC não carrega essa informação.**

**`IMAGEM`** — ícones da interface do AltoQi, **não fotos de produto**.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_IMAGEM` | INTEGER PK | |
| `NOME_IMAGEM` | TEXT | ex: `'Interruptor simples'`, `'Tomada 2P+T'` |
| `IMAGEM` | BLOB | ícone da paleta |

> Vazia nas bibliotecas hidráulicas; preenchida na Intelbras, onde há `SUB_TIPO_PONTO` elétricos. **A imagem do produto é sempre `SIMBOLOGIA_3D.IMAGEM`**, nunca esta tabela.

**`CLASSIFICACAO_IFC`** / **`CLASSIFICACAO_IFC_PECA`** — classificação IFC quando preenchida pelo fabricante (vazias nas três bibliotecas testadas).

---

## Formato OQ3D — a geometria 3D

Assinatura: 5 bytes + `b'OQ3D 3D Objects File'`.

É uma **árvore de objetos** serializada no estilo Delphi:

```
0x5B <len:u32> <ClassName>   abre um objeto
...payload...
0x5D                         fecha
```

### Cabeçalho — 37 bytes, e um deles é informação

```
offset  bytes                      significado
0       3a 01 01 00 00             5 bytes OPACOS, idênticos nas 12 bibliotecas
5       'OQ3D 3D Objects File'     20 bytes de assinatura
25      02 00 00 00                u32 = 2, versão do arquivo
29      N  00 00 00                u32 = NÚMERO DE OBJETOS-RAIZ
33      00 00 00 00                u32 = 0
```

Os 5 primeiros bytes são constantes nas 12 bibliotecas e nas 6 versões de schema. Não se
sabe o que significam; sabe-se que não variam.

> **O campo em +29 serve de verificação de parse, e revelou DOIS defeitos reais do parser
> tolerante.**
> O parse encontra **sempre mais** raízes do que o cabeçalho declara, nunca menos.
> Medido em **todas** as 783 geometrias das 12 bibliotecas de fabricante: **54 divergiam
> (6,9%), em 6 bibliotecas** — as cinco da Intelbras que têm geometria e a Maxbar, esta com
> 31 de 135.
>
> **As 31 da Maxbar eram outro bug (corrigido em 2026-09-03):** malhas
> `TQi3DIndexedTriangleMeshData` de **versão 3** — e arquivo versão 3 no offset +25 —, que o
> parser rejeitava por só conhecer a 2. O bloco não consumido deixava os `0x5B`/`0x5D` dos
> doubles à vista do scanner (daí as raízes a mais) e **a geometria era perdida por
> inteiro**: 56 peças saíam do catálogo como "sem 3D". O layout da versão 3 é byte a byte o
> da versão 2 (mesma cauda de 19 bytes entre malhas). Aceite `ver in (2, 3)`. Restam 23
> divergências, todas na Intelbras, com a causa abaixo e geometria completa.
> 
> A diferença vai de **+2 a +10 e não é sempre par** (+7 e +9 aparecem), o que descarta
> "um `0x5D` desempilha um nível e promove dois filhos" como regra única: o
> desempilhamento espúrio acontece em quantidade variável dentro do mesmo blob.
>
> Nesses 23 casos a geometria emitida não muda, mas a hierarquia muda — e com ela a
> composição dos transforms dos nós promovidos. Na Intelbras as malhas já vêm em
> coordenadas de mundo, então não aparece; numa biblioteca de conexões deslocaria a peça.
> **Nunca deixe esse aviso só no `warnings.warn`:** colete-o por simbologia
> (`catch_warnings(record=True)`) e mostre id + nome no resumo do build — foi assim que a
> versão 3 apareceu.

### Classes que carregam dados

```
TQi3DIndexedTriangleMeshData
    u32 versao(2 ou 3 — layout idêntico; a 3 aparece na Maxbar) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos

TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A     (cor UNIFORME da malha)

TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 COLUMN-major + translação
```

⚠️ **A rotação é column-major:** o elemento `(i, j)` está em `r[j*3 + i]`.
Lida como row-major sai **transposta** — e toda instância com rotação não
simétrica cai fora do lugar. Transponha na leitura.

### Hierarquia

```
TQi3DReusedObject(guid)            instância
  TQi3DReusableObject                definição inline (opcional)
    TQi3DTriangleMesh
      TCoatingColor
      TQi3DIndexedTriangleMeshData
  TCoordinateTransformation3D        origem — quase sempre identidade
  TCoordinateTransformation3D        alvo  — posiciona a instância
```

O **último** `TCoordinateTransformation3D` filho direto é o que posiciona. O par origem/alvo espelha `MappingOrigin`/`MappingTarget` do `IFCCARTESIANTRANSFORMATIONOPERATOR3D`.

### Instâncias repetidas — como resolver a referência

A maioria dos `TQi3DReusedObject` **não** traz a definição inline: referencia
uma `TQi3DReusableObject` já serializada. Layout do payload:

```
+0   u32 versão (2 ou 3)
+28  u32 tamanho do GUID (sempre 36)
+32  GUID, 36 bytes ASCII    ← ÚNICO POR INSTÂNCIA, não serve de chave
...  bloco de 15 bytes (versão 2) ou 16 bytes (versão 3)
+B   u8 discriminador:
        0x02 → a definição vem inline, como filho TQi3DReusableObject
        0x01 → seguem 4 bytes: u32 com a referência
```

**A referência é o índice de serialização, base 1, contado sobre TODOS os
objetos da árvore em ordem de documento.** Não é o GUID, não é um índice de
definição e não é "a última definição vista" — as duas últimas hipóteses foram
testadas e refutadas. Só as sete classes acima aparecem no fluxo, então o
contador não dessincroniza.

Para desenhar a instância: aplique o transform DELA à subárvore da
`TQi3DReusableObject` referenciada (que traz o próprio transform de origem,
quase sempre identidade).

Validado em 10 bibliotecas: 2.960 `TQi3DReusedObject`, dos quais 1.096 por
referência — todos resolvem para uma `TQi3DReusableObject`.

### Correspondência com o IFC

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18 `IFCMAPPEDITEM`), confirmando que o exportador IFC é tradução direta desta estrutura. A cor é **uniforme por malha** no OQ3D; o exportador a converte em cor por face ao fundir as malhas num único face set.

### Unidades e eixos

**Centímetros, Z-up** — a mesma orientação do IFC nativo. Para Three.js (metros, Y-up):

```python
three_x =  v[0] * 0.01
three_y =  v[2] * 0.01
three_z = -v[1] * 0.01
```

### Armadilhas do parser

| Armadilha | Consequência |
|---|---|
| **Ignorar os transforms** | Funciona em bibliotecas de equipamentos (malhas já em coordenadas de mundo) e **quebra** em conexões, onde a peça é montada de malhas reaproveitadas — joelhos saem retos. Use sempre o parser de árvore. |
| **Buscar `0x5B` com o byte anterior no padrão** | O byte que precede varia conforme o contexto (`\x02\x5b`, `\x01\x09\x00\x00\x00\x5b`…). Ancore só no `0x5B`. |
| **Varrer delimitadores byte a byte** | `0x5B`/`0x5D` ocorrem dentro de doubles. Consuma por inteiro os blocos de tamanho conhecido (malha, cor, transform) antes de qualquer varredura. |
| **Somar os bocais na bounding box** | As cores verde `(1,154,63)` e azul `(10,84,152)` são marcadores de conexão do AltoQi, não parte do produto — inflam a bbox em até 2 cm. Filtre-os ao medir. |
| **`SELECT *` em `SIMBOLOGIA_3D`** | Carrega o `WIREFRAME` — centenas de MB inúteis. |
| **Ler a rotação como row-major** | Ela é **column-major**. Lida errada, sai transposta: instâncias rotacionadas caem fora do lugar (uma peça "solta no ar"), sem mudar a contagem de triângulos — por isso passa despercebido. |
| **Ignorar as instâncias que referenciam a definição** | 1.096 das 2.960 instâncias não trazem malha inline. Ignorá-las perde ~30% dos triângulos numa biblioteca de conexões. |
| **Comparar com o IFC só pela bounding box** | Uma rotação e a sua transposta podem gerar a MESMA caixa. Compare o conjunto de pontos. |

### Como conferir que o parser está certo

O IFC da mesma biblioteca é o gabarito. Em biblioteca **tessellated**
(`IFCTRIANGULATEDFACESET`) a conferência é exata — reconstrua o IFC a partir do
STEP (placement do produto × mapped item) e compare o **conjunto de pontos**:

- contagem de triângulos idêntica → as instâncias repetidas resolveram;
- pontos idênticos → os transforms estão na convenção certa.

Cuidado com dois detalhes ao comparar:

- **alinhe pelo canto da bounding box, não pelo centróide** — o OQ3D guarda
  várias malhas como sopa de triângulos e o IFC solda os vértices, então os
  centróides têm pesos diferentes;
- **compare por tolerância** (~10 µm), não por igualdade de conjunto
  arredondado: coordenadas na fronteira de arredondamento caem para lados
  diferentes nos dois lados.

Em biblioteca **B-rep** (`IFCADVANCEDBREP`) a tesselação é independente: aí só
dá para comparar a forma (extensão da bounding box).

### Sempre deduplique os vértices

O OQ3D indexa dentro de cada malha, mas as malhas de uma peça repetem vértices entre si. Deduplicar reduz **~79%** dos vértices — sem isso, um conjunto de 9 catálogos passou de 148 MB para 571 MB de JSON.

```python
from dedup import dedup
data, orig, n, pct = dedup(oq3d.to_buffers(blob))
json.dump(data, f, separators=(',', ':'))   # sem os separadores default: +12%
```

### Implementação de referência

`www/apps/ingestao/pipeline/oq3d.py` no projeto **bilds-bim-3d**. API:

```python
import oq3d

oq3d.is_oq3d(blob)                    # valida a assinatura
oq3d.parse(blob)                      # árvore de nós
oq3d.extract(blob, skip_markers=True) # [(verts_cm, tris, rgba)] com transforms aplicados
oq3d.to_buffers(blob)                 # {'pos','col','idx'} em metros, Y-up
oq3d.bbox(blob)                       # (dx,dy,dz) em cm — para validação
oq3d.stats(blob)                      # resumo para logs
oq3d.MESH_VERSOES                     # (2, 3) — versões de malha aceitas
```

**Contrato de erro** (o mesmo do port TypeScript `www/tools/oq3d-parser.ts`, conferido
por teste de paridade): sem assinatura ou **truncado** (contagem declarada excede o
buffer) → `OQ3DError` antes de alocar; malha com **layout desconhecido** (versão fora de
`MESH_VERSOES`, zero coordenadas, contagem não múltipla de 3) → bloco pulado +
`OQ3DAvisoParse`; contagem de raízes ≠ cabeçalho → `OQ3DAvisoParse`. Um parser que devolve
o offset em silêncio nesses casos entrega geometria incompleta sem ninguém saber — foi o
estado do `oq3d.py` até 2026-09-03.

---

## Escrever um `.aq`

Um `.aq` gerado do zero foi validado contra este próprio leitor em 2026-09-02 — e, no
mesmo dia, **aberto no AltoQi Builder real**: árvore de classes, grupos e peças correta,
propriedades personalizadas visíveis, acentos íntegros (`Água`, `Redução`, `kgf/cm²`).
É a prova de que a receita abaixo (schema 607 do `sqlite_master`, texto em cp1252 via
`CAST(? AS TEXT)`, colunas não observadas deixadas no `DEFAULT` do DDL, sentinelas onde
a biblioteca real as usa) produz um arquivo que o Builder aceita. Não foi verificado no
Builder: a malha OQ3D na janela 3D, e a peça lançada numa rede sem `ENTRADA_PECA`.

### O texto tem de ser gravado em cp1252

**É o erro que corrompe o arquivo em silêncio.** O `sqlite3` do Python vincula `str` como
UTF-8 e `bytes` como BLOB — nenhum dos dois serve. A saída é o `CAST`:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes sem converter: `typeof()` volta `'text'`, os
bytes ficam idênticos aos de uma biblioteca real, e o `_decode_texto` devolve a string
original.

Gravar em UTF-8 faz `'Soldável'` voltar `'SoldÃ¡vel'` — **sem levantar exceção em lugar
nenhum**, passando no `integrity_check`. Encode **estrito**: um caractere fora do cp1252
não pode virar `?` dentro do nome de um produto.

**Como conferir:** os bytes altos das colunas de texto **não podem** ser UTF-8 válido. Em
cp1252 um acento é um byte alto isolado, que é UTF-8 inválido; em UTF-8 são dois.

### Ordem de inserção

Uma biblioteca de fabricante preenche 16 a 25 das 77 tabelas. A ordem que fecha as FKs:

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

O SQLite **não** aplica FKs por padrão: um `ID_GRUPO_PECA` órfão passa pelo `INSERT` sem
erro e só aparece no AltoQi. Rodar `PRAGMA foreign_key_check` no fim.

**O DDL não se escreve à mão** — 77 tabelas e 84 índices, e uma coluna faltando faz o
AltoQi recusar o arquivo. Copie do `sqlite_master` de um `.aq` real.

### Os enums, com os valores observados

`GRUPO_PECA.PROJETO_APLICACAO` — tipo de instalação:
**8** esgoto · **12** água fria · **22** incêndio · **36** gás · **64/76** elétrico

`ENTIDADE_IFC` / `TIPO_ENTIDADE_IFC` / `ENTIDADE_IFC_2X3` andam sempre juntos:

| IFC4 | tipo | 2×3 | O que é |
|---|---|---|---|
| 2071 | 4099 | 2088 | `IfcPipeFitting` — curva, luva, cap, tê, redução |
| 2072 | 4096 | 2086 | `IfcPipeSegment` — tubo |
| 2075 | 4118 | 2093 | bomba |
| 2076 | 4122 | 2092 | aparelho sanitário |
| 2079 | 4121 | 2092 | terminal de ventilação |
| 2084 | 4103 | 2091 | válvula |
| 2085 | 4123 | 2092 | ralo, caixa sifonada |
| 2090 | 4138 | 2090 | aquecedor a gás |

`SUBTIPO_IFC` dentro de `IfcPipeFitting` (2071), pelos 156 grupos da Amanco:
**0** curva/joelho · **1** luva · **3** cap · **4** tê/junção · **6** redução · **7** ramal.
O `SUBTIPO_IFC_2X3` é sempre igual ao `SUBTIPO_IFC`.

`PECA.TIPO_APLICACAO_PECA`:
**1** tubo · **2** conexão · **6** bomba · **8** aparelho sanitário · **9** caixa
sifonada · **10** ralo · **55** ramal de ventilação

PVC, nas 265 linhas de `GRUPO_PECA` da Amanco: `RUGOSIDADE_GP=135.0`,
`RUGOSIDADE_EQUIVALENTE=6e-05`, `COEFICIENTE_MANNING=0.01`, `TIPO_FWH=1`,
`TIPO_SECAO_GP=0`, `TIPO_MATERIAL=0`, `TIPO_CONFIGURACAO_GP=-2147483647`;
`ELEMENTO_APLICACAO` e `REPRESENTACAO_GP` são 0, exceto 1 e 2 nos grupos de tubo.

### `ITEM.CODIGO_ITEM` é onde vive o código comercial

| Biblioteca | `CODIGO_ITEM` | `NOME_ITEM` |
|---|---|---|
| Amanco | `14808` | `50mm` |
| Dancor | `10652511` | `3,0CV T 220/380V INC FLG IR3 - 10652511` |
| Komeco | `KO 16D GLP` | `GLP KO 16D` |

`FABRICANTE` e `TABELA_REFERENCIA` repetem o fabricante; `CATEGORIA` é `'Insumo'` nas
três. `GRUPO_ITEM.UNIDADE_GI` = 1 nos grupos de tubo (medidos por metro), 0 no resto;
`ITEM_ASSOCIADO.MEDICAO_PECA` = 1 nas peças de tubo, 2 nas conexões.

O código de catálogo pertence aqui — não a uma propriedade personalizada.

### Preencha `PECA.BIBLIOTECA`

É o passo 2 da cascata de inferência de fabricante, está **vazio nas 12 bibliotecas
reais**, e é a única fonte que sobrevive a uma biblioteca **sem geometria** — sem
`CLASSE_SIMBOLOGIA_3D` o passo 1 não existe e a cascata cai no nome da pasta.

### Escrever OQ3D

O leitor é **tolerante**: varre à procura de `0x5B`/`0x5D` e consome por inteiro só os
três blocos de tamanho conhecido, pulando o resto. Um escritor não tem essa liberdade, e
o resto é o que ele precisa saber — o mais seguro é copiar a moldura byte a byte de uma
subárvore real e substituir só os dados que se controla.

Três coisas que só aparecem escrevendo:

- **A cor é gravada duas vezes** — no payload de `TQi3DTriangleMesh` e em
  `TCoatingColor`, os mesmos 4 bytes. O leitor usa só a segunda.
- **A rotação tem de ser transposta de volta para colunas.** Gravar row-major produz a
  transposta, e a instância sai do lugar **sem mudar nenhuma contagem**. O teste que pega
  isso grava a rotação e a sua transposta e confere que dão resultados diferentes; sem
  essa contraprova, uma rotação simétrica passaria e não provaria nada.
- **Nada é alinhado**: o `double` do payload de `TQi3DReusedObject` começa num offset que
  não é múltiplo de 8.

> **Malha gerada precisa de checagem topológica, e de olhar.** Duas classes de erro
> passam por bounding box, contagem de triângulos e round-trip binário: (a) perfil de
> revolução que fecha em si mesmo sem soldar o último anel no primeiro deixa
> `2 × lados` arestas de borda — sólido que parece fechado e mostra o interior pela
> costura; (b) malhas corretas em **posição relativa** errada. A primeira se pega
> contando arestas compartilhadas por exatamente dois triângulos; a segunda só abrindo o
> viewer e olhando.

---

### Um `.aq` mínimo a partir de qualquer malha — `www/apps/ingestao/pipeline/geo_to_aq.py`

Quando a geometria não nasceu no AltoQi (um STEP tesselado, uma peça editada num viewer),
o `.aq` de uma peça só precisa de: `VERSAO_BANCO_CADASTRO`; `CLASSE_PECA` → `GRUPO_PECA`
→ `PECA` (+ `DADOS_HIDRAULICOS`); `CLASSE_SIMBOLOGIA_3D` → `GRUPO_SIMBOLOGIA_3D` →
`SIMBOLOGIA_3D` (o blob OQ3D) e `PECA_SIMBOLOGIA_3D`; `GRUPO_PROPRIEDADE_PERSONALIZADA` →
`PROPRIEDADE_PERSONALIZADA` → `VALOR_PROPRIEDADE_PERSONALIZADA`; e `CLASSE_ITEM` →
`GRUPO_ITEM` → `ITEM` (com `CODIGO_ITEM`) → `ITEM_ASSOCIADO`. Schema completo do
`eng-reversa/dados/schema-aq-607.sql`, texto em cp1252 via `CAST(? AS TEXT)`.

Regras que o `bilds-bim-3d/www/apps/ingestao/pipeline/geo_to_aq.py` segue e que valem para qualquer gerador:

- **Uma raiz OQ3D por malha de cor uniforme.** O OQ3D só tem cor por malha
  (`TCoatingColor`); uma malha do viewer com várias cores tem de ser dividida por cor antes
  de escrever, senão a cor se perde. Se a origem já traz partes (o editor), uma raiz por parte.
- **Unidades:** do viewer (m, Y-up) para o OQ3D (cm, Z-up): `(x·100, −z·100, y·100)`.
- **Sem código de diâmetro** para peça genérica: `DIAMETRO_PECA = −DBL_MAX`, como as 700
  conexões da Amanco. `TIPO_APLICACAO_PECA = 2` (conexão) e `ENTIDADE_IFC` de
  `IfcPipeFitting` (`2071, 4099, 2088`) são o enquadramento mais inofensivo.
- **Registre a origem** numa propriedade personalizada ("Geometria 3D: malha importada —
  STEP x.stp; N malhas, T triângulos") — a distinção entre forma de fabricante e malha
  importada tem de sobreviver até a ficha do produto.
- **Título/fabricante da página** vêm da cascata do `build.py`, que começa por
  `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` ("Fabricante - Linha") e cai para a **pasta** do
  arquivo. Um `.aq` gerado fora de `input/<Fabricante>/<Linha>/` publica com o nome da
  pasta onde estiver.
- **Confira com o leitor do projeto**, não com o SQLite: `eng-reversa/tools/validar_aq.py`
  (a checagem "barras de tubo com 600 cm" é da Akato e não se aplica) e
  `read_aq.extract_simbologias` + `oq3d.to_buffers` devolvendo a mesma contagem, bbox e cor.

---

## Inferir fabricante e título

Fabricante e título são o cabeçalho da página publicada — **nunca podem sair vazios nem em forma de slug**. Cascata validada nas três bibliotecas:

**Fabricante**, em ordem de confiança:
1. Prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` antes de `" - "`, em Title Case
2. `PECA.BIBLIOTECA` — **vazia nas três bibliotecas testadas**, não confie nela
3. Pasta avô, se descritiva
4. Pasta pai, se coincidir com o primeiro token do nome do arquivo
5. Primeiro token do nome do arquivo

**Título**, em ordem:
1. Pasta pai, se descritiva e **diferente do fabricante**
   (`input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq` → o título é a pasta)
2. Tokens do nome do arquivo, menos o fabricante e menos ruído (`pecas`, anos, versões)
3. Prefixo comum das linhas das classes (`'PVC Esgoto SN'` + `'PVC Esgoto SR'` → `'PVC Esgoto'`)
4. Último recurso: o próprio fabricante

> **Armadilha:** em `input/Intelbras/pecas_Intelbras_....aq` a pasta pai é o **fabricante**, não o título. Compare o slug da pasta com o do primeiro token do arquivo antes de usá-la como título.

### Nome do produto: quando prefixar com o grupo

`NOME_PECA` às vezes é só a dimensão (`'100mm'`) e precisa do `NOME_GP` para identificar o produto; outras vezes já é completo e o grupo só polui.

**Decida por grupo, não por peça** — assim todas as peças do grupo saem no mesmo padrão. Prefixe o grupo inteiro quando qualquer `NOME_PECA` dele tiver menos de 4 caracteres ou aparecer em mais de um grupo:

| Biblioteca | `NOME_PECA` | Colide? | Resultado |
|---|---|---|---|
| Amanco | `100mm` | sim (Cap, Luva, Joelho…) | `Cap 100mm` |
| Dancor | `3CV T 220/380V INC FLG IR3` | sim (CAM-W21/W16/W14/W10) | `CAM-W21 3CV T 220/380V…` |
| Intelbras | `Interruptor inteligente 1 tecla - EWS 1001 BR` | não | mantém como está |

---

## Queries de extração

### Listar todos os grupos e peças

```python
cur.execute("""
    SELECT
        gp.ID_GRUPO_PECA,
        gp.NOME_GP          AS serie,
        p.ID_PECA,
        p.NOME_PECA,
        p.DESCRICAO_DADOS   AS conexoes,
        p.DIAMETRO_PECA,
        p.COMPRIMENTO_PECA
    FROM GRUPO_PECA gp
    JOIN PECA p ON p.ID_GRUPO_PECA = gp.ID_GRUPO_PECA
    WHERE gp.ATIVO = 1 AND p.ATIVO = 1
    ORDER BY gp.ID_GRUPO_PECA, p.ID_PECA
""")
```

### Extrair curva Q-H completa por peça

```python
cur.execute("""
    SELECT
        p.NOME_PECA,
        gp.NOME_GP          AS serie,
        mb.NOME_MB          AS modelo_bomba,
        mb.POTENCIA_MB      AS potencia_cv,
        icb.VAZAO_ICB       AS vazao,
        icb.ALTURA_ICB      AS altura,
        icb.POTENCIA_ICB    AS potencia_ponto,
        icb.RENDIMENTO_ICB  AS rendimento,
        icb.NPSH
    FROM PECA p
    JOIN GRUPO_PECA gp          ON gp.ID_GRUPO_PECA = p.ID_GRUPO_PECA
    JOIN DADOS_HIDRAULICOS dh   ON dh.ID_PECA = p.ID_PECA
    JOIN MODELO_BOMBA mb        ON mb.ID_MODELO_BOMBA = dh.ID_MODELO_BOMBA
    JOIN ITEM_CURVA_BOMBA icb   ON icb.ID_MODELO_BOMBA = mb.ID_MODELO_BOMBA
    WHERE p.ATIVO = 1
    ORDER BY p.ID_PECA, icb.VAZAO_ICB
""")
```

### Extrair propriedades personalizadas

```python
cur.execute("""
    SELECT
        p.NOME_PECA,
        gprop.NOME          AS grupo_prop,
        prop.NOME           AS propriedade,
        vprop.VALOR
    FROM VALOR_PROPRIEDADE_PERSONALIZADA vprop
    JOIN PROPRIEDADE_PERSONALIZADA prop
        ON prop.ID_PROPRIEDADE_PERSONALIZADA = vprop.ID_PROPRIEDADE_PERSONALIZADA
    JOIN GRUPO_PROPRIEDADE_PERSONALIZADA gprop
        ON gprop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA = prop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA
    JOIN PECA p ON p.ID_PECA = vprop.ID_PECA
    ORDER BY p.ID_PECA, prop.NOME
""")
```

### Extrair geometria 3D e miniaturas

```python
import oq3d   # www/apps/ingestao/pipeline/oq3d.py do projeto bilds-bim-3d

# Nunca use SELECT * aqui: traria o WIREFRAME (centenas de MB).
cur.execute("""
    SELECT s.ID_SIMBOLOGIA_3D, s.NOME,
           CAST(s.SIMBOLOGIA_3D AS BLOB), CAST(s.IMAGEM AS BLOB), g.NOME_GRUPO
    FROM SIMBOLOGIA_3D s
    LEFT JOIN GRUPO_SIMBOLOGIA_3D g
           ON g.ID_GRUPO_SIMBOLOGIA_3D = s.ID_GRUPO_SIMBOLOGIA_3D
""")
for sid, nome, blob, bmp, grupo in cur.fetchall():
    # CAST AS BLOB acima garante bytes — sem re-encode, que com cp1252
    # não seria reversível
    if not oq3d.is_oq3d(blob):
        continue
    data = oq3d.to_buffers(blob)          # {'pos','col','idx'} em metros, Y-up
    with open(f'geo/{sid}.json', 'w') as f:
        json.dump(data, f)
    if bmp:                                # miniatura BMP 100×100 já pronta
        open(f'thumb/{sid}.bmp', 'wb').write(bmp)
```

### Vincular peça → geometria (sem matching)

```python
cur.execute("""
    SELECT p.ID_PECA, gp.NOME_GP, p.NOME_PECA, ps.ID_SIMBOLOGIA_3D
    FROM PECA p
    LEFT JOIN GRUPO_PECA gp ON gp.ID_GRUPO_PECA = p.ID_GRUPO_PECA
    JOIN PECA_SIMBOLOGIA_3D ps ON ps.ID_PECA = p.ID_PECA
    ORDER BY p.ID_PECA
""")
```

Peças sem linha em `PECA_SIMBOLOGIA_3D` **não têm forma fixa** — na Amanco são 312 de 1.168 (27%): tubos, gerados como cilindro por diâmetro × comprimento, e kits de aparelho sanitário (ramal de ventilação, tanque de lavar, vaso com tê). Pular essas peças é o comportamento correto.

### Extrair ícones da interface (raramente útil)

```python
cur.execute("SELECT ID_IMAGEM, NOME_IMAGEM, IMAGEM FROM IMAGEM")
```

São ícones da paleta do AltoQi, não fotos de produto. Para a imagem do produto use `SIMBOLOGIA_3D.IMAGEM`.

---

## Script completo de extração

```python
#!/usr/bin/env python3
"""
Extrai dados de uma biblioteca BIM AltoQi (.aq) para JSON.
Uso: python3 leitor_aq.py <arquivo.aq> <saida.json>
"""
import sys, json, zipfile, sqlite3, os, shutil, tempfile

def _decode_texto(b):
    """cp1252, não latin-1 — ver o aviso de encoding acima."""
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')

def open_aq(aq_path):
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(aq_path, 'r') as z:
            z.extractall(tmp)
        db_files = [f for f in os.listdir(tmp)
                    if os.path.isfile(os.path.join(tmp, f)) and not f.endswith('.xml')]
        if not db_files:
            raise FileNotFoundError("Nenhum arquivo SQLite encontrado dentro do .aq")
        dest = aq_path + '._db'
        shutil.copy(os.path.join(tmp, db_files[0]), dest)
    con = sqlite3.connect(dest)
    con.text_factory = _decode_texto
    con.row_factory = sqlite3.Row
    return con, dest

def extract(aq_path):
    con, tmp_db = open_aq(aq_path)
    cur = con.cursor()
    result = {'grupos': [], 'pecas': [], 'curvas': [], 'propriedades': []}

    # Grupos
    for r in cur.execute("SELECT * FROM GRUPO_PECA WHERE ATIVO=1"):
        result['grupos'].append(dict(r))

    # Peças
    for r in cur.execute("SELECT * FROM PECA WHERE ATIVO=1"):
        result['pecas'].append(dict(r))

    # Curvas Q-H
    for r in cur.execute("""
        SELECT p.ID_PECA, p.NOME_PECA, gp.NOME_GP AS serie,
               mb.NOME_MB, mb.POTENCIA_MB,
               icb.VAZAO_ICB, icb.ALTURA_ICB,
               icb.POTENCIA_ICB, icb.RENDIMENTO_ICB, icb.NPSH
        FROM PECA p
        JOIN GRUPO_PECA gp ON gp.ID_GRUPO_PECA = p.ID_GRUPO_PECA
        JOIN DADOS_HIDRAULICOS dh ON dh.ID_PECA = p.ID_PECA
        JOIN MODELO_BOMBA mb ON mb.ID_MODELO_BOMBA = dh.ID_MODELO_BOMBA
        JOIN ITEM_CURVA_BOMBA icb ON icb.ID_MODELO_BOMBA = mb.ID_MODELO_BOMBA
        WHERE p.ATIVO=1 ORDER BY p.ID_PECA, icb.VAZAO_ICB
    """):
        result['curvas'].append(dict(r))

    # Propriedades personalizadas
    for r in cur.execute("""
        SELECT p.ID_PECA, p.NOME_PECA,
               gprop.NOME AS grupo, prop.NOME AS propriedade, vprop.VALOR
        FROM VALOR_PROPRIEDADE_PERSONALIZADA vprop
        JOIN PROPRIEDADE_PERSONALIZADA prop
            ON prop.ID_PROPRIEDADE_PERSONALIZADA = vprop.ID_PROPRIEDADE_PERSONALIZADA
        JOIN GRUPO_PROPRIEDADE_PERSONALIZADA gprop
            ON gprop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA = prop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA
        JOIN PECA p ON p.ID_PECA = vprop.ID_PECA
        ORDER BY p.ID_PECA, prop.NOME
    """):
        result['propriedades'].append(dict(r))

    con.close()
    os.remove(tmp_db)
    return result

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Uso: python3 leitor_aq.py <arquivo.aq> <saida.json>")
        sys.exit(1)
    data = extract(sys.argv[1])
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"Extraídos: {len(data['grupos'])} grupos, {len(data['pecas'])} peças, "
          f"{len(data['curvas'])} pontos de curva, {len(data['propriedades'])} propriedades")
```

---

## build_product_map — estrutura para cruzar com IFCs

> **Histórico.** Servia ao modo de compatibilidade `build.py --ifc`, **removido em 2026-09-05** (I6). A geometria vem do próprio `.aq` e o vínculo é a chave estrangeira `PECA_SIMBOLOGIA_3D` — sem matching por nome. `build_product_map` continua em `read_aq.py` (útil para qualquer cruzamento por nome); o matcher `find_aq_product` mora agora em `docs/estudo-oq3d/valida_ifc.py`.

`build_product_map(aq_data)` organiza os dados extraídos em um mapa indexado por nome de grupo,
pronto para cruzar com nomes vindos de fora (era o `build_catalog()` do modo `--ifc`):

```python
def build_product_map(aq_data):
    """
    Retorna:
      { nome_gp → {
          'serie': str,
          'pecas': [{ id, nome, conexoes, diametro_codigo, comprimento_cm,
                      altura_cm, largura_cm, specs, curva_pts }]
      }}
    """
    props_by_peca = {}
    for p in aq_data['propriedades']:
        pid = p['ID_PECA']
        if pid not in props_by_peca:
            props_by_peca[pid] = {}
        props_by_peca[pid][p['propriedade']] = p['VALOR']

    curves_by_peca = {}
    for pt in aq_data['curvas']:
        pid = pt['ID_PECA']
        if pid not in curves_by_peca:
            curves_by_peca[pid] = []
        curves_by_peca[pid].append([
            round(pt['vazao'], 3), round(pt['altura'], 3),
            round(pt['potencia_ponto'] or 0, 3), round(pt['rendimento'] or 0, 1),
        ])

    grupos_by_id = {g['ID_GRUPO_PECA']: g for g in aq_data['grupos']}
    product_map = {}
    for p in aq_data['pecas']:
        gid = p['ID_GRUPO_PECA']
        if gid not in grupos_by_id:
            continue
        nome_gp = grupos_by_id[gid]['NOME_GP']
        if nome_gp not in product_map:
            product_map[nome_gp] = {'serie': nome_gp, 'pecas': []}
        pid = p['ID_PECA']
        product_map[nome_gp]['pecas'].append({
            'id':             pid,
            'nome':           p['NOME_PECA'],
            'conexoes':       p.get('DESCRICAO_DADOS', ''),
            # CÓDIGO de diâmetro, não centímetro — e -DBL_MAX é sentinela
            'diametro_codigo': _sem_sentinela(p.get('DIAMETRO_PECA')),
            'comprimento_cm': p.get('COMPRIMENTO_PECA'),
            'altura_cm':      p.get('ALTURA_PECA'),
            'largura_cm':     p.get('LARGURA_PECA'),
            'specs':          props_by_peca.get(pid, {}),
            'curva_pts':      curves_by_peca.get(pid),
        })
    return product_map
```

### Como o find_aq_product cruza IFC → .aq

`find_aq_product(slug, product_map, ifc_path_hint=None)` — hoje em `docs/estudo-oq3d/valida_ifc.py` (saiu do `build.py` em 2026-09-05, I6):

- **Sem** `ifc_path_hint`: usa tokens do slug para match (IFCs flat, ex: Dancor)
- **Com** `ifc_path_hint` (caminho relativo do IFC, ex: `"Cap/PVC Esgoto SN/100mm.ifc"`):
  extrai tokens de **todos** os componentes do caminho e calcula cobertura do GRUPO_PECA.
  Exige ≥ 100% de tokens do grupo cobertos (relaxa para 75%); dentro do grupo,
  a PECA com maior sobreposição com o leaf (filename) é selecionada.
- Nome do produto = `f"{nome_gp} {peca['nome']}"` quando o grupo não está no nome da peça.
- Para catálogos hierárquicos (Amanco), a chave do `file_map` deve ser o caminho relativo
  completo (`"Cap/PVC SN/100mm.ifc"`), não só o filename.

---

## Cobertura: por que há mais IFCs que geometrias

Ao comparar uma pasta de IFCs com o banco, a conta raramente fecha. Três motivos, todos esperados:

**1. O AltoQi exporta duas variantes de IFC por peça** — com e sem a luva de encaixe — e o banco guarda só a canônica (a **com luva**). Na Amanco: 184 IFCs "com luva", 195 "sem luva", 123 sem variante no nome, para 457 geometrias. Medindo por semelhança de bounding box, a separação é limpa:

| Conjunto de IFCs | Δ ≤ 1% | Δ ≤ 5% |
|---|---|---|
| Com luva | 76,1% | 87,5% |
| Sem variante no nome | 57,7% | 84,6% |
| Sem luva | **1,5%** | 35,9% |

**2. Peças sem forma fixa não têm geometria.** 312 das 1.168 peças da Amanco (27%): tubos — que o AltoQi gera como cilindro por diâmetro × comprimento — e kits de aparelho sanitário (ramal de ventilação, tanque de lavar, vaso com tê). São entradas de projeto. Pular é o correto.

**3. Peças que só existem como IFC.** A bomba 89-62 TJM da Dancor tem `.IFC` em disco mas nenhum registro no `.aq`. Para essas, o IFC continua sendo a única fonte.

> **Bounding box é assinatura fraca** para parear peça a peça: sustenta a separação entre grupos, não a precisão de cada linha. Para validar de verdade, confira alguns pares um a um.

---

## Publicar num viewer web: armadilhas

**Deduplique** (ver acima) e serialize com `separators=(',', ':')`.

**Caminho da geometria com `cleanUrls`.** Se o host serve a página em `/<slug>` **sem barra final** (Vercel com `cleanUrls: true`), um `fetch('./data/x.json')` resolve para `/data/x.json` — a raiz, onde os arquivos não estão. Use caminho absoluto derivado do slug:

```javascript
const DATA_BASE = '/' + CATALOG.slug + '/data/';
```

**Cheque `r.ok` antes do `.json()`.** Sem isso o 404 devolve a página de erro em HTML, o `JSON.parse` engasga nela e o erro aparece como `Unexpected token 'T'` ("**T**he page could not be found") — escondendo a causa real.

**Nomes de geometria colidem entre bibliotecas.** `NOME` da simbologia costuma ser só a dimensão (`'50MM'`), que se repete em toda biblioteca de conexões. Se vários catálogos compartilham um diretório de dados, prefixe com o grupo ou isole por catálogo.

**A estrutura de partes se recupera do `{pos,col,idx}` plano.** O `to_buffers()` concatena
todas as malhas e o `dedup()` funde vértices por `(posição, cor)` em float32. Como a cor
entra na chave, dois triângulos de cores diferentes **nunca** compartilham índice — logo
os **componentes conexos do grafo de triângulos** (union-find sobre `idx`) devolvem partes
de cor uniforme que aproximam as `TQi3DTriangleMesh` originais (58 na bomba 20CV da
Dancor, 31 na 2CV). É isso que permite editar por parte sem mudar o formato do storage.
Os bocais do AltoQi saem como componentes próprios, identificáveis pela cor (verde
`1,154,63`, azuis `10,84,152` e `0,116,232`).

**Arestas de borda não medem qualidade em malha de fabricante.** Contar arestas com um só
triângulo pega perfil de revolução não soldado (`2 × lados`) em malha **gerada** — mas nas
13 geometrias da Dancor **25–32% das arestas são de borda**: a tesselação chega como sopa
de triângulos e o dedup exato não solda as emendas. Use o critério só para malha gerada ou
importada, que deve dar 0.

**Arredondar a 1 µm antes do dedup reduz o JSON pela metade** (6,3 → 3,2 MB na 20CV) sem
perder triângulo: funde vizinhos que o float32 distinguia (239 vértices em 44.242). A
precisão nativa do AltoQi é o centímetro.

---

## Diagnóstico de problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `UnicodeDecodeError` ou lixo nos textos | Encoding padrão UTF-8 | `con.text_factory = _decode_texto` (cp1252) |
| Travessão/aspas viram `\x96`, `\x94` | Decodificado como latin-1 em vez de cp1252 | Ver o aviso de encoding — latin-1 e cp1252 diferem em 0x80–0x9F |
| `zipfile.BadZipFile` | Arquivo não é ZIP / corrompido | Verificar extensão real com `file arquivo.aq` |
| SQLite dentro do ZIP tem nome inesperado | Cada versão do AltoQi pode nomear diferente | Listar todos os arquivos no ZIP e pegar o que não é `.xml` |
| `MODELO_BOMBA` vazio / sem curvas | Biblioteca não contém bombas | Verificar `PROJETO_APLICACAO` em `GRUPO_PECA` — 22 = incêndio, outros tipos não têm curva Q-H |
| Propriedades ausentes para algumas peças | Nem toda peça tem todas as propriedades | Usar `LEFT JOIN` ao consultar `VALOR_PROPRIEDADE_PERSONALIZADA` |
| Valores numéricos como texto | `TIPO_VALOR = 0` mesmo para números | Converter com `float(valor)`; `TIPO_VALOR` indica o tipo esperado |
| Leitura do `.aq` lentíssima / estoura memória | `SELECT *` em `SIMBOLOGIA_3D` traz o `WIREFRAME` | Selecionar colunas explicitamente, nunca `*` |
| Joelhos e curvas saem retos | Transforms do OQ3D ignorados | Usar o parser de **árvore**; o linear só serve a malhas em coordenadas de mundo |
| Peças empilhadas na origem | Idem — instâncias sem posicionamento | Aplicar o último `TCoordinateTransformation3D` filho direto, acumulando pai → filho |
| Bounding box ~2 cm maior que o IFC | Bocais de conexão contam na medida | Filtrar as cores marcadoras verde/azul (`skip_markers=True`) |
| Modelo 100× maior ou menor | OQ3D é **centímetros**, não metros | Multiplicar por 0.01 |
| Modelo deitado / espelhado | OQ3D é Z-up | `x, y=z, z=-y` |
| `IMAGEM` vazia | Esperado nas bibliotecas hidráulicas | A imagem do produto é `SIMBOLOGIA_3D.IMAGEM`; a tabela `IMAGEM` guarda ícones de UI |
| Fabricante sai vazio | `PECA.BIBLIOTECA` está vazia (as três bibliotecas) | Usar o prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` |
| Título vira o nome do fabricante | Pasta pai é o fabricante (`input/Intelbras/`) | Comparar o slug da pasta com o 1º token do arquivo antes de usá-la |
| Título sai em forma de slug | Derivado do nome do arquivo sem limpeza | Remover ruído (`pecas`, anos, versões) e capitalizar |
| Nome do produto redundante (`Pontos de comando Interruptor…`) | Grupo prefixado sem necessidade | Prefixar só quando o nome for ambíguo — e decidir **por grupo** |
| Menos produtos que peças no banco | Peças sem `PECA_SIMBOLOGIA_3D` | Esperado: tubos e kits não têm forma fixa — **mas confira** que a diferença é toda de peças sem vínculo, e não de simbologias que o parser descartou |
| Simbologia com blob OQ3D válido devolve `pos` vazio | Malha em versão que o parser não conhece (Maxbar: versão 3) ou bloco malformado | Aceitar `ver in (2, 3)`; em versão desconhecida, avisar com id da simbologia em vez de devolver vazio em silêncio |
| Raízes encontradas > declaradas no cabeçalho **e** geometria vazia/parcial | Bloco de malha não consumido (versão desconhecida) expõe `0x5B`/`0x5D` dos doubles | É o sintoma da linha acima; raízes a mais **com** geometria completa é o caso Intelbras (0x5D dentro de double) |
| ZIP com arquivos duplicados | Peças compartilham geometria | Escrever cada arquivo de geo uma única vez |
| Query com `WHERE NOME_x = 'algo acentuado'` volta vazia, sem erro | O texto é cp1252 e o `sqlite3` vincula `str` como UTF-8 | `CAST(? AS TEXT)` com `.encode('cp1252')` |
| Diâmetro vale ~2× o esperado, ou vem `-1.8e308` | `DIAMETRO_PECA` é **código**, e `-DBL_MAX` é a sentinela de "não definido" | Ver o aviso na tabela da `PECA` |
| `no such column: DIAMETRO` em `ENTRADA_3D` | Coluna só existe no schema 607 | Testar a versão antes, ou usar `PRAGMA table_info` |
| `.aq` gerado abre e valida, mas os nomes saem `SoldÃ¡vel` | Texto gravado em UTF-8; o AltoQi grava cp1252 | `CAST(? AS TEXT)` com bytes cp1252 |
| `.aq` gerado sem geometria publica com o fabricante errado | Sem `CLASSE_SIMBOLOGIA_3D` o passo 1 da cascata não existe | Preencher `PECA.BIBLIOTECA` |
| Sólido gerado mostra o interior por uma emenda | Perfil de revolução fechado sem soldar o último anel no primeiro | Descartar o anel repetido e costurar a última faixa no anel 0 |
| Peça gerada com partes soltas ou flutuando | Malhas corretas em posição relativa errada | Não aparece em bbox nem em round-trip — abrir o viewer e olhar |
| Sobrou um `.aq` de 0 byte onde não havia arquivo | `sqlite3.connect()` **cria** o arquivo num caminho inexistente cujo diretório existe | `os.path.isfile()` antes e `connect('file:…?mode=ro', uri=True)` — a armadilha ficou dois meses documentada aqui sem o código ser corrigido; a tabela não substitui o fix |
| Função "só de leitura" (`peek_metadata`) devolve vazio para caminho errado | `except Exception: return meta` engolia o `FileNotFoundError` junto com "não é .aq" | Deixar `FileNotFoundError` subir; engolir só o que é "arquivo existe mas não é legível" |

---

## Histórico

**2.8.1** — `build_product_map`/`find_aq_product` marcados como históricos: o modo `--ifc` do `build.py` foi removido em 2026-09-05 (I6); o matcher vive em `docs/estudo-oq3d/valida_ifc.py`.

**2.8.0** — Malha OQ3D **versão 3** (Maxbar, 31 simbologias, 56 peças): mesmo layout da
2, aceita em `MESH_VERSOES`. Corrige a explicação das 54 divergências de raízes: 31 eram
esse bug e perdiam a geometria inteira; só as 23 da Intelbras são o `0x5D` dentro de
double. Contrato de erro do parser explicitado (truncado → `OQ3DError`; layout
desconhecido → pulado + `OQ3DAvisoParse`), igual ao port TS, e a regra de mostrar o aviso
por simbologia no resumo do build. Três linhas novas na tabela de diagnóstico. Tudo isto
tem teste em `bilds-bim-3d/tests/`.

**2.7.0** — Registro de que o `.aq` gerado pela receita "Escrever um `.aq`" **abre no AltoQi
Builder** (Akato, 2026-09-02): propriedades personalizadas e acentos corretos, colunas no
`DEFAULT` aceitas. Antes a skill só afirmava compatibilidade com o próprio leitor. Fica
explícito o que ainda não foi visto no Builder (render OQ3D, lançamento em rede).

**2.6.0** — `open_aq` do exemplo corrigido: `isfile` antes de conectar e abertura em
`mode=ro` via URI (com `pathname2url`, porque os caminhos reais têm espaço e acento). O
`peek_metadata` deixa `FileNotFoundError` subir. A armadilha já estava na tabela desde a
2.3.0 e o código do `bilds-bim-3d` continuou com o bug até 2026-09-03 — lição para quem
lê esta skill: a tabela de armadilhas descreve o sintoma, não garante que o código ao lado
já o evite.

**2.5.0** — Nova subseção "Um `.aq` mínimo a partir de qualquer malha": a lista de tabelas que uma peça só exige, uma raiz OQ3D por malha de cor uniforme (dividir por cor antes de escrever), a conversão de unidades do viewer, o enquadramento inofensivo (conexão, sem código de diâmetro), a origem gravada em propriedade, e a armadilha do título vindo da pasta. Vem do `www/apps/ingestao/pipeline/geo_to_aq.py` do `bilds-bim-3d`, verificado com um STEP tesselado relido pelo `read_aq.py`/`oq3d.py`.

**2.4.0** — Três aprendizados de quem **edita** a geometria depois de extraída (POC de
edição, `bilds-bim-3d` branch `poc-edicao`): a estrutura de partes perdida no
`{pos,col,idx}` se recupera por componentes conexos porque o `dedup` carrega a cor na
chave; a tesselação de fabricante não é estanque (25–32% de arestas de borda na Dancor),
então esse critério só vale para malha gerada; e arredondar a 1 µm antes do dedup corta o
JSON pela metade sem perder triângulo. Seção "Publicar num viewer web: armadilhas".

**2.3.0** — **`DIAMETRO_PECA` é um CÓDIGO de diâmetro, não centímetro** — a 2.2.0 dizia
"diâmetro nominal (cm)" e estava errado: na Amanco `50 mm` → 9 e `100 mm` → 12, e em
963 das 1.168 peças o valor é a sentinela `-DBL_MAX` e nenhuma das 700 conexões traz
código. Documentadas também as duas
sentinelas de "não definido" (`-2147483647` e `-DBL_MAX`), o mecanismo por trás da
armadilha de encoding (o `.aq` **declara** UTF-8 e **guarda** cp1252, e o SQLite não
valida) e a consequência dele para quem consulta: **literal acentuado dentro do SQL
também precisa ir em cp1252**, senão a query volta vazia sem erro. Nova seção
**"Escrever um `.aq`"** — `CAST(? AS TEXT)` com bytes cp1252, ordem de inserção das FKs,
os enums de `PROJETO_APLICACAO`/`ENTIDADE_IFC`/`SUBTIPO_IFC`/`TIPO_APLICACAO_PECA` com os
valores observados, `ITEM.CODIGO_ITEM` como lugar do código comercial, e as armadilhas de
escrever OQ3D. Documentado o **cabeçalho OQ3D** (37 bytes, com o número de objetos-raiz
no offset 29). Esse campo serve de verificação de parse e expôs um defeito do leitor
tolerante: em 54 das 783 geometrias de fabricante (6,9%, em 6 das 12 bibliotecas) ele
conta raízes a mais, de +2 a +10. Validado gerando uma biblioteca
completa a partir de um catálogo em PDF — 262 peças, lidas de volta por este leitor sem
ressalvas.

**2.2.0** — Resolvidas as duas armadilhas que deslocavam geometria. (a) A referência de instância repetida é o **índice de serialização base 1 sobre todos os objetos em ordem de documento**, com discriminador `0x01`/`0x02` após o GUID — o GUID é único por instância e nunca foi a chave. (b) A rotação de `TCoordinateTransformation3D` é **column-major**, não row-major. Conferido contra o IFC nas 13 peças da Dancor: conjunto de pontos idêntico, 27.425 triângulos batendo exatamente na CAM-W21 2CV. Adicionadas as armadilhas de comparação com IFC (alinhar pelo canto da bbox, comparar por tolerância, bbox não distingue rotação de transposta).

**2.1.0** — **Correção de encoding: o `.aq` é cp1252, não latin-1.** A versão anterior
afirmava "latin-1 (Windows-1252)" tratando os dois como sinônimo. Diferem na faixa
0x80–0x9F, onde estão travessão, aspas curvas e reticências — nomes de produto chegavam
quebrados em produção (`5U \x96 19\x94 x 570mm`) sem nunca lançar exceção. Documentado
também por que trocar o `text_factory` exige `CAST(col AS BLOB)` nas colunas binárias: o
latin-1 era byte-preserving e o round-trip `.encode('latin-1')` do BLOB de geometria não
sobrevive à troca. Verificado com hash SHA-256 dos blobs antes e depois, e zero bytes de
controle nos nomes de 1.441 peças em nove bibliotecas.

**2.0.0** — Formato OQ3D documentado e validado em nove bibliotecas, seis versões de schema (552–607) e três domínios: o `.aq` dispensa os IFCs para gerar 3D com forma, cor e miniatura. Adicionados: tabelas de geometria, vínculo determinístico peça → malha, cascata de inferência de fabricante/título, regra de prefixo por grupo, armadilhas do parser binário, análise de cobertura (variantes com/sem luva, peças sem forma fixa) e armadilhas de publicação web. Em produção no bilds-bim-3d desde o commit `c3be58b`.

**1.1.0** — Extração de peças, curvas Q-H e propriedades personalizadas.
