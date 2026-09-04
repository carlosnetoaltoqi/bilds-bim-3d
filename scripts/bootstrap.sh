#!/usr/bin/env bash
# bootstrap.sh — prepara (ou só confere) o ambiente do bilds-bim-3d numa máquina.
#
#   bash scripts/bootstrap.sh            # instala o que falta para o pipeline padrão + miniaturas
#   bash scripts/bootstrap.sh --check    # só confere e imprime a tabela; exit 1 se algo OBRIGATÓRIO falta
#   bash scripts/bootstrap.sh --www      # também `pnpm install` em www/ (POC dinâmica + edição)
#   bash scripts/bootstrap.sh --cad      # também requirements-cad.txt (ifcopenshell, OpenCASCADE, pypdf)
#
# Idempotente: rodar de novo não refaz o que já está certo. Nunca chama sudo — quando
# faltam libs de sistema, imprime o comando para você rodar.
#
# As versões esperadas vêm dos arquivos versionados, não deste script:
#   .python-version (3.12) · .nvmrc (24) · package.json → packageManager (pnpm) e engines.node (>= 22.6)
#
# Por que Node >= 22.6 e não só o 20 do Playwright: os testes `.mts` de www/tools rodam com
# --experimental-strip-types e os de paridade usam node:sqlite (22.5+). O `build.py` sozinho
# aceita 20 (NODE_MINIMO) e procura um Node bom em ~/.nvm porque o nvm não entra no PATH de
# subprocess — ver `_find_node`. Se o seu Node novo está em outro lugar: BILDS_NODE=/caminho/node.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

CHECK=0; WWW=0; CAD=0
for a in "$@"; do case "$a" in
  --check) CHECK=1;; --www) WWW=1;; --cad) CAD=1;;
  -h|--help) sed -n '2,20p' "$0"; exit 0;;
  *) echo "argumento desconhecido: $a (use --check, --www, --cad)"; exit 2;;
esac; done

PY_MIN="$(tr -d '[:space:]' < .python-version)"          # ex.: 3.12
NODE_MAJOR_ESPERADO="$(tr -d '[:space:]' < .nvmrc)"     # ex.: 24
NODE_MIN="22.6"                                          # engines.node
PNPM_ESPERADO="$(sed -n 's/.*"packageManager": *"pnpm@\([0-9.]*\)".*/\1/p' package.json)"

