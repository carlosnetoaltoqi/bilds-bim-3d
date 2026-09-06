# Serviços web — armadilhas de NestJS, build e ambiente

Lições genéricas de rodar serviços HTTP (NestJS/Express, TypeScript, Mongo) por trás deste
pipeline — não específicas de um formato de arquivo, mas repetidas o bastante entre serviços para
valer registrar uma vez só.

## `@Post` responde 201 — download precisa de `res.status(200)` explícito

Um handler `@Post()` do Nest responde `201 Created` por padrão, mesmo quando o corpo da resposta
é um arquivo para download, não um recurso criado. Um cliente que confere `resposta.status ===
200` antes de processar o arquivo falha **em silêncio** — nem sempre existe um teste que capture
isso, porque o corpo da resposta pode estar perfeitamente correto; só o código HTTP está errado
para a semântica esperada.

```typescript
// download.ts — todo endpoint que serve um arquivo gerado precisa disto
export async function enviarArquivo(res: Response, caminho: string, opts: {...}): Promise<void> {
  res.status(200);   // explícito — sem isto o @Post() do controller responde 201
  res.setHeader('Content-Type', opts.contentType);
  ...
}
```

## `ValidationPipe` global com `forbidNonWhitelisted` e um DTO por corpo

O `ValidationPipe` instalado em cada serviço usa `whitelist: true` e `forbidNonWhitelisted: true`:
um campo que chega no corpo da requisição mas não está declarado no DTO correspondente é
**rejeitado com 400**, não descartado silenciosamente. A escolha deliberada é rejeitar alto — um
cliente que manda um campo a mais (nome digitado errado, campo de uma versão antiga da API)
descobre na hora, em vez de o valor simplesmente desaparecer sem aviso.

```typescript
export const opcoesValidacao: ValidationPipeOptions = {
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
  forbidUnknownValues: false,   // `true` rejeitaria objetos livres legítimos, como specs
  stopAtFirstError: false,
};
```

**Arrays gigantes ficam fora do pipe, de propósito.** Um corpo com `pos`/`col`/`idx` de uma
geometria tem centenas de milhares de números; passar isso pelo `class-validator` (que decora e
valida cada elemento) é caro sem necessidade. Esses campos são tipados como `unknown`/`Record` —
o Nest pula a validação decorativa para eles — e uma função de validação dedicada roda um loop
simples sobre o array cru.

## `nomeOriginalUtf8` — o multer decodifica multipart como latin1

O multer embutido numa versão específica do `@nestjs/platform-express` decodifica o `filename` do
multipart como **latin1**, e não conhece a opção de trocar o charset. Um nome de arquivo com
acento chega corrompido (`gás.aq` vira `gÃ¡s.aq`) em todo lugar que usa `originalname` direto: log,
nome do import, nome de produto derivado de arquivo.

A correção é refazer a decodificação: pegar os bytes que o latin1 gerou e reinterpretá-los como
UTF-8 — com uma guarda de ida e volta, para não corromper um nome que por algum motivo já tenha
chegado certo:

```typescript
export function nomeOriginalUtf8(originalname: string | undefined, padrao: string): string {
  if (!originalname) return padrao;
  const bytes = Buffer.from(originalname, 'latin1');
  const utf8 = bytes.toString('utf8');
  return Buffer.from(utf8, 'utf8').equals(bytes) ? utf8 : originalname;
}
```

Todo lugar que usa `originalname` do multer direto, sem passar por essa função, reintroduz o bug.

## Ajv padrão não aceita `$schema` 2020-12 — precisa de `Ajv2020`

Contratos JSON Schema escritos no draft 2020-12 (`$schema:
"https://json-schema.org/draft/2020-12/schema"`) são recusados pelo Ajv importado do jeito
comum — o construtor padrão só conhece draft-07. A importação certa é a build dedicada:

```typescript
import Ajv2020 from 'ajv/dist/2020';
const ajv = new Ajv2020({ allErrors: false, strict: false });
```

Isso escapou de testes de paridade por um bom tempo porque nenhum harness de teste passava pelo
validador de contrato — só um smoke real, exercitando o caminho de verdade entre dois serviços,
pegou o erro. A lição prática: um teste que constrói o objeto esperado à mão e compara nunca
exercita a validação do schema; só um teste que passa pelo validador de verdade acusa esse tipo de
incompatibilidade de draft.

## `tsc -b` incremental: `tsBuildInfoFile` precisa estar em `dist/`

Com `"incremental": true` mas sem `tsBuildInfoFile` explícito, o TypeScript grava o cache
incremental **ao lado do `tsconfig.json`**, não dentro de `dist/`. Um `rm -rf dist` para forçar
rebuild completo não funciona: o cache sobrevive fora da pasta apagada, e o `tsc` acha que nada
mudou. A correção é forçar o caminho:

```json
{ "compilerOptions": { "incremental": true, "tsBuildInfoFile": "dist/tsconfig.tsbuildinfo" } }
```

## Pacote de workspace como fonte crua não é emitido em `dist/` — precisa de project references

Um pacote interno do monorepo (`@escopo/base`, `@escopo/dominio`) importado por caminho de
workspace aponta para o **TypeScript fonte** em desenvolvimento (via symlink do gerenciador de
pacotes), não para um `dist/` compilado. Rodar a partir do `dist/` de um serviço
(`node dist/main.js`, não `ts-node`) quebra: o Node não sabe interpretar `.ts`, e o pacote
importado nunca foi compilado para aquele serviço levar consigo.

