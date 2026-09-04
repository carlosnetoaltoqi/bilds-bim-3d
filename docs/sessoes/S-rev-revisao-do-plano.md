# S-rev — Revisão do plano com ce-doc-review

**Data:** 2026-08-29 · **Sessão do plano:** S-rev · **Status:** concluída
**Commits:** `2a8574f` `ac0e217` `7ffa739` `107edbf` `4acbf0b` `7a75772` `b95e765` `926c435`

---

## 1. O que era para fazer

Revisar `docs/plano-produto-dinamico.md` com `ce-doc-review`. Entregável: emendas ao
plano, ADRs que a revisão conseguisse fechar, e este registro. Pronto quando o plano
tivesse incorporado o que a revisão apontou — ou registrado por que não incorporou.

## 2. O que foi feito

Sete lentes revisaram o plano em contextos independentes: coherence, feasibility,
product-lens, design-lens, security-lens, scope-guardian e adversarial. Produziram **41
achados brutos**, deduplicados para **19 decisões**. Todas fechadas.

**A mudança estrutural: o ADR-001.** No meio do walk-through o dono do projeto fechou a
arquitetura de dados, e ela reescreveu o plano:

> Geometria e miniaturas vão para **arquivo** (S3 na bilds.com, disco na POC), com o
> **ponteiro no banco**. No MongoDB ficam os **dados BIM do produto** — specs, curvas,
> série — que é o que se busca. A **API serve a geometria**, como a bilds.com já faz para
> evitar CORS. O acesso ao blob passa pelo driver `GeometryStore`.

Arquivos tocados: `docs/plano-produto-dinamico.md` (seções 0, 1, 2.4, 3, 5, 7.1–7.5, 8,
9, 10, 11, 12, nova 13), `docs/sessoes/TEMPLATE.md` (criado antes), `CLAUDE.md`.

## 3. O que foi verificado — e como

- **Cluster Atlas.** Conexão testada com o driver `mongodb@6.21.0`: MongoDB 8.0.30, base
  `bilds-bim-3d`, coleção `catalog` com 0 documentos, IP da máquina liberado.
- **Compressão da geometria.** O feasibility mediu 4 geometrias reais da Dancor (85.866
  vértices, 136.687 triângulos): JSON cru 12,45 MB · JSON gzip 2,21 MB · binário cru
  2,93 MB · binário gzip 1,25 MB.
- **Divergência Python × Node.** Para o mesmo array, Python emite `[-0.0,0.0,1e-05,1e+21]`
  e Node emite `[0,0,0.00001,1e+21]`.
- **Comandos do M0.** `dbStats` e `collStats` respondem; `serverStatus` e `hostInfo`
  retornam AtlasError; `dbStats` não devolve `fsUsedSize`.
- **Deps dos componentes `b-bim-3d`.** Levantadas arquivo a arquivo: cinco importam
  `react-i18next`; só `three` e `OrbitControls` são dependências de verdade.
- **Chromium.** O `thumbs.mjs` já sobe com `--use-gl=angle --use-angle=swiftshader
  --enable-unsafe-swiftshader` — WebGL por software, o que faz o passo rodar sem GPU.

## 4. Decisões tomadas

**ADR-001 — onde mora cada dado** (seção 9 do plano). Fechada pelo dono. Rejeitou
geometria em `BinData` no Mongo, e com ela o codec binário e o portão de volumetria.

**A questão do parse é portabilidade, não linguagem** (7.3). Python nunca foi a objeção;
o critério é rodar na AWS como ela é lá, sem depender de liberdade que só a máquina local
tem. A decisão saiu da linguagem para a **fronteira de execução**, e S2.1/S2.2 viraram
dois spikes comparativos: worker Python isolado × port TypeScript numa biblioteca.

**Miniaturas ganharam sessão própria (S2.4)**, ocupando a sessão que o ADR-001 liberou.
Mede dois caminhos: Chromium+SwiftShader e um rasterizador TS sem browser.

