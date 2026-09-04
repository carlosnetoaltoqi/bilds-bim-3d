# S0 — Scaffold da POC

**Data:** 2026-08-29 · **Sessão do plano:** S0 · **Status:** concluída
**Commits:** `08e9037`

---

## 1. O que era para fazer

Criar `www/` com workspace pnpm, `apps/api` (NestJS) e `apps/web` (Next.js) mínimos,
lendo o `www/.env` que já existe.

Pronto quando: `GET /health` responde mostrando a versão do Mongo lida do Atlas, **e a
página inicial do `apps/web` carrega no navegador**.

## 2. O que foi feito

Estrutura criada em `www/`:

```
www/
├── package.json               workspace root (scripts dev:api, dev:web)
├── pnpm-workspace.yaml        declara apps/*; allowBuilds: @nestjs/core: true
├── pnpm-lock.yaml
└── apps/
    ├── api/
    │   ├── package.json       NestJS 10, mongodb, dotenv, ts-node
    │   ├── tsconfig.json      emitDecoratorMetadata, commonjs, ES2021
    │   └── src/
    │       ├── main.ts        bootstrap; carrega www/.env via dotenv antes do NestJS
    │       ├── app.module.ts  AppModule registra HealthController
    │       └── health/
    │           └── health.controller.ts  GET /health → Atlas buildInfo.version
    └── web/
        ├── package.json       Next.js 15, react 19
        ├── next.config.ts
        ├── tsconfig.json      App Router (bundler moduleResolution)
        ├── next-env.d.ts      gerado pelo next build
        └── src/app/
            ├── layout.tsx     RootLayout + metadado de título
            └── page.tsx       landing mínima
```

`.gitignore` atualizado: `.next/` e `www/**/dist/`.

## 3. O que foi verificado — e como

```bash
# API — subida do workspace root:
cd /home/foltz/bilds-bim-3d/www
pnpm dev:api
# em outra aba:
curl http://localhost:4000/health
# → {"status":"ok","mongo":"8.0.30"}

# Web — build completo:
cd www/apps/web
npx next build
# → Route (app) / 127 B; 4 static pages; sem erros
```

## 4. Decisões tomadas

**dotenv antes do NestJS:** `main.ts` chama `dotenv.config({ path: resolve(__dirname, '../../../.env') })`
antes de importar `@nestjs/core`. Com ts-node, `__dirname` = `www/apps/api/src`, portanto
`../../../` resolve para `www/`. Se o CWD for `www/apps/api/`, o resultado é o mesmo.

**Script `dev` via `node --require`:** `ts-node --transpile-only` não carrega
`emitDecoratorMetadata` corretamente em Node 24. A forma
`node --require ts-node/register --require reflect-metadata src/main.ts` funciona e é
a que está no `package.json`.

**`allowBuilds: '@nestjs/core': true`** no `pnpm-workspace.yaml`: pnpm 11 exige aprovação
explícita de postinstall scripts; sem isso, `pnpm install` encerra com erro. O pnpm
próprio adicionou a entrada ao YAML — aprovei.

**Next.js 15 + React 19:** versões atuais, App Router por padrão, sem `pages/`.

**NestJS sem `@nestjs/mongoose`:** S0 é scaffold; o driver `mongodb` diretamente resolve o
health check sem adicionar dependência de schema. `@nestjs/mongoose` entra em S1.1 com os
schemas.

## 5. O que NÃO foi feito, e por quê

Nada foi cortado do escopo — S0 é exatamente o que estava definido. Deixa pendente
explicitamente para as próximas sessões:

- `@nestjs/mongoose`, Zod, DTOs — S1.1
- Schemas e `GeometryStore` — S1.1
- Rotas de leitura e upload — S2.3
- Login e empresa — S3.1

## 6. Surpresas — onde a documentação estava errada

Nenhuma discrepância real com o plano. Dois pontos práticos que o plano não antecipava:

- **pnpm 11 exige `allowBuilds` explícito** para `postinstall` scripts. Não é erro — o
  pnpm adicionou a entrada e o install concluiu na segunda tentativa.
- **`ts-node --transpile-only` não funciona bem com decoradores em Node 24:** a flag
  `--transpile-only` pula o compiler e não processa `emitDecoratorMetadata`. A forma com
  `--require ts-node/register` funciona. Registrado aqui para S1.1 não reintroduzir.

## 7. Onde a próxima sessão começa

**Próxima: S1.1 — Schemas e contrato do storage.**

Antes de começar:
1. Ler `CLAUDE.md` da raiz
2. Ler `docs/plano-produto-dinamico.md` inteiro
3. Ler este arquivo (`docs/sessoes/S0-scaffold-poc.md`)
4. Ler `docs/sessoes/S-rev-revisao-do-plano.md` (ADR-001)

Pré-condições:
- `www/` existe com o scaffold commitado (`08e9037`)
- `pnpm install` já rodou; `node_modules/` está em `www/`
- `GET /health` funciona — prove antes de começar: `pnpm dev:api` + `curl localhost:4000/health`

Armadilhas concretas:
- Usar `node --require ts-node/register --require reflect-metadata src/main.ts` (não
  `ts-node --transpile-only`) para que decoradores funcionem.
- `@nestjs/mongoose` vai exigir aprovação de build em `pnpm-workspace.yaml` — acrescente
  `'@nestjs/mongoose': true` ao `allowBuilds` quando instalar.
- Não instalar `mongoose` diretamente sem `@nestjs/mongoose` — o NestJS tem integração
  própria com injeção de dependência que S1.1 vai precisar.

## 8. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| Workspace pnpm | inicializado | `ls www/pnpm-lock.yaml` |
| `apps/api` | NestJS 10 rodando na porta 4000 | `pnpm --filter api dev` → `curl localhost:4000/health` → `{"status":"ok","mongo":"8.0.30"}` |
| `apps/web` | Next.js 15 buildável | `cd www/apps/web && npx next build` → sem erro |
| Atlas | conectado, MongoDB 8.0.30 | output do health endpoint |
| Commit | `08e9037` em `main` | `git log --oneline -1` |