A correção é **project references**: cada pacote de workspace ganha `"composite": true` no seu
próprio `tsconfig.json`, e cada consumidor declara `"references": [{ "path": "../../pacotes/base"
}, ...]`. Com isso, `tsc -b` (build mode) compila as dependências primeiro e na ordem certa, e o
`dist/` de cada serviço passa a ter, junto do seu próprio código, os `.d.ts`/`.js` dos pacotes
internos de que depende.

## `next build` com `next dev` de pé derruba o dev server

Rodar um build de produção (`next build`, ou um `build` de monorepo que o inclua) enquanto o
servidor de desenvolvimento (`next dev`) ainda está no ar sobrescreve o `.next/` que o dev server
está servindo. O sintoma é toda página do app respondendo 500 com um `Cannot find module
'./<número>.js'` do webpack-runtime — um chunk que o dev server tinha em memória e que o build
novo removeu ou renumerou. A correção é reiniciar o dev server depois do build; para conferir
tipos sem esse risco, `tsc --noEmit` isolado não toca o `.next/`.

## `pgrep -f` casa com o próprio shell

`pgrep -f '<padrão>'` (e `pkill -f`) casam contra a **linha de comando inteira** de cada processo,
inclusive a do shell usado para lançar o alvo. Um gerenciador de scripts que executa
`sh -c 'node src/main.ts'` faz o padrão `src/main.ts` aparecer também na linha de comando do
próprio `sh` — `pgrep -f 'src/main.ts' | head -1` frequentemente pega esse `sh`, não o `node`
filho dele. Um `pkill -f` nessas condições pode matar o terminal errado (o próprio, inclusive).
Mais confiável: achar o processo que de fato escuta a porta (`ss -ltnp | grep ':<porta> '`) e, se
precisar do pai também, `ps -o ppid= -p <pid>`.

## ts-node sem watch

Um serviço rodado via `ts-node` (não `tsc -b` + `node dist/`) não recompila sozinho quando o
código muda — sem um wrapper de watch explícito, o processo continua servindo a versão que
carregou no start. Reiniciar manualmente depois de qualquer mudança é o comportamento esperado
desse modo, não um bug.

## Atlas whitelist — a assinatura é `SSL alert number 80`

Um IP não liberado no Network Access de um cluster Atlas (ou um cluster pausado) não produz um
erro de autenticação — o handshake TLS morre **antes** de qualquer credencial ser trocada. A
assinatura no log é `tlsv1 alert internal error` / `SSL alert number 80` nos três nós do replica
set, com a conexão TCP abrindo normalmente. Isso é fácil de confundir com problema de usuário/senha
porque a mensagem de log do driver, no caminho de retry, tende a citar autenticação — mas a
diagnose correta é medir camada por camada: DNS resolve, TCP abre, TLS morre. Liberar o IP resolve
sem mexer em credencial nenhuma; o serviço reconecta sozinho no próximo retry, sem reiniciar.

## Mongo fora do ar → 503 por guard, não 500 depois de esperar

Em vez de deixar cada rota tentar falar com um Mongo indisponível e responder 500 só depois de um
timeout longo, um guard checa o `readyState` da conexão **antes** de a rota rodar e responde
`503` na hora, com uma mensagem dizendo que o serviço está em modo de espera/retry. `GET /health`
expõe esse `readyState` diretamente, para diagnóstico rápido sem precisar disparar uma rota de
negócio só para descobrir se o banco está acessível.

## `git clean -fdq` apaga o que ainda não está no `.gitignore`

`git clean -fdq` remove todo arquivo não rastreado que o `.gitignore` **atual** não cobre — se um
diretório de dados foi movido para um novo lugar (por um script de migração, por exemplo) mas o
`.gitignore` ainda aponta para o caminho antigo, o diretório novo fica sem proteção nenhuma e é
apagado junto com o lixo que o comando pretendia limpar. A ordem correta é: mover dados só depois
de o `.gitignore` já cobrir o destino novo, e conferir `git status`/`git clean -ndq` (dry-run)
antes de rodar a versão que de fato apaga.

## `git mv` de diretório para destino existente move para dentro

`git mv origem/ destino/` quando `destino/` **já existe** não funde nem substitui — move `origem/`
para dentro de `destino/`, resultando em `destino/origem/` em vez do `destino/` esperado. Uma
rodada anterior de um script de reorganização que deixou o destino já criado (com `node_modules`
dentro, por exemplo) faz a rodada seguinte empilhar um diretório dentro do outro sem erro nenhum
— o comando "funciona", só que não do jeito pretendido. Limpar (ou renomear) o destino antes de
repetir a operação evita o aninhamento.

## Onde está no código

- `pacotes/base/src/download.ts` — `enviarArquivo()`, o `res.status(200)` explícito.
- `pacotes/base/src/validacao.ts` — `opcoesValidacao`, `criarValidationPipe()`, os limites de
  corpo (`LIMITES`).
- `pacotes/base/src/upload.ts` — `nomeOriginalUtf8()`, `armazenamentoTemporario()`.
- `pacotes/base/src/contratos.ts` — `Ajv2020`, `validarContrato`.
- `pacotes/dominio/src/mongo-pronto.guard.ts` — o guard de `readyState` por trás do 503.
- `*/tsconfig.json` de cada pacote/serviço — `tsBuildInfoFile`, `composite`, `references`.

## Ver também

- `docs/conhecimento/processos-filhos.md` — o outro lado do mesmo serviço: como ele chama e
  vigia os processos filhos que fazem o trabalho pesado.
- `docs/conhecimento/diagnostico.md`, seção "Serviços e ferramentas".
