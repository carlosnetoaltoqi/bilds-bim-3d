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

## Histórico

**2.10.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/aq-formato.md`, `aq-escrita.md`, `oq3d.md`, `geometria.md` e `inferencia.md`; removidas as seções obsoletas `build_product_map` e "Como o find_aq_product cruza IFC → .aq" (o modo `--ifc` do build foi removido em 2026-09-05); sem nomes de fabricantes (ADR-016).

**2.9.1** — O `.aq` de 854 peças gerado pela receita "catálogo inteiro" (uma biblioteca de conexões real exportada) foi aberto no AltoQi Builder pelo usuário e funcionou — primeira prova no Builder de geometria OQ3D reescrita em escala. Ressalvas de "não visto no Builder" ajustadas.

**2.9.0** — Regras que só aparecem ao escrever N peças: uma simbologia por geometria distinta (não por peça), uma propriedade por chave (não por peça), `NOME_PECA` sem o nome do grupo, códigos IFC do grupo inferidos do nome quando faltam os originais, bomba identificada pela curva Q-H, colunas de peça com 3D como o fabricante grava. Conferido com uma biblioteca de conexões real inteira: 854 peças, 448 simbologias, nomes e geometria iguais aos originais.

**2.8.1** — `build_product_map`/`find_aq_product` marcados como históricos: o modo `--ifc` do build foi removido em 2026-09-05; o matcher ficou fora do caminho padrão.

**2.8.0** — Malha OQ3D **versão 3** (uma biblioteca de barramentos): mesmo layout da versão 2, aceita em `MESH_VERSOES`. Corrige a explicação das divergências de contagem de raízes: parte era esse bug — e perdia a geometria inteira —, e uma fração menor era um caractere fora do padrão dentro de um double. Contrato de erro do parser explicitado (truncado → `OQ3DError`; layout desconhecido → pulado + `OQ3DAvisoParse`), e a regra de mostrar o aviso por simbologia no resumo do build. Coberto por teste.

**2.7.0** — Registro de que o `.aq` gerado pela receita "Escrever um `.aq`" **abre no AltoQi Builder**: propriedades personalizadas e acentos corretos, colunas no `DEFAULT` aceitas. Antes a skill só afirmava compatibilidade com o próprio leitor. Fica explícito o que ainda não foi visto no Builder (render OQ3D, lançamento em rede).

**2.6.0** — `open_aq` do exemplo corrigido: `isfile` antes de conectar e abertura em `mode=ro` via URI (com `pathname2url`, porque os caminhos reais têm espaço e acento). O `peek_metadata` deixa `FileNotFoundError` subir. A armadilha já estava na tabela desde a 2.3.0 e o código do projeto continuou com o bug por um tempo — lição para quem lê esta skill: a tabela de armadilhas descreve o sintoma, não garante que o código ao lado já o evite.

**2.5.0** — Nova subseção "Um `.aq` mínimo a partir de qualquer malha": a lista de tabelas que uma peça só exige, uma raiz OQ3D por malha de cor uniforme (dividir por cor antes de escrever), a conversão de unidades do viewer, o enquadramento inofensivo (conexão, sem código de diâmetro), a origem gravada em propriedade, e a armadilha do título vindo da pasta. Verificado com um STEP tesselado relido pelo leitor do projeto.

**2.4.0** — Três aprendizados de quem **edita** a geometria depois de extraída (uma prova de conceito de edição de geometria, em branch própria do projeto): a estrutura de partes perdida no `{pos,col,idx}` se recupera por componentes conexos porque o `dedup` carrega a cor na chave; a tesselação de fabricante não é estanque (25–32% de arestas de borda numa biblioteca real), então esse critério só vale para malha gerada; e arredondar a 1 µm antes do dedup corta o JSON pela metade sem perder triângulo. Seção "Publicar num viewer web: armadilhas".

**2.3.0** — **`DIAMETRO_PECA` é um CÓDIGO de diâmetro, não centímetro** — a 2.2.0 dizia "diâmetro nominal (cm)" e estava errado: numa biblioteca de conexões real `50 mm` → 9 e `100 mm` → 12, e na maioria das peças o valor é a sentinela `-DBL_MAX` — nenhuma conexão traz código. Documentadas também as duas sentinelas de "não definido" (`-2147483647` e `-DBL_MAX`), o mecanismo por trás da armadilha de encoding (o `.aq` **declara** UTF-8 e **guarda** cp1252, e o SQLite não valida) e a consequência para quem consulta: **literal acentuado dentro do SQL também precisa ir em cp1252**, senão a query volta vazia sem erro. Nova seção "Escrever um `.aq`" — `CAST(? AS TEXT)` com bytes cp1252, ordem de inserção das FKs, os enums de `PROJETO_APLICACAO`/`ENTIDADE_IFC`/`SUBTIPO_IFC`/`TIPO_APLICACAO_PECA` com os valores observados, `ITEM.CODIGO_ITEM` como lugar do código comercial, e as armadilhas de escrever OQ3D. Documentado o cabeçalho OQ3D (37 bytes, com o número de objetos-raiz num offset fixo) — esse campo serve de verificação de parse e expôs um defeito do leitor tolerante: numa fração das geometrias de fabricante ele conta raízes a mais. Validado gerando uma biblioteca completa a partir de um catálogo em PDF — 262 peças, lidas de volta por este leitor sem ressalvas.

**2.2.0** — Resolvidas as duas armadilhas que deslocavam geometria. (a) A referência de instância repetida é o **índice de serialização base 1 sobre todos os objetos em ordem de documento**, com discriminador após o GUID — o GUID é único por instância e nunca foi a chave. (b) A rotação é **column-major**, não row-major. Conferido contra o IFC numa biblioteca real: conjunto de pontos idêntico, milhares de triângulos batendo exatamente numa peça de referência. Adicionadas as armadilhas de comparação com IFC (alinhar pelo canto da bbox, comparar por tolerância, bbox não distingue rotação de transposta).

**2.1.0** — **Correção de encoding: o `.aq` é cp1252, não latin-1.** A versão anterior afirmava "latin-1 (Windows-1252)" tratando os dois como sinônimo. Diferem na faixa 0x80–0x9F, onde estão travessão, aspas curvas e reticências — nomes de produto chegavam quebrados em produção sem nunca lançar exceção. Documentado também por que trocar o `text_factory` exige `CAST(col AS BLOB)` nas colunas binárias: o latin-1 era byte-preserving e o round-trip `.encode('latin-1')` do BLOB de geometria não sobrevive à troca. Verificado com hash SHA-256 dos blobs antes e depois, e zero bytes de controle nos nomes de mais de mil peças em nove bibliotecas.

**2.0.0** — Formato OQ3D documentado e validado em nove bibliotecas, seis versões de schema e três domínios: o `.aq` dispensa os IFCs para gerar 3D com forma, cor e miniatura. Adicionados: tabelas de geometria, vínculo determinístico peça → malha, cascata de inferência de fabricante/título, regra de prefixo por grupo, armadilhas do parser binário, análise de cobertura e armadilhas de publicação web.

**1.1.0** — Extração de peças, curvas Q-H e propriedades personalizadas.
