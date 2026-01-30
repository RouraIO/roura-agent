"""
Tests for the Jupyter Notebook tools.

© Roura.io
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from roura_agent.tools.notebook import (
    Notebook,
    NotebookCell,
    CellType,
    NotebookExecutor,
    NotebookReadTool,
    NotebookEditTool,
    NotebookAddCellTool,
    NotebookRemoveCellTool,
    NotebookExecuteTool,
    NotebookCreateTool,
    NotebookToPythonTool,
    NotebookClearOutputsTool,
    get_notebook_executor,
    read_notebook,
    edit_notebook_cell,
    execute_notebook,
    create_notebook,
)


class TestCellType:
    """Tests for CellType enum."""

    def test_cell_types_exist(self):
        """Test all cell types exist."""
        assert CellType.CODE.value == "code"
        assert CellType.MARKDOWN.value == "markdown"
        assert CellType.RAW.value == "raw"


class TestNotebookCell:
    """Tests for NotebookCell."""

    def test_create_cell(self):
        """Test creating a cell."""
        cell = NotebookCell(
            cell_type=CellType.CODE,
            source="print('hello')",
        )
        assert cell.cell_type == CellType.CODE
        assert cell.source == "print('hello')"
        assert cell.outputs == []

    def test_from_dict_code_cell(self):
        """Test creating code cell from dict."""
        data = {
            "cell_type": "code",
            "source": ["print('hello')\n", "print('world')"],
            "execution_count": 1,
            "outputs": [
                {"output_type": "stream", "text": ["hello\nworld\n"]}
            ],
            "metadata": {},
        }
        cell = NotebookCell.from_dict(data)
        assert cell.cell_type == CellType.CODE
        assert cell.source == "print('hello')\nprint('world')"
        assert cell.execution_count == 1

    def test_from_dict_markdown_cell(self):
        """Test creating markdown cell from dict."""
        data = {
            "cell_type": "markdown",
            "source": "# Title",
            "metadata": {},
        }
        cell = NotebookCell.from_dict(data)
        assert cell.cell_type == CellType.MARKDOWN
        assert cell.source == "# Title"

    def test_to_dict(self):
        """Test converting cell to dict."""
        cell = NotebookCell(
            cell_type=CellType.CODE,
            source="x = 1",
            execution_count=5,
        )
        d = cell.to_dict()
        assert d["cell_type"] == "code"
        assert d["source"] == ["x = 1"]
        assert d["execution_count"] == 5

    def test_get_output_text_stream(self):
        """Test getting stream output text."""
        cell = NotebookCell(
            cell_type=CellType.CODE,
            source="print('hello')",
            outputs=[
                {"output_type": "stream", "text": ["hello\n"]}
            ],
        )
        assert cell.get_output_text() == "hello\n"

    def test_get_output_text_execute_result(self):
        """Test getting execute result output."""
        cell = NotebookCell(
            cell_type=CellType.CODE,
            source="1 + 1",
            outputs=[
                {
                    "output_type": "execute_result",
                    "data": {"text/plain": ["2"]},
                }
            ],
        )
        assert cell.get_output_text() == "2"

    def test_get_output_text_error(self):
        """Test getting error output."""
        cell = NotebookCell(
            cell_type=CellType.CODE,
            source="raise Error",
            outputs=[
                {
                    "output_type": "error",
                    "ename": "ValueError",
                    "evalue": "bad value",
                }
            ],
        )
        assert "ValueError: bad value" in cell.get_output_text()

    def test_has_error(self):
        """Test checking for errors."""
        cell_ok = NotebookCell(
            cell_type=CellType.CODE,
            source="x = 1",
            outputs=[{"output_type": "stream", "text": []}],
        )
        assert cell_ok.has_error() is False

        cell_err = NotebookCell(
            cell_type=CellType.CODE,
            source="raise",
            outputs=[{"output_type": "error", "ename": "Error"}],
        )
        assert cell_err.has_error() is True


class TestNotebook:
    """Tests for Notebook."""

    @pytest.fixture
    def sample_notebook_dict(self):
        """Sample notebook data."""
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# My Notebook"],
                    "metadata": {},
                },
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "execution_count": 1,
                    "outputs": [
                        {"output_type": "stream", "text": ["hello\n"]}
                    ],
                    "metadata": {},
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    @pytest.fixture
    def sample_notebook_file(self, sample_notebook_dict):
        """Create a sample notebook file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ipynb", delete=False
        ) as f:
            json.dump(sample_notebook_dict, f)
            return Path(f.name)

    def test_from_file(self, sample_notebook_file):
        """Test loading notebook from file."""
        try:
            nb = Notebook.from_file(sample_notebook_file)
            assert len(nb.cells) == 2
            assert nb.cells[0].cell_type == CellType.MARKDOWN
            assert nb.cells[1].cell_type == CellType.CODE
        finally:
            sample_notebook_file.unlink()

    def test_from_file_not_found(self):
        """Test loading nonexistent notebook."""
        with pytest.raises(FileNotFoundError):
            Notebook.from_file("/nonexistent.ipynb")

    def test_from_file_not_ipynb(self):
        """Test loading non-notebook file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a notebook")
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Not a notebook"):
                Notebook.from_file(path)
        finally:
            path.unlink()

    def test_create_new(self):
        """Test creating new notebook."""
        nb = Notebook.create_new(kernel_name="python3")
        assert len(nb.cells) == 0
        assert nb.get_kernel_name() == "python3"

    def test_to_dict(self, sample_notebook_file):
        """Test converting to dict."""
        try:
            nb = Notebook.from_file(sample_notebook_file)
            d = nb.to_dict()
            assert "cells" in d
            assert "metadata" in d
            assert d["nbformat"] == 4
        finally:
            sample_notebook_file.unlink()

    def test_save(self, sample_notebook_file):
        """Test saving notebook."""
        try:
            nb = Notebook.from_file(sample_notebook_file)
            nb.add_cell("x = 1", CellType.CODE)
            nb.save()

            # Reload and verify
            nb2 = Notebook.from_file(sample_notebook_file)
            assert len(nb2.cells) == 3
        finally:
            sample_notebook_file.unlink()

    def test_add_cell(self):
        """Test adding a cell."""
        nb = Notebook.create_new()
        cell = nb.add_cell("# Header", CellType.MARKDOWN)
        assert len(nb.cells) == 1
        assert cell.source == "# Header"

    def test_add_cell_at_index(self):
        """Test adding cell at specific index."""
        nb = Notebook.create_new()
        nb.add_cell("cell 0")
        nb.add_cell("cell 2")
        nb.add_cell("cell 1", index=1)

        assert nb.cells[1].source == "cell 1"

    def test_remove_cell(self):
        """Test removing a cell."""
        nb = Notebook.create_new()
        nb.add_cell("cell 0")
        nb.add_cell("cell 1")

        removed = nb.remove_cell(0)
        assert removed.source == "cell 0"
        assert len(nb.cells) == 1

    def test_remove_cell_out_of_range(self):
        """Test removing cell at invalid index."""
        nb = Notebook.create_new()
        assert nb.remove_cell(0) is None

    def test_get_cell(self):
        """Test getting a cell."""
        nb = Notebook.create_new()
        nb.add_cell("test")
        assert nb.get_cell(0).source == "test"
        assert nb.get_cell(99) is None

    def test_update_cell(self):
        """Test updating a cell."""
        nb = Notebook.create_new()
        nb.add_cell("original")

        assert nb.update_cell(0, "updated") is True
        assert nb.cells[0].source == "updated"
        assert nb.cells[0].outputs == []

    def test_update_cell_out_of_range(self):
        """Test updating cell at invalid index."""
        nb = Notebook.create_new()
        assert nb.update_cell(0, "test") is False

    def test_get_code_cells(self):
        """Test getting code cells."""
        nb = Notebook.create_new()
        nb.add_cell("# header", CellType.MARKDOWN)
        nb.add_cell("code1", CellType.CODE)
        nb.add_cell("code2", CellType.CODE)

        code_cells = nb.get_code_cells()
        assert len(code_cells) == 2

    def test_get_markdown_cells(self):
        """Test getting markdown cells."""
        nb = Notebook.create_new()
        nb.add_cell("# header", CellType.MARKDOWN)
        nb.add_cell("code", CellType.CODE)

        md_cells = nb.get_markdown_cells()
        assert len(md_cells) == 1

    def test_clear_outputs(self):
        """Test clearing outputs."""
        nb = Notebook.create_new()
        cell = nb.add_cell("print(1)")
        cell.outputs = [{"output_type": "stream", "text": ["1"]}]
        cell.execution_count = 1

        nb.clear_outputs()
        assert nb.cells[0].outputs == []
        assert nb.cells[0].execution_count is None

    def test_to_python_script(self):
        """Test converting to Python script."""
        nb = Notebook.create_new()
        nb.add_cell("# My notebook", CellType.MARKDOWN)
        nb.add_cell("x = 1", CellType.CODE)
        nb.add_cell("print(x)", CellType.CODE)

        script = nb.to_python_script()
        assert "x = 1" in script
        assert "print(x)" in script
        assert "# My notebook" in script


class TestNotebookExecutor:
    """Tests for NotebookExecutor."""

    def test_create_executor(self):
        """Test creating executor."""
        executor = NotebookExecutor(timeout=300)
        assert executor.timeout == 300

    @patch("roura_agent.tools.notebook.subprocess.run")
    def test_check_nbconvert_available(self, mock_run):
        """Test nbconvert availability check."""
        mock_run.return_value = Mock(returncode=0)

        executor = NotebookExecutor()
        assert executor._check_nbconvert() is True

    @patch("roura_agent.tools.notebook.subprocess.run")
    def test_check_nbconvert_not_available(self, mock_run):
        """Test nbconvert not available."""
        mock_run.side_effect = Exception("not found")

        executor = NotebookExecutor()
        assert executor._check_nbconvert() is False


class TestNotebookReadTool:
    """Tests for NotebookReadTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook."""
        data = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["x = 1"],
                    "execution_count": 1,
                    "outputs": [
                        {"output_type": "execute_result", "data": {"text/plain": ["1"]}}
                    ],
                    "metadata": {},
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookReadTool()
        assert tool.name == "notebook.read"
        assert tool.requires_approval is False

    def test_execute_success(self, sample_notebook):
        """Test successful read."""
        try:
            tool = NotebookReadTool()
            result = tool.execute(path=str(sample_notebook))
            assert result.success is True
            assert result.output["cell_count"] == 1
            assert result.output["code_cells"] == 1
            assert len(result.output["cells"]) == 1
        finally:
            sample_notebook.unlink()

    def test_execute_not_found(self):
        """Test reading nonexistent notebook."""
        tool = NotebookReadTool()
        result = tool.execute(path="/nonexistent.ipynb")
        assert result.success is False


class TestNotebookEditTool:
    """Tests for NotebookEditTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook."""
        data = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["x = 1"],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {},
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookEditTool()
        assert tool.name == "notebook.edit"
        assert tool.requires_approval is True

    def test_execute_success(self, sample_notebook):
        """Test successful edit."""
        try:
            tool = NotebookEditTool()
            result = tool.execute(
                path=str(sample_notebook),
                cell_index=0,
                new_source="y = 2",
            )
            assert result.success is True

            # Verify the change
            nb = Notebook.from_file(sample_notebook)
            assert nb.cells[0].source == "y = 2"
        finally:
            sample_notebook.unlink()

    def test_execute_invalid_index(self, sample_notebook):
        """Test editing with invalid index."""
        try:
            tool = NotebookEditTool()
            result = tool.execute(
                path=str(sample_notebook),
                cell_index=99,
                new_source="test",
            )
            assert result.success is False
            assert "out of range" in result.error
        finally:
            sample_notebook.unlink()


class TestNotebookAddCellTool:
    """Tests for NotebookAddCellTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook."""
        data = {
            "cells": [],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookAddCellTool()
        assert tool.name == "notebook.add_cell"
        assert tool.requires_approval is True

    def test_execute_add_code_cell(self, sample_notebook):
        """Test adding a code cell."""
        try:
            tool = NotebookAddCellTool()
            result = tool.execute(
                path=str(sample_notebook),
                source="print('hello')",
                cell_type="code",
            )
            assert result.success is True
            assert result.output["cell_type"] == "code"

            nb = Notebook.from_file(sample_notebook)
            assert len(nb.cells) == 1
        finally:
            sample_notebook.unlink()

    def test_execute_add_markdown_cell(self, sample_notebook):
        """Test adding a markdown cell."""
        try:
            tool = NotebookAddCellTool()
            result = tool.execute(
                path=str(sample_notebook),
                source="# Header",
                cell_type="markdown",
            )
            assert result.success is True
            assert result.output["cell_type"] == "markdown"
        finally:
            sample_notebook.unlink()

    def test_execute_invalid_cell_type(self, sample_notebook):
        """Test adding with invalid cell type."""
        try:
            tool = NotebookAddCellTool()
            result = tool.execute(
                path=str(sample_notebook),
                source="test",
                cell_type="invalid",
            )
            assert result.success is False
            assert "Invalid cell type" in result.error
        finally:
            sample_notebook.unlink()


class TestNotebookRemoveCellTool:
    """Tests for NotebookRemoveCellTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook with cells."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["cell 0"], "outputs": [], "metadata": {}},
                {"cell_type": "code", "source": ["cell 1"], "outputs": [], "metadata": {}},
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookRemoveCellTool()
        assert tool.name == "notebook.remove_cell"
        assert tool.requires_approval is True

    def test_execute_success(self, sample_notebook):
        """Test removing a cell."""
        try:
            tool = NotebookRemoveCellTool()
            result = tool.execute(path=str(sample_notebook), cell_index=0)
            assert result.success is True
            assert result.output["total_cells"] == 1

            nb = Notebook.from_file(sample_notebook)
            assert len(nb.cells) == 1
            assert nb.cells[0].source == "cell 1"
        finally:
            sample_notebook.unlink()


