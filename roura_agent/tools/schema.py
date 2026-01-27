"""
Roura Agent Tool Schema - Convert tool definitions to JSON Schema for LLM APIs.

© Roura.io
"""
from __future__ import annotations

from typing import Any, Type

from .base import Tool, ToolParam, ToolRegistry


# Python type to JSON Schema type mapping
TYPE_MAP: dict[Type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def python_type_to_json_schema(python_type: Type) -> str:
    """Convert a Python type to JSON Schema type string."""
    # Handle Optional types and other generics
    origin = getattr(python_type, "__origin__", None)

    if origin is list:
        return "array"
    if origin is dict:
        return "object"

    return TYPE_MAP.get(python_type, "string")


def param_to_json_schema(param: ToolParam) -> dict[str, Any]:
    """
    Convert a ToolParam to a JSON Schema property definition.

    Args:
        param: The tool parameter to convert

    Returns:
        JSON Schema property definition dict
    """
    schema: dict[str, Any] = {
        "type": python_type_to_json_schema(param.type),
        "description": param.description,
    }

    # Handle array types - default to string items
    if param.type == list or getattr(param.type, "__origin__", None) is list:
        schema["items"] = {"type": "string"}

    # Add default value if present and not required
    if param.default is not None and not param.required:
        schema["default"] = param.default

    return schema


def tool_to_json_schema(tool: Tool) -> dict[str, Any]:
    """
    Convert a Tool to Ollama's tool format (JSON Schema).

    Args:
        tool: The tool to convert

    Returns:
        Tool definition in Ollama's expected format:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in tool.parameters:
        properties[param.name] = param_to_json_schema(param)
        if param.required:
            required.append(param.name)

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def registry_to_json_schema(registry: ToolRegistry) -> list[dict[str, Any]]:
    """
    Convert all registered tools to JSON Schema format.

    Args:
        registry: The tool registry to convert

    Returns:
        List of tool definitions in Ollama's expected format
    """
    return [tool_to_json_schema(tool) for tool in registry.list_tools()]


def tools_to_json_schema(tools: list[Tool]) -> list[dict[str, Any]]:
    """
    Convert a list of tools to JSON Schema format.

    Args:
        tools: List of tools to convert

    Returns:
        List of tool definitions in Ollama's expected format
    """
    return [tool_to_json_schema(tool) for tool in tools]


def get_tool_names(registry: ToolRegistry) -> list[str]:
    """Get list of all registered tool names."""
    return [tool.name for tool in registry.list_tools()]


def get_tool_descriptions(registry: ToolRegistry) -> dict[str, str]:
    """Get mapping of tool names to descriptions."""
    return {tool.name: tool.description for tool in registry.list_tools()}
