#!/usr/bin/env bash
# scripts/check-release-gate.sh — Unified, fail-closed offline release quality gate
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Ensure fail-closed error handling with step attribution
current_step=""

trap 'code=$?; if [ $code -ne 0 ]; then echo "Release gate failed at step: $current_step (exit code $code)" >&2; fi; exit $code' EXIT

# [1/7] Specification consistency
current_step="check-spec-consistency.py"
echo "=== [1/7] Specification Consistency Gate ==="
uv run --offline python3 scripts/check-spec-consistency.py

# Optional early failure for testing
if [[ "${MIA_FAIL_EARLY_STEP:-}" == "spec" ]]; then
  echo "Simulated step failure at spec gate" >&2
  exit 1
fi

# [2/7] Code formatting check
current_step="ruff format"
echo "=== [2/7] Code Formatting Check (Ruff) ==="
uv run --offline ruff format --check .

# [3/7] Code lint check
current_step="ruff check"
echo "=== [3/7] Code Lint Check (Ruff) ==="
uv run --offline ruff check .

# [4/7] Static typing
current_step="mypy"
echo "=== [4/7] Strict Static Type Check (mypy) ==="
uv run --offline mypy src

# [5/7] Tests
current_step="pytest"
echo "=== [5/7] Full Test Suite (pytest) ==="
uv run --offline pytest

# [6/7] Coverage
current_step="check-coverage.sh"
echo "=== [6/7] Scoped Coverage Enforcement ==="
bash scripts/check-coverage.sh

# [7/7] Public surface
current_step="check-public-surface.sh"
echo "=== [7/7] Public Package Surface Gate ==="
bash scripts/check-public-surface.sh

current_step="done"
echo "=== All Release Quality Gates Passed Cleanly ==="
