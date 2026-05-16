#!/usr/bin/env sh
cd "$(dirname "$0")"
uv run carta
echo
read -r -p "Press Enter to close..." _
