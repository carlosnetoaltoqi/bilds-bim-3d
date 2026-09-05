# bilds-bim-3d

Gera catálogos BIM com viewer 3D a partir de bibliotecas `.aq` do AltoQi Builder.

**Você só precisa do arquivo `.aq`.** Ele carrega a malha 3D, a cor e a miniatura de cada peça — não é preciso ter os IFCs.

## Início rápido

```bash
git clone https://github.com/carlosnetoaltoqi/bilds-bim-3d.git
cd bilds-bim-3d

bash scripts/bootstrap.sh             # instala o que falta (pip, Three.js, Playwright) e imprime a tabela
bash scripts/bootstrap.sh --check     # só confere: exit 1 se falta algo obrigatório
sudo apt-get install -y libnss3 libnspr4 libasound2t64   # libs do Chromium — o único passo com sudo

# copie as bibliotecas .aq para input/, organizadas por fabricante:
#   input/Dancor/pecas_dancor_bombas.aq
#   input/Amanco/PVC Esgoto SN, SR e Silentium/pecas_amanco.aq

python3 scripts/build.py --all        # gera um ZIP por biblioteca

python3 -m http.server 8080 --directory output/preview
# abrir http://localhost:8080
```

## Os dois modos

### Padrão — só o `.aq`

```bash
python3 scripts/build.py              # uma biblioteca, com perguntas
python3 scripts/build.py --all        # todas as bibliotecas, sem perguntar
```

Forma, cor e dados saem todos do `.aq`. É o caminho normal: mais rápido (85× a 421×), um único arquivo de entrada, e sem o matching por nome que os IFCs exigem.

### Peça que existe só como IFC

O modo `--ifc` — geometria lida dos arquivos `.IFC` da pasta, com matching por nome de arquivo —
foi **removido em 2026-09-05** (I6 da auditoria): ~440 linhas sem fixture nem teste, que só
serviam a dois casos raros. Se uma peça existe como IFC mas não está cadastrada no `.aq`, o build
não a inclui; o caminho é cadastrá-la na biblioteca ou importar o IFC pela POC
(`www/apps/ingestao/pipeline/ifc_to_geo.py`). `www/apps/ingestao/pipeline/parse_ifc.py` continua no repositório para esse conversor.

## Como a saída é organizada

A estrutura de `output/` espelha a de `input/`:

```
input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq
  → output/Amanco/PVC Esgoto SN, SR e Silentium/pvc-esgoto-sn-sr-e-silentium-202608241730.zip

input/Dancor/pecas_dancor_bombas.aq
  → output/Dancor/bombas-incendio-202608241730.zip
```

| Caminho | O que é |
|---|---|
| `output/<origem>/<slug>-<timestamp>.zip` | **o pacote para subir no dashboard.bilds.com** |
| `output/<origem>/<slug>-catalog.json` | catálogo solto, para inspeção |
| `output/geo/<origem>/<slug>/*.json` | geometria por produto |
| `output/thumbs/<origem>/<slug>/*.webp` | miniatura por geometria, embutida no ZIP |
| `output/preview/<slug>/index.html` | preview navegável do catálogo |
| `output/preview/catalogs.json` | índice dos catálogos gerados |

ZIPs, geometria e catálogos soltos são gitignored — sempre regeráveis a partir do `.aq`.

## Opções

```bash
python3 scripts/build.py --all              # todas as bibliotecas de input/
python3 scripts/build.py --all --force      # refaz também as que já têm ZIP
python3 scripts/build.py --input-dir PASTA  # varre outra pasta
python3 scripts/build.py --skip-preview     # só catalog.json e ZIP
python3 scripts/build.py --skip-zip         # só preview
python3 scripts/build.py --skip-thumbs      # nem tenta renderizar as miniaturas
python3 scripts/build.py --allow-no-thumbs  # tenta; se falhar, avisa e segue em vez de parar
```

**Sem miniaturas o build falha** (exit 1) — é o cenário que custa 39,9 s de LCP na página
publicada, e até 2026-09-03 saía como aviso. As duas flags acima são as saídas explícitas;
nos dois casos o `manifest.json` do ZIP registra `thumbCount` para quem consome ver que
faltam.

