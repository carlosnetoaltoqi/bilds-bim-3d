# Histórico — arquivo, não guia

**Não carregar esta pasta ao iniciar uma sessão.** Nada aqui orienta o trabalho atual: `CLAUDE.md`,
`docs/arquitetura.md`, `docs/decisoes/` e `docs/conhecimento/` orientam. Esta pasta existe para
consulta pontual do operador — quando se precisa da evidência de um número, do raciocínio de uma
decisão antiga ou de um estudo original. Nomes de fabricantes e caminhos da época ficam como estavam
(ADR-016). Desde 2026-09-06 não se registram mais sessões; o que vale fica nos documentos oficiais.

| Pasta / arquivo | O que tem |
|---|---|
| `sessoes/` | 51 registros de sessão (2026-08-23 a 2026-09-06) e o índice cronológico `README.md` — o que cada sessão fez, verificou e decidiu; a evidência numérica dos documentos de conhecimento |
| `estudos/` | os estudos que geraram conhecimento (OQ3D, escrita de `.aq` a partir de PDF, plugin de CAD → catálogo web, soluções da POC dinâmica) e para onde cada um foi promovido (`README.md`) |
| `planos/` | planos e inventários superados: a arquitetura anterior em três apps, o plano da integração, a POC dinâmica, as fases F0–F6 da reengenharia (`reengenharia-2026-09-06-fases.md`), a spec original do ZIP (`bilds-bim-3d-zip-spec.md`) |
| `preview-estatico/` | o gerador de preview HTML com Jinja2 que saiu do produto (ADR-017) |
| `skills-historico.md` | a trilha de versões e correções das quatro skills de `docs/skills/` |
| `licoes-de-processo.md` | o que deu errado no processo (storage apagado por `git clean`, suíte coletando menos testes, histórico git reescrito) e como não repetir |
