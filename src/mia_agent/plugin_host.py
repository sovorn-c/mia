"""Governed Plugin extension host, activation planning, and lifecycle management."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from mia_agent.agents.model import Agent, normalize_plugin_id
from mia_agent.plugin_models import (
    CORE_PLUGIN_API_VERSION,
    PluginManifest,
    _validate_secret_free,
)
from mia_agent.plugins import PluginManager
from mia_tools.base import BaseTool

T = TypeVar("T")

RunObserverPhase = Literal["run_started", "event_emitted", "run_finished"]
VALID_OBSERVER_PHASES: set[RunObserverPhase] = {"run_started", "event_emitted", "run_finished"}


@runtime_checkable
class RunObserver(Protocol):
    def __call__(self, event: Any) -> None | Awaitable[None]: ...


ContextContributor = Callable[[], str | Awaitable[str]]
PluginContribution = Any


@dataclass(frozen=True, slots=True)
class ActivationPlan:
    """Validated, complete enabled Plugin plan in deterministic activation order."""

    agent_id: str
    plugins: tuple[str, ...]
    manifests: Mapping[str, PluginManifest] = field(default_factory=dict)


class PluginContext:
    """Narrow per-activation registration context for trusted-code Plugins."""

    def __init__(
        self,
        *,
        plugin_id: str,
        agent_id: str,
        config: Mapping[str, Any],
        data_dir: Path,
        manifest: PluginManifest,
    ) -> None:
        self.plugin_id = normalize_plugin_id(plugin_id)
        self.agent_id = agent_id
        # Secret-free immutable mapping
        _validate_secret_free(dict(config), f"plugin_config.{self.plugin_id}")
        self.config: Mapping[str, Any] = dict(config)
        self.data_dir = data_dir
        self._manifest = manifest

        self._tools: list[BaseTool] = []
        self._context_contributors: list[ContextContributor] = []
        self._observers: dict[RunObserverPhase, list[RunObserver]] = {
            "run_started": [],
            "event_emitted": [],
            "run_finished": [],
        }
        self._tool_middleware: list[Any] = []
        self._disposers: list[Callable[[], Any]] = []

    def register(self, contribution: PluginContribution) -> None:
        """Register one declared runtime contribution."""
        if isinstance(contribution, BaseTool):
            # Must match a declared tool spec
            declared_specs = {s.name: s for s in self._manifest.tool_specs}
            if contribution.name not in declared_specs:
                raise ValueError(
                    f"Plugin '{self.plugin_id}' registered undeclared Tool '{contribution.name}'"
                )
            spec = declared_specs[contribution.name]
            if getattr(contribution, "effect", None) != spec.effect:
                raise ValueError(
                    f"Plugin '{self.plugin_id}' registered Tool '{contribution.name}' with undeclared effect '{getattr(contribution, 'effect', None)}'"
                )
            # Enforce attribution
            object.__setattr__(contribution, "plugin_id", self.plugin_id)
            self._tools.append(contribution)
        elif callable(contribution) and not hasattr(contribution, "name"):
            self._context_contributors.append(contribution)
        elif hasattr(contribution, "pre_tool") or hasattr(contribution, "post_tool"):
            self._tool_middleware.append(contribution)
        else:
            self._tools.append(contribution)

    def observe(self, phase: RunObserverPhase, observer: RunObserver) -> None:
        """Register one notification-only observer for an approved Run phase."""
        if phase not in VALID_OBSERVER_PHASES:
            raise ValueError(
                f"Invalid observer phase '{phase}'. Valid phases: {', '.join(sorted(VALID_OBSERVER_PHASES))}"
            )
        if not callable(observer):
            raise TypeError("Observer must be callable")
        self._observers[phase].append(observer)

    async def effect(
        self,
        acquire: Callable[[], T | Awaitable[T]] | Awaitable[T] | T,
        cleanup: Callable[[], Any] | None = None,
    ) -> Any:
        """Acquire one Core-owned reversible resource or record a disposer."""
        if cleanup is not None:
            if callable(acquire):
                res = acquire()
                val = await res if isinstance(res, Awaitable) else res
            elif isinstance(acquire, Awaitable):
                val = await acquire
            else:
                val = acquire
            self._disposers.append(cleanup)
            return val
        elif callable(acquire):
            self._disposers.append(acquire)
            return None
        elif isinstance(acquire, Awaitable):
            val = await acquire
            return val
        else:
            return acquire


@dataclass(frozen=True, slots=True)
class PluginActivation:
    """Immutable Run-scoped snapshot of activated Plugin contributions."""

    agent_id: str
    tools: tuple[BaseTool, ...] = ()
    context_contributors: tuple[ContextContributor, ...] = ()
    observers: Mapping[RunObserverPhase, tuple[RunObserver, ...]] = field(
        default_factory=lambda: {
            "run_started": (),
            "event_emitted": (),
            "run_finished": (),
        }
    )
    tool_middleware: tuple[Any, ...] = ()
    disposers: tuple[Callable[[], Any], ...] = ()


def _attributed_disposer(fn: Callable[[], Any], plugin_id: str) -> Callable[[], Any]:
    def _wrapper() -> Any:
        return fn()

    _wrapper.plugin_id = plugin_id  # type: ignore[attr-defined]
    return _wrapper


class PluginHost:
    """Core extension host for planning and activating governed Plugins."""

    def __init__(self) -> None:
        self._implementations: dict[str, Any] = {}

    def register_implementation(self, plugin_id: str, implementation: Any) -> None:
        """Register an in-memory Plugin implementation (e.g. for testing or synthetic plugins)."""
        self._implementations[normalize_plugin_id(plugin_id)] = implementation

    async def _rollback(self, disposers: list[tuple[str, Callable[[], Any]]]) -> None:
        """Dispose every acquired effect in reverse order on activation failure."""
        for _pid, disposer in reversed(disposers):
            with contextlib.suppress(Exception):
                res = disposer()
                if isinstance(res, Awaitable):
                    await res

    def plan(self, agent: Agent, plugin_manager: PluginManager) -> ActivationPlan:
        """Plan the complete enabled Plugin set without executing any callbacks."""
        if not agent.plugins:
            return ActivationPlan(agent_id=agent.agent_id, plugins=(), manifests={})

        manifests: dict[str, PluginManifest] = {}
        for plugin_id in agent.plugins:
            norm_id = normalize_plugin_id(plugin_id)
            if plugin_manager.is_quarantined(norm_id):
                raise ValueError(
                    f"Plugin '{norm_id}' is quarantined due to previous cleanup timeout"
                )
            manifest = plugin_manager.get_manifest(norm_id)
            if manifest.api_version != CORE_PLUGIN_API_VERSION:
                raise ValueError(
                    f"Plugin '{norm_id}' has incompatible API version {manifest.api_version}"
                )
            if manifest.plugin_type == "trusted-code" and not plugin_manager.is_trusted(norm_id):
                raise ValueError(f"Plugin '{norm_id}' is not trusted; explicit trust required")
            manifests[norm_id] = manifest

        # Verify all dependencies are enabled and present in manifests
        for norm_id, manifest in manifests.items():
            for dep in manifest.dependencies:
                dep_norm = normalize_plugin_id(dep)
                if dep_norm not in manifests:
                    raise ValueError(
                        f"Plugin '{norm_id}' has unsatisfied dependency '{dep_norm}'; it must be installed, trusted, and enabled"
                    )

        # Topological sort with stable normalized_id tie-breaking
        ordered: list[str] = []
        visited: dict[str, int] = {}  # 0: visiting, 1: visited

        def visit(node: str, path: list[str]) -> None:
            if visited.get(node) == 0:
                cycle_str = " -> ".join([*path, node])
                raise ValueError(f"Plugin dependency cycle detected: {cycle_str}")
            if visited.get(node) == 1:
                return
            visited[node] = 0
            for dep in sorted(manifests[node].dependencies):
                visit(normalize_plugin_id(dep), [*path, node])
            visited[node] = 1
            ordered.append(node)

        for norm_id in sorted(manifests.keys()):
            if visited.get(norm_id) != 1:
                visit(norm_id, [])

        return ActivationPlan(
            agent_id=agent.agent_id,
            plugins=tuple(ordered),
            manifests=manifests,
        )

    async def activate(
        self,
        plan: ActivationPlan,
        *,
        agent: Agent,
        agent_manager: Any | None = None,
        plugin_manager: PluginManager | None = None,
    ) -> PluginActivation:
        """Deterministically activate all enabled Plugins in plan, or roll back entirely on failure."""
        if not plan.plugins:
            return PluginActivation(agent_id=plan.agent_id)

        from mia_agent.plugin_catalog import NotesPlugin
        from mia_agent.plugins import discover_entry_points

        all_disposers: list[tuple[str, Callable[[], Any]]] = []
        staged_tools: list[BaseTool] = []
        staged_context_contributors: list[ContextContributor] = []
        staged_observers: dict[RunObserverPhase, list[RunObserver]] = {
            "run_started": [],
            "event_emitted": [],
            "run_finished": [],
        }
        staged_middleware: list[Any] = []
        seen_tool_names: set[str] = set()

        for plugin_id in plan.plugins:
            norm_id = normalize_plugin_id(plugin_id)
            manifest = plan.manifests.get(norm_id)
            if manifest is None and plugin_manager is not None:
                with contextlib.suppress(Exception):
                    manifest = plugin_manager.get_manifest(norm_id)
            if manifest is None:
                await self._rollback(all_disposers)
                raise ValueError(f"Plugin '{norm_id}' has no manifest in plan")

            # Look up implementation
            impl = self._implementations.get(norm_id)
            if impl is None:
                if norm_id == "notes":
                    impl = NotesPlugin()
                else:
                    with contextlib.suppress(Exception):
                        for ep in discover_entry_points():
                            if normalize_plugin_id(getattr(ep, "name", "")) == norm_id:
                                loaded = ep.load()
                                impl = (
                                    loaded()
                                    if callable(loaded) and not hasattr(loaded, "activate")
                                    else loaded
                                )
                                break

            if impl is None:
                await self._rollback(all_disposers)
                raise ValueError(f"Plugin '{norm_id}' has no implementation available")

            config = getattr(agent, "plugin_config", {}).get(norm_id, {})
            if agent_manager is not None:
                data_dir = agent_manager.agent_home(agent.agent_id) / "plugins" / norm_id
            else:
                data_dir = Path.home() / ".mia" / "agents" / agent.agent_id / "plugins" / norm_id
            data_dir.mkdir(parents=True, exist_ok=True)

            ctx = PluginContext(
                plugin_id=norm_id,
                agent_id=agent.agent_id,
                config=config,
                data_dir=data_dir,
                manifest=manifest,
            )

            try:
                if hasattr(impl, "activate"):
                    res = impl.activate(ctx)
                    if isinstance(res, Awaitable):
                        await res
                elif hasattr(impl, "build_tools"):
                    for tool in impl.build_tools(
                        agent_id=agent.agent_id, data_dir=data_dir, config=dict(config)
                    ):
                        ctx.register(tool)
                else:
                    raise ValueError(f"Plugin '{norm_id}' implementation has no activate method")

                # Validate tool declarations match manifest tool_specs
                declared_specs = {s.name: s for s in manifest.tool_specs}
                actual_tools = {t.name: t for t in ctx._tools}
                if set(actual_tools) != set(declared_specs):
                    missing = set(declared_specs) - set(actual_tools)
                    extra = set(actual_tools) - set(declared_specs)
                    errs = []
                    if missing:
                        errs.append(f"missing declared tools: {sorted(missing)}")
                    if extra:
                        errs.append(f"undeclared tools: {sorted(extra)}")
                    raise ValueError(f"Plugin '{norm_id}' tool mismatch: {'; '.join(errs)}")

                # Check collisions with tools from earlier plugins
                for t_name in actual_tools:
                    if t_name in seen_tool_names:
                        raise ValueError(
                            f"Plugin contribution collision: duplicate Tool name '{t_name}'"
                        )
                    seen_tool_names.add(t_name)

                # Record disposers
                for disp in ctx._disposers:
                    all_disposers.append((norm_id, disp))

                # Stage contributions
                staged_tools.extend(ctx._tools)
                staged_context_contributors.extend(ctx._context_contributors)
                for phase in VALID_OBSERVER_PHASES:
                    staged_observers[phase].extend(ctx._observers[phase])
                staged_middleware.extend(ctx._tool_middleware)

            except Exception as exc:
                for disp in ctx._disposers:
                    all_disposers.append((norm_id, disp))
                await self._rollback(all_disposers)
                raise ValueError(f"Activation failed for plugin '{norm_id}': {exc}") from exc

        final_disposers = tuple(_attributed_disposer(disp, pid) for pid, disp in all_disposers)

        return PluginActivation(
            agent_id=agent.agent_id,
            tools=tuple(staged_tools),
            context_contributors=tuple(staged_context_contributors),
            observers={phase: tuple(staged_observers[phase]) for phase in VALID_OBSERVER_PHASES},
            tool_middleware=tuple(staged_middleware),
            disposers=final_disposers,
        )


__all__ = [
    "ActivationPlan",
    "ContextContributor",
    "PluginActivation",
    "PluginContext",
    "PluginContribution",
    "PluginHost",
    "RunObserver",
    "RunObserverPhase",
    "VALID_OBSERVER_PHASES",
]
