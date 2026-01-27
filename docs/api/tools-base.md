# Tool API Reference

Base classes and utilities for creating tools.

## Module: `roura_agent.tools.base`

### RiskLevel

Enumeration of tool risk levels.

```python
from enum import Enum

class RiskLevel(Enum):
    SAFE = "safe"       # No user data affected, read-only
    MODERATE = "moderate"  # Modifies user files
    DANGEROUS = "dangerous"  # System commands, irreversible actions
```

### ToolResult

Result of a tool execution.

```python
@dataclass
class ToolResult:
    success: bool
    output: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
```

**Fields:**
- `success`: Whether the operation succeeded
- `output`: Result data as a dictionary (tool-specific)
- `error`: Error message if `success` is False

### Tool

Base class for all tools.

```python
class Tool:
    """Base class for agent tools."""

    # Required class attributes
    name: str           # Unique tool identifier (e.g., "fs.read")
    description: str    # Human-readable description
    risk_level: RiskLevel  # Risk classification

    # JSON Schema for parameters
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        raise NotImplementedError

    def preview(self, **kwargs) -> dict:
        """
        Generate a preview of what this tool would do.
        Optional - returns empty dict if not implemented.
        """
        return {}

    def validate_args(self, **kwargs) -> tuple[bool, str]:
        """
        Validate arguments before execution.
        Returns (is_valid, error_message).
        """
        return True, ""
```

### ToolRegistry

Registry for discovering and managing tools.

```python
class ToolRegistry:
    """Registry for agent tools."""

    def register(self, name: str):
        """Decorator to register a tool class."""
        def decorator(cls):
            self._tools[name] = cls()
            return cls
        return decorator

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""

    def list_tools(self) -> list[str]:
        """List all registered tool names."""

    def get_by_risk(self, risk: RiskLevel) -> list[Tool]:
        """Get all tools with a specific risk level."""

    def remove(self, name: str) -> bool:
        """Remove a tool from the registry."""

# Global registry instance
registry = ToolRegistry()
```

## Creating Custom Tools

### Basic Tool

```python
from roura_agent.tools.base import Tool, RiskLevel, ToolResult, registry

@registry.register("custom.timestamp")
class TimestampTool(Tool):
    """Get the current timestamp."""

    name = "custom.timestamp"
    description = "Get the current UTC timestamp"
    risk_level = RiskLevel.SAFE

    parameters = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "Output format (iso, unix, human)",
                "enum": ["iso", "unix", "human"],
                "default": "iso",
            }
        },
    }

    def execute(self, format: str = "iso") -> ToolResult:
        from datetime import datetime

        now = datetime.utcnow()

        if format == "unix":
            output = {"timestamp": int(now.timestamp())}
        elif format == "human":
            output = {"timestamp": now.strftime("%B %d, %Y at %H:%M UTC")}
        else:
            output = {"timestamp": now.isoformat() + "Z"}

        return ToolResult(success=True, output=output)
```

### Tool with Preview

```python
@registry.register("custom.replace")
class ReplaceTool(Tool):
    """Replace text in files."""

    name = "custom.replace"
    description = "Replace all occurrences of text in a file"
    risk_level = RiskLevel.MODERATE

    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old": {"type": "string", "description": "Text to find"},
            "new": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old", "new"],
    }

    def preview(self, path: str, old: str, new: str) -> dict:
        """Show what would be replaced."""
        from pathlib import Path

        try:
            content = Path(path).read_text()
            count = content.count(old)
            return {
                "path": path,
                "occurrences": count,
                "sample": content[:200] if count > 0 else None,
            }
        except FileNotFoundError:
            return {"error": f"File not found: {path}"}

    def execute(self, path: str, old: str, new: str) -> ToolResult:
        from pathlib import Path

        try:
            file = Path(path)
            content = file.read_text()
            count = content.count(old)

            if count == 0:
                return ToolResult(
                    success=False,
                    error=f"Text '{old}' not found in {path}"
                )

            new_content = content.replace(old, new)
            file.write_text(new_content)

            return ToolResult(
                success=True,
                output={"replaced": count, "path": path}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### Tool with Validation

```python
@registry.register("custom.fetch")
class FetchTool(Tool):
    """Fetch content from a URL."""

    name = "custom.fetch"
    description = "Fetch content from a URL"
    risk_level = RiskLevel.MODERATE

    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "timeout": {"type": "integer", "description": "Timeout in seconds"},
        },
        "required": ["url"],
    }

    def validate_args(self, url: str, timeout: int = 30) -> tuple[bool, str]:
        """Validate URL and timeout."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False, "URL must use http or https"

        if not parsed.netloc:
            return False, "URL must have a host"

        if timeout < 1 or timeout > 300:
            return False, "Timeout must be between 1 and 300 seconds"

        return True, ""

    def execute(self, url: str, timeout: int = 30) -> ToolResult:
        import httpx

        # Validation runs automatically if defined
        valid, error = self.validate_args(url, timeout)
        if not valid:
            return ToolResult(success=False, error=error)

        try:
            response = httpx.get(url, timeout=timeout)
            return ToolResult(
                success=True,
                output={
                    "status": response.status_code,
                    "content": response.text[:10000],
                    "headers": dict(response.headers),
                }
            )
        except httpx.TimeoutException:
            return ToolResult(success=False, error="Request timed out")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

## JSON Schema Reference

Tools use JSON Schema to define parameters:

```python
parameters = {
    "type": "object",
    "properties": {
        # String parameter
        "name": {
            "type": "string",
            "description": "The name",
            "minLength": 1,
            "maxLength": 100,
        },

        # Integer parameter
        "count": {
            "type": "integer",
            "description": "Number of items",
            "minimum": 0,
            "maximum": 100,
            "default": 10,
        },

        # Boolean parameter
        "verbose": {
            "type": "boolean",
            "description": "Enable verbose output",
            "default": False,
        },

        # Enum parameter
        "format": {
            "type": "string",
            "description": "Output format",
            "enum": ["json", "yaml", "xml"],
        },

        # Array parameter
        "files": {
            "type": "array",
            "description": "List of files",
            "items": {"type": "string"},
        },

        # Object parameter
        "options": {
            "type": "object",
            "description": "Additional options",
            "properties": {
                "key": {"type": "string"},
            },
        },
    },
    "required": ["name"],  # Required parameters
}
```

## Best Practices

1. **Use descriptive names**: `project.action` format (e.g., `fs.read`, `git.status`)
2. **Appropriate risk levels**: Be conservative - if in doubt, use MODERATE
3. **Good error messages**: Return helpful errors that guide the user
4. **Preview support**: Implement `preview()` for destructive operations
5. **Input validation**: Use `validate_args()` for complex validation
6. **Documentation**: Write clear descriptions for the tool and parameters