Sem `--all`, o build pergunta fabricante, título, descrição e layout — com tudo pré-preenchido a partir do `.aq`. Basta ir dando Enter. Com `--all` nada é perguntado: os campos são inferidos.

`--all` **pula bibliotecas que já têm ZIP** na pasta de destino. Use `--force` para refazer.

## Layouts

| Layout | Quando usar |
|---|---|
| `series-rows` | Poucas famílias, muitas variantes; ideal com curva Q-H. Ex: bombas |
| `catalog-grid` | Muitos itens heterogêneos, com filtros por categoria. Ex: conexões |

Escolhido automaticamente: `series-rows` se a biblioteca tem curvas Q-H, `catalog-grid` acima de 6 peças. Ajustável na pergunta do modo interativo ou no `config.json`.

## Publicar o preview

`output/preview/` é **gitignored** (só a landing `index.html` é versionada) e a integração
git da Vercel está **desligada** desde 2026-09-02 — push não publica nada. O único fluxo
que funciona é o CLI, sempre da raiz do repositório, depois de um build local:

```bash
python3 scripts/build.py --all        # gera output/preview/ nesta máquina
vercel --prod --yes                   # sobe output/preview/ (vercel.json) para bilds-bim-3d.vercel.app
```

Índice em `bilds-bim-3d.vercel.app`, cada catálogo em `bilds-bim-3d.vercel.app/<slug>`.
**Nunca** passe `output/preview` como argumento do `vercel` — isso ignora o
`.vercel/project.json` e cria um projeto novo. A estratégia definitiva (build na Vercel,
storage externo ou preview só local) é uma decisão em aberto — item C7 de
`docs/auditoria-2026-09-03-pendencias.md`.

## Ferramentas auxiliares

```bash
# Inspecionar uma biblioteca sem gerar nada
python3 www/apps/ingestao/pipeline/read_aq.py caminho/para/pecas.aq --meta
# → fabricante, linhas, nº de peças, nº de geometrias, curvas Q-H, versão do schema

# O pipeline sem o ZIP/preview: geometria + catálogo em JSON (+ miniaturas) — é o que o serviço de ingestão roda
python3 www/apps/ingestao/pipeline/catalogo_de_aq.py caminho/para/pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json --thumbs-dir /tmp/thumbs
```

O código que lê o `.aq` e gera catálogo, geometria e miniaturas mora em `www/apps/ingestao/pipeline/`
(README lá); `scripts/build.py` só faz o que é do preview e do ZIP.

## Testes

```bash
python3 -m pytest                                   # 53 testes, ≈ 20 s
python3 -m pytest -m "not thumbs"                   # sem abrir o Chromium
python3 -m pytest -m "not thumbs and not paridade"  # só Python, sem Node
```

Cobrem o parser OQ3D (inclusive blobs truncados e de versão desconhecida), a leitura do
`.aq`, o diagnóstico do build, o escape dos templates, o ZIP, o comportamento sem
miniaturas e a **paridade com o port TypeScript** de `www/tools` (rodado direto no Node
24). Os testes que usam bibliotecas reais de `input/` pulam com motivo quando o arquivo não
está na máquina. Detalhes em `CLAUDE.md`, seção "Testes".

## Requisitos

`bash scripts/bootstrap.sh --check` confere tudo abaixo e diz como corrigir cada linha
(`--www` e `--cad` instalam os opcionais). O que ele confere:

- Python 3.12 (`.python-version`); `pip install -r requirements.txt` — Jinja2 e numpy
- Node 24 (`.nvmrc`) e pnpm 11 (`packageManager` no `package.json`) — só para as miniaturas e para `www/`
- bash e curl, para o `setup_vendor.sh`
- testes: `pip install -r requirements-dev.txt`

`ifcopenshell`, `cadquery-ocp` e `pypdf` são opcionais e estão pinados em `requirements-cad.txt`:
IFC B-rep (`IFCADVANCEDBREP`) e IFC grande no conversor da POC (`www/apps/ingestao/pipeline/ifc_to_geo.py`), STEP
no editor e extração de PDF. O pipeline estático não usa nenhum deles. O repositório é **pnpm só** — não use `npm install` (gera um
`package-lock.json` que não é versionado).

