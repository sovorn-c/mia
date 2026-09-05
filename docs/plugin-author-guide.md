# Mia Plugin Author and Trust Guide

This guide explains how to develop, package, declare, and govern Plugins for Mia under the **Governed Core Extension Host** architecture (ADR 0003).

## Table of Contents

- [Extension Host Philosophy](#extension-host-philosophy)
- [Plugin Provenance and Explicit Trust](#plugin-provenance-and-explicit-trust)
- [Static Resources: Skills and Templates](#static-resources-skills-and-templates)
- [Typed Contributions](#typed-contributions)
- [Plugin Lifecycle and Core Governance](#plugin-lifecycle-and-core-governance)
- [Execution Boundaries: Unsandboxed Trusted Code](#execution-boundaries-unsandboxed-trusted-code)
- [Data Ownership and Isolation](#data-ownership-and-isolation)
- [Related Guides](#related-guides)

---

## Extension Host Philosophy

In Mia, **Agent acts, Skill guides, Tool enables, Plugin extends, and Agent delegates through Mia Core**.

Mia Core remains the sole authority for:
- Agent lifecycle, prompt routing, and session history.
- Tool filtering, authorization, and onion-style middleware pipeline execution.
- Credential management and audit logging.

Plugins do not replace or bypass Mia Core; instead, they contribute typed extensions that Mia Core governs and schedules.

---

## Plugin Provenance and Explicit Trust

Mia operates on an **explicit trust model**:
1. **No Automatic Ingestion:** Mia never scans arbitrary network sources or unconfigured local paths to execute code automatically.
2. **Explicit Installation & Activation:** An operator must explicitly install a Plugin and enable it for designated named Agents.
3. **Declared Provenance:** Each Plugin includes a manifest declaring its unique identifier, version, author, capabilities, and dependencies.

### Bundled Plugins

Mia ships with verified, bundled plugins that have undergone static analysis and review. Inspect available plugins with:

```bash
uv run mia plugin list
```

---

## Static Resources: Skills and Templates

Plugins can provide declarative, static assets that do not require executing untrusted Python code:

### Static Skills

A Skill is a markdown document or prompt bundle providing specialized methodology and step-by-step guidance for an Agent. Skills enrich an Agent's reasoning without introducing executable side effects.

### Agent Templates

A Template provides pre-packaged Agent configurations, default tool selections, and starter instructions:

```bash
# List available templates
uv run mia template list

# Inspect a specific template
uv run mia template show coder

# Create a new Agent from a template
uv run mia template create dev-agent --template coder
```

---

## Typed Contributions

A Plugin declares its contributions through typed schemas recognized by Mia Core:

- **Tools:** Expose discrete functions to Agents. Must declare Pydantic input schemas, capability descriptions, and required permissions.
- **Skills:** Provide structured, reusable instruction sets.
- **Middleware Hooks:** Intercept tool invocations to provide custom telemetry, policy enforcement, or domain-specific transformation.

All contributed Tools pass through Mia's security middleware, ensuring that path traversal checks, secret scrubbing, and user approvals remain uncompromised.

---

## Plugin Lifecycle and Core Governance

The lifecycle of a Plugin is managed entirely by Mia Core. Plugins cannot start background daemon threads or detach from the harness.

### Managing Plugins via CLI

- **List Plugins:**
  ```bash
  uv run mia plugin list
  ```
- **Inspect Plugin Manifest:**
  ```bash
  uv run mia plugin show <plugin_id>
  ```
- **Install a Plugin:**
  ```bash
  uv run mia plugin install <plugin_id>
  ```
- **Enable for a Specific Agent:**
  ```bash
  uv run mia plugin enable <plugin_id> --agent researcher
  ```
- **Configure Plugin Parameters:**
  ```bash
  uv run mia plugin configure <plugin_id> --agent researcher
  ```
- **Disable a Plugin:**
  ```bash
  uv run mia plugin disable <plugin_id> --agent researcher
  ```

---

## Execution Boundaries: Unsandboxed Trusted Code

> [!WARNING]
> **No Process Sandbox:** Trusted Python plugins run **in-process** within Mia's Python runtime. They are **not** isolated by an operating system container, virtual machine, or seccomp sandbox.

Because plugins run in-process:
- **Trust Requirement:** You should only install plugins from authors and sources that you fully trust.
- **Invariant Immutability:** Plugins are prohibited from monkey-patching `AgentHarness`, modifying `AgentRunner`, or altering the global credential store.
- **Middleware Inviolability:** Any Tool registered by a Plugin is wrapped in Mia's onion-style middleware pipeline; plugins cannot exempt their Tools from user approval or safety rules.

---

## Data Ownership and Isolation

Plugins that maintain persistent state must store files exclusively within their designated directory under `~/.mia/plugins/<plugin_id>/`.

- Plugins must **never** write to other Agents' configurations, Session files, or system directories.
- All Plugin storage directories are included in `mia data backup` archives and checked during `mia data verify`.

---

## Related Guides

- **[User Guide](user-guide.md)** — Installation, daily workflows, and accessibility.
- **[Operator Guide](operator-guide.md)** — Data locations, backups, and operational diagnostics.
- **[Documentation Index](README.md)** — Index of all documentation resources.
- **[Project README](../README.md)** — Repository overview and build commands.
