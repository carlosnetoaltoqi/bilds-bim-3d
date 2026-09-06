# Miniaturas idênticas ao viewer 3D em tempo de execução

**Criado em:** 2026-08-30  
**Contexto:** S4.3 — o rasterizador TS (Approach B, ADR-003) não produz qualidade aceitável  
**Status:** ✅ **RESOLVIDO em 2026-08-30 (S4.4).** Implementado como descrito abaixo.
Ver "6. Como ficou" no fim deste documento para o que mudou em relação ao plano.

---

## 1. O problema

O `thumb-rasterizer.ts` (Abordagem B do ADR-003) é um rasterizador software que tenta
reproduzir o que o Three.js renderiza. Após todos os fixes da S4.3 (SSAA box-average,
correção de projeção), a qualidade ainda não é aceitável porque:

| Aspecto | Rasterizador TS | Three.js (viewer real) |
|---|---|---|
| Sombreamento | Flat (normal por triângulo) | Smooth (Gouraud/Phong — normais interpoladas por vértice) |
| Material | Ambient + key + fill aproximados | MeshStandardMaterial (PBR completo) |
| Anti-aliasing | SSAA box-average em código | Hardware MSAA do WebGL |
| Reflexos/especular | Ausentes | Presentes |
| Fidelidade | Diferente do viewer | **Idêntica ao viewer** |

O usuário avaliou o resultado e confirmou que a diferença é perceptível e inaceitável
para o produto.

---

## 2. A solução correta: Playwright + harness.html no thumb-worker

O pipeline estático (`www/apps/ingestao/pipeline/thumbs.mjs`) já resolve isso: abre `www/apps/ingestao/pipeline/harness.html`
no Chromium via Playwright, renderiza com o mesmo Three.js do viewer e captura a imagem.
O resultado é bit-a-bit idêntico ao que o usuário vê na aplicação.

Para o POC dinâmico (NestJS), o `thumb-worker.ts` deve usar a mesma abordagem.

### 2.1 Arquitetura proposta

```
thumb-worker.ts
  └─ renderThumbPlaywright(geoData: RasterBuffers): Promise<Buffer>
       └─ playwright.chromium.launch({ args: SWIFTSHADER_ARGS })
       └─ page.goto('file://.../harness.html')
       └─ page.evaluate(data => window.renderThumbFromData(data), geoData)
       └─ retorna Buffer WebP
```

O browser pode ser reutilizado entre thumbs dentro do mesmo worker (uma instância por
processo worker), drasticamente reduzindo o overhead de inicialização.

### 2.2 Mudanças necessárias

**`www/apps/ingestao/pipeline/harness.html`** — adicionar função que recebe dados em memória:
```javascript
// Já existe: window.renderThumb(id) — busca geo da API
// Adicionar:
window.renderThumbFromData = async function(geoData) {
  // igual ao renderThumb mas recebe o JSON diretamente, sem fetch
  const buf = buildScene(geoData);        // reutilizar lógica existente
  return renderer.domElement.toDataURL('image/webp', 0.85);
  // ou: capturar via page.screenshot()
};
```

**`www/tools/thumb-rasterizer.ts`** — substituir `renderThumbTs` por
`renderThumbPlaywright`, mantendo a mesma assinatura `(data, width, height) → Buffer`.

**`www/apps/api/src/importacoes/thumb-worker.ts`** — sem mudança na interface;
apenas a função que chama muda.

**`www/package.json`** — adicionar `playwright` e `@playwright/test` às deps do workspace
(já está em `www/package.json` para o pipeline estático — verificar se já está disponível).

### 2.3 Flags SwiftShader (WSL / sem GPU)

```typescript
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--no-sandbox',
];
```

Essas flags já estão em `www/apps/ingestao/pipeline/thumbs.mjs` e são validadas em WSL.

### 2.4 Considerações de performance

| Item | TS rasterizer | Playwright |
|---|---|---|
| Inicialização | ~0ms | ~800–1200ms (uma vez por worker) |
| Render por thumb | ~130–170ms | ~60–100ms (WebGL vs software) |
| Memória | ~50 MB | ~150–250 MB (Chromium) |
| Paralelismo | N workers × 1 thread cada | N workers × 1 browser cada |

Para o POC (fire-and-forget, thumbs em background), o overhead de inicialização é
amortizado sobre o lote de thumbs de um import. Aceitável.

---

## 3. Riscos e armadilhas

**SwiftShader em produção:** em ambiente sem GPU (container, CI), SwiftShader é lento
mas funcional. Em produção na AWS/GCP, usar instâncias com GPU ou habilitar Mesa LLVM.

**Memória por worker:** com N=4 workers simultâneos, cada um com um browser Chromium,
o uso de memória pode chegar a 1 GB. Ajustar `MAX_THUMB_WORKERS` se necessário.

**Armadilha do `sudo` + nvm:** descrita em `CLAUDE.md` seção "Miniaturas pré-renderizadas".
A mesma armadilha se aplica aqui. Usar `apt-get install -y libnss3 libnspr4 libasound2t64`
em vez de `playwright install-deps` com sudo.

**Path do harness.html:** o worker roda em `apps/api/` mas o harness está em
`www/apps/ingestao/pipeline/harness.html`. O caminho absoluto deve ser resolvido a partir da raiz
do mono-repo, não do CWD da API. Usar `path.resolve(__dirname, '../../../../www/apps/ingestao/pipeline/harness.html')`.