### Miniaturas (opcional, mas recomendado)

O passo que pré-renderiza as miniaturas precisa de **Node 20+** (exigência do
Playwright) e do Chromium:

```bash
pnpm install                                           # playwright + Chromium (postinstall)
sudo apt-get install -y libnss3 libnspr4 libasound2t64  # libs de sistema
```

⚠️ **Não use `sudo npx playwright install-deps chromium`.** É o comando que a
documentação do Playwright manda, e ele falha em qualquer máquina com nvm: o `sudo` do
Ubuntu usa `secure_path` e **descarta o PATH do usuário**, então o `npx` cai no Node do
apt (v18 aqui) e o Playwright recusa com _"requires Node.js 20 or higher"_ — mesmo com
o `nvm default` apontando para uma versão nova. O `apt-get` acima instala exatamente as
mesmas libs sem envolver Node. Se preferir o comando do Playwright, repasse o PATH:

```bash
sudo env "PATH=$PATH" npx playwright install-deps chromium
```

⚠️ **Duas versões de Node na mesma máquina** é a outra armadilha. O Node do
apt (`/usr/bin/node`) costuma ser antigo, e o do nvm só entra no PATH em shell
interativo — um subprocess do `build.py` pega o do apt e o Playwright recusa. O build
procura sozinho um Node >= 20 em `~/.nvm/versions/node/`, mas se você tiver o Node novo
em outro lugar, aponte:

```bash
BILDS_NODE=/caminho/para/node python3 scripts/build.py --all
```

**Sem sudo?** Dá para resolver as libs de sistema sem root, baixando os `.deb` e
extraindo num diretório local:

```bash
mkdir -p ~/.local/chromium-libs && cd ~/.local/chromium-libs
apt-get download libnspr4 libnss3 libasound2t64
for d in *.deb; do dpkg-deb -x "$d" root/; done
export LD_LIBRARY_PATH=~/.local/chromium-libs/root/usr/lib/x86_64-linux-gnu
```

**Não instalar quebra o build** (desde 2026-09-03): o passo de miniaturas falha com
`ERRO: miniaturas — …` e o processo sai com código 1, porque um ZIP sem `thumbs/` faz a
página gerar as miniaturas no browser do visitante — 39,9 s de LCP nos catálogos com
geometria pesada. Se for de propósito, `--allow-no-thumbs` (tenta e segue) ou
`--skip-thumbs` (nem tenta).

## Uma peça não apareceu no catálogo

Peças sem geometria no banco são puladas, e o build informa quantas. Normalmente são **tubos** (que o AltoQi gera como cilindro a partir do diâmetro e do comprimento) e **kits de aparelho sanitário** — entradas de projeto, não peças com forma fixa. Na biblioteca de esgoto da Amanco são 312 de 1.168 peças, e é o comportamento correto. Essa linha sai como `N peça(s) sem simbologia 3D (tubos/kits) puladas — esperado`.

Se em vez disso aparecer `AVISO: N simbologia(s) descartada(s)` ou `AVISO: N simbologia(s) com aviso de parse`, **não é tubo**: a peça tem geometria no banco e o parser não conseguiu lê-la (blob nulo, sem assinatura OQ3D, truncado, sem malha, ou com layout que o `oq3d.py` não conhece). O aviso traz o id e o nome da simbologia. Foi assim que se descobriu, em 2026-09-03, que 56 peças da Maxbar estavam sem 3D por usarem uma versão de malha que o parser rejeitava.

Se faltar uma peça que deveria ter forma e ela só existe como IFC, não no `.aq`, o build não a inclui — o modo `--ifc` foi removido em 2026-09-05 (ver "Peça que existe só como IFC").

## POC de edição (em `www/`, local)

Sobre a POC dinâmica em `www/` (NestJS + Next.js + Mongo), a POC de edição acrescenta
**edição das informações e do modelo 3D** de cada produto, sem login:

