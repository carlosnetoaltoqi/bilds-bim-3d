# docs/conhecimento — o que era o "Conhecimento crítico" do CLAUDE.md

Movido do `CLAUDE.md` em 2026-09-04 (S7.8, I22). Cada arquivo é a **fonte única** do seu assunto
dentro do repositório; as skills em `docs/skills/` repetem o que serve a outros projetos.

| Arquivo | Assunto |
|---|---|
| `pipeline-estatico.md` | fluxo do usuário, os dois modos, inferência de fabricante/título/layout, `config.json`, `catalog.json`, layouts e padrão dos templates, conteúdo do ZIP, miniaturas pré-renderizadas (por quê, como, dependências, `page.evaluate`), matching IFC → `.aq`, integração com a bilds.com |
| `oq3d.md` | o formato binário dentro do `.aq`: cabeçalho de 37 bytes, classes, instâncias por referência, unidades (cm), escrever OQ3D, API do `oq3d.py`, como conferir contra o IFC |
| `read-aq.md` | schema do `.aq`: cp1252 (não latin-1), ZIP ou SQLite, tabelas de produto e de geometria, `DIAMETRO_PECA` é código, sentinelas, peças sem geometria, escrever um `.aq`, diferenças entre versões de schema |
| `parse-ifc.md` | IFC4 → geometria: `IFCLOCALPLACEMENT`, caminhos A e B, matriz 4×4, Z-up → Y-up, `split_top()`, `IFCINDEXEDCOLOURMAP`, unidades, outliers |
| `templates-html.md` | Three.js self-hosted, miniatura estática + click-to-3D, cache de geometria, `vertexColors`, escape, design tokens |
| `diagnostico.md` | tabela sintoma → causa provável, do parser ao editor |

Regra: conhecimento novo entra **aqui** (no arquivo do assunto), com data; o `CLAUDE.md` só aponta.