FALTA_OBRIG=0
LINHAS=()
linha() { # linha <ok|FALTA|opcional> <item> <detalhe> <como conferir>
  LINHAS+=("| $2 | $1 — $3 | \`$4\` |")
  [ "$1" = FALTA ] && FALTA_OBRIG=1
  return 0
}
ver_ge() { # ver_ge A B  → 0 se A >= B (comparação por componentes numéricos)
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

# ── Python ────────────────────────────────────────────────────────────────────
if command -v python3 >/dev/null; then
  PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  if ver_ge "$PYV" "$PY_MIN"; then linha ok "Python" "$PYV (>= $PY_MIN)" "python3 --version"
  else linha FALTA "Python" "$PYV, precisa >= $PY_MIN (.python-version)" "python3 --version"; fi
else linha FALTA "Python" "python3 não está no PATH" "python3 --version"; fi

pip_install() { # tenta sem flag; no Ubuntu (PEP 668) repete com --user --break-system-packages
  python3 -m pip install -q "$@" 2>/dev/null || python3 -m pip install -q --user --break-system-packages "$@"
}
if python3 -c 'import jinja2, numpy' 2>/dev/null; then linha ok "requirements.txt" "jinja2 e numpy importam" "python3 -c 'import jinja2, numpy'"
elif [ $CHECK = 1 ]; then linha FALTA "requirements.txt" "jinja2/numpy não importam" "pip install -r requirements.txt"
else echo ">> pip install -r requirements-dev.txt"; pip_install -r requirements-dev.txt && linha ok "requirements.txt" "instalado agora" "python3 -c 'import jinja2, numpy'" || linha FALTA "requirements.txt" "pip falhou" "pip install -r requirements.txt"; fi
if python3 -c 'import pytest' 2>/dev/null; then linha ok "pytest (dev)" "importa" "python3 -m pytest -q"
elif [ $CHECK = 1 ]; then linha opcional "pytest (dev)" "ausente — só para a suíte tests/" "pip install -r requirements-dev.txt"
else pip_install -r requirements-dev.txt && linha ok "pytest (dev)" "instalado agora" "python3 -m pytest -q" || linha opcional "pytest (dev)" "pip falhou" "pip install -r requirements-dev.txt"; fi

# ── Node / pnpm ───────────────────────────────────────────────────────────────
node_ver() { "$1" --version 2>/dev/null | sed 's/^v//'; }
NODE_BIN=""; NODE_V=""
for cand in "${BILDS_NODE:-}" node; do
  [ -n "$cand" ] || continue
  v="$(node_ver "$cand")"; [ -n "$v" ] && ver_ge "$v" "$NODE_MIN" && { NODE_BIN="$cand"; NODE_V="$v"; break; }
done
if [ -z "$NODE_BIN" ] && [ -d "$HOME/.nvm/versions/node" ]; then
  for d in "$HOME"/.nvm/versions/node/v*/bin/node; do
    v="$(node_ver "$d")"; [ -n "$v" ] && ver_ge "$v" "$NODE_MIN" && { NODE_BIN="$d"; NODE_V="$v"; }
  done
fi
if [ -n "$NODE_BIN" ]; then
  if [ "$NODE_BIN" = node ]; then linha ok "Node" "$NODE_V no PATH (>= $NODE_MIN; .nvmrc pede $NODE_MAJOR_ESPERADO)" "node -v"
  else linha ok "Node" "$NODE_V em $NODE_BIN — NÃO está no PATH deste shell; build.py acha sozinho, ou exporte BILDS_NODE=$NODE_BIN" "node -v; ls ~/.nvm/versions/node"; fi
else
  linha FALTA "Node" "nenhum Node >= $NODE_MIN no PATH nem em ~/.nvm (o do apt costuma ser 18) — nvm install $NODE_MAJOR_ESPERADO" "node -v"
fi
if command -v pnpm >/dev/null; then
  PV="$(pnpm -v 2>/dev/null)"
  if ver_ge "$PV" "${PNPM_ESPERADO%%.*}"; then linha ok "pnpm" "$PV (packageManager pede $PNPM_ESPERADO; o pnpm troca sozinho)" "pnpm -v"
  else linha FALTA "pnpm" "$PV, precisa >= ${PNPM_ESPERADO%%.*} — corepack enable, ou npm i -g pnpm" "pnpm -v"; fi
else linha FALTA "pnpm" "não está no PATH — corepack enable && corepack prepare pnpm@$PNPM_ESPERADO --activate" "pnpm -v"; fi

# ── Three.js self-hosted ──────────────────────────────────────────────────────
if [ -s templates/vendor/three.module.js ] && [ -s templates/vendor/OrbitControls.js ]; then linha ok "templates/vendor (Three.js)" "presente" "ls templates/vendor"
elif [ $CHECK = 1 ]; then linha FALTA "templates/vendor (Three.js)" "vazio — o preview não abre sem ele" "bash scripts/setup_vendor.sh"
else echo ">> bash scripts/setup_vendor.sh"; bash scripts/setup_vendor.sh >/dev/null && linha ok "templates/vendor (Three.js)" "baixado agora" "ls templates/vendor" || linha FALTA "templates/vendor (Three.js)" "setup_vendor.sh falhou (rede?)" "bash scripts/setup_vendor.sh"; fi

# ── Miniaturas: Playwright + Chromium + libs ──────────────────────────────────
if [ -f node_modules/playwright/package.json ]; then linha ok "Playwright (raiz)" "node_modules/playwright presente" "ls node_modules/playwright"
elif [ $CHECK = 1 ] || [ -z "$NODE_BIN" ] || ! command -v pnpm >/dev/null; then linha FALTA "Playwright (raiz)" "ausente — sem ele o build FALHA nas miniaturas (ou use --skip-thumbs/--allow-no-thumbs)" "pnpm install"
else echo ">> pnpm install (raiz: playwright + chromium)"; pnpm install --frozen-lockfile >/dev/null && linha ok "Playwright (raiz)" "instalado agora" "ls node_modules/playwright" || linha FALTA "Playwright (raiz)" "pnpm install falhou" "pnpm install"; fi
if ls "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"/chromium-* >/dev/null 2>&1; then linha ok "Chromium do Playwright" "em ${PLAYWRIGHT_BROWSERS_PATH:-~/.cache/ms-playwright}" "ls ~/.cache/ms-playwright"
else linha FALTA "Chromium do Playwright" "não baixado — o postinstall do pnpm install faz isso; manual: npx playwright install chromium" "ls ~/.cache/ms-playwright"; fi
NLIBS="$(ldconfig -p 2>/dev/null | grep -c -E 'libnss3\.so|libnspr4\.so|libasound\.so')"
if [ "${NLIBS:-0}" -ge 3 ]; then linha ok "libs do Chromium" "libnss3, libnspr4, libasound no ldconfig" "ldconfig -p | grep -E 'libnss3|libnspr4|libasound'"
else linha FALTA "libs do Chromium" "faltam ($NLIBS/3) — sudo apt-get install -y libnss3 libnspr4 libasound2t64 (NÃO use 'sudo npx playwright install-deps': o sudo descarta o PATH do nvm)" "ldconfig -p | grep -E 'libnss3|libnspr4|libasound'"; fi

# ── Opcionais ─────────────────────────────────────────────────────────────────
if [ -d www/apps/web/node_modules/three ]; then linha ok "www/ (pnpm install)" "dependências presentes" "ls www/apps/web/node_modules/three"
elif [ $WWW = 1 ] && [ $CHECK = 0 ] && command -v pnpm >/dev/null; then echo ">> pnpm install em www/"; (cd www && pnpm install --frozen-lockfile >/dev/null) && linha ok "www/ (pnpm install)" "instalado agora" "ls www/apps/web/node_modules/three" || linha opcional "www/ (pnpm install)" "falhou" "cd www && pnpm install"
else linha opcional "www/ (pnpm install)" "ausente — só para a POC (www/README.md); --www instala" "cd www && pnpm install"; fi
if python3 -c 'import OCP, ifcopenshell, pypdf' 2>/dev/null; then linha ok "requirements-cad.txt" "OCP, ifcopenshell e pypdf importam" "python3 -c 'import OCP, ifcopenshell, pypdf'"
elif [ $CAD = 1 ] && [ $CHECK = 0 ]; then echo ">> pip install -r requirements-cad.txt (grande: ~400 MB)"; pip_install -r requirements-cad.txt && linha ok "requirements-cad.txt" "instalado agora" "python3 -c 'import OCP, ifcopenshell, pypdf'" || linha opcional "requirements-cad.txt" "pip falhou" "pip install --user --break-system-packages -r requirements-cad.txt"
else linha opcional "requirements-cad.txt" "ausente — só STEP/IFC B-rep/PDF; --cad instala" "pip install --user --break-system-packages -r requirements-cad.txt"; fi
if [ -f www/.env ]; then linha ok "www/.env" "existe" "test -f www/.env"
else linha opcional "www/.env" "ausente — cp www/.env.example www/.env e preencher (só para a POC)" "test -f www/.env"; fi
N_AQ="$(find input -name '*.aq' 2>/dev/null | wc -l)"
if [ "$N_AQ" -gt 0 ]; then linha ok "input/*.aq" "$N_AQ biblioteca(s)" "find input -name '*.aq'"
else linha opcional "input/*.aq" "nenhuma — input/ é gitignored; copie as bibliotecas para input/<Fabricante>/[<Linha>/]" "find input -name '*.aq'"; fi

# ── Relatório ─────────────────────────────────────────────────────────────────
echo
echo "| Item | Estado | Como conferir |"
echo "|---|---|---|"
printf '%s\n' "${LINHAS[@]}"
echo
if [ $FALTA_OBRIG = 1 ]; then
  echo "FALTA algo obrigatório (linhas 'FALTA'). Obrigatório = pipeline padrão com miniaturas; 'opcional' = POC www/ e CAD."
  exit 1
fi
echo "Ambiente OK para o pipeline padrão. Próximo passo: python3 scripts/build.py --all   (ou python3 -m pytest -q)"
