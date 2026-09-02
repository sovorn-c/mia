#!/usr/bin/env bash
set -euo pipefail

roots=(src tests README.md AGENTS.md CLAUDE.md docs specs)
pattern='\b(AgentProfile|ProfileManager|ModeRuntime|ModeCatalog|WorkflowStage|HerdManager|ManagedAgent|AgentState|MiaHerdApp)\b|mia_agent\.(profiles|herd)|--profile\b|/profile([^[:alnum:]_-]|$)|--mode\b|/mode([^[:alnum:]_-]|$)|code_mode\b'

matches=$(grep -RIlE "$pattern" "${roots[@]}" 2>/dev/null || true)
if [[ -n "$matches" ]]; then
  printf 'retired public surface found in:\n%s\n' "$matches" >&2
  exit 1
fi
printf '%s\n' 'public surface: clean'
