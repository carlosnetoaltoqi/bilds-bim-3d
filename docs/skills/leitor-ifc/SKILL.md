---
name: leitor-ifc
description: Transforma arquivos IFC4 em JSONs de geometria prontos para consumo em viewers 3D. Cobre parse de entidades STEP, resolução de transforms, conversão de coordenadas, cores por face (IFCINDEXEDCOLOURMAP) e geração de buffers de vértices. Se a origem for uma biblioteca AltoQi, verifique antes se há um .aq — ele traz a mesma geometria.
version: 1.9.0
author: Bilds / carlosnetoaltoqi
---

> Os documentos de `docs/conhecimento/` citados abaixo também estão em `referencias/` (symlink), para que esta skill leve o conhecimento junto quando usada fora do repositório.

# Skill: leitor-ifc

Você é especialista em extrair geometria de arquivos IFC4 e transformá-la em `{pos,col,idx}` pronto para viewers 3D (Three.js, Babylon.js, ou qualquer renderer que aceite buffers de vértices e índices). Esta skill não assume nenhum projeto, tecnologia de frontend ou localização de arquivos. Ao ser invocada, pergunte onde estão os `.IFC` e onde salvar os JSONs.

## Quando usar

- A fonte é IFC4 (Revit, CATIA, 3DEXPERIENCE, ou exportação de uma biblioteca AltoQi sem `.aq` disponível).
- Precisa de cor por face, resolução de transforms aninhados, ou comparação por round-trip contra outro parser/formato.

## Antes de começar: existe um `.aq` junto?

Se a origem é uma biblioteca do AltoQi Builder, verifique primeiro se há um `.aq` — ele traz a mesma malha (cor e miniatura inclusas) num BLOB binário (OQ3D), é 85×–421× mais rápido de ler, e o vínculo peça↔geometria é por chave estrangeira, não por nome de arquivo. Use a skill `leitor-biblioteca-aq` nesse caso. Volte para o IFC quando não há `.aq`, quando há peças no IFC ausentes do banco, ou quando a variante exata do exportador importa (o AltoQi exporta mais de uma variante por peça e o banco guarda só a canônica).

## Workflow

1. Ler as entidades STEP do texto (`#id=TIPO(args);`), indexando por linha.
2. Resolver `IFCLOCALPLACEMENT` recursivamente até o placement mundial.
3. Escolher o caminho de geometria (tessellated indexado, tessellated por instância mapeada, ou B-rep) e emitir os triângulos.
4. Aplicar cor por face (`IFCINDEXEDCOLOURMAP`) quando presente; senão, cor uniforme.
5. Converter eixos (Z-up → Y-up) e unidades; deduplicar.
6. Conferir: bbox, contagem de triângulos, e round-trip contra outro parser/formato quando possível.

## Armadilhas essenciais (uma linha cada)

- `IFCLOCALPLACEMENT` ignorado é o bug mais comum — sem acumular a hierarquia, peças aparecem espalhadas por metros.
- `split(',')` simples quebra em atributo com vírgula dentro de string — use um parser que respeite parênteses e aspas.
- Regex de float sem casa decimal perde notação científica sem dígito fracionário (`.E-05`).
- Regex gananciosa ao indexar entidades pode engolir o `);` final da linha — ancore no último `)`.
- O índice do atributo de placement/geometria varia por exportador — não assuma posição fixa sem checar o schema.
- Unidade: confira a declaração **e** a magnitude da bbox — exportador pode declarar errado.
- `ifcopenshell` descarta triângulos degenerados — bata a contagem pelo `CoordIndex` bruto quando o arquivo é tessellated.
- Arquivo grande (dezenas/centenas de MB): o parser manual em Python não escala — use `ifcopenshell.geom.iterator` (paraleliza por produto; cor via `r()/g()/b()` como métodos, não atributos).

## Pontos de entrada neste repo

