"""
Roura Agent Jupyter Notebook Tools - Read, edit, and execute notebooks.

Provides tools for working with .ipynb files.

© Roura.io
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from .base import Tool, ToolParam, ToolResult, RiskLevel, registry


class CellType(Enum):
    """Jupyter notebook cell types."""
    CODE = "code"
    MARKDOWN = "markdown"
    RAW = "raw"


@dataclass
class NotebookCell:
    """Represents a cell in a Jupyter notebook."""
    cell_type: CellType
    source: str
    execution_count: Optional[int] = None
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    cell_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotebookCell":
        """Create a cell from notebook JSON."""
        source = data.get("source", [])
        if isinstance(source, list):
            source = "".join(source)

        return cls(
            cell_type=CellType(data.get("cell_type", "code")),
            source=source,
            execution_count=data.get("execution_count"),
            outputs=data.get("outputs", []),
            metadata=data.get("metadata", {}),
            cell_id=data.get("id"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert cell to notebook JSON format."""
        result = {
            "cell_type": self.cell_type.value,
            "source": self.source.split("\n") if self.source else [],
            "metadata": self.metadata,
        }

        if self.cell_id:
            result["id"] = self.cell_id

        if self.cell_type == CellType.CODE:
            result["execution_count"] = self.execution_count
            result["outputs"] = self.outputs

        return result

    def get_output_text(self) -> Optional[str]:
        """Extract text output from cell outputs."""
        texts = []
        for output in self.outputs:
            output_type = output.get("output_type")

            if output_type == "stream":
                text = output.get("text", [])
                if isinstance(text, list):
                    texts.append("".join(text))
                else:
                    texts.append(text)

            elif output_type == "execute_result":
                data = output.get("data", {})
                if "text/plain" in data:
                    text = data["text/plain"]
                    if isinstance(text, list):
                        texts.append("".join(text))
                    else:
                        texts.append(text)

            elif output_type == "error":
                ename = output.get("ename", "Error")
                evalue = output.get("evalue", "")
                texts.append(f"{ename}: {evalue}")

        return "\n".join(texts) if texts else None

    def has_error(self) -> bool:
        """Check if the cell has an error output."""
        return any(o.get("output_type") == "error" for o in self.outputs)


@dataclass
class Notebook:
    """Represents a Jupyter notebook."""
    cells: List[NotebookCell]
    metadata: Dict[str, Any]
    nbformat: int = 4
    nbformat_minor: int = 5
    path: Optional[Path] = None

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Notebook":
        """Load a notebook from a file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Notebook not found: {path}")

        if not path.suffix.lower() == ".ipynb":
            raise ValueError(f"Not a notebook file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cells = [NotebookCell.from_dict(c) for c in data.get("cells", [])]

        return cls(
            cells=cells,
            metadata=data.get("metadata", {}),
            nbformat=data.get("nbformat", 4),
            nbformat_minor=data.get("nbformat_minor", 5),
            path=path,
        )

    @classmethod
    def create_new(cls, kernel_name: str = "python3") -> "Notebook":
        """Create a new empty notebook."""
        return cls(
            cells=[],
            metadata={
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": kernel_name,
                },
                "language_info": {
                    "name": "python",
                    "version": "3.10",
                },
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert notebook to JSON format."""
        return {
            "cells": [c.to_dict() for c in self.cells],
            "metadata": self.metadata,
            "nbformat": self.nbformat,
            "nbformat_minor": self.nbformat_minor,
        }

    def save(self, path: Optional[Union[str, Path]] = None) -> None:
        """Save the notebook to a file."""
        save_path = Path(path) if path else self.path
        if not save_path:
            raise ValueError("No path specified for saving")

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1, ensure_ascii=False)

        self.path = save_path

    def add_cell(
        self,
        source: str,
        cell_type: CellType = CellType.CODE,
        index: Optional[int] = None,
    ) -> NotebookCell:
        """Add a new cell to the notebook."""
        cell = NotebookCell(
            cell_type=cell_type,
            source=source,
        )

        if index is not None:
            self.cells.insert(index, cell)
        else:
            self.cells.append(cell)

        return cell

    def remove_cell(self, index: int) -> Optional[NotebookCell]:
        """Remove a cell by index."""
        if 0 <= index < len(self.cells):
            return self.cells.pop(index)
        return None

    def get_cell(self, index: int) -> Optional[NotebookCell]:
        """Get a cell by index."""
        if 0 <= index < len(self.cells):
            return self.cells[index]
        return None

    def update_cell(self, index: int, source: str) -> bool:
        """Update a cell's source code."""
        if 0 <= index < len(self.cells):
            self.cells[index].source = source
            self.cells[index].outputs = []  # Clear outputs
            self.cells[index].execution_count = None
            return True
        return False

    def get_code_cells(self) -> List[NotebookCell]:
        """Get all code cells."""
        return [c for c in self.cells if c.cell_type == CellType.CODE]

    def get_markdown_cells(self) -> List[NotebookCell]:
        """Get all markdown cells."""
        return [c for c in self.cells if c.cell_type == CellType.MARKDOWN]

    def clear_outputs(self) -> None:
        """Clear all cell outputs."""
        for cell in self.cells:
            cell.outputs = []
            cell.execution_count = None

    def get_kernel_name(self) -> str:
        """Get the notebook's kernel name."""
        return self.metadata.get("kernelspec", {}).get("name", "python3")

    def to_python_script(self) -> str:
        """Convert notebook to Python script."""
        lines = ["#!/usr/bin/env python", "# -*- coding: utf-8 -*-", ""]
        lines.append(f'"""Converted from {self.path.name if self.path else "notebook"}"""')
        lines.append("")

        for i, cell in enumerate(self.cells):
            if cell.cell_type == CellType.CODE:
                lines.append(f"# %% Cell {i + 1}")
                lines.append(cell.source)
                lines.append("")
            elif cell.cell_type == CellType.MARKDOWN:
                lines.append(f"# %% [markdown]")
                for line in cell.source.split("\n"):
                    lines.append(f"# {line}")
                lines.append("")

        return "\n".join(lines)


