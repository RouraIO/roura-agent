"""
Tests for the Image tools.

© Roura.io
"""
import pytest
import base64
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from roura_agent.tools.image import (
    ImageData,
    ImageSource,
    ImageInfo,
    ImageAnalyzer,
    ImageReadTool,
    ImageAnalyzeTool,
    ImageCompareTool,
    ImageToBase64Tool,
    ImageFromUrlTool,
    get_image_analyzer,
    set_image_analyzer,
    read_image,
    analyze_image,
    compare_images,
    _get_image_dimensions,
    SUPPORTED_FORMATS,
)


class TestImageSource:
    """Tests for ImageSource enum."""

    def test_sources_exist(self):
        """Test all image sources exist."""
        assert ImageSource.FILE.value == "file"
        assert ImageSource.URL.value == "url"
        assert ImageSource.BASE64.value == "base64"


class TestSupportedFormats:
    """Tests for supported formats."""

    def test_common_formats_supported(self):
        """Test common image formats are supported."""
        assert ".png" in SUPPORTED_FORMATS
        assert ".jpg" in SUPPORTED_FORMATS
        assert ".jpeg" in SUPPORTED_FORMATS
        assert ".gif" in SUPPORTED_FORMATS
        assert ".webp" in SUPPORTED_FORMATS


