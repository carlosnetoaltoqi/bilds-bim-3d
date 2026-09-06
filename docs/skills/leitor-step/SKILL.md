---
name: leitor-step
description: Lê arquivos STEP (.stp/.step — ISO 10303 AP203/AP214/AP242) e IGES (.igs/.iges — faces soltas do SolidWorks, costuradas em sólido) — B-rep paramétrico de CAD como Inventor, SolidWorks, CATIA — e os tessela para o JSON de geometria do viewer ({pos, col, idx} em metros, Y-up) com OpenCASCADE em Python (OCP). Cobre unidades, nomes e cores via XCAF, sentido dos triângulos, montagens, deflexão, e as armadilhas de referência morta que dão segfault. O caminho de saída para IFC4 e .aq está nas skills irmãs.
version: 1.2.0
author: Bilds / carlosnetoaltoqi
---

> Os documentos de `docs/conhecimento/` citados abaixo também estão em `referencias/` (symlink), para que esta skill leve o conhecimento junto quando usada fora do repositório.

# Skill: leitor-step

Você é especialista em transformar arquivos STEP e IGES em malha pronta para viewer 3D. Ao ser invocada, pergunte o caminho do arquivo e o destino do JSON. Não assuma diretórios.

## Quando usar

- Peça de CAD paramétrico (Inventor, SolidWorks, CATIA) em `.stp`/`.step` — B-rep com topologia de faces/arestas, sem triângulo nenhum no arquivo — ou `.igs`/`.iges` — faces soltas, tipicamente sem sólido.
- É preciso tesselar para o contrato `{pos,col,idx}` do viewer, preservando unidade, nome e cor.

## Workflow

1. Instalar o kernel: OpenCASCADE via `cadquery-ocp` (`pip install --user --break-system-packages cadquery-ocp` — PEP 668 no Ubuntu).
2. Ler com `STEPCAFControl_Reader`/`IGESCAFControl_Reader` (XCAF: forma + nome + cor juntos), mantendo documento/reader/rótulos vivos.
3. Se não houver sólido (IGES, ou STEP só com cascas): unir as faces livres, costurar (`BRepBuilderAPI_Sewing`), fechar em sólido, orientar pelo volume assinado, remapear cor por face pós-costura.
4. Tesselar (`BRepMesh_IncrementalMesh`), respeitando o sentido da face (`TopAbs_REVERSED`) e a `TopLoc_Location` de cada sub-forma.
5. Converter unidade (o OCC sempre entrega mm internamente → `×0.001`) e eixos (Z-up → `(x, z, −y)`); deduplicar por `(pos, cor)`.
6. Conferir: bbox, contagem crescendo com deflexão menor, aparência (face escura = sentido errado), round-trip pelos parsers do projeto.

## Armadilhas essenciais (uma linha cada)

- Referência morta é a causa nº 1 de segfault sem traceback: documento, reader e sequência de rótulos saem de escopo — mantenha os três vivos; `python3 -X faulthandler` acha a linha.
- `TopExp_Explorer.Current()` guardado para depois também segfaulta — copie tipado na hora (`TopoDS.Solid_s(ex.Current())`, `TopoDS.Face_s(...)`).
- `ColorTool.GetColor` recebe a **forma**, não o rótulo — passar o rótulo é `TypeError`.
- Unidade: sempre `×0.001` para metros, não só "se declarar mm" — confira a magnitude da bbox.
- IGES sem sólido: o volume assinado decide a orientação, não `ShapeFix_Solid` sozinho (casca que não fechou não é invertida).
- Cor pós-costura exige mapear face costurada → face original (`sew.Modified`/`ModifiedSubShape`) antes de tesselar, senão cai no cinza padrão.

## Pontos de entrada neste repo

- Módulo: `biblioteca/bim_pipeline/conversores/step_iges.py` (`costurar`, `volume_cm3`, `tesselar`, `converter`, `formato_de`).
- CLI: `python -m bim_pipeline.cli.step_iges <peca.stp|.igs> <saida.json> [--deflexao] [--angulo] [--info]`.
- Eixos/unidades e dedup (compartilhados com IFC): `biblioteca/bim_pipeline/geometria/eixos.py`, `biblioteca/bim_pipeline/geometria/dedup.py`.
- Serviço web: `POST /tesselar` (multipart `.stp`/`.step`/`.igs`/`.iges`/`.ifc`), síncrono e stateless, em `servicos/conversores` (:4300) — despacho por extensão em `pacotes/base/src/biblioteca.ts`. **A rota `POST /step/importar` não existe mais.**
- Virar produto de catálogo (assíncrono, na fila): `POST /importacoes` em `servicos/criador-de-catalogos`.
- Saída alimenta as skills irmãs: exportar IFC4 (`leitor-ifc`) ou gerar `.aq` (`leitor-biblioteca-aq`, via `biblioteca/bim_pipeline/saida/geo_to_aq.py`).

## Leia antes (docs/conhecimento/)

| Tópico | Doc |
|---|---|
| STEP/IGES, kernel OCP, XCAF, armadilhas de referência morta, tesselação, costura/orientação do IGES | `step-iges.md` |
| Contrato de geometria `{pos,col,idx}`, eixos, dedup | `geometria.md` |
| Exportar para IFC4 | `ifc.md` |
| Gerar `.aq` a partir da malha | `aq-escrita.md` |
| Serviços web (rotas, filas, despacho por extensão) | `servicos-web.md` |
| Diagnóstico rápido | `diagnostico.md` |