class TestNotebookExecuteTool:
    """Tests for NotebookExecuteTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookExecuteTool()
        assert tool.name == "notebook.execute"
        assert tool.requires_approval is True
        assert tool.requires_confirmation is True  # DANGEROUS


class TestNotebookCreateTool:
    """Tests for NotebookCreateTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookCreateTool()
        assert tool.name == "notebook.create"
        assert tool.requires_approval is True

    def test_execute_success(self):
        """Test creating a notebook."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "new_notebook.ipynb"
            tool = NotebookCreateTool()
            result = tool.execute(path=str(path))

            assert result.success is True
            assert path.exists()

            nb = Notebook.from_file(path)
            assert len(nb.cells) == 0

    def test_execute_adds_extension(self):
        """Test that .ipynb extension is added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notebook"
            tool = NotebookCreateTool()
            result = tool.execute(path=str(path))

            assert result.success is True
            assert Path(result.output["path"]).suffix == ".ipynb"

    def test_execute_file_exists(self):
        """Test creating when file exists."""
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as f:
            path = Path(f.name)

        try:
            tool = NotebookCreateTool()
            result = tool.execute(path=str(path))
            assert result.success is False
            assert "already exists" in result.error
        finally:
            path.unlink()


class TestNotebookToPythonTool:
    """Tests for NotebookToPythonTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook."""
        data = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Header"], "metadata": {}},
                {"cell_type": "code", "source": ["x = 1"], "outputs": [], "metadata": {}},
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookToPythonTool()
        assert tool.name == "notebook.to_python"
        assert tool.requires_approval is False

    def test_execute_success(self, sample_notebook):
        """Test converting to Python."""
        try:
            tool = NotebookToPythonTool()
            result = tool.execute(path=str(sample_notebook))

            assert result.success is True
            out_path = Path(result.output["output_path"])
            assert out_path.exists()

            content = out_path.read_text()
            assert "x = 1" in content
            assert "# Header" in content

            out_path.unlink()
        finally:
            sample_notebook.unlink()


