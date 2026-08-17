---
name: leitor-biblioteca-aq
description: Lê arquivos de biblioteca BIM do AltoQi Builder (.aq) — SQLite direto ou SQLite zipado — e extrai estrutura de peças, dados hidráulicos, curvas de bomba e propriedades personalizadas em formatos prontos para consumo.
version: 1.1.0
author: Bilds / carlosnetoaltoqi
---

# Skill: leitor-biblioteca-aq

Você é especialista em abrir e extrair dados de arquivos de biblioteca BIM do AltoQi Builder (`.aq`). Ao ser invocada, pergunte ao usuário o caminho do arquivo `.aq`. Não assuma nenhum diretório padrão.

---

## O que é um arquivo .aq

Um `.aq` pode ser de **dois tipos** dependendo de como foi obtido:

1. **ZIP contendo SQLite** — o caso mais comum ao baixar diretamente do AltoQi. Extensão `.aq` é um ZIP renomeado; dentro há um arquivo SQLite (geralmente sem extensão ou `.db`).

2. **SQLite direto** — ocorre quando o `.aq` foi extraído de outro ZIP (ex: `Bombas de Combate a Incêndio.zip` → `pecas_dancor.aq`). Nesse caso o arquivo já é um banco SQLite, não um ZIP.

**Sempre tente SQLite direto primeiro** — é o método robusto:

```python
import zipfile, sqlite3, os, shutil, tempfile

def open_aq(aq_path: str):
    """Abre um .aq como SQLite — tenta direto, cai para ZIP se falhar."""
    # Tentativa 1: é um SQLite direto (extraído de outro ZIP)
    try:
        con = sqlite3.connect(aq_path)
        con.text_factory = lambda b: b.decode('latin-1')
        con.row_factory = sqlite3.Row
        con.execute("SELECT 1 FROM GRUPO_PECA LIMIT 1")  # valida que é o banco certo
        return con, None  # None = sem arquivo temporário para limpar
    except Exception:
        pass

    # Tentativa 2: é um ZIP contendo o SQLite
    tmp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(aq_path, 'r') as z:
        z.extractall(tmp_dir)
    db_files = [f for f in os.listdir(tmp_dir)
                if os.path.isfile(os.path.join(tmp_dir, f)) and not f.endswith('.xml')]
    if not db_files:
        raise FileNotFoundError("Nenhum SQLite encontrado dentro do .aq")
    dest = os.path.join(tmp_dir, '_extracted.db')
    shutil.copy(os.path.join(tmp_dir, db_files[0]), dest)
    con = sqlite3.connect(dest)
    con.text_factory = lambda b: b.decode('latin-1')
    con.row_factory = sqlite3.Row
    return con, tmp_dir  # tmp_dir para limpar depois com shutil.rmtree

# Uso:
con, tmp = open_aq('/path/to/arquivo.aq')
# ... extrações ...
con.close()
if tmp:
    shutil.rmtree(tmp, ignore_errors=True)
```

> **Encoding:** strings no banco usam `latin-1` (Windows-1252). Sempre configure `con.text_factory = lambda b: b.decode('latin-1')` antes de qualquer query.

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

### Outras tabelas relevantes

**`IMAGEM`** — imagens dos produtos (BLOB)
| Coluna | Tipo | Descrição |
|---|---|---|
| `ID_IMAGEM` | INTEGER PK | |
| `NOME_IMAGEM` | TEXT | Nome/descrição da imagem |
| `IMAGEM` | BLOB | Bytes da imagem (PNG/JPG) |

**`ENTRADA_3D`** / **`PECA_SIMBOLOGIA_3D`** — referências a símbolos e geometria 3D parametrizados (não são os arquivos IFC diretamente — os IFCs são distribuídos separadamente).

**`CLASSIFICACAO_IFC`** / **`CLASSIFICACAO_IFC_PECA`** — classificação IFC das peças quando preenchida pelo fabricante.

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