- Parser exato (texto STEP): `biblioteca/bim_pipeline/conversores/parse_ifc.py` — CLI `python -m bim_pipeline.cli.parse_ifc <ifc> <dir> [--slug]`.
- Caminho rápido (`ifcopenshell`, escolhido acima de um limiar de tamanho): `biblioteca/bim_pipeline/conversores/ifc.py` — CLI `python -m bim_pipeline.cli.ifc <ifc> <saida.json> [--info] [--forcar-rapido] [--max-triangulos]`.
- Eixos/unidades e dedup (compartilhados com STEP/IGES): `biblioteca/bim_pipeline/geometria/eixos.py`, `biblioteca/bim_pipeline/geometria/dedup.py`.
- Exportador IFC4 — o caminho inverso, para escrever IFC que este parser lê: `web/src/components/bim-editor/ifc-export.ts`.
- Conferência de ida e volta: `web/tools/testes-editor.sh` + `roundtrip-ifc-export.mts`; teste `tests/servicos/test_editor_roundtrips.py`.
- Serviço web: `POST /tesselar` (multipart, `.ifc`/`.stp`/`.igs`), síncrono e stateless, em `servicos/conversores` (:4300).

## Leia antes (docs/conhecimento/)

| Tópico | Doc |
|---|---|
| Estrutura do IFC, os três caminhos de geometria, `IFCLOCALPLACEMENT`, cor por face, unidades, parsing STEP, escrita, verificação de ida e volta, IFC como gabarito | `ifc.md` |
| Contrato de geometria `{pos,col,idx}`, eixos, dedup | `geometria.md` |
| A mesma geometria via `.aq` — mais rápida, sem IFC | `aq-formato.md` |
| Serviços web (`POST /tesselar`, despacho por extensão) | `servicos-web.md` |
| Diagnóstico rápido | `diagnostico.md` |

## Histórico

**1.9.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/ifc.md`, `geometria.md`, `aq-formato.md` e `servicos-web.md`; removida a seção `FILE_MAP` (o script de referência tomava argumentos fixos por dicionário; o CLI atual recebe o arquivo de entrada direto); sem nomes de fabricantes (ADR-016).

**1.8.1** — Correção da armadilha "igualdade de conjunto arredondado": comparar conjuntos a 10 µm e tolerar uma fração na fronteira era o erro, não a solução — numa malha de 44 mil vértices a fração chega a 2,2% com desvio real de 1,4 µm. Agora: par por vizinho mais próximo a ≤ 2 µm (tolerância derivada dos 6 decimais do `REAL`), nos dois sentidos, zero sem par, exit 1 e autoteste sabotado. Os "14 µm" citados na 1.6.0 eram artefato dessa comparação.

**1.8.0** — Subseção "Arquivo grande": quando o parser manual não escala e como usar o `ifcopenshell.geom.iterator` como caminho rápido (cor por material com `r()/g()/b()` como métodos, metros já convertidos, degenerados descartados, dedup em numpy, um produto só não paraleliza, conversão fora da requisição HTTP). Medido num IFC de projeto de 124 MB: 760.038 △ em 221 s, 3,6 GB.

**1.7.0** — Nova seção "O parser como biblioteca — IFC entrando num editor": o que falta ao `parse_ifc_file` para servir de entrada (dedup, unidade decidida pela declaração **e** pela magnitude, nomes via `ifcopenshell`) e a conferência por round-trip com o exportador da 1.6.0.

**1.6.0** — Nova seção "Escrever IFC que este parser lê": as regras para gerar IFC4 a partir de um `{pos,col,idx}` (uma entidade por linha, montagem sem Representation, METRE coerente, eixos `(x,−z,y)`, placement rígido vs escala assada, REAL sem expoente, mapa de cor 1-based + `IFCSTYLEDITEM`, `Closed` honesto, strings `\X2\`, propriedades). Cada uma é uma armadilha deste documento vista pelo lado de quem escreve. Conferido com o próprio `parse_ifc.py` (mesmos triângulos, 14 µm) e `ifcopenshell.validate` (0 erros).

**1.5.0** — Nova seção "O IFC como gabarito": como reconstruir a geometria de um arquivo tessellated direto do STEP (sem tesselador, exato) e usá-la para validar o parser de outro formato. Quatro armadilhas de comparação, todas encontradas na prática: bbox não distingue rotação de transposta, centróide não serve de âncora quando um lado solda vértices e o outro não, igualdade de conjunto arredondado falha na fronteira, e o `ifcopenshell` descarta degenerados (50 triângulos a menos que o STEP numa peça real).

**1.4.0** — Aviso no início: se a origem for uma biblioteca AltoQi, o `.aq` traz a mesma geometria e é muito mais rápido de ler (ver `leitor-biblioteca-aq`). Listados os casos em que o IFC continua sendo a fonte certa.

**1.3.1** — Bug do `IFCMAPPEDITEM`: falta um nível de indireção até o face set.

**1.3.0** — Cinco bugs de parsing STEP documentados com suas correções.