class TestNotebookClearOutputsTool:
    """Tests for NotebookClearOutputsTool."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a notebook with outputs."""
        data = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["print(1)"],
                    "execution_count": 1,
                    "outputs": [{"output_type": "stream", "text": ["1\n"]}],
                    "metadata": {},
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_tool_properties(self):
        """Test tool properties."""
        tool = NotebookClearOutputsTool()
        assert tool.name == "notebook.clear_outputs"
        assert tool.requires_approval is True

    def test_execute_success(self, sample_notebook):
        """Test clearing outputs."""
        try:
            tool = NotebookClearOutputsTool()
            result = tool.execute(path=str(sample_notebook))
            assert result.success is True

            nb = Notebook.from_file(sample_notebook)
            assert nb.cells[0].outputs == []
            assert nb.cells[0].execution_count is None
        finally:
            sample_notebook.unlink()


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.fixture
    def sample_notebook(self):
        """Create a sample notebook."""
        data = {
            "cells": [
                {"cell_type": "code", "source": ["x = 1"], "outputs": [], "metadata": {}}
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_read_notebook(self, sample_notebook):
        """Test read_notebook function."""
        try:
            result = read_notebook(str(sample_notebook))
            assert result.success is True
        finally:
            sample_notebook.unlink()

    def test_edit_notebook_cell(self, sample_notebook):
        """Test edit_notebook_cell function."""
        try:
            result = edit_notebook_cell(str(sample_notebook), 0, "y = 2")
            assert result.success is True
        finally:
            sample_notebook.unlink()

    def test_create_notebook(self):
        """Test create_notebook function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.ipynb"
            result = create_notebook(str(path))
            assert result.success is True
            assert path.exists()

    def test_get_notebook_executor(self):
        """Test get_notebook_executor returns same instance."""
        e1 = get_notebook_executor()
        e2 = get_notebook_executor()
        assert e1 is e2
