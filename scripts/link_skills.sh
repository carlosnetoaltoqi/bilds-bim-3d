#!/usr/bin/env bash
# link_skills.sh — aponta ~/.claude/skills/ para as skills versionadas neste repo.
#
# As skills vivem em docs/skills/ (versionadas) e o diretório do Claude recebe
# symlinks. Assim existe uma única cópia: editar em qualquer um dos caminhos é
# editar o arquivo do repositório, e o git acompanha.
#
# Rode uma vez após clonar. É idempotente.
#
#   bash scripts/link_skills.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/docs/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

[ -d "$SRC" ] || { echo "ERRO: $SRC não existe"; exit 1; }
mkdir -p "$DEST"

for dir in "$SRC"/*/; do
    name="$(basename "$dir")"
    target="$DEST/$name"

    # Já aponta para cá: nada a fazer.
    if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$(readlink -f "$dir")" ]; then
        echo "  = $name (já vinculada)"
        continue
    fi

    # Diretório real com conteúdo próprio: não sobrescrever em silêncio.
    if [ -d "$target" ] && [ ! -L "$target" ]; then
        if diff -rq "$target" "$dir" >/dev/null 2>&1; then
            rm -rf "$target"                      # cópia idêntica, pode ir
        else
            backup="$target.bak.$(date +%Y%m%d%H%M%S)"
            mv "$target" "$backup"
            echo "  ! $name divergia — guardado em $(basename "$backup")"
        fi
    else
        rm -f "$target"
    fi

    ln -s "$dir" "$target"
    echo "  + $name -> $dir"
done

echo
echo "Skills vinculadas em $DEST"
echo "Fonte de verdade: $SRC (versionado no git)"
