#!/usr/bin/env bash
# Copies the catalogue into docs/levantar-d3 so GitHub Pages serves it from main.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dest="$here/../docs/levantar-d3"
mkdir -p "$dest"
rsync -a --delete --exclude dist --exclude scripts --exclude README.md --exclude shots "$here/" "$dest/"
echo "published to $dest"