### Extrair imagens

```python
cur.execute("SELECT ID_IMAGEM, NOME_IMAGEM, IMAGEM FROM IMAGEM")
for row in cur.fetchall():
    if row['IMAGEM']:
        with open(f"img_{row['ID_IMAGEM']}.png", 'wb') as f:
            f.write(row['IMAGEM'])
```

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

## Peças presentes no IFC mas ausentes no .aq

Às vezes o fabricante distribui um IFC que não tem entrada correspondente no banco `.aq`. Isso pode ocorrer por modelos mais novos adicionados ao kit IFC sem atualizar a biblioteca, ou por variantes de desenvolvimento.

**Como identificar:** cruzar os slugs dos JSONs gerados pelo `leitor-ifc` com os grupos/peças encontrados no banco. Qualquer JSON sem correspondente no banco é um caso especial.

**Como tratar na página:**
- Incluir a peça com dados mínimos derivados do nome do arquivo IFC (potência, tensão genérica da série)
- Marcar `pts: null` (sem curva Q-H)
- Listar apenas specs inferíveis; não inventar valores

```javascript
// Exemplo: CAM 89-62 TJM — presente no IFC (50CV), ausente no .aq
{id:'89-62', tipo:'TJM', serie:'CAM 89-62 TJM', code:'CAM 89-62', pot:50,
 geo:'cam-89-62-tjm', nome:'50 CV · 2.1/2" T 4V INC IR3',
 specs:{'Tensão':'Trifásico 220/380V','Grau de Proteção':'IP55-TFVE',
        'Isolamento':'Classe F','Rotação':'3.500 rpm · 60Hz'},
 pts: null}
```

---

## Diagnóstico de problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `UnicodeDecodeError` ou lixo nos textos | Encoding padrão UTF-8 | `con.text_factory = lambda b: b.decode('latin-1')` |
| `zipfile.BadZipFile` ao abrir o .aq | O arquivo já é SQLite direto (extraído de outro ZIP) | Usar `open_aq()` que tenta SQLite direto antes de tentar como ZIP |
| SQLite dentro do ZIP tem nome inesperado | Cada versão do AltoQi pode nomear diferente | Listar todos os arquivos no ZIP e pegar o que não é `.xml` |
| `MODELO_BOMBA` vazio / sem curvas | Biblioteca não contém bombas | Verificar `PROJETO_APLICACAO` em `GRUPO_PECA` — 22 = incêndio, outros tipos não têm curva Q-H |
| `IMAGEM` vazia | Fabricante não incluiu imagens no .aq | Imagens podem estar em arquivo separado ou só nos IFCs |
| Propriedades ausentes para algumas peças | Nem toda peça tem todas as propriedades | Usar `LEFT JOIN` ao invés de `JOIN` ao consultar `VALOR_PROPRIEDADE_PERSONALIZADA` |
| Valores numéricos como texto | `TIPO_VALOR = 0` mesmo para números | Converter com `float(valor)` quando necessário; o campo `TIPO_VALOR` indica o tipo esperado |

---

## Segurança — Zip Slip na extração do .aq

Arquivos `.aq` são ZIPs contendo o SQLite. **Nunca usar `z.extractall(tmp_dir)` diretamente** — em Python < 3.12 não há validação dos paths internos do ZIP. Um `.aq` craftado pode conter uma entrada `../../../../home/user/.ssh/authorized_keys` que é extraída fora do `tmp_dir`.

Padrão obrigatório:

```python
safe_root = os.path.realpath(tmp_dir)
for member in z.namelist():
    dest = os.path.realpath(os.path.join(safe_root, member))
    if not dest.startswith(safe_root + os.sep):
        continue  # zip slip — ignorar
    z.extract(member, tmp_dir)
```
| Peça no IFC sem entrada no banco | Fabricante não sincronizou .aq com os IFCs | Incluir a peça com specs mínimas derivadas do nome do arquivo; `pts: null` |