---

## 4. Critério de aceite

A sessão que implementar isso estará concluída quando:

1. Um thumb gerado pelo worker Playwright for visualmente idêntico ao render do viewer
   3D para o mesmo produto (comparar lado a lado no browser).
2. O import de um `.aq` completo (Dancor, 13 produtos) gerar todos os thumbs sem erros.
3. O tempo total de geração for < 30 segundos para 13 produtos.
4. Os thumbs aparecerem corretamente na listagem do catálogo (`LazyBimCard`).


---

## 5. Alternativa considerada e descartada: alinhar a versão do Three.js

O harness carrega o Three.js vendorizado em `templates/vendor/three.module.js` (**r170**),
enquanto o viewer do POC usa o do `node_modules` do app web (**r185**). A dúvida legítima
era se o thumb deveria carregar o r185 para ser fiel ao viewer.

Medido: mesma geometria, mesmo `buildScene()`, mesma câmera, 448×324, r170 × r185.

| Geometria | PSNR r170 × r185 | MSE |
|---|---|---|
| 20cv-2-1-2-t-4v-inc-flg-ir3 | 70,7 dB | 0,01 |
| 2cv-t-220-380v-inc-flg-ir3 | 71,8 dB | 0,00 |
| 4cv-2-1-2-t-4v-inc-ir3 | 72,0 dB | 0,00 |

Diferença de arredondamento de 1/255 em poucos pixels — imperceptível. **Não vale um
alias de servidor nem uma segunda cópia do Three.js no caminho de render**, que
introduziriam exatamente o tipo de divergência que o harness existe para evitar. O
harness continua servindo o vendor do repo, um único caminho para os dois pipelines.

---

## 6. Como ficou

Implementado em `www/tools/thumb-rasterizer.ts` (o arquivo trocou de implementação, não
de nome — `renderThumbTs` continua exportado com a mesma assinatura). O rasterizador
software antigo virou `www/tools/thumb-rasterizer-sw.ts`, usado só por `measure-thumbs.ts`.

**Diferenças em relação ao plano da seção 2:**

| Planejado | Como ficou | Por quê |
|---|---|---|
| `page.goto('file://.../harness.html')` | servidor HTTP efêmero (`listen(0)`) sobre a raiz do repo | o harness importa o Three.js como módulo ES; o Chromium recusa `import` sobre `file://` por CORS. É o mesmo servidor que o `thumbs.mjs` já subia. |
| `page.evaluate(d => …, geoData)` | `page.evaluate(j => …(JSON.parse(j)), JSON.stringify(geoData))` | **6× de diferença** — ver abaixo |
| `playwright` nas deps de `www/` | resolvido de `bilds-bim-3d/node_modules/` | o `package.json` da raiz já isola o Playwright para o pipeline estático; duplicar a dependência no workspace pnpm não traria nada |

### A armadilha que dominava o tempo: como o argumento chega ao `page.evaluate`

Passar o objeto de geometria direto como argumento faz o serializador do Playwright
andar o grafo inteiro — e a geometria é um array de centenas de milhares de números.
Medido com uma peça Dancor de 4,8 MB (35 k vértices, 52 k triângulos):

| Forma | Tempo |
|---|---|
| argumento como **objeto** | ~2 200 ms |
| argumento como **string JSON**, `JSON.parse` dentro da página | ~370 ms (dos quais ~120 ms são o render WebGL) |

O `JSON.stringify` do lado do Node custa ~40 ms e o `JSON.parse` do lado da página ~13 ms.
No lote de 13 produtos da Dancor isso é a diferença entre **24,5 s e 6,2 s** — ou seja,
entre estourar e cumprir com folga o critério de aceite nº 3.

`window.renderThumbFromData` continua recebendo o objeto, como especificado; quem faz o
`JSON.parse` é o callback do `evaluate`, dentro da página.

### Fechar a sessão é obrigatório

O browser e o servidor HTTP são um singleton por processo (`getSession()`). Quem usa o
módulo **precisa** chamar `closeThumbRenderer()` antes de `process.exit()`: sem isso o
handle do servidor prende o event loop e o Chromium pode ficar órfão. O `thumb-worker.ts`
faz isso num `finally`, antes do `process.send({type:'done'}, () => process.exit(0))`.

---

## 7. Resultado medido

| Critério de aceite | Resultado |
|---|---|
| 1. Visualmente idêntico ao viewer | **PSNR 47 dB** contra o render do viewer (r185, mesma câmera) — a diferença que sobra é só a compressão WebP q=0,85. O rasterizador software antigo dava **27 dB**. |
| 2. Import Dancor (13 produtos) sem erros | 13/13, `thumbKey` gravado nos 13 documentos |
| 3. < 30 s para 13 produtos | **~6,3 s** no worker real (primeira thumb 1,2 s por causa da subida do Chromium; as demais 220–470 ms) |
| 4. Thumbs no catálogo (`LazyBimCard`) | 13/13 cards com `<img src="http://localhost:4000/thumbs/…">`, nenhum caiu no render dinâmico |

Memória: um Chromium por worker, ~200 MB. Com `MAX_THUMB_WORKERS` > 1 isso multiplica —
o alerta da seção 3 continua valendo.
