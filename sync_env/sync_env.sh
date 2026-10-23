#!/usr/bin/env bash
# Bootstrap: ensure uv is available, then run sync_env.py (deps resolved by uv
# from the inline script metadata).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found, installing ..." >&2
    if command -v brew >/dev/null 2>&1; then
        brew install uv
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
fi

exec uv run --quiet --script "$SCRIPT_DIR/sync_env.py" "$@"
