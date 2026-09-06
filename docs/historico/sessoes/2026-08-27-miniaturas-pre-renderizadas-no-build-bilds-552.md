# 2026-08-27 — Miniaturas pré-renderizadas no build (BILDS-552)

**Data:** 2026-08-27 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**O gatilho.** Lighthouse em `bilds.com/dancor/bombas-incendio` mostrou LCP de 39,9 s com
score 0. O elemento LCP é o `<img src="data:image/jpeg;base64,…">` do card — a miniatura
que o próprio browser gera. Decomposição: 259 ms de TTFB e **7.230 ms de element render
delay**. Ou seja, 96,5% do LCP é esperar o browser baixar geometria e rodar WebGL.

**O que a medição mostrou, além do LCP:**

- **Zero compressão nos `geo/*.json`.** `transfer 1.765 KB / resource 1.763 KB` — razão
  1,00×. A API serve cru. No ZIP o deflate dá 5,8×, então há um ganho grande parado ali.
- **3,75 MB para desenhar 2 miniaturas** em viewport mobile; 57% das 6.610 KiB da página.
- As geometrias carregam **em série** — a fila de render é um `while` sequencial.

**O que foi construído.** `build_thumbs()` em `build.py`, dirigindo
`scripts/thumbs.mjs` (Node + Playwright), que abre `templates/thumbs/harness.html` no
Chromium e chama `window.renderThumb()` por geometria. Saída em
`output/thumbs/<origem>/<slug>/*.webp`, empacotada em `thumbs/` no ZIP, com o campo
`produto.thumb` anotado no `catalog.json`.

**Por que browser e não rasterizador em Python.** O pedido era usar *a imagem que a página
gera*, não uma aproximação. `MeshStandardMaterial` é PBR com metalness/roughness sobre três
luzes; reproduzir isso em numpy daria algo parecido e diferente. Dirigir o mesmo Three.js
no Chromium dá a imagem idêntica — ao custo de uma dependência de browser, que foi isolada
num `package.json` próprio e degrada em silêncio quando ausente.

**Decisões que valem lembrar:**

- **Uma miniatura por geometria, não por produto.** A câmera sai só do bounding box, então
  geometria compartilhada produz imagem idêntica. Amanco: 856 produtos → 448 arquivos.
- **`pixelRatio` fixo em 1** no harness, com `setSize(448, 324)`. No runtime é
  `min(devicePixelRatio, 1.5)` porque lá o alvo é a tela do visitante; aqui o alvo é um
  arquivo de dimensão previsível.
- **Fundo `#F3F4F6` opaco**, igual ao `setClearColor` do viewer e ao `bg-gray-100` do card.
  É o que permite letterbox invisível quando o card é mais largo que a proporção da imagem.
- **Tudo opcional.** Sem Node, sem Playwright, sem browser ou com `--skip-thumbs`, o build
  avisa e segue. Produto sem `thumb` cai no render dinâmico. Catálogo publicado antes disso
  continua funcionando sem re-upload. *(Revisto na S7.6, 2026-09-03: agora o build FALHA
  sem miniaturas; `--allow-no-thumbs` restaura o comportamento descrito aqui — ver
  "Dependências e degradação".)*

**Armadilhas pagas:**

- O Chromium headless não inicializa WebGL sem
  `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`. Não há GPU em
  WSL, CI nem container; sem os flags o `renderThumb` falha em todas as geometrias.
- **Dois Node na mesma máquina.** `/usr/bin/node` é v18 aqui e o nvm tem v24; o nvm só
  entra no PATH de shell interativo, então o `subprocess` do `build.py` pegava o v18 e o
  Playwright recusava. Daí o `_find_node()`.
- **Libs de sistema sem sudo.** `apt-get download` + `dpkg-deb -x` + `LD_LIBRARY_PATH`
  resolve sem root — foi como esta sessão validou. Receita no `README.md`.