class TestImageData:
    """Tests for ImageData."""

    @pytest.fixture
    def sample_png(self):
        """Create a minimal valid PNG file."""
        # Minimal 1x1 red PNG
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        return png_data

    def test_from_file(self, sample_png):
        """Test creating ImageData from file."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(sample_png)
            temp_path = Path(f.name)

        try:
            image = ImageData.from_file(temp_path)
            assert image.source == ImageSource.BASE64
            assert image.media_type == "image/png"
            assert image.width == 1
            assert image.height == 1
        finally:
            temp_path.unlink()

    def test_from_file_not_found(self):
        """Test from_file with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            ImageData.from_file("/nonexistent/path.png")

    def test_from_file_unsupported_format(self):
        """Test from_file with unsupported format."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"not an image")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Unsupported"):
                ImageData.from_file(temp_path)
        finally:
            temp_path.unlink()

    def test_from_url(self):
        """Test creating ImageData from URL."""
        image = ImageData.from_url("https://example.com/image.png")
        assert image.source == ImageSource.URL
        assert image.data == "https://example.com/image.png"
        assert image.media_type == "image/png"

    def test_from_url_invalid(self):
        """Test from_url with invalid URL."""
        with pytest.raises(ValueError, match="Invalid"):
            ImageData.from_url("not-a-url")

    def test_from_base64(self):
        """Test creating ImageData from base64."""
        b64_data = base64.b64encode(b"fake image data").decode()
        image = ImageData.from_base64(b64_data, "image/png")
        assert image.source == ImageSource.BASE64
        assert image.media_type == "image/png"

    def test_from_base64_with_data_url(self):
        """Test from_base64 with data URL prefix."""
        b64_data = base64.b64encode(b"fake image").decode()
        data_url = f"data:image/jpeg;base64,{b64_data}"
        image = ImageData.from_base64(data_url)
        assert image.media_type == "image/jpeg"
        assert image.data == b64_data

    def test_to_anthropic_format_url(self):
        """Test converting URL image to Anthropic format."""
        image = ImageData.from_url("https://example.com/image.png")
        fmt = image.to_anthropic_format()
        assert fmt["type"] == "image"
        assert fmt["source"]["type"] == "url"
        assert fmt["source"]["url"] == "https://example.com/image.png"

    def test_to_anthropic_format_base64(self):
        """Test converting base64 image to Anthropic format."""
        b64_data = base64.b64encode(b"data").decode()
        image = ImageData.from_base64(b64_data, "image/png")
        fmt = image.to_anthropic_format()
        assert fmt["type"] == "image"
        assert fmt["source"]["type"] == "base64"
        assert fmt["source"]["media_type"] == "image/png"

    def test_to_dict(self):
        """Test converting to dictionary."""
        b64_data = base64.b64encode(b"data").decode()
        image = ImageData.from_base64(b64_data, "image/png")
        d = image.to_dict()
        assert d["source"] == "base64"
        assert d["media_type"] == "image/png"
        assert d["data_length"] == len(b64_data)


class TestGetImageDimensions:
    """Tests for _get_image_dimensions helper."""

    def test_png_dimensions(self):
        """Test getting PNG dimensions."""
        # Minimal PNG header with 100x200 dimensions
        png_header = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x64,  # width = 100
            0x00, 0x00, 0x00, 0xC8,  # height = 200
        ])
        width, height = _get_image_dimensions(png_header, "image/png")
        assert width == 100
        assert height == 200

    def test_gif_dimensions(self):
        """Test getting GIF dimensions."""
        gif_header = b"GIF89a" + bytes([
            0x64, 0x00,  # width = 100 (little endian)
            0xC8, 0x00,  # height = 200 (little endian)
        ])
        width, height = _get_image_dimensions(gif_header, "image/gif")
        assert width == 100
        assert height == 200

    def test_invalid_data(self):
        """Test with invalid image data."""
        width, height = _get_image_dimensions(b"not an image", "image/png")
        assert width is None
        assert height is None


class TestImageInfo:
    """Tests for ImageInfo dataclass."""

    def test_create_info(self):
        """Test creating ImageInfo."""
        info = ImageInfo(
            path="/test/image.png",
            url=None,
            media_type="image/png",
            width=100,
            height=200,
            file_size=1024,
        )
        assert info.path == "/test/image.png"
        assert info.width == 100
        assert info.height == 200
        assert info.objects == []


class TestImageAnalyzer:
    """Tests for ImageAnalyzer."""

    def test_create_analyzer(self):
        """Test creating analyzer."""
        analyzer = ImageAnalyzer()
        assert analyzer._llm_callback is None

    def test_set_llm_callback(self):
        """Test setting LLM callback."""
        analyzer = ImageAnalyzer()
        callback = Mock()
        analyzer.set_llm_callback(callback)
        assert analyzer._llm_callback is callback

    def test_analyze_without_callback(self):
        """Test analyze without LLM callback."""
        analyzer = ImageAnalyzer()
        b64_data = base64.b64encode(b"data").decode()
        image = ImageData.from_base64(b64_data, "image/png")

        info = analyzer.analyze(image)
        assert "not configured" in info.analysis

    def test_analyze_with_callback(self):
        """Test analyze with LLM callback."""
        callback = Mock(return_value={
            "analysis": "A test image",
            "objects": ["object1", "object2"],
        })
        analyzer = ImageAnalyzer(llm_callback=callback)

        b64_data = base64.b64encode(b"data").decode()
        image = ImageData.from_base64(b64_data, "image/png")

        info = analyzer.analyze(image)
        assert info.analysis == "A test image"
        assert info.objects == ["object1", "object2"]
        callback.assert_called_once()

    def test_compare_without_callback(self):
        """Test compare without LLM callback."""
        analyzer = ImageAnalyzer()
        images = [
            ImageData.from_base64(base64.b64encode(b"1").decode(), "image/png"),
            ImageData.from_base64(base64.b64encode(b"2").decode(), "image/png"),
        ]

        result = analyzer.compare(images)
        assert "not configured" in result["comparison"]
        assert result["image_count"] == 2

    def test_compare_with_callback(self):
        """Test compare with LLM callback."""
        callback = Mock(return_value="Images are similar")
        analyzer = ImageAnalyzer(llm_callback=callback)

        images = [
            ImageData.from_base64(base64.b64encode(b"1").decode(), "image/png"),
            ImageData.from_base64(base64.b64encode(b"2").decode(), "image/png"),
        ]

        result = analyzer.compare(images)
        assert result["comparison"] == "Images are similar"


class TestImageReadTool:
    """Tests for ImageReadTool."""

    @pytest.fixture
    def sample_png(self):
        """Create a sample PNG file."""
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        return png_data

    def test_tool_properties(self):
        """Test tool properties."""
        tool = ImageReadTool()
        assert tool.name == "image.read"
        assert tool.requires_approval is False

    def test_execute_success(self, sample_png):
        """Test successful image read."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(sample_png)
            temp_path = f.name

        try:
            tool = ImageReadTool()
            result = tool.execute(path=temp_path)
            assert result.success is True
            assert result.output["media_type"] == "image/png"
            assert result.output["format"] == "png"
        finally:
            Path(temp_path).unlink()

    def test_execute_not_found(self):
        """Test with nonexistent file."""
        tool = ImageReadTool()
        result = tool.execute(path="/nonexistent/image.png")
        assert result.success is False
        assert "not found" in result.error.lower()


