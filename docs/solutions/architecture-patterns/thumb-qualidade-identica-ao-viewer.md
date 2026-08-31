# Problema em aberto: miniaturas idênticas ao viewer 3D em tempo de execução

**Criado em:** 2026-08-30  
**Contexto:** S4.3 — o rasterizador TS (Approach B, ADR-003) não produz qualidade aceitável  
**Status:** EM ABERTO — próxima sessão deve implementar a solução

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

O pipeline estático (`scripts/thumbs.mjs`) já resolve isso: abre `templates/thumbs/harness.html`
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

**`templates/thumbs/harness.html`** — adicionar função que recebe dados em memória:
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

Essas flags já estão em `scripts/thumbs.mjs` e são validadas em WSL.

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
`templates/thumbs/harness.html`. O caminho absoluto deve ser resolvido a partir da raiz
do mono-repo, não do CWD da API. Usar `path.resolve(__dirname, '../../../../templates/thumbs/harness.html')`.

---

## 4. Critério de aceite

A sessão que implementar isso estará concluída quando:

1. Um thumb gerado pelo worker Playwright for visualmente idêntico ao render do viewer
   3D para o mesmo produto (comparar lado a lado no browser).
2. O import de um `.aq` completo (Dancor, 13 produtos) gerar todos os thumbs sem erros.
3. O tempo total de geração for < 30 segundos para 13 produtos.
4. Os thumbs aparecerem corretamente na listagem do catálogo (`LazyBimCard`).
