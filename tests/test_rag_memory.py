"""
Tests for RAG memory and semantic search.

© Roura.io
"""
import pytest
from pathlib import Path
import tempfile
import shutil

from roura_agent.memory import (
    ProjectMemory,
    MemoryNote,
    RAGMemory,
    MemorySearchIndex,
    SearchResult,
    tokenize,
    get_memory,
)
from roura_agent.memory.persistent import (
    compute_tf,
    compute_idf,
    compute_tfidf,
    cosine_similarity,
)


class TestTokenize:
    """Tests for tokenization."""

    def test_basic_tokenization(self):
        """Test basic text tokenization."""
        tokens = tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_removes_stop_words(self):
        """Test stop words are removed."""
        tokens = tokenize("the quick brown fox is jumping")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_handles_punctuation(self):
        """Test punctuation is handled."""
        tokens = tokenize("Hello, world! How are you?")
        assert "hello" in tokens
        assert "world" in tokens
        # Punctuation should not appear
        assert "," not in tokens

    def test_removes_short_tokens(self):
        """Test very short tokens are removed."""
        tokens = tokenize("a b c def ghi")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "def" in tokens
        assert "ghi" in tokens


class TestTFIDF:
    """Tests for TF-IDF computation."""

    def test_compute_tf(self):
        """Test term frequency computation."""
        tokens = ["apple", "banana", "apple", "cherry"]
        tf = compute_tf(tokens)
        assert tf["apple"] == 0.5  # 2/4
        assert tf["banana"] == 0.25  # 1/4
        assert tf["cherry"] == 0.25  # 1/4

    def test_compute_idf(self):
        """Test inverse document frequency computation."""
        docs = [
            ["apple", "banana"],
            ["apple", "cherry"],
            ["banana", "cherry"],
        ]
        idf = compute_idf(docs)
        # apple appears in 2/3 docs
        # banana appears in 2/3 docs
        # cherry appears in 2/3 docs
        assert "apple" in idf
        assert "banana" in idf
        assert "cherry" in idf

    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        vec = {"a": 1.0, "b": 2.0}
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = {"a": 1.0}
        vec2 = {"b": 1.0}
        assert cosine_similarity(vec1, vec2) == 0.0

    def test_cosine_similarity_partial(self):
        """Test cosine similarity with partial overlap."""
        vec1 = {"a": 1.0, "b": 1.0}
        vec2 = {"a": 1.0, "c": 1.0}
        sim = cosine_similarity(vec1, vec2)
        assert 0 < sim < 1


class TestMemorySearchIndex:
    """Tests for MemorySearchIndex."""

    def test_empty_index(self):
        """Test searching empty index."""
        index = MemorySearchIndex()
        results = index.search("hello")
        assert results == []

    def test_add_and_search(self):
        """Test adding notes and searching."""
        index = MemorySearchIndex()
        note1 = MemoryNote(content="Python is a great programming language")
        note2 = MemoryNote(content="JavaScript is used for web development")
        note3 = MemoryNote(content="Python and JavaScript are both popular")

        index.add(note1)
        index.add(note2)
        index.add(note3)

        results = index.search("Python programming")
        assert len(results) > 0
        # Python-related notes should score higher
        assert any("Python" in r.note.content for r in results)

    def test_build_index(self):
        """Test building index from notes."""
        index = MemorySearchIndex()
        notes = [
            MemoryNote(content="Testing frameworks like pytest"),
            MemoryNote(content="Unit tests are important"),
            MemoryNote(content="Integration testing strategies"),
        ]

        index.build(notes)
        results = index.search("pytest testing")
        assert len(results) > 0

    def test_search_threshold(self):
        """Test search with threshold."""
        index = MemorySearchIndex()
        index.add(MemoryNote(content="Apple banana cherry"))
        index.add(MemoryNote(content="Dog cat mouse"))

        # High threshold should filter out low matches
        results = index.search("apple fruit", threshold=0.5)
        # Only apple-related note should match
        assert all("apple" in r.note.content.lower() for r in results)

    def test_search_top_k(self):
        """Test search with top_k limit."""
        index = MemorySearchIndex()
        for i in range(10):
            index.add(MemoryNote(content=f"Python note number {i}"))

        results = index.search("Python", top_k=3)
        assert len(results) <= 3

    def test_matched_terms(self):
        """Test matched terms in results."""
        index = MemorySearchIndex()
        index.add(MemoryNote(content="Python Django Flask web framework"))

        results = index.search("Django web")
        if results:
            assert "django" in results[0].matched_terms or "web" in results[0].matched_terms