- **`sudo` descarta o PATH e derruba o `install-deps`.** `sudo npx playwright
  install-deps chromium` — o comando que a própria documentação do Playwright manda —
  falha em máquina com nvm: o `secure_path` do sudo faz o `npx` cair no Node do apt e o
  Playwright recusa por versão. O sintoma engana, porque `node --version` e `nvm default`
  no shell mostram a versão nova. Use `sudo apt-get install -y libnss3 libnspr4
  libasound2t64`, ou `sudo env "PATH=$PATH" npx playwright install-deps chromium`.

**Validado nos 9 catálogos — 622 geometrias, zero falhas:**

| Catálogo | Geometrias | geo | thumbs | Razão |
|---|---|---|---|---|
| `pvc-esgoto-sn-sr-e-silentium` | 457 | 145,0 MB | 1.858 KB | 80× |
| `cftv` | 55 | 54,3 MB | 222 KB | 251× |
| `sdai-fiacao` | 25 | 29,2 MB | 111 KB | 270× |
| `sensor-alarme` | 16 | 16,6 MB | 61 KB | 281× |
| `equipamento-de-rede-rack` | 17 | 17,0 MB | 68 KB | 256× |
| `ppci-incendio` | 11 | 15,3 MB | 48 KB | 328× |
| `cont-acesso-cond` | 10 | 19,9 MB | 46 KB | 442× |
| `bombas-incendio` | 13 | 44,7 MB | 74 KB | **620×** |
| `dispositivos-eletricos-inteligentes` | 18 | 6,3 MB | 70 KB | 92× |
| **TOTAL** | **622** | **348,2 MB** | **2,5 MB** | **136×** |

Média de **4 KB por miniatura**. Render a ~0,08 s por geometria depois do browser subir
(os 457 do Amanco em 36 s).

O que isso faz com a primeira viewport da Dancor, que era o pior caso: **3,75 MB → 12 KB**
em mobile (2 cards) e **40 MB → ~72 KB** em desktop (12 cards).

**Dependência do outro lado.** `thumbs/` e `produto.thumb` nasceram como extensão
proposta: a API do bilds.com ainda não extraía a pasta. O trabalho correspondente ficou
na branch `perf/BILDS-552-bim-3d-miniatura-estatica` do bilds.com — hoje mergeada
(PR #1244, ver "Dependência cruzada com o bilds.com" no topo deste arquivo).

**O estudo que motivou tudo isso está resumido abaixo — não é preciso abrir nada fora
deste repositório.** Ele foi medido sobre `output/preview/` desta própria árvore.

Custo da **primeira viewport** (grid de ~4 colunas, ~12 cards antes de rolar), antes das
miniaturas, quando cada card baixava o JSON de geometria e rodava WebGL + `toDataURL`:

| Catálogo | Produtos | Geometrias na 1ª viewport | Cru | ~gzip |
|---|---|---|---|---|
| `bombas-incendio` (Dancor) | 13 | 12 | **40,4 MB** | ~7,0 MB |
| `cftv` | 60 | 11 | 10,9 MB | ~1,9 MB |
| `sdai-fiacao` | 51 | 7 | 9,9 MB | ~1,7 MB |
| `dispositivos-eletricos-inteligentes` | 32 | 8 | 3,2 MB | ~0,6 MB |
| `pvc-esgoto-sn-sr-e-silentium` | 856 | 12 | 2,7 MB | ~0,5 MB |

Peso por geometria: de **324 KB** de média (Amanco) a **3,5 MB** (Dancor); maior arquivo
4,8 MB. Razão de compressão medida no ZIP: **5,8×**.

Dois achados do estudo que continuam valendo:

- **Contextos WebGL simultâneos eram 3, não 2.** O `sharedRenderer` é um contexto
  persistente de módulo e costuma não ser contado; somam-se a ele o viewer do card ativo
  (montado no `onMouseEnter`) e o do modal. Remover o viewer do card leva a 2.
- **As geometrias são gravadas cruas no S3**, sem `ContentEncoding: 'gzip'`. Se há
  compressão, ela vem da opção "Compress objects automatically" do CloudFront — o que não
  dá para verificar por nenhum repositório. No pior caso é a diferença entre 40 MB e 7 MB.
  Confirmar no console AWS.
