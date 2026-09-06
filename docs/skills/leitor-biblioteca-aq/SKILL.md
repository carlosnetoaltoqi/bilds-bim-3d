---
name: leitor-biblioteca-aq
description: Lê E ESCREVE arquivos de biblioteca BIM do AltoQi Builder (.aq) — SQLite com geometria 3D embutida. Extrai peças, dados hidráulicos, curvas de bomba, propriedades, miniaturas e a malha 3D completa (formato OQ3D), dispensando os IFCs; e gera um .aq do zero, com o schema, os enums, o encoding cp1252 e o binário OQ3D corretos.
version: 2.10.0
author: Bilds / carlosnetoaltoqi
---

> Os documentos de `docs/conhecimento/` citados abaixo também estão em `referencias/` (symlink), para que esta skill leve o conhecimento junto quando usada fora do repositório.

# Skill: leitor-biblioteca-aq

Você é especialista em ler e escrever bibliotecas BIM do AltoQi Builder (`.aq`). Ao ser invocada, pergunte o caminho do arquivo; não assuma diretório padrão.

## Quando usar

- Precisa de peças, dados hidráulicos, curva Q-H, propriedades, miniatura ou a malha 3D de uma biblioteca `.aq`, sem depender dos IFCs equivalentes — ler o `.aq` é 85×–421× mais rápido.
- Precisa gerar um `.aq` do zero — uma peça avulsa ou um catálogo inteiro — a partir de uma malha `{pos,col,idx}` e dados de catálogo.

## O essencial

- Um `.aq` é um ZIP renomeado contendo um SQLite (versões recentes distribuem o SQLite puro, sem ZIP) — tente abrir direto e caia para ZIP só se falhar.
- A geometria 3D mora no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, num formato binário próprio (OQ3D) — a mesma malha que o AltoQi exporta como IFC, o que dispensa os IFCs.
- O texto é **cp1252**, não latin-1 nem UTF-8 — mesmo o `.aq` declarando `PRAGMA encoding = UTF-8` — e isso afeta leitura, escrita e literais de query.

## Workflow de leitura

1. Abrir com `open_aq` (SQLite direto → fallback ZIP), `text_factory` em cp1252.
2. Ler o catálogo de produto: `GRUPO_PECA` → `PECA` → dados hidráulicos / curva Q-H / propriedades personalizadas.
3. Ler a geometria: `PECA_SIMBOLOGIA_3D` (FK, não matching por nome) → `SIMBOLOGIA_3D` (BLOB) → parser OQ3D → `{pos,col,idx}`.
4. Inferir fabricante/título/slug quando a peça não os traz de forma direta.

## Workflow de escrita

1. Criar o schema a partir do DDL de referência do projeto — nunca escrever as 77 tabelas à mão.
2. Inserir na ordem que fecha as FKs; gravar texto em cp1252 (`CAST(? AS TEXT)` com bytes já codificados).
3. Escrever o BLOB OQ3D: uma `SIMBOLOGIA_3D` por geometria **distinta** (não por peça) — várias peças podem apontar para a mesma.
4. Validar lendo de volta com o leitor do projeto e, quando possível, abrindo no AltoQi Builder.

## Armadilhas essenciais (uma linha cada)

- cp1252 ≠ latin-1: divergem em 0x80–0x9F (travessão, aspas curvas, reticências) — latin-1 nunca lança erro, só corrompe o nome em silêncio.
- Literal acentuado dentro do SQL também precisa ir em cp1252 — comparar `str` (UTF-8) com os bytes cp1252 do banco nunca casa, e a query volta vazia sem erro.
- `sqlite3.connect(caminho)` **cria** um arquivo vazio se ele não existir — cheque `os.path.isfile` antes e abra em `mode=ro`.
- `DIAMETRO_PECA` é um **código** de diâmetro, não centímetro, e a maioria das peças traz a sentinela `-DBL_MAX` em vez de um valor.
- Sentinelas substituem `NULL` no AltoQi: `-2147483647` e `-1.7976931348623157e+308`.
- Trocar `text_factory` sem `CAST(col AS BLOB)` na query corrompe o BLOB da geometria — o round-trip via latin-1 não sobrevive à troca para cp1252.
- Deduplique vértices só na malha **gerada** — a malha de fabricante já vem como sopa de triângulos e não é estanque.

## Pontos de entrada neste repo

- Ler: `biblioteca/bim_pipeline/aq/read_aq.py`, `biblioteca/bim_pipeline/aq/oq3d.py` — CLI `python -m bim_pipeline.cli.read_aq <arquivo.aq> [saida.json] [--meta]`.
- Escrever uma peça: `biblioteca/bim_pipeline/saida/geo_to_aq.py` — CLI `python -m bim_pipeline.cli.gerar_aq entrada.json saida.aq [--fabricante] [--linha] [--nome] [--codigo]`.
- Escrever um catálogo inteiro: `biblioteca/bim_pipeline/saida/catalogo_to_aq.py` — CLI `python -m bim_pipeline.cli.catalogo_para_aq manifesto.json saida.aq [--manter-prefixo-serie] [--quiet]`.
- Schema e escritores binários: `biblioteca/bim_pipeline/aq/aq_writer.py`, `biblioteca/bim_pipeline/aq/oq3d_writer.py`.
- Inferência de fabricante/título/slug: `biblioteca/bim_pipeline/catalogo/inferencia.py`; catálogo/prefixo por grupo: `biblioteca/bim_pipeline/catalogo/catalogo.py`.
- Ferramentas de diagnóstico e validação (fora do caminho padrão): `biblioteca/bim_pipeline/cli/ferramentas/validar_aq.py`, `aq_referencia.py`, `oq3d_anatomy.py`, `oq3d_roundtrip.py`.
- Testes: `tests/biblioteca/test_*.py`.

## Leia antes (docs/conhecimento/)

| Tópico | Doc |
|---|---|
| Schema do `.aq`, encoding, sentinelas, `DIAMETRO_PECA`, versões de schema | `aq-formato.md` |
| Escrever um `.aq` — peça e catálogo inteiro, enums, ordem de inserção | `aq-escrita.md` |
| Formato binário OQ3D — cabeçalho, árvore, instâncias por referência, escrita, validação contra IFC | `oq3d.md` |
| Contrato de geometria `{pos,col,idx}`, eixos, unidades, dedup | `geometria.md` |
| Inferência de fabricante/título/slug/layout | `inferencia.md` |
| Forma representativa quando não há geometria de fabricante | `formas-representativas.md` |
| Modelo do catálogo (produto, specs, ponteiro de geometria) | `catalogo-modelo.md` |
| Diagnóstico rápido | `diagnostico.md` |