```bash
cd www && cp .env.example .env      # preencher Mongo, seed, JWT, STORAGE_PATH
pnpm install
pnpm dev:api                        # :4000
pnpm dev:web                        # :3000  (outro terminal)
# importar uma biblioteca (interface em /empresa/importar, ou pela API — ver CLAUDE.md)
# abrir http://localhost:3000/<empresa>/<catalogo>/editar
```

No editor: selecionar partes do modelo (o JSON plano é re-segmentado em componentes
conexos), mover/girar/escalar com gizmo ou campos em cm, recolorir, espelhar, fundir,
excluir, adicionar cilindro/tubo/caixa ou STL/OBJ, corte em Y, fantasma do original.
**Salvar** grava de volta o `{pos, col, idx}` que o viewer público lê, preservando o
original para "restaurar". **Exportar IFC** baixa um IFC4 do que está na tela (uma
`IFCBUILDINGELEMENTPROXY` por parte, cores por face, informações do produto em
`IFCPROPERTYSET`), lido de volta pelo `www/apps/ingestao/pipeline/parse_ifc.py` com os mesmos triângulos. A aba **Informações** edita nome, série, specs, curva Q-H,
potência e conexões no banco, com "voltar" por campo. Detalhes em
`docs/sessoes/S7.1-poc-edicao.md`.

## Peça STEP ou IFC no editor, e saída em `.aq`

No mesmo `www/`, um `.stp`/`.step` (Inventor, SolidWorks, CATIA…) ou um `.ifc` entra no
editor como produto de um catálogo e sai como IFC4 ou `.aq`:

```bash
pip install --user --break-system-packages cadquery-ocp   # OpenCASCADE em Python, uma vez
python3 www/apps/ingestao/pipeline/step_to_geo.py input/STEP/2831A09.stp --info   # inspeciona: unidade, sólidos, bbox
python3 www/apps/ingestao/pipeline/ifc_to_geo.py peca.ifc --info                   # idem para IFC (parse_ifc.py + dedup)
# com a API e o web de pé: http://localhost:3000/importar-step   (aceita .stp, .step e .ifc)
```

O STEP é B-rep paramétrico (não tem triângulos); a API tessela com OpenCASCADE. O IFC passa
pelo `parse_ifc.py` do projeto quando é pequeno e pelo `ifcopenshell` quando é grande (um
Revit de 124 MB leva ~4 min e 3,6 GB de RAM). A importação é assíncrona: a página mostra
as etapas e o progresso do conversor. Nos dois casos a API cria o produto e a miniatura. No editor, **Exportar .aq** gera uma biblioteca AltoQi com a peça
(`www/apps/ingestao/pipeline/geo_to_aq.py`, sobre o escritor OQ3D do `eng-reversa/`), lida de volta pelo
`read_aq.py` do projeto. Detalhes em `docs/sessoes/S7.2-step-e-aq.md`.

## Documentação

- `CLAUDE.md` — arquitetura, formato OQ3D, decisões e armadilhas conhecidas
- `docs/bilds-bim-3d-zip-spec.md` — contrato do ZIP consumido pela bilds.com
- `docs/plano-integracao-bilds.md` — plano original da integração (**histórico**: o módulo já está em produção; não use como guia)
- `docs/estudo-oq3d/` — como a geometria dentro do `.aq` foi descoberta e validada
- `docs/skills/` — skills de agente sobre `.aq`, IFC e páginas de catálogo
- `eng-reversa/` — como **escrever** um `.aq` e OQ3D, e extrair catálogo de um PDF comercial (o caminho inverso do pipeline)
- `docs/sessoes/S7.1-poc-edicao.md` — a POC de edição: o que faz, como foi verificada, o que ficou pendente
- `docs/sessoes/S7.2-step-e-aq.md` — STEP tesselado no editor e exportação em `.aq`

## Skills de agente

As quatro skills que cobrem o terreno técnico do projeto (`.aq`, IFC, STEP e páginas de
catálogo) são versionadas em `docs/skills/`. Para usá-las com o Claude Code:

```bash
bash scripts/link_skills.sh
```

Cria symlinks de `~/.claude/skills/` para cá — uma cópia só, versionada no git.
Idempotente: pode rodar quantas vezes quiser.
