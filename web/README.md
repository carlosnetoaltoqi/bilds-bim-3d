# web — páginas de catálogo, importação e editor (:3000)

Next.js, sem login (ADR-007). Fala **direto** com os serviços, **um cliente por serviço** em `src/servicos/`
(`catalogo.ts`, `criador.ts`, `editor.ts`, `zip.ts`, `conversores.ts`) — nenhuma URL fixa fora deles
(`tests/test_servicos_fronteiras.py`). No browser valem as `NEXT_PUBLIC_*_URL`; no servidor Next as sem prefixo.

| Página | Contexto | Serviços |
|---|---|---|
| `/` | catálogo | empresas e catálogos (catalogo); menu: importar `.aq`, importar peça CAD, importar plugin, converter CAD, **Gerar ZIP bilds.com** (zip), criar empresa |
| `/:empresa/:catalogo` | catálogo | página pública com miniaturas e viewer 3D (catalogo) |
| `/importar[?tipo=aq\|cad]` · `/importar/plugin` | criador | upload com progresso, status a cada 2 s, últimas importações (criador); inspecionar DLL (conversores) |
| `/cad` | conversores | STEP/IGES/IFC → viewer, download JSON/IFC4 (browser)/.aq |
| `/:empresa/:catalogo/editar` | catálogo | metadados (catalogo), baixar `.aq` do catálogo (criador), apagar |
| `/:empresa/:catalogo/editar/:produtoId` | editor | viewport 3D, informações (editor `PATCH`), salvar geometria (editor `PUT`, copy-on-write), restaurar, exportar IFC4 (browser) e `.aq` (conversores) |
| `/empresa/criar` | catálogo | nome, customUrl, logo |

`tools/`: round-trips do editor (`testes-editor.sh`: `mesh-model` a 2 µm e o exportador IFC conferido pela
biblioteca) — `tests/test_editor_roundtrips.py` os roda. Subir: `pnpm dev:web`.
