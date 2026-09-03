#!/usr/bin/env bash
set -euo pipefail

pattern='\b(AgentProfile|ProfileManager|ModeRuntime|ModeCatalog|WorkflowStage|HerdManager|ManagedAgent|AgentState|MiaHerdApp|HerdEvent|InvokeSubagentTool|OrchestrationEventEnvelope|OrchestrationErrorEvent)\b|mia_agent\.(profiles|herd|orchestration(_events|_models)?)|--profile\b|/profile([^[:alnum:]_-]|$)|--mode\b|/mode([^[:alnum:]_-]|$)|code_mode\b'
files=(README.md AGENTS.md CLAUDE.md pyproject.toml)
while IFS= read -r file; do
  files+=("$file")
done < <(find src tests docs specs scripts -type f \
  ! -path 'scripts/check-public-surface.sh' \
  ! -path 'scripts/check-wheel-surface.py' -print 2>/dev/null)

matches=$(grep -IlE "$pattern" "${files[@]}" 2>/dev/null || true)
file_matches=$(find src tests docs specs scripts -type f -print 2>/dev/null \
  | grep -E '/(profiles|herd|mode_runtime|orchestration(_events|_models)?|legacy)(/|\.py$)' || true)
if [[ -n "$matches" || -n "$file_matches" ]]; then
  printf 'retired public surface found in:\n%s\n%s\n' "$matches" "$file_matches" >&2
  exit 1
fi
printf '%s\n' 'public surface: clean'
