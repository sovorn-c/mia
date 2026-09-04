"""Governed Plugin extension host, activation planning, and lifecycle management."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
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


class PluginHost:
    """Core extension host for planning and activating governed Plugins."""

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