**Quinta pergunta da POC:** escala em produção, projetada em S1.2.

## 5. O que NÃO foi feito, e por quê

**Três achados recusados pelo dono** — não re-levantar sem fato novo:

- **Cortar S3.1/S3.2** (login e cadastro de empresa). O product-lens argumentou que ~18%
  das sessões não servem a nenhuma das perguntas. Recusado: o fluxo do dono da empresa é
  o produto que a POC existe para demonstrar.
- **Senha própria para o usuário semente.** Recusado: cluster free descartável.
- **Restringir o grant do Atlas agora.** Adiado, não recusado — virou pendência 1 da
  seção 12, porque depende de ação no console, fora do repositório.

**A passagem cross-model não rodou.** `codex`, `gemini` e `cursor-agent` não estão
instalados. Nenhum achado tem corroboração de outro modelo; as concordâncias registradas
são entre contextos independentes do mesmo modelo.

**Três lentes morreram no meio** (coherence, feasibility, adversarial) com HTTP 429 —
limite de gastos da conta, não falha do trabalho. Redisparadas após o reset e concluídas.

## 6. Surpresas — onde a documentação estava errada

- **A premissa central do plano estava errada, e era minha.** O plano afirmava que os
  348,2 MB contra o teto de 512 MB tornavam o binário "um requisito, não uma otimização".
  Falso: o M0 cobra armazenamento **já comprimido** pelo WiredTiger, e o JSON comprimido
  sai menor que o binário cru. Registrado na seção 3.4 para ninguém refazer a conta.
- **`~12 bytes por float` em JSON estava errado** — o real medido é ~19–20, porque o
  pipeline serializa doubles sem arredondar. Corrigido, com o ganho separado por tipo.
- **"onze sessões"** contradizia as tabelas. Corrigido para treze (S-rev + S2.4).
- **`5.690 linhas no wizard`** era soma errada — o correto é 5.269. Corrigido.
- **A lista de componentes `b-bim-3d`** omitia justamente o `BimViewer.tsx`. Corrigido.
- **Duas instruções do plano se contradiziam:** a seção 1 excluía i18n e a seção 5 mandava
  reaproveitar componentes que importam `react-i18next`. Corrigido nas duas pontas.

## 7. Onde a próxima sessão começa

**Próxima: S0 — scaffold da POC.** Antes de começar:

- Leia o plano **inteiro**. Ele mudou muito hoje: seções 3, 7.1–7.5 e a Fase 2 foram
  reescritas, e há uma seção 13 nova.
- **Não reintroduza o codec binário nem o portão de volumetria.** Se encontrar referência
  a eles em algum lugar do repositório, é resíduo — corrija (ver 3.4).
- `www/.env` já existe com as credenciais do Atlas, `chmod 600`, fora do git. Não recrie.
- `www/` já está no `.vercelignore`.
- `output/` está **vazia**. S1.2 e S2.2 precisam do oráculo do pipeline Python: rode
  `python3 scripts/build.py --all` antes (leva alguns minutos).

**Armadilhas concretas encontradas hoje:** blocos de citação em markdown partem tabelas
ao meio — se inserir uma nota no meio de uma tabela do plano, a tabela quebra. E o
`ce-doc-review` classifica quase tudo como `gated_auto`; espere poucos `safe_auto`.

## 8. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| Plano | 19 achados fechados, ADR-001 registrado | `grep -c "ADR-001" docs/plano-produto-dinamico.md` |
| Sessões | treze, de S-rev a S4.2 | tabela da seção 11 |
| ADRs fechados | 1 | seção 9 |
| Pendências abertas | 3 | seção 12 |
| `www/` | só o `.env`, nenhum código | `find www -type f` |
| Atlas | base `bilds-bim-3d`, coleção `catalog` vazia | ver o one-liner da seção 0 |
| `output/` | vazia, só a landing | `find output -type f` |