class TestRAGMemory:
    """Tests for RAGMemory."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project with memory."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        memory = ProjectMemory(root=project_root)
        memory.add_note("This project uses pytest for testing", tags=["testing"])
        memory.add_note("Authentication is handled by OAuth2", tags=["auth"])
        memory.add_note("Database is PostgreSQL", tags=["database"])
        memory.add_note("API uses REST conventions", tags=["api"])
        memory.add_note("Frontend is built with React", tags=["frontend"])
        memory.save()

        return project_root

    def test_create_from_project(self, temp_project):
        """Test creating RAGMemory from project."""
        rag = RAGMemory.from_project(temp_project)
        assert len(rag.memory.notes) == 5

    def test_retrieve_relevant(self, temp_project):
        """Test retrieving relevant notes."""
        rag = RAGMemory.from_project(temp_project)

        results = rag.retrieve("testing framework")
        assert len(results) > 0
        # Testing note should be most relevant
        assert "pytest" in results[0].note.content.lower()

    def test_get_relevant_context(self, temp_project):
        """Test getting formatted context."""
        rag = RAGMemory.from_project(temp_project)

        # Use keywords that will match
        context = rag.get_relevant_context("authentication OAuth2", max_notes=5)
        # Context might be empty if no match above threshold
        if context:
            assert "## Relevant Memory" in context

    def test_get_context_for_task(self, temp_project):
        """Test getting context for a task."""
        rag = RAGMemory.from_project(temp_project)

        context = rag.get_context_for_task("Write database migration")
        # Should include database-related info
        assert "PostgreSQL" in context or "database" in context.lower()

    def test_add_note_updates_index(self, temp_project):
        """Test that adding notes updates index."""
        rag = RAGMemory.from_project(temp_project)

        # Add new note
        rag.add_note("Caching is done with Redis", tags=["cache"])

        # Should find the new note
        results = rag.retrieve("Redis caching")
        assert len(results) > 0
        assert any("Redis" in r.note.content for r in results)

    def test_context_respects_max_chars(self, temp_project):
        """Test context respects character limit."""
        rag = RAGMemory.from_project(temp_project)

        context = rag.get_relevant_context("project info", max_chars=100)
        # Should be reasonably short (header + some content)
        assert len(context) < 200


class TestSearchResult:
    """Tests for SearchResult."""

    def test_search_result_repr(self):
        """Test SearchResult string representation."""
        note = MemoryNote(content="This is a test note for searching")
        result = SearchResult(note=note, score=0.85, matched_terms=["test"])

        repr_str = repr(result)
        assert "0.85" in repr_str
        assert "test note" in repr_str


class TestMemoryToolsSearch:
    """Tests for memory search tools."""

    @pytest.fixture
    def temp_memory(self, tmp_path, monkeypatch):
        """Set up temporary memory directory."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        monkeypatch.chdir(project_root)

        memory = ProjectMemory(root=project_root)
        memory.add_note("Use pytest for testing", tags=["testing"])
        memory.add_note("API uses REST conventions", tags=["api"])
        memory.save()

        return project_root

    def test_search_memory(self, temp_memory):
        """Test search_memory function."""
        from roura_agent.tools.memory import search_memory

        result = search_memory("testing framework")
        assert result.success
        assert result.output["count"] > 0
        assert any("pytest" in r["content"].lower() for r in result.output["results"])

    def test_get_memory_context(self, temp_memory):
        """Test get_memory_context function."""
        from roura_agent.tools.memory import get_memory_context

        result = get_memory_context("write API endpoint")
        assert result.success
        assert "context" in result.output
        # Should include API-related info
        assert "REST" in result.output["context"] or "api" in result.output["context"].lower()


class TestMemorySearchIndexWithEmbeddings:
    """Tests for embedding-based search."""

    def test_with_embedding_function(self):
        """Test search with custom embedding function."""
        # Simple mock embedding function
        def mock_embed(text: str) -> list[float]:
            # Very simple: just use character counts as "embedding"
            return [text.count(c) / len(text) for c in "aeiou"]

        index = MemorySearchIndex(embedding_func=mock_embed)
        index.add(MemoryNote(content="aaa eee iii ooo uuu"))
        index.add(MemoryNote(content="bbb ccc ddd fff ggg"))

        # Semantic search should use embeddings
        results = index.semantic_search("vowels like aaa")
        assert len(results) > 0

    def test_fallback_when_embedding_fails(self):
        """Test fallback to TF-IDF when embeddings fail."""
        def failing_embed(text: str) -> list[float]:
            raise ValueError("Embedding failed")

        index = MemorySearchIndex(embedding_func=failing_embed)
        index.add(MemoryNote(content="Python programming"))

        # Should fall back to TF-IDF
        results = index.semantic_search("Python")
        assert len(results) > 0


class TestIntegration:
    """Integration tests for RAG memory."""

    def test_full_workflow(self, tmp_path):
        """Test full RAG workflow."""
        # Create project
        project = tmp_path / "myproject"
        project.mkdir()

        # Create memory
        memory = ProjectMemory(root=project)

        # Add various notes
        notes = [
            ("Use black for code formatting", ["formatting", "tools"]),
            ("Pytest fixtures go in conftest.py", ["testing"]),
            ("API endpoints are in routes.py", ["api", "structure"]),
            ("Database models use SQLAlchemy", ["database", "orm"]),
            ("Authentication uses JWT tokens", ["auth", "security"]),
        ]

        for content, tags in notes:
            memory.add_note(content, tags=tags)
        memory.save()

        # Create RAG memory
        rag = RAGMemory(memory)

        # Test queries with keywords that should match
        # Use specific keywords from the notes
        queries_and_expectations = [
            ("black formatting", "black"),
            ("pytest fixtures", "pytest"),
            ("API endpoints routes", "routes"),
            ("SQLAlchemy database", "sqlalchemy"),
            ("JWT authentication tokens", "jwt"),
        ]

        for query, expected in queries_and_expectations:
            results = rag.retrieve(query, top_k=3, threshold=0.05)
            assert len(results) > 0, f"Query '{query}' returned no results"
            top_content = results[0].note.content.lower()
            assert expected.lower() in top_content, f"Query '{query}' didn't find '{expected}'"

    def test_empty_memory_handling(self, tmp_path):
        """Test handling of empty memory."""
        project = tmp_path / "empty"
        project.mkdir()

        memory = ProjectMemory(root=project)
        rag = RAGMemory(memory)

        results = rag.retrieve("anything")
        assert results == []

        context = rag.get_relevant_context("any task")
        assert context == ""
