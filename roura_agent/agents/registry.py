"""
Roura Agent Registry - Dynamic agent management and discovery.

© Roura.io
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from .base import BaseAgent, AgentContext


class AgentRegistry:
    """
    Registry for managing and discovering agents.

    Provides:
    - Agent registration and lookup
    - Capability-based agent discovery
    - Singleton pattern for global access
    """

    _instance: Optional["AgentRegistry"] = None

    def __init__(self):
        self._agents: dict[str, "BaseAgent"] = {}
        self._console = Console()

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        """Get the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, agent: "BaseAgent") -> None:
        """
        Register an agent.

        Args:
            agent: The agent instance to register
        """
        self._agents[agent.name] = agent

    def unregister(self, name: str) -> bool:
        """
        Unregister an agent by name.

        Returns:
            True if agent was found and removed
        """
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    def get(self, name: str) -> Optional["BaseAgent"]:
        """Get an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list["BaseAgent"]:
        """Get all registered agents."""
        return list(self._agents.values())

    def find_capable(
        self,
        task: str,
        context: Optional["AgentContext"] = None,
    ) -> list[tuple["BaseAgent", float]]:
        """
        Find agents capable of handling a task.

        Returns:
            List of (agent, confidence) tuples, sorted by confidence descending
        """
        capable = []

        for agent in self._agents.values():
            can_handle, confidence = agent.can_handle(task, context)
            if can_handle:
                capable.append((agent, confidence))

        # Sort by confidence, highest first
        capable.sort(key=lambda x: x[1], reverse=True)
        return capable

    def best_agent(
        self,
        task: str,
        context: Optional["AgentContext"] = None,
    ) -> Optional["BaseAgent"]:
        """
        Find the best agent for a task.

        Returns:
            The agent with highest confidence, or None if no capable agent
        """
        capable = self.find_capable(task, context)
        return capable[0][0] if capable else None

    def has_capability(self, capability: str) -> list["BaseAgent"]:
        """Find all agents with a specific capability."""
        from .base import AgentCapability

        try:
            cap = AgentCapability(capability)
        except ValueError:
            return []

        return [
            agent for agent in self._agents.values()
            if cap in agent.capabilities
        ]

    def clear(self) -> None:
        """Clear all registered agents."""
        self._agents.clear()

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents


# Global registry instance
_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get the global agent registry."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry.get_instance()
    return _registry
