#!/usr/bin/env bash
# Release coverage gate: statement coverage, with UI/transport adapters scoped separately.
set -euo pipefail

uv run --offline coverage erase
uv run --offline coverage run -m pytest "$@"

# Overall first-party core excludes terminal UI and provider transport adapters.
uv run --offline coverage report \
  --include='src/*' \
  --omit='src/mia_cli/*,src/mia_agent/auth/openai_auth.py,src/mia_ai/providers/anthropic.py,src/mia_ai/providers/openai_compatible.py' \
  --fail-under=80

# Business boundary: execution, filesystem safety, and access-policy enforcement.
uv run --offline coverage report \
  --include='src/mia_agent/harness.py,src/mia_middleware/access.py,src/mia_tools/fs.py' \
  --fail-under=95