class TestImageAnalyzeTool:
    """Tests for ImageAnalyzeTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = ImageAnalyzeTool()
        assert tool.name == "image.analyze"
        assert tool.requires_approval is False

    def test_execute_not_found(self):
        """Test with nonexistent file."""
        tool = ImageAnalyzeTool()
        result = tool.execute(path="/nonexistent/image.png")
        assert result.success is False


class TestImageCompareTool:
    """Tests for ImageCompareTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = ImageCompareTool()
        assert tool.name == "image.compare"
        assert tool.requires_approval is False

    def test_execute_needs_multiple_images(self):
        """Test that comparison needs at least 2 images."""
        tool = ImageCompareTool()
        result = tool.execute(paths=["single.png"])
        assert result.success is False
        assert "2 images required" in result.error


class TestImageToBase64Tool:
    """Tests for ImageToBase64Tool."""

    @pytest.fixture
    def sample_png(self):
        """Create a sample PNG file."""
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        return png_data

    def test_tool_properties(self):
        """Test tool properties."""
        tool = ImageToBase64Tool()
        assert tool.name == "image.to_base64"
        assert tool.requires_approval is False

    def test_execute_with_data_url(self, sample_png):
        """Test conversion with data URL prefix."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(sample_png)
            temp_path = f.name

        try:
            tool = ImageToBase64Tool()
            result = tool.execute(path=temp_path, include_data_url=True)
            assert result.success is True
            assert result.output["data"].startswith("data:image/png;base64,")
        finally:
            Path(temp_path).unlink()

    def test_execute_without_data_url(self, sample_png):
        """Test conversion without data URL prefix."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(sample_png)
            temp_path = f.name

        try:
            tool = ImageToBase64Tool()
            result = tool.execute(path=temp_path, include_data_url=False)
            assert result.success is True
            assert not result.output["data"].startswith("data:")
        finally:
            Path(temp_path).unlink()


class TestImageFromUrlTool:
    """Tests for ImageFromUrlTool."""

    def test_tool_properties(self):
        """Test tool properties."""
        tool = ImageFromUrlTool()
        assert tool.name == "image.from_url"
        assert tool.requires_approval is False

    @patch("httpx.Client")
    def test_execute_success(self, mock_client_class):
        """Test successful URL fetch."""
        mock_response = Mock()
        mock_response.headers = {"content-type": "image/png"}
        mock_response.content = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        ] + [0] * 20)
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client_class.return_value = mock_client

        tool = ImageFromUrlTool()
        result = tool.execute(url="https://example.com/image.png")
        assert result.success is True
        assert result.output["media_type"] == "image/png"

    @patch("httpx.Client")
    def test_execute_not_image(self, mock_client_class):
        """Test URL that doesn't return an image."""
        mock_response = Mock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client_class.return_value = mock_client

        tool = ImageFromUrlTool()
        result = tool.execute(url="https://example.com/page.html")
        assert result.success is False
        assert "not point to an image" in result.error


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.fixture
    def sample_png(self):
        """Create a sample PNG file."""
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x18, 0xDD,
            0x8D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
        ])
        return png_data

    def test_read_image(self, sample_png):
        """Test read_image convenience function."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(sample_png)
            temp_path = f.name

        try:
            result = read_image(temp_path)
            assert result.success is True
        finally:
            Path(temp_path).unlink()

    def test_get_image_analyzer(self):
        """Test get_image_analyzer returns singleton."""
        a1 = get_image_analyzer()
        a2 = get_image_analyzer()
        assert a1 is a2

    def test_set_image_analyzer(self):
        """Test setting custom analyzer."""
        custom = ImageAnalyzer(llm_callback=Mock())
        set_image_analyzer(custom)
        assert get_image_analyzer() is custom
