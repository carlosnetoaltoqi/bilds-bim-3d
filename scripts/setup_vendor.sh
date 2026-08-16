#!/usr/bin/env bash
# setup_vendor.sh — Baixa Three.js r170 para templates/vendor/
# Necessário para preview local e Vercel funcionar (CDNs são bloqueados por CSP).
# Executar uma vez após clonar o projeto.

set -e
VENDOR_DIR="$(dirname "$0")/../templates/vendor"
mkdir -p "$VENDOR_DIR"

THREE_VERSION="r170"
BASE_URL="https://cdn.jsdelivr.net/npm/three@0.170.0/build"
EXAMPLES_URL="https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/controls"

echo "Baixando Three.js $THREE_VERSION..."
curl -fsSL "$BASE_URL/three.module.js" -o "$VENDOR_DIR/three.module.js"
echo "  ✓ three.module.js"

curl -fsSL "$EXAMPLES_URL/OrbitControls.js" -o "$VENDOR_DIR/OrbitControls.js"
echo "  ✓ OrbitControls.js"

echo "Vendor pronto: $VENDOR_DIR"
ls -lh "$VENDOR_DIR"
