# Impact — Agent Core Clean Break

## Scope

This change removes obsolete identity and runtime surfaces from the active repository. The canonical path is:

```text
CLI/REPL/TUI → AgentRunner → AgentRuntimeFactory → AgentHarness → Provider/Tools/Middleware/Session
```

## Affected boundaries

- `src/mia_agent/agents/`: strict Agent schema, native registry, and Agent-owned persistence.
- `src/mia_agent/runtime_*.py`: canonical Run identity, events, and runtime composition.
- `src/mia_agent/session/`: append-only Session metadata with Agent attribution.
- `src/mia_agent/plugins.py`: Plugin lifecycle now uses canonical AgentManager methods.
- `src/mia_middleware/access.py`: three supported access levels only.
- `src/mia_cli/`: CLI, REPL, and Textual adapter use AgentRunner and AgentManager.
- `tests/`: public contracts cover Agent, Runtime, Session, Plugin, Delegation, CLI, and TUI behavior.
- `specs/`: active guidance and status metadata describe the shipped model.

## Preserved contracts

- AgentRunner remains the canonical headless prompt entry point.
- AgentHarness remains UI-independent and asynchronous.
- Access checks, security middleware, approval, redaction, and full-access consent remain enforced.
- Plugin tools remain attributed and pass through the normal policy pipeline.
- Delegation remains bounded, attributed, and secret-free.
- Sessions remain append-only and Agent-owned.
- `mia tui` and the Textual dependency remain supported and packaged.

## Risks and controls

| Risk | Control |
| --- | --- |
| A deleted interface returns | `scripts/check-public-surface.sh` scans source, tests, docs, and specs. |
| TUI packaging is lost | Wheel inspection asserts `mia_cli/tui/` is present. |
| User data is changed | No repository operation reads, migrates, or deletes user-home data. |
| Runtime behavior regresses | Full Ruff, Mypy, pytest, coverage, and build gates run offline. |

## Verification

See `specs/verifications/e06s04-verify.yaml` for the final clean-break evidence.
