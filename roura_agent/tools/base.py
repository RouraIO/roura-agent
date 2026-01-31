"""
Roura Agent Tool Base - Foundation for all tools.

© Roura.io
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Type


class RiskLevel(Enum):
    """Risk classification for tools."""
    SAFE = "safe"           # No approval needed (read-only operations)
    MODERATE = "moderate"   # Requires approval (writes, modifications)
    DANGEROUS = "dangerous" # Requires approval + confirmation (deletes, shell)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class ToolParam:
    """Definition of a tool parameter."""
    name: str
    type: Type
    description: str
    required: bool = True
    default: Any = None


@dataclass
class Tool(ABC):
    """Base class for all tools."""
    name: str
    description: str
    risk_level: RiskLevel
    parameters: list[ToolParam] = field(default_factory=list)

    @property
    def requires_approval(self) -> bool:
        """Whether this tool requires user approval before execution."""
        return self.risk_level in (RiskLevel.MODERATE, RiskLevel.DANGEROUS)

    @property
    def requires_confirmation(self) -> bool:
        """Whether this tool requires extra confirmation (dangerous ops)."""
        return self.risk_level == RiskLevel.DANGEROUS

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass

    def validate_params(self, **kwargs) -> Optional[str]:
        """Validate parameters. Returns error message or None if valid."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            if param.name in kwargs:
                value = kwargs[param.name]
                if value is not None and not isinstance(value, param.type):
                    return f"Parameter {param.name} must be {param.type.__name__}"
        return None

    def dry_run(self, **kwargs) -> str:
        """Return a description of what the tool would do without executing."""
        return f"Would execute {self.name} with params: {kwargs}"


class ToolRegistry:
    """Registry for all available tools."""

    _instance: Optional[ToolRegistry] = None

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, Tool] = {}
        return cls._instance

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_risk(self, risk_level: RiskLevel) -> list[Tool]:
        """List tools by risk level."""
        return [t for t in self._tools.values() if t.risk_level == risk_level]


# Global registry instance
registry = ToolRegistry()
