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
#   bash www/tools/testes-editor.sh [caminho/para/geo.json]
#
# Sem argumento usa a primeira geometria encontrada em www/storage/bim/geo/.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/www/apps/web"
SRC="$WEB/src/components/bim-editor"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

GEO="${1:-$(find "$REPO/www/storage/bim/geo" -name '*.json' ! -name '*.orig.json' 2>/dev/null | head -1 || true)}"
[ -n "$GEO" ] && [ -f "$GEO" ] || { echo "ERRO: passe um geo.json (não há geometria em www/storage/bim/geo)"; exit 1; }

cp "$SRC/mesh-model.ts" "$TMP/mesh-model.ts"
sed "s#from './mesh-model'#from './mesh-model.ts'#" "$SRC/ifc-export.ts" > "$TMP/ifc-export.ts"
cp "$REPO/www/tools/roundtrip-mesh-model.mts" "$REPO/www/tools/roundtrip-ifc-export.mts" "$TMP/"
ln -s "$WEB/node_modules" "$TMP/node_modules"     # resolve 'three'

echo "== round-trip do modelo de malha: $GEO"
node --experimental-strip-types --no-warnings "$TMP/roundtrip-mesh-model.mts" "$GEO"

echo
echo "== exportador IFC4 → parse_ifc.py / ifcopenshell"
node --experimental-strip-types --no-warnings "$TMP/roundtrip-ifc-export.mts" "$GEO" "$TMP/teste.ifc" "$TMP/esperado.json"
cd "$REPO" && python3 - "$TMP/teste.ifc" "$TMP/esperado.json" <<'EOF'
import sys, json
ifc, esperado = sys.argv[1], sys.argv[2]
sys.path.insert(0, 'scripts')
import parse_ifc
res = parse_ifc.parse_ifc_file(ifc); exp = json.load(open(esperado))
ntri = len(res['idx'])//3 if 'idx' in res else len(res['pos'])//9
ok = ntri == len(exp['idx'])//3
print(f"  [{'ok  ' if ok else 'FALHA'}] parse_ifc.py devolve os mesmos triângulos — {ntri} vs {len(exp['idx'])//3}")
def pts(pos): return {(round(pos[i]*1e5), round(pos[i+1]*1e5), round(pos[i+2]*1e5)) for i in range(0, len(pos), 3)}
A, B = pts(exp['pos']), pts(res['pos'])
frac = len(A - B) / max(1, len(A))
print(f"  [{'ok  ' if frac < 0.02 else 'FALHA'}] pontos a 10 µm: {len(A-B)} de {len(A)} na fronteira de arredondamento ({100*frac:.1f}%)")
ca = {tuple(round(c,2) for c in exp['col'][i:i+3]) for i in range(0, len(exp['col']), 3)}
cb = {tuple(round(c,2) for c in res['col'][i:i+3]) for i in range(0, len(res['col']), 3)}
print(f"  [{'ok  ' if ca == cb else 'FALHA'}] cores idênticas — {sorted(cb)}")
try:
    import ifcopenshell, ifcopenshell.validate, logging
    f = ifcopenshell.open(ifc)
    asm = f.by_type('IfcElementAssembly')[0]
    props = {p.Name: p.NominalValue.wrappedValue for r in asm.IsDefinedBy for p in r.RelatingPropertyDefinition.HasProperties if r.RelatingPropertyDefinition.Name == 'bilds_Produto'}
    print(f"  [{'ok  ' if props.get('Nome','').startswith('Peça de teste') else 'FALHA'}] ifcopenshell lê o pset com acento — {props.get('Nome')!r}")
    logger = logging.getLogger('v'); logger.setLevel(logging.ERROR); errs = []
    class H(logging.Handler):
        def emit(self, rec): errs.append(rec.getMessage()[:160])
    logger.addHandler(H()); ifcopenshell.validate.validate(f, logger, express_rules=False)
    print(f"  [{'ok  ' if not errs else 'FALHA'}] ifcopenshell.validate — {len(errs)} erro(s) {errs[:3]}")
except ImportError:
    print('  [pulo] ifcopenshell não instalado')
EOF
echo
echo "Concluído. Para o teste no browser: node www/tools/e2e/e2e-editor.mjs --validar"
