#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

confirm="${1:-}"
if [[ "$confirm" != "-y" && "$confirm" != "--yes" ]]; then
  echo "This will remove $ROOT_DIR/data and $ROOT_DIR/cache"
  read -r -p "Continue? [y/N] " reply
  if [[ "$reply" != "y" && "$reply" != "Y" ]]; then
    echo "Cancelled"
    exit 0
  fi
fi

rm -rf "$ROOT_DIR/data" "$ROOT_DIR/cache"

echo "Removed data/ and cache/"
