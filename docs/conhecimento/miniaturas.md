# Miniaturas — render pré-gerado idêntico ao viewer

Uma miniatura WebP por geometria, renderizada uma vez no build/import e servida como arquivo
estático. Existe porque o caminho óbvio — cada card baixa o JSON de geometria e roda WebGL no
browser do visitante — mede **7.230 ms de _element render delay_** e um LCP de **39,9 s** numa
página real de catálogo: o elemento LCP é a própria miniatura, e o cache do viewer é um `Map` em
memória que morre no reload.

## Não reimplementar o render

A tentação, ao mover o render para o build (ou para um worker Node), é reimplementá-lo em
software — rasterizar sem abrir um browser. Medido contra o mesmo Three.js do viewer real, num
Chromium headless:

| Caminho | PSNR contra o viewer |
|---|---|
| Rasterizador próprio (software) | **27 dB** — silhueta chapada, sem o relevo do PBR |
| Chromium headless com o Three.js real | **47 dB** |

**47 dB é o piso, não uma meta a bater**: é a perda que a própria compressão WebP q=0,85 já
impõe — dois renders idênticos por construção, comparados depois de salvos em WebP, não passam
disso. Não existe "melhorar o rasterizador" que chegue lá, porque a diferença de 27 → 47 dB não é
de otimização, é de categoria: `MeshStandardMaterial` é PBR com metalness/roughness sobre três
luzes, sombreamento por vértice interpolado (Gouraud/Phong) e anti-aliasing de hardware. Qualquer
reimplementação dá uma imagem **parecida**, e o catálogo passa a exibir dois visuais conforme o
produto tenha ou não miniatura pronta — exatamente o defeito que a miniatura pré-gerada existe
para eliminar.

A solução é abrir o próprio template num Chromium headless via Playwright e deixar o Three.js de
verdade desenhar.

## A mesma `buildScene`, em cópias que precisam andar juntas

O harness (`biblioteca/bim_pipeline/miniaturas/harness.html`) não importa o Three.js do viewer em
tempo de execução — ele tem uma **cópia literal** de `buildScene()`, da câmera, do material e das
luzes. É essa cópia, não um import compartilhado, que garante que a miniatura pré-gerada seja bit
a bit a imagem que o viewer produziria:

```javascript
function buildScene(data) {
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3))
  const hasCol = data.col && data.col.length > 0
  if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3))
  if (data.idx) geom.setIndex(data.idx)
  geom.computeVertexNormals()
  // ... material MeshStandardMaterial({ vertexColors: hasCol, metalness: 0.25, roughness: 0.55 })
  // ... AmbientLight + duas DirectionalLight fixas
}
// câmera: PerspectiveCamera(38, W/H, 0.001, 500); posição derivada só do bounding box
```

Isso significa que existem hoje **três lugares com a mesma função**, e mexer num sem mexer nos
outros divide o catálogo em dois visuais:

| Lugar | Papel |
|---|---|
| `harness.html` (miniaturas) | gera o arquivo estático |
| motor do viewer 3D de produção (modal, render dinâmico) | fallback quando não há miniatura, e a visualização interativa |
| viewport do editor de peças | mesma cena, para editar vendo o que o catálogo mostra |

Ao mexer em material, luz ou câmera em qualquer um, o critério de aceite é olhar os outros dois.

## Geometria para `page.evaluate`: string JSON, nunca objeto

O serializador de argumentos do Playwright anda o grafo inteiro do que recebe — e a geometria é
um array de centenas de milhares de números. Medido numa peça real de 4,8 MB (35 mil vértices,
52 mil triângulos):

| Forma do argumento | Tempo por miniatura |
|---|---|
| objeto `{pos, col, idx}` | ~2.200 ms |
| **string JSON**, com `JSON.parse` dentro da página | **~370 ms** (dos quais ~120 ms são o WebGL) |

`JSON.stringify` do lado do Node custa ~40 ms e o `JSON.parse` do lado da página, ~13 ms — o
resto é ganho puro. Num lote de 13 geometrias isso é **24,5 s → 6,2 s**: a diferença entre estourar
e cumprir com folga o orçamento de tempo de um import.

```javascript
const dataUrl = await page.evaluate(
  ([u, w, h, m, q]) => window.renderThumb(u, w, h, m, q),
  [geoUrl, width, height, mime, quality]   // renderThumb busca por URL e delega a renderThumbFromData
)
```

O caminho de build (`thumbs.mjs`) evita o problema de outro jeito: em vez de mandar a geometria
como argumento, sobe um servidor HTTP efêmero e deixa a própria página buscar o JSON por
`fetch` — `window.renderThumb(url, …)` é o wrapper que faz isso e delega para
`window.renderThumbFromData`, a única função que de fato toca WebGL. Quem já tem a geometria em
memória (uma regeneração pontual, por exemplo) é quem enfrenta o custo do `page.evaluate` e por
isso precisa da string.

## O harness precisa de `http://`, nunca de `file://`

