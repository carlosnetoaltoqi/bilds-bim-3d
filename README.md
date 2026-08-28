# bilds-bim-3d

Gera catálogos BIM com viewer 3D a partir de bibliotecas `.aq` do AltoQi Builder.

**Você só precisa do arquivo `.aq`.** Ele carrega a malha 3D, a cor e a miniatura de cada peça — não é preciso ter os IFCs.

## Início rápido

```bash
git clone https://github.com/carlosnetoaltoqi/bilds-bim-3d.git
cd bilds-bim-3d

pip install -r requirements.txt
bash scripts/setup_vendor.sh          # baixa o Three.js — uma vez só

npm install                           # miniaturas — opcional, ver "Requisitos"
sudo npx playwright install-deps chromium

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

### `--ifc` — quando a geometria vem dos arquivos IFC

```bash
python3 scripts/build.py --ifc
python3 scripts/build.py --all --ifc
```

Use **apenas** quando:

- **Há peças em IFC que não estão no banco.** Foi o caso da bomba 89-62 TJM da Dancor: existe como `.IFC` na pasta, mas não tem registro no `.aq`. Sem `--ifc` ela não entra no catálogo.
- **Você quer conferir uma fonte contra a outra**, por exemplo ao validar uma biblioteca nova.

Fora isso, não use. O modo `--ifc` é mais lento, depende do `ifcopenshell` para IFCs B-rep, e precisa casar nome de arquivo com nome de peça — heurística que erra em catálogos grandes.

Com `--ifc`, os IFCs precisam estar **na mesma pasta do `.aq`** correspondente.

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
python3 scripts/build.py --ifc              # geometria dos IFCs (ver acima)
python3 scripts/build.py --input-dir PASTA  # varre outra pasta
python3 scripts/build.py --skip-preview     # só catalog.json e ZIP
python3 scripts/build.py --skip-zip         # só preview
python3 scripts/build.py --skip-thumbs      # não renderiza as miniaturas
```

Sem `--all`, o build pergunta fabricante, título, descrição e layout — com tudo pré-preenchido a partir do `.aq`. Basta ir dando Enter. Com `--all` nada é perguntado: os campos são inferidos.

`--all` **pula bibliotecas que já têm ZIP** na pasta de destino. Use `--force` para refazer.

## Layouts

| Layout | Quando usar |
|---|---|
| `series-rows` | Poucas famílias, muitas variantes; ideal com curva Q-H. Ex: bombas |
| `catalog-grid` | Muitos itens heterogêneos, com filtros por categoria. Ex: conexões |

Escolhido automaticamente: `series-rows` se a biblioteca tem curvas Q-H, `catalog-grid` acima de 6 peças. Ajustável na pergunta do modo interativo ou no `config.json`.

## Publicar o preview

O push para `main` dispara o deploy na Vercel automaticamente.

```bash
git add output/preview/
git commit -m "build: catálogo <slug>"
git push
```

Índice em `bilds-bim-3d.vercel.app`, cada catálogo em `bilds-bim-3d.vercel.app/<slug>`.

## Ferramentas auxiliares

```bash
# Inspecionar uma biblioteca sem gerar nada
python3 scripts/read_aq.py caminho/para/pecas.aq --meta
# → fabricante, linhas, nº de peças, nº de geometrias, curvas Q-H, versão do schema
```

## Requisitos

- Python 3.8+
- `pip install -r requirements.txt` — Jinja2 e numpy
- bash e curl, para o `setup_vendor.sh`

`ifcopenshell` só é necessário para o modo `--ifc` com IFCs B-rep (`IFCADVANCEDBREP`), como os do AltoQi Hidráulico. O modo padrão não usa.

### Miniaturas (opcional, mas recomendado)

O passo que pré-renderiza as miniaturas precisa de **Node 20+** (exigência do
Playwright) e do Chromium:

```bash
npm install                                 # playwright + download do Chromium
sudo npx playwright install-deps chromium   # libs de sistema (libnss3, libasound2)
```

⚠️ **Duas versões de Node na mesma máquina é o problema mais provável aqui.** O Node do
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

**Não instalar não quebra nada:** o build avisa, pula o passo e o ZIP sai sem `thumbs/`.
A página do catálogo volta a gerar as miniaturas no browser do visitante — que é o
comportamento antigo, e é justamente o que custa 39,9 s de LCP nos catálogos com
geometria pesada. Vale instalar.

## Uma peça não apareceu no catálogo

Peças sem geometria no banco são puladas, e o build informa quantas. Normalmente são **tubos** (que o AltoQi gera como cilindro a partir do diâmetro e do comprimento) e **kits de aparelho sanitário** — entradas de projeto, não peças com forma fixa. Na biblioteca de esgoto da Amanco são 312 de 1.168 peças, e é o comportamento correto.

Se faltar uma peça que deveria ter forma, verifique se ela existe só como IFC: nesse caso use `--ifc`.

## Documentação

- `CLAUDE.md` — arquitetura, formato OQ3D, decisões e armadilhas conhecidas
- `docs/bilds-bim-3d-zip-spec.md` — contrato do ZIP consumido pela bilds.com
- `docs/plano-integracao-bilds.md` — plano original da integração (**histórico**: o módulo já está em produção; não use como guia)
- `docs/estudo-oq3d/` — como a geometria dentro do `.aq` foi descoberta e validada
- `docs/skills/` — skills de agente sobre `.aq`, IFC e páginas de catálogo

## Skills de agente

As três skills que cobrem o terreno técnico do projeto são versionadas em
`docs/skills/`. Para usá-las com o Claude Code:

```bash
bash scripts/link_skills.sh
```

Cria symlinks de `~/.claude/skills/` para cá — uma cópia só, versionada no git.
Idempotente: pode rodar quantas vezes quiser.
