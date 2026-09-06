#!/usr/bin/env bash
# testes-editor.sh — testes sem browser do editor 3D (POC de edição).
#
# Roda os dois round-trips em Node (mesh-model.ts e ifc-export.ts) e a conferência
# do IFC em Python com o parse_ifc.py do projeto (+ ifcopenshell, se instalado).
#
# Por que copia os módulos para um diretório temporário: o Node roda TypeScript com
# `--experimental-strip-types`, mas exige a extensão `.ts` nos imports relativos, e o
# código do web importa `./mesh-model` sem extensão (resolução do bundler). Em vez de
# mudar o código de produção, copia e ajusta. Precisa de Node >= 22.6.
#
#   bash web/tools/testes-editor.sh [caminho/para/geo.json]
#
# Sem argumento usa a primeira geometria encontrada em storage/bim/geo/.
# Sai 1 em qualquer [FALHA] — dos round-trips em Node e da conferência do IFC em Python.
# ROUNDTRIP_SABOTAR=1 e ROUNDTRIP_SABOTAR_IFC=1 têm de fazê-lo falhar (autoteste das métricas).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/web"
SRC="$WEB/src/components/bim-editor"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

GEO="${1:-$(find "$REPO/storage/bim/geo" -name '*.json' ! -name '*.orig.json' 2>/dev/null | head -1 || true)}"
[ -n "$GEO" ] && [ -f "$GEO" ] || { echo "ERRO: passe um geo.json (não há geometria em storage/bim/geo)"; exit 1; }

cp "$SRC/mesh-model.ts" "$TMP/mesh-model.ts"
sed "s#from './mesh-model'#from './mesh-model.ts'#" "$SRC/ifc-export.ts" > "$TMP/ifc-export.ts"
cp "$REPO/web/tools/roundtrip-mesh-model.mts" "$REPO/web/tools/roundtrip-ifc-export.mts" "$TMP/"
ln -s "$WEB/node_modules" "$TMP/node_modules"     # resolve 'three'

echo "== round-trip do modelo de malha: $GEO"
node --experimental-strip-types --no-warnings "$TMP/roundtrip-mesh-model.mts" "$GEO"

echo
echo "== exportador IFC4 → parse_ifc.py / ifcopenshell"
node --experimental-strip-types --no-warnings "$TMP/roundtrip-ifc-export.mts" "$GEO" "$TMP/teste.ifc" "$TMP/esperado.json"
cd "$REPO" && python3 - "$TMP/teste.ifc" "$TMP/esperado.json" <<'EOF'
import sys, json
from collections import defaultdict
import numpy as np
ifc, esperado = sys.argv[1], sys.argv[2]
sys.path.insert(0, 'biblioteca')   # o pacote bim_pipeline (S8/F1)
from bim_pipeline.conversores import parse_ifc
res = parse_ifc.parse_ifc_file(ifc); exp = json.load(open(esperado))
falhas = 0
def check(ok, msg):
    global falhas
    falhas += not ok
    print(f"  [{'ok  ' if ok else 'FALHA'}] {msg}")

ntri = len(res['idx'])//3 if 'idx' in res else len(res['pos'])//9
check(ntri == len(exp['idx'])//3, f"parse_ifc.py devolve os mesmos triângulos — {ntri} vs {len(exp['idx'])//3}")

# Pontos: cada vértice do bake esperado tem de ter um par no IFC lido a <= TOL, e vice-versa.
# O exportador escreve REAL com 6 decimais em metros (0,5 µm por eixo) e o IFCLOCALPLACEMENT
# idem, então o pior caso teórico é ~1,7 µm (medido: 1,37 µm na 20cv da Dancor). Até S7.9 isto
# comparava conjuntos de coordenadas arredondadas a 10 µm com um limite de 2% — acusava
# fronteira de arredondamento (2,2% na 20cv), não erro. Mesma armadilha do I13.
TOL = 2e-6
def sem_par(A, B):
    """(quantos pontos de A não têm par em B a <= TOL, maior distância ao vizinho mais próximo).
    Grade de célula TOL e busca nos 27 vizinhos — um par a <= TOL está sempre numa célula vizinha."""
    cel = defaultdict(list)
    for j, c in enumerate(map(tuple, np.floor(B / TOL).astype(np.int64))): cel[c].append(j)
    n, pior = 0, 0.0
    for i, c in enumerate(map(tuple, np.floor(A / TOL).astype(np.int64))):
        viz = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
               for j in cel.get((c[0] + dx, c[1] + dy, c[2] + dz), ())]
        d = float(np.sqrt(((B[viz] - A[i]) ** 2).sum(axis=1)).min()) if viz else float('inf')
        n += d > TOL; pior = max(pior, d)
    return n, pior
A = np.array(exp['pos'], dtype=np.float64).reshape(-1, 3)
B = np.unique(np.array(res['pos'], dtype=np.float64).reshape(-1, 3), axis=0)   # parse_ifc devolve 3 pontos por triângulo
nA, dA = sem_par(A, B); nB, dB = sem_par(B, A)
desvio = f"{dA*1e6:.2f} µm" if dA != float('inf') else f"> {TOL*1e6*1.5:.0f} µm (fora da grade)"
check(nA == 0, f"todo vértice esperado tem par no IFC lido a ≤ {TOL*1e6:.0f} µm ({nA} de {len(A)} sem par; desvio máximo {desvio})")
check(nB == 0, f"todo vértice do IFC lido tem par no esperado a ≤ {TOL*1e6:.0f} µm ({nB} de {len(B)} sem par)")

ca = {tuple(round(c,2) for c in exp['col'][i:i+3]) for i in range(0, len(exp['col']), 3)}
cb = {tuple(round(c,2) for c in res['col'][i:i+3]) for i in range(0, len(res['col']), 3)}
check(ca == cb, f"cores idênticas — {sorted(cb)}")
try:
    import ifcopenshell, ifcopenshell.validate, logging
    f = ifcopenshell.open(ifc)
    asm = f.by_type('IfcElementAssembly')[0]
    props = {p.Name: p.NominalValue.wrappedValue for r in asm.IsDefinedBy for p in r.RelatingPropertyDefinition.HasProperties if r.RelatingPropertyDefinition.Name == 'bilds_Produto'}
    check(props.get('Nome','').startswith('Peça de teste'), f"ifcopenshell lê o pset com acento — {props.get('Nome')!r}")
    logger = logging.getLogger('v'); logger.setLevel(logging.ERROR); errs = []
    class H(logging.Handler):
        def emit(self, rec): errs.append(rec.getMessage()[:160])
    logger.addHandler(H()); ifcopenshell.validate.validate(f, logger, express_rules=False)
    check(not errs, f"ifcopenshell.validate — {len(errs)} erro(s) {errs[:3]}")
except ImportError:
    print('  [pulo] ifcopenshell não instalado')
if falhas:
    print(f"  {falhas} FALHA(s) na conferência do IFC"); sys.exit(1)
EOF
echo
echo "Concluído. Para o teste no browser: node tests/e2e/e2e-editor.mjs --validar"