O harness importa o Three.js como módulo ES (`<script type="importmap">` + `import * as THREE from
'three'`), e o Chromium recusa `import` sobre `file://` por CORS. `thumbs.mjs` sobe um servidor
HTTP efêmero (`listen(0)` em `127.0.0.1` — porta zero nunca colide com nada) com **três
montagens**:

| Rota | Pasta servida |
|---|---|
| `/harness.html` | o próprio diretório do harness |
| `/vendor/*` | onde está `three.module.js` |
| `/geo/*` | a pasta de geometrias do import |

Duas armadilhas nesse servidor minúsculo:

- **MIME de módulo ES.** O Chromium rejeita um `<script type="module">` com qualquer
  `Content-Type` que não seja `text/javascript`; `.js` e `.mjs` precisam do MIME certo, não do
  genérico `application/octet-stream`.
- **Um `encodeURIComponent` por segmento, não na URL inteira.** Nomes de pasta reais têm espaço e
  vírgula (uma linha de produto guardada como `"PVC Esgoto SN, SR e Silentium"`, por exemplo), e a
  barra que separa os segmentos não pode ser escapada — senão a rota deixa de bater com o
  prefixo montado:

  ```javascript
  const geoUrl = '/geo/' + geo.split(/[\\/]/).map(encodeURIComponent).join('/')
  ```

## SwiftShader — sem GPU em CI, WSL e container

Sem GPU, o Chromium headless não inicializa WebGL de jeito nenhum — nem devolve uma imagem
degradada, falha todas as geometrias de uma vez. Os flags do rasterizador em software são
obrigatórios nessa classe de máquina:

```javascript
chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
```

## Instalação: libs de sistema e a armadilha do `sudo`

Além do Chromium (`playwright install chromium`), o navegador precisa de libs do sistema:

```bash
sudo apt-get install -y libnss3 libnspr4 libasound2t64
```

A documentação do Playwright manda rodar `sudo npx playwright install-deps chromium` — **isso
não funciona em máquina com nvm**. O `sudo` do Ubuntu usa `secure_path` e descarta o PATH do
usuário, então o `npx` resolve `node` para o do `apt` (uma versão velha) e o Playwright recusa
com "requires Node.js 20 or higher" — uma mensagem enganosa, porque `node --version` no mesmo
shell mostra a versão certa. O `apt-get` acima instala exatamente as mesmas libs
(`libnspr4.so`, `libnss3.so`, `libnssutil3.so`, `libasound.so.2`) sem passar por Node nenhum.
Repassar o PATH pelo `sudo` também funciona: `sudo env "PATH=$PATH" npx playwright install-deps
chromium`.

## Dois Node na mesma máquina

Distinta da anterior: é comum a máquina ter o Node do `apt` em `/usr/bin/node` (velho) e um do
nvm (novo) — mas o nvm só entra no PATH de shell **interativo**. Um `subprocess` do Python
lançado fora desse contexto pega o do `apt`, e o Playwright recusa sem indicar que existe um Node
bom instalado. `find_node()` (`biblioteca/bim_pipeline/miniaturas/render.py`) procura, em ordem:
`$BILDS_NODE`, o `node` do PATH e a maior versão em `~/.nvm/versions/node/`.

## O harness resolve `three` e `playwright` do próprio diretório

`biblioteca/bim_pipeline/miniaturas/` tem `package.json` próprio, com `three` e `playwright`
como dependências dele — não da raiz do repositório. `thumbs.mjs` resolve o pacote `three`
instalado ao lado (`createRequire(import.meta.url).resolve('three')`) e toma a pasta que contém
`three.module.js`; como o `exports` do pacote `three` não expõe `build/three.module.js`
diretamente, resolver pelo pacote em vez de montar o caminho à mão é o que sobrevive a upgrades
do pacote. `$BILDS_THREE_DIR` sobrepõe quando é preciso apontar para outro lugar.

## Versão do Three.js entre harness e viewer: não importa

O harness e o viewer de produção podem estar em revisões diferentes do Three.js sem que isso
afete a miniatura. Medido com a mesma geometria, o mesmo `buildScene()` e a mesma câmera, uma
revisão contra a outra:

| Comparação | PSNR | MSE |
|---|---|---|
| revisão antiga × revisão nova do Three.js | 70,7 – 72,0 dB | 0,00 – 0,01 |

Arredondamento de 1/255 em poucos pixels — imperceptível, e **~24 dB acima** do piso de 47 dB
imposto pela compressão WebP. Não vale um alias de servidor nem uma segunda cópia do Three.js só
para alinhar versões: isso reintroduziria exatamente o tipo de divergência que o harness existe
para evitar (uma cena construída por código diferente do que o produto usa).

## Fechar browser e servidor antes de `process.exit`

O Chromium e o servidor HTTP efêmero são reaproveitados sequencialmente entre todas as
miniaturas de um lote (a subida do Chromium custa ~1 s, e amortiza sobre o lote inteiro). Por
isso `thumbs.mjs` fecha os dois num `finally`, **antes** do `process.exit`:

