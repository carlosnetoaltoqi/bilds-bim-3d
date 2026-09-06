# 2026-08-24 — Correções de documentação e pipeline

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

- `build_zip()` em `build.py`: manifest.json gerado com campos em **inglês** conforme
  contrato da API bilds.com (`title`, `manufacturer`, `description`, `filters`, `productCount`).
  Antes usava os mesmos campos em português do `catalog.json`.
- ZIP renomeado de `bilds-upload.zip` para `<slug>-AAAAMMDDHHMM.zip`.
- `output/preview/.gitignore` criado para excluir `*_raw.json` (artefatos do CLI do parse_ifc).
- Skill `leitor-ifc` atualizada para v1.3.0 com todos os 5 bugs e suas correções documentadas.