class NotebookExecutor:
    """Executes Jupyter notebooks."""

    def __init__(self, timeout: int = 600):
        """
        Initialize the executor.

        Args:
            timeout: Maximum execution time per cell in seconds
        """
        self.timeout = timeout
        self._nbconvert_available: Optional[bool] = None

    def _check_nbconvert(self) -> bool:
        """Check if nbconvert is available."""
        if self._nbconvert_available is None:
            try:
                result = subprocess.run(
                    ["jupyter", "nbconvert", "--version"],
                    capture_output=True,
                    text=True,
                )
                self._nbconvert_available = result.returncode == 0
            except Exception:
                self._nbconvert_available = False
        return self._nbconvert_available

    def execute(
        self,
        notebook: Notebook,
        in_place: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a notebook.

        Args:
            notebook: The notebook to execute
            in_place: Whether to modify the notebook in place

        Returns:
            Execution result with cell outputs
        """
        if not self._check_nbconvert():
            return {
                "success": False,
                "error": "jupyter nbconvert not available",
                "outputs": [],
            }

        # Save to temp file if needed
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False, mode="w") as f:
            json.dump(notebook.to_dict(), f)
            temp_path = f.name

        try:
            # Execute using nbconvert
            result = subprocess.run(
                [
                    "jupyter", "nbconvert",
                    "--to", "notebook",
                    "--execute",
                    "--inplace",
                    f"--ExecutePreprocessor.timeout={self.timeout}",
                    temp_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": result.stderr or "Execution failed",
                    "outputs": [],
                }

            # Load the executed notebook
            executed = Notebook.from_file(temp_path)

            # Collect outputs
            outputs = []
            has_errors = False
            for i, cell in enumerate(executed.cells):
                if cell.cell_type == CellType.CODE:
                    output_text = cell.get_output_text()
                    has_error = cell.has_error()
                    if has_error:
                        has_errors = True

                    outputs.append({
                        "cell_index": i,
                        "execution_count": cell.execution_count,
                        "output": output_text,
                        "has_error": has_error,
                    })

            # Update notebook in place if requested
            if in_place and notebook.path:
                notebook.cells = executed.cells
                notebook.save()

            return {
                "success": not has_errors,
                "error": None,
                "outputs": outputs,
                "cells_executed": len([o for o in outputs if o["execution_count"] is not None]),
            }

        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)


# Global executor instance
_executor: Optional[NotebookExecutor] = None


def get_notebook_executor() -> NotebookExecutor:
    """Get the global notebook executor."""
    global _executor
    if _executor is None:
        _executor = NotebookExecutor()
    return _executor


# Tool implementations

@dataclass
class NotebookReadTool(Tool):
    """Read a Jupyter notebook."""

    name: str = "notebook.read"
    description: str = "Read a Jupyter notebook and get its contents (cells, outputs, metadata)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("include_outputs", bool, "Include cell outputs", required=False, default=True),
    ])

    def execute(
        self,
        path: str,
        include_outputs: bool = True,
    ) -> ToolResult:
        """Read a notebook."""
        try:
            notebook = Notebook.from_file(path)

            cells = []
            for i, cell in enumerate(notebook.cells):
                cell_data = {
                    "index": i,
                    "type": cell.cell_type.value,
                    "source": cell.source,
                }

                if cell.cell_type == CellType.CODE:
                    cell_data["execution_count"] = cell.execution_count
                    if include_outputs:
                        cell_data["output"] = cell.get_output_text()
                        cell_data["has_error"] = cell.has_error()

                cells.append(cell_data)

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "kernel": notebook.get_kernel_name(),
                    "cell_count": len(notebook.cells),
                    "code_cells": len(notebook.get_code_cells()),
                    "markdown_cells": len(notebook.get_markdown_cells()),
                    "cells": cells,
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to read notebook: {e}",
            )


@dataclass
class NotebookEditTool(Tool):
    """Edit a cell in a Jupyter notebook."""

    name: str = "notebook.edit"
    description: str = "Edit a specific cell in a Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("cell_index", int, "Index of the cell to edit (0-based)", required=True),
        ToolParam("new_source", str, "New source content for the cell", required=True),
    ])

    def execute(
        self,
        path: str,
        cell_index: int,
        new_source: str,
    ) -> ToolResult:
        """Edit a notebook cell."""
        try:
            notebook = Notebook.from_file(path)

            if not notebook.update_cell(cell_index, new_source):
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Cell index {cell_index} out of range (0-{len(notebook.cells) - 1})",
                )

            notebook.save()

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "cell_index": cell_index,
                    "cell_type": notebook.cells[cell_index].cell_type.value,
                    "new_source_length": len(new_source),
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to edit notebook: {e}",
            )


@dataclass
class NotebookAddCellTool(Tool):
    """Add a new cell to a Jupyter notebook."""

    name: str = "notebook.add_cell"
    description: str = "Add a new cell to a Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("source", str, "Cell content", required=True),
        ToolParam("cell_type", str, "Cell type: 'code' or 'markdown'", required=False, default="code"),
        ToolParam("index", int, "Index to insert at (default: end)", required=False),
    ])

    def execute(
        self,
        path: str,
        source: str,
        cell_type: str = "code",
        index: Optional[int] = None,
    ) -> ToolResult:
        """Add a cell to a notebook."""
        try:
            notebook = Notebook.from_file(path)

            try:
                ct = CellType(cell_type)
            except ValueError:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Invalid cell type: {cell_type}. Use 'code' or 'markdown'",
                )

            cell = notebook.add_cell(source, ct, index)
            notebook.save()

            actual_index = index if index is not None else len(notebook.cells) - 1

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "cell_index": actual_index,
                    "cell_type": cell.cell_type.value,
                    "total_cells": len(notebook.cells),
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to add cell: {e}",
            )


@dataclass
class NotebookRemoveCellTool(Tool):
    """Remove a cell from a Jupyter notebook."""

    name: str = "notebook.remove_cell"
    description: str = "Remove a cell from a Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("cell_index", int, "Index of the cell to remove (0-based)", required=True),
    ])

    def execute(
        self,
        path: str,
        cell_index: int,
    ) -> ToolResult:
        """Remove a cell from a notebook."""
        try:
            notebook = Notebook.from_file(path)

            removed = notebook.remove_cell(cell_index)
            if not removed:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Cell index {cell_index} out of range",
                )

            notebook.save()

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "removed_index": cell_index,
                    "removed_type": removed.cell_type.value,
                    "total_cells": len(notebook.cells),
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to remove cell: {e}",
            )


@dataclass
class NotebookExecuteTool(Tool):
    """Execute a Jupyter notebook."""

    name: str = "notebook.execute"
    description: str = "Execute all cells in a Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.DANGEROUS
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("save_outputs", bool, "Save outputs to the notebook", required=False, default=True),
    ])

    def execute(
        self,
        path: str,
        save_outputs: bool = True,
    ) -> ToolResult:
        """Execute a notebook."""
        try:
            notebook = Notebook.from_file(path)
            executor = get_notebook_executor()

            result = executor.execute(notebook, in_place=save_outputs)

            if result["success"]:
                return ToolResult(
                    success=True,
                    output={
                        "path": path,
                        "cells_executed": result.get("cells_executed", 0),
                        "outputs": result.get("outputs", []),
                        "saved": save_outputs,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    output={
                        "outputs": result.get("outputs", []),
                    },
                    error=result.get("error", "Execution failed"),
                )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to execute notebook: {e}",
            )


@dataclass
class NotebookCreateTool(Tool):
    """Create a new Jupyter notebook."""

    name: str = "notebook.create"
    description: str = "Create a new Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path for the new notebook", required=True),
        ToolParam("kernel", str, "Kernel name (default: python3)", required=False, default="python3"),
    ])

    def execute(
        self,
        path: str,
        kernel: str = "python3",
    ) -> ToolResult:
        """Create a new notebook."""
        try:
            path = Path(path)
            if not path.suffix.lower() == ".ipynb":
                path = path.with_suffix(".ipynb")

            if path.exists():
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"File already exists: {path}",
                )

            notebook = Notebook.create_new(kernel_name=kernel)
            notebook.save(path)

            return ToolResult(
                success=True,
                output={
                    "path": str(path),
                    "kernel": kernel,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to create notebook: {e}",
            )


@dataclass
class NotebookToPythonTool(Tool):
    """Convert a Jupyter notebook to a Python script."""

    name: str = "notebook.to_python"
    description: str = "Convert a Jupyter notebook to a Python script"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
        ToolParam("output_path", str, "Output path for Python file (optional)", required=False),
    ])

    def execute(
        self,
        path: str,
        output_path: Optional[str] = None,
    ) -> ToolResult:
        """Convert notebook to Python script."""
        try:
            notebook = Notebook.from_file(path)
            script = notebook.to_python_script()

            # Determine output path
            if output_path:
                out_path = Path(output_path)
            else:
                out_path = Path(path).with_suffix(".py")

            # Write the script
            out_path.write_text(script)

            return ToolResult(
                success=True,
                output={
                    "input_path": path,
                    "output_path": str(out_path),
                    "script_length": len(script),
                    "code_cells_converted": len(notebook.get_code_cells()),
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to convert notebook: {e}",
            )


@dataclass
class NotebookClearOutputsTool(Tool):
    """Clear all outputs from a Jupyter notebook."""

    name: str = "notebook.clear_outputs"
    description: str = "Clear all cell outputs from a Jupyter notebook"
    risk_level: RiskLevel = RiskLevel.MODERATE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the notebook file", required=True),
    ])

    def execute(self, path: str) -> ToolResult:
        """Clear notebook outputs."""
        try:
            notebook = Notebook.from_file(path)
            notebook.clear_outputs()
            notebook.save()

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "cells_cleared": len(notebook.cells),
                },
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to clear outputs: {e}",
            )


# Create and register tool instances
notebook_read = NotebookReadTool()
notebook_edit = NotebookEditTool()
notebook_add_cell = NotebookAddCellTool()
notebook_remove_cell = NotebookRemoveCellTool()
notebook_execute = NotebookExecuteTool()
notebook_create = NotebookCreateTool()
notebook_to_python = NotebookToPythonTool()
notebook_clear_outputs = NotebookClearOutputsTool()

registry.register(notebook_read)
registry.register(notebook_edit)
registry.register(notebook_add_cell)
registry.register(notebook_remove_cell)
registry.register(notebook_execute)
registry.register(notebook_create)
registry.register(notebook_to_python)
registry.register(notebook_clear_outputs)


# Convenience functions
def read_notebook(path: str, include_outputs: bool = True) -> ToolResult:
    """Read a Jupyter notebook."""
    return notebook_read.execute(path=path, include_outputs=include_outputs)


def edit_notebook_cell(path: str, cell_index: int, new_source: str) -> ToolResult:
    """Edit a notebook cell."""
    return notebook_edit.execute(path=path, cell_index=cell_index, new_source=new_source)


def execute_notebook(path: str, save_outputs: bool = True) -> ToolResult:
    """Execute a notebook."""
    return notebook_execute.execute(path=path, save_outputs=save_outputs)


def create_notebook(path: str, kernel: str = "python3") -> ToolResult:
    """Create a new notebook."""
    return notebook_create.execute(path=path, kernel=kernel)
