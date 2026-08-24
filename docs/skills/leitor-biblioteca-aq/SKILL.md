---
name: leitor-biblioteca-aq
description: Lê arquivos de biblioteca BIM do AltoQi Builder (.aq) — SQLite com geometria 3D embutida — e extrai peças, dados hidráulicos, curvas de bomba, propriedades, miniaturas e a malha 3D completa (formato OQ3D), dispensando os IFCs.
version: 2.0.0
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

def open_aq(aq_path):
    """
    Abre um .aq como SQLite. Tenta direto primeiro (caso mais comum),
    cai para extração de ZIP se falhar.
    Retorna (connection, tmp_dir_ou_None).
    Caller deve fechar a connection; se tmp_dir não for None, remover com shutil.rmtree.
    """
    # Tentativa 1: SQLite direto (alguns .aq são SQLite com extensão .aq)
    try:
        con = sqlite3.connect(aq_path)
        con.text_factory = lambda b: b.decode('latin-1')
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
    con.text_factory = lambda b: b.decode('latin-1')
    con.row_factory = sqlite3.Row
    return con, tmp_dir
```

> **Encoding:** strings no banco usam `latin-1` (Windows-1252). Sempre configure `con.text_factory = lambda b: b.decode('latin-1')` antes de qualquer query.
>
> **Por que tentar SQLite direto primeiro:** versões recentes do AltoQi Builder distribuem o .aq como SQLite puro (sem ZIP). O ZIP é o caso legado. Tentar SQLite primeiro evita `zipfile.BadZipFile` desnecessário.

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
| `DIAMETRO_PECA` | REAL | Diâmetro nominal (cm) |
| `COMPRIMENTO_PECA` | REAL | Comprimento (cm) |
| `ALTURA_PECA` | REAL | Altura (cm) |
| `LARGURA_PECA` | REAL | Largura (cm) |
| `BIBLIOTECA` | TEXT | Nome da biblioteca de origem |
| `ATIVO` | INTEGER | 1 = ativo |

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
| `NOME_MB` | TEXT | Nome completo do modelo (encoding latin-1) |
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

### Classes que carregam dados

```
TQi3DIndexedTriangleMeshData
    u32 versao(=2) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos

TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A     (cor UNIFORME da malha)

TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 row-major + translação
```

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

### Limitação conhecida — instâncias repetidas não emitem geometria

Instâncias `TQi3DReusedObject` **sem** definição inline referenciam a malha por GUID, mas os GUIDs são **únicos por instância** — a chave de resolução não foi identificada.

Na bomba CAM-W21 2CV: **5 instâncias com malha própria, 13 só com transform**, que não emitem nada. Efeito visível em produção: parafusos faltando, e um deles aparece solto no ar — a definição inline é desenhada na posição da sua própria instância, longe do corpo.

Não afeta a silhueta do produto (os renders continuam equivalentes ao IFC), mas é visível em close. Hipóteses a testar: o `u32` em `+8` do payload do `TQi3DReusedObject` (valores observados 1..6) pode ser índice da definição; ou a definição a herdar é a última vista no mesmo nível da árvore.

### Sempre deduplique os vértices

O OQ3D indexa dentro de cada malha, mas as malhas de uma peça repetem vértices entre si. Deduplicar reduz **~79%** dos vértices — sem isso, um conjunto de 9 catálogos passou de 148 MB para 571 MB de JSON.

```python
from dedup import dedup
data, orig, n, pct = dedup(oq3d.to_buffers(blob))
json.dump(data, f, separators=(',', ':'))   # sem os separadores default: +12%
```

### Implementação de referência

`scripts/oq3d.py` no projeto **bilds-bim-3d**. API:

```python
import oq3d

oq3d.is_oq3d(blob)                    # valida a assinatura
oq3d.parse(blob)                      # árvore de nós
oq3d.extract(blob, skip_markers=True) # [(verts_cm, tris, rgba)] com transforms aplicados
oq3d.to_buffers(blob)                 # {'pos','col','idx'} em metros, Y-up
oq3d.bbox(blob)                       # (dx,dy,dz) em cm — para validação
oq3d.stats(blob)                      # resumo para logs
```

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
import oq3d   # scripts/oq3d.py do projeto bilds-bim-3d

# Nunca use SELECT * aqui: traria o WIREFRAME (centenas de MB).
cur.execute("""
    SELECT s.ID_SIMBOLOGIA_3D, s.NOME, s.SIMBOLOGIA_3D, s.IMAGEM, g.NOME_GRUPO
    FROM SIMBOLOGIA_3D s
    LEFT JOIN GRUPO_SIMBOLOGIA_3D g
           ON g.ID_GRUPO_SIMBOLOGIA_3D = s.ID_GRUPO_SIMBOLOGIA_3D
""")
for sid, nome, blob, bmp, grupo in cur.fetchall():
    blob = blob if isinstance(blob, bytes) else blob.encode('latin-1')
    if not oq3d.is_oq3d(blob):
        continue
    data = oq3d.to_buffers(blob)          # {'pos','col','idx'} em metros, Y-up
    with open(f'geo/{sid}.json', 'w') as f:
        json.dump(data, f)
    if bmp:                                # miniatura BMP 100×100 já pronta
        bmp = bmp if isinstance(bmp, bytes) else bmp.encode('latin-1')
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
    con.text_factory = lambda b: b.decode('latin-1')
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

> **Só necessário no modo de compatibilidade** (`build.py --ifc`). No caminho padrão a geometria vem do próprio `.aq` e o vínculo é a chave estrangeira `PECA_SIMBOLOGIA_3D` — sem matching por nome.

`build_product_map(aq_data)` organiza os dados extraídos em um mapa indexado por nome de grupo,
pronto para o `build_catalog()` do pipeline cruzar com os slugs dos IFCs:

```python
def build_product_map(aq_data):
    """
    Retorna:
      { nome_gp → {
          'serie': str,
          'pecas': [{ id, nome, conexoes, diametro_cm, comprimento_cm,
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
            'diametro_cm':    p.get('DIAMETRO_PECA'),
            'comprimento_cm': p.get('COMPRIMENTO_PECA'),
            'altura_cm':      p.get('ALTURA_PECA'),
            'largura_cm':     p.get('LARGURA_PECA'),
            'specs':          props_by_peca.get(pid, {}),
            'curva_pts':      curves_by_peca.get(pid),
        })
    return product_map
```

### Como o find_aq_product cruza IFC → .aq

`find_aq_product(slug, product_map, ifc_path_hint=None)` em `build.py`:

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

---

## Diagnóstico de problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `UnicodeDecodeError` ou lixo nos textos | Encoding padrão UTF-8 | `con.text_factory = lambda b: b.decode('latin-1')` |
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
| Menos produtos que peças no banco | Peças sem `PECA_SIMBOLOGIA_3D` | Esperado: tubos e kits não têm forma fixa |
| ZIP com arquivos duplicados | Peças compartilham geometria | Escrever cada arquivo de geo uma única vez |

---

## Histórico

**2.0.0** — Formato OQ3D documentado e validado em nove bibliotecas, seis versões de schema (552–607) e três domínios: o `.aq` dispensa os IFCs para gerar 3D com forma, cor e miniatura. Adicionados: tabelas de geometria, vínculo determinístico peça → malha, cascata de inferência de fabricante/título, regra de prefixo por grupo, armadilhas do parser binário, análise de cobertura (variantes com/sem luva, peças sem forma fixa) e armadilhas de publicação web. Em produção no bilds-bim-3d desde o commit `9b85f6c`.

**1.1.0** — Extração de peças, curvas Q-H e propriedades personalizadas.
