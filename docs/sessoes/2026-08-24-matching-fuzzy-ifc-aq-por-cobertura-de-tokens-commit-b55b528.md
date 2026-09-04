# 2026-08-24 — Matching fuzzy IFC → .aq por cobertura de tokens (commit b55b528)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

`find_aq_product(slug, product_map, ifc_path_hint=None)` — substituição do match por
prefixo simples por scoring de cobertura de tokens:

- **Tokenização do caminho**: todos os componentes do path relativo do IFC viram tokens
  (ex: `"Cap/PVC Esgoto SN/100mm.ifc"` → `{cap, pvc, esgoto, sn, 100mm}`).
- **Score de grupo**: `covered_tokens / total_gp_tokens`. Exige ≥ 100%; relaxa para ≥ 75%
  se não encontrar nada. Em empate, prefere o grupo com mais tokens (mais específico).
- **Score de peça**: dentro do grupo vencedor, a PECA com maior sobreposição com o leaf
  (nome do arquivo sem extensão e sem pasta) é selecionada.
- **Nome composto**: se o nome do GRUPO_PECA não está contido no nome da PECA, o build
  produz `f"{nome_gp} {peca['nome']}"` como nome do produto (ex: `"Cap 100mm"`).
- **Fallback**: prefixo/número preservado para IFCs flat sem hierarquia (Dancor).

`build_catalog()` passa `ifc_name` (a chave do `file_map`) como `ifc_path_hint`.