```javascript
} finally {
  await browser.close()
  srv.close()
}
process.exit(falhas || abortado ? 2 : 0)
```

Sem isso o handle do servidor HTTP prende o event loop e o Chromium pode ficar órfão — a mesma
classe de bug que motivou o `--sair-com-stdin`/`sairComStdin` (ver `processos-filhos.md`): o
processo devolve controle ao chamador antes de liberar o que abriu.

## `--sair-com-stdin` / `sairComStdin`

Quem chama `thumbs.mjs` como processo filho de um serviço passa `sairComStdin: true` no JSON de
configuração. O script assina o fechamento do stdin (`process.stdin.on('end'/'close', …)`) e, se
o pai morrer no meio do lote, para de renderizar geometrias que ninguém vai registrar — a
próxima iteração do loop simplesmente não roda, e o processo sai com código 2. Fora de um
serviço (terminal, CI) a flag fica desligada e o lote roda até o fim mesmo com stdin fechado.

## Parâmetros da miniatura

| Item | Valor | Por quê |
|---|---|---|
| Dimensão | 448 × 324 px | 2× o card renderizado, para telas de DPR 2 |
| Formato | WebP, qualidade 0,85 | melhor razão tamanho/qualidade que JPEG no mesmo alvo |
| pixelRatio | fixo em 1 | no runtime é `min(devicePixelRatio, 1.5)` — mas ali o alvo é a tela do visitante; aqui o alvo é um arquivo de dimensão previsível |
| Fundo | opaco, igual ao `setClearColor` do viewer | some o letterbox quando o card é mais largo que a proporção da miniatura (`object-fit: contain`) |

Tamanho típico medido em produção: **~4 KB por miniatura**, contra dezenas a milhares de KB da
geometria de origem — numa biblioteca real de conexões, centenas de MB de geometria viram poucos
MB de miniaturas.

## Uma miniatura por geometria, não por produto

A câmera sai só do bounding box da geometria — produtos que compartilham geometria (variantes que
mudam apenas em dados: orientação, cor de acabamento, dados elétricos) produzem imagem idêntica.
Numa biblioteca real de conexões, 856 produtos → 448 geometrias → 448 miniaturas, não 856. O
nome do arquivo de saída é o mesmo da geometria, com a extensão trocada.

## Degradação: não some em silêncio

Até uma correção anterior, a ausência de Node compatível, de Playwright ou de qualquer falha de
render virava um aviso e o build seguia sem `thumbs/` — o cenário que produz os 39,9 s de LCP.
Hoje `build_thumbs()` (`biblioteca/bim_pipeline/miniaturas/render.py`) lança `ThumbsError`
quando:

- não há Node ≥ 20 no PATH nem em `$BILDS_NODE`;
- Playwright ou o Chromium não estão instalados (a mensagem tenta extrair a lib de sistema
  faltando de dentro do stack trace do Playwright);
- o render inteiro estoura 30 minutos;
- **qualquer** geometria individual falha no render.

Quem chama decide se segue mesmo assim (um flag explícito de "aceitar sem miniaturas"), mas o
padrão é falhar alto. `thumbCount` no manifesto do resultado é o sinal de que algo degradou: um
catálogo com produtos mas `thumbCount: 0` (ou menor que o total de geometrias) diz que as
miniaturas faltam e que quem consome vai cair de volta no render dinâmico no browser — o LCP
lento que este pipeline inteiro existe para evitar.

## Onde está no código

- `biblioteca/bim_pipeline/miniaturas/thumbs.mjs` — o processo Node: servidor HTTP efêmero,
  Chromium, laço de render, `--sair-com-stdin`.
- `biblioteca/bim_pipeline/miniaturas/harness.html` — a cópia de `buildScene()`, câmera,
  material e luzes; `renderThumb` (por URL) e `renderThumbFromData` (objeto em memória).
- `biblioteca/bim_pipeline/miniaturas/render.py` — `build_thumbs()`, `ThumbsError`,
  `find_node()`, `vendor_dir_padrao()`.
- `biblioteca/bim_pipeline/miniaturas/package.json` — dependências (`three`, `playwright`)
  isoladas deste diretório.
- `servicos/criador-de-catalogos/src/miniaturas/miniaturas.service.ts` — quem chama o pipeline a
  partir de um import ou de uma regeneração pontual, e grava `thumbKey`/`thumbErro`.

## Ver também

- `docs/conhecimento/catalogo-modelo.md` — o ponteiro `thumbKey`, quem regenera miniatura e como
  a falha vira `thumbErro` sem derrubar a edição.
- `docs/conhecimento/zip-bilds-formato.md` — o contrato de `thumbs/<nome>.webp` dentro do pacote.
- `docs/skills/pagina-biblioteca/SKILL.md` — o padrão de miniatura estática + click-to-3D do lado
  do viewer que consome este arquivo.
