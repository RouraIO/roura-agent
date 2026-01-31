"""
Roura Agent Image Tools - Image analysis and understanding.

Provides tools for analyzing images using vision models.

© Roura.io
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import RiskLevel, Tool, ToolParam, ToolResult, registry

# Supported image formats
SUPPORTED_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

# Maximum image size (20MB)
MAX_IMAGE_SIZE = 20 * 1024 * 1024


class ImageSource(Enum):
    """Source type for an image."""
    FILE = "file"
    URL = "url"
    BASE64 = "base64"


@dataclass
class ImageData:
    """Represents image data for analysis."""
    source: ImageSource
    data: str  # File path, URL, or base64 data
    media_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> ImageData:
        """Create ImageData from a file path."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported image format: {suffix}")

        # Check file size
        if path.stat().st_size > MAX_IMAGE_SIZE:
            raise ValueError(f"Image too large: {path.stat().st_size} bytes (max {MAX_IMAGE_SIZE})")

        media_type = SUPPORTED_FORMATS[suffix]

        # Read and encode the image
        with open(path, "rb") as f:
            image_bytes = f.read()

        base64_data = base64.b64encode(image_bytes).decode("utf-8")

        # Try to get dimensions using basic header parsing
        width, height = _get_image_dimensions(image_bytes, media_type)

        return cls(
            source=ImageSource.BASE64,
            data=base64_data,
            media_type=media_type,
            width=width,
            height=height,
        )

    @classmethod
    def from_url(cls, url: str) -> ImageData:
        """Create ImageData from a URL."""
        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid image URL: {url}")

        # Guess media type from URL extension
        media_type = None
        for ext, mime in SUPPORTED_FORMATS.items():
            if url.lower().endswith(ext) or f"{ext}?" in url.lower():
                media_type = mime
                break

        return cls(
            source=ImageSource.URL,
            data=url,
            media_type=media_type,
        )

    @classmethod
    def from_base64(cls, data: str, media_type: str = "image/png") -> ImageData:
        """Create ImageData from base64 encoded data."""
        # Remove data URL prefix if present
        if data.startswith("data:"):
            match = re.match(r"data:([^;]+);base64,(.+)", data)
            if match:
                media_type = match.group(1)
                data = match.group(2)

        return cls(
            source=ImageSource.BASE64,
            data=data,
            media_type=media_type,
        )

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic API image format."""
        if self.source == ImageSource.URL:
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": self.data,
                },
            }
        else:  # BASE64
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.media_type or "image/png",
                    "data": self.data,
                },
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "source": self.source.value,
            "media_type": self.media_type,
            "width": self.width,
            "height": self.height,
            "data_length": len(self.data) if self.source == ImageSource.BASE64 else None,
            "url": self.data if self.source == ImageSource.URL else None,
        }


def _get_image_dimensions(data: bytes, media_type: str) -> tuple[Optional[int], Optional[int]]:
    """
    Get image dimensions from binary data using basic header parsing.
    Returns (width, height) or (None, None) if unable to determine.
    """
    try:
        if media_type == "image/png":
            # PNG: width/height at bytes 16-23
            if len(data) >= 24 and data[:8] == b'\x89PNG\r\n\x1a\n':
                width = int.from_bytes(data[16:20], "big")
                height = int.from_bytes(data[20:24], "big")
                return width, height

        elif media_type in ("image/jpeg", "image/jpg"):
            # JPEG: find SOF0 marker
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF:
                    marker = data[i + 1]
                    if marker in (0xC0, 0xC1, 0xC2):  # SOF markers
                        height = int.from_bytes(data[i + 5:i + 7], "big")
                        width = int.from_bytes(data[i + 7:i + 9], "big")
                        return width, height
                    elif marker in (0xD8, 0xD9):  # SOI, EOI
                        i += 2
                    elif marker == 0xFF:
                        i += 1
                    else:
                        length = int.from_bytes(data[i + 2:i + 4], "big")
                        i += 2 + length
                else:
                    i += 1

        elif media_type == "image/gif":
            # GIF: width/height at bytes 6-9
            if len(data) >= 10 and data[:6] in (b"GIF87a", b"GIF89a"):
                width = int.from_bytes(data[6:8], "little")
                height = int.from_bytes(data[8:10], "little")
                return width, height

        elif media_type == "image/webp":
            # WebP: more complex, basic check for VP8
            if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                if data[12:16] == b"VP8 ":
                    # Lossy VP8
                    width = (data[26] | (data[27] << 8)) & 0x3FFF
                    height = (data[28] | (data[29] << 8)) & 0x3FFF
                    return width, height

    except Exception:
        pass

    return None, None


@dataclass
class ImageInfo:
    """Information about an analyzed image."""
    path: Optional[str]
    url: Optional[str]
    media_type: str
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    analysis: Optional[str] = None
    objects: List[str] = field(default_factory=list)
    text_content: Optional[str] = None
    colors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class ImageAnalyzer:
    """
    Analyzes images using vision models.

    This is a framework class - actual analysis requires an LLM with vision capabilities.
    """

    def __init__(self, llm_callback=None):
        """
        Initialize the analyzer.

        Args:
            llm_callback: Optional callback function that takes (prompt, images) and returns analysis.
                          If not provided, basic analysis is returned.
        """
        self._llm_callback = llm_callback

    def set_llm_callback(self, callback) -> None:
        """Set the LLM callback for vision analysis."""
        self._llm_callback = callback

    def analyze(
        self,
        image: ImageData,
        prompt: Optional[str] = None,
        extract_text: bool = False,
        identify_objects: bool = False,
    ) -> ImageInfo:
        """
        Analyze an image.

        Args:
            image: The image to analyze
            prompt: Optional prompt for specific analysis
            extract_text: Whether to extract text from the image (OCR)
            identify_objects: Whether to identify objects in the image

        Returns:
            ImageInfo with analysis results
        """
        info = ImageInfo(
            path=image.data if image.source == ImageSource.FILE else None,
            url=image.data if image.source == ImageSource.URL else None,
            media_type=image.media_type or "unknown",
            width=image.width,
            height=image.height,
            file_size=len(base64.b64decode(image.data)) if image.source == ImageSource.BASE64 else None,
        )

        # Build the analysis prompt
        analysis_prompt = prompt or "Describe this image in detail."

        if extract_text:
            analysis_prompt += "\n\nAlso extract any text visible in the image."

        if identify_objects:
            analysis_prompt += "\n\nList all identifiable objects in the image."

        # If we have an LLM callback, use it
        if self._llm_callback:
            try:
                result = self._llm_callback(analysis_prompt, [image.to_anthropic_format()])
                if isinstance(result, dict):
                    info.analysis = result.get("analysis")
                    info.text_content = result.get("text")
                    info.objects = result.get("objects", [])
                    info.tags = result.get("tags", [])
                else:
                    info.analysis = str(result)
            except Exception as e:
                info.analysis = f"Analysis failed: {e}"
        else:
            # Return basic info without LLM analysis
            info.analysis = "LLM callback not configured for detailed analysis"

        return info

    def compare(
        self,
        images: List[ImageData],
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare multiple images.

        Args:
            images: List of images to compare
            prompt: Optional prompt for comparison

        Returns:
            Comparison results
        """
        comparison_prompt = prompt or "Compare these images and describe their similarities and differences."

        if self._llm_callback:
            try:
                image_formats = [img.to_anthropic_format() for img in images]
                result = self._llm_callback(comparison_prompt, image_formats)
                return {
                    "comparison": result if isinstance(result, str) else result.get("comparison"),
                    "image_count": len(images),
                }
            except Exception as e:
                return {
                    "comparison": f"Comparison failed: {e}",
                    "image_count": len(images),
                }
        else:
            return {
                "comparison": "LLM callback not configured for comparison",
                "image_count": len(images),
            }


# Global analyzer instance
_analyzer: Optional[ImageAnalyzer] = None


def create_vision_callback():
    """
    Create an LLM callback for vision analysis.

    This creates a callback function that uses the configured LLM provider
    to analyze images using Claude's vision capabilities.

    Returns:
        A callback function that takes (prompt, images) and returns analysis
    """
    def vision_callback(prompt: str, images: list[dict]) -> str:
        """Analyze images using the LLM provider."""
        try:
            import os

            from ..llm.base import ProviderType, get_provider

            # Prefer Anthropic for vision (best vision capabilities)
            if os.getenv("ANTHROPIC_API_KEY"):
                provider = get_provider(ProviderType.ANTHROPIC, check_license=False)
            else:
                # Try to get any available provider
                provider = get_provider(check_license=False)

            # Check if provider supports vision
            if not provider.supports_vision():
                return f"Provider {provider.provider_type.value} does not support vision analysis"

            # Use chat_with_images for vision-capable providers
            response = provider.chat_with_images(
                prompt=prompt,
                images=images,
                system_prompt="You are a helpful assistant that analyzes images. Describe what you see clearly and concisely.",
            )

            if response.error:
                return f"Analysis failed: {response.error}"

            return response.content

        except ImportError:
            return "LLM provider not available for vision analysis"
        except Exception as e:
            return f"Vision analysis error: {str(e)}"

    return vision_callback


def get_image_analyzer() -> ImageAnalyzer:
    """Get the global image analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = ImageAnalyzer()
        # Try to set up vision callback
        try:
            callback = create_vision_callback()
            _analyzer.set_llm_callback(callback)
        except Exception:
            pass  # Vision callback not available
    return _analyzer


def set_image_analyzer(analyzer: ImageAnalyzer) -> None:
    """Set the global image analyzer instance."""
    global _analyzer
    _analyzer = analyzer


# Tool implementations

@dataclass
class ImageReadTool(Tool):
    """Read and get information about an image file."""

    name: str = "image.read"
    description: str = "Read an image file and get its basic information (dimensions, format, etc.)"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the image file", required=True),
    ])

    def execute(self, path: str) -> ToolResult:
        """Read an image file."""
        try:
            image = ImageData.from_file(path)

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "media_type": image.media_type,
                    "width": image.width,
                    "height": image.height,
                    "format": Path(path).suffix.lower()[1:],
                    "size_bytes": len(base64.b64decode(image.data)),
                },
            )
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to read image: {e}",
            )


@dataclass
class ImageAnalyzeTool(Tool):
    """Analyze an image using vision capabilities."""

    name: str = "image.analyze"
    description: str = "Analyze an image to describe its contents, extract text, or identify objects"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the image file", required=True),
        ToolParam("prompt", str, "Analysis prompt (optional)", required=False),
        ToolParam("extract_text", bool, "Extract text from image (OCR)", required=False, default=False),
        ToolParam("identify_objects", bool, "Identify objects in image", required=False, default=False),
    ])

    def execute(
        self,
        path: str,
        prompt: Optional[str] = None,
        extract_text: bool = False,
        identify_objects: bool = False,
    ) -> ToolResult:
        """Analyze an image."""
        try:
            image = ImageData.from_file(path)
            analyzer = get_image_analyzer()

            info = analyzer.analyze(
                image=image,
                prompt=prompt,
                extract_text=extract_text,
                identify_objects=identify_objects,
            )

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "media_type": info.media_type,
                    "width": info.width,
                    "height": info.height,
                    "analysis": info.analysis,
                    "text_content": info.text_content,
                    "objects": info.objects,
                    "tags": info.tags,
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
                error=f"Failed to analyze image: {e}",
            )


@dataclass
class ImageCompareTool(Tool):
    """Compare multiple images."""

    name: str = "image.compare"
    description: str = "Compare multiple images and describe their similarities and differences"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("paths", list, "List of image file paths to compare", required=True),
        ToolParam("prompt", str, "Comparison prompt (optional)", required=False),
    ])

    def execute(
        self,
        paths: List[str],
        prompt: Optional[str] = None,
    ) -> ToolResult:
        """Compare multiple images."""
        if len(paths) < 2:
            return ToolResult(
                success=False,
                output=None,
                error="At least 2 images required for comparison",
            )

        try:
            images = [ImageData.from_file(p) for p in paths]
            analyzer = get_image_analyzer()

            result = analyzer.compare(images, prompt)

            return ToolResult(
                success=True,
                output={
                    "paths": paths,
                    "comparison": result.get("comparison"),
                    "image_count": result.get("image_count"),
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
                error=f"Failed to compare images: {e}",
            )


@dataclass
class ImageToBase64Tool(Tool):
    """Convert an image to base64 encoding."""

    name: str = "image.to_base64"
    description: str = "Convert an image file to base64 encoding"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("path", str, "Path to the image file", required=True),
        ToolParam("include_data_url", bool, "Include data URL prefix", required=False, default=True),
    ])

    def execute(
        self,
        path: str,
        include_data_url: bool = True,
    ) -> ToolResult:
        """Convert image to base64."""
        try:
            image = ImageData.from_file(path)

            if include_data_url:
                data = f"data:{image.media_type};base64,{image.data}"
            else:
                data = image.data

            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "media_type": image.media_type,
                    "base64_length": len(image.data),
                    "data": data,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to convert image: {e}",
            )


@dataclass
class ImageFromUrlTool(Tool):
    """Fetch and analyze an image from a URL."""

    name: str = "image.from_url"
    description: str = "Fetch an image from a URL and get its information"
    risk_level: RiskLevel = RiskLevel.SAFE
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("url", str, "URL of the image", required=True),
    ])

    def execute(self, url: str) -> ToolResult:
        """Fetch image from URL."""
        try:
            import httpx

            # Fetch the image
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"URL does not point to an image: {content_type}",
                    )

                # Get image data
                image_bytes = response.content
                if len(image_bytes) > MAX_IMAGE_SIZE:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Image too large: {len(image_bytes)} bytes",
                    )

                # Determine media type
                media_type = content_type.split(";")[0].strip()
                width, height = _get_image_dimensions(image_bytes, media_type)

                return ToolResult(
                    success=True,
                    output={
                        "url": url,
                        "media_type": media_type,
                        "width": width,
                        "height": height,
                        "size_bytes": len(image_bytes),
                    },
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to fetch image: {e}",
            )


# Create and register tool instances
image_read = ImageReadTool()
image_analyze = ImageAnalyzeTool()
image_compare = ImageCompareTool()
image_to_base64 = ImageToBase64Tool()
image_from_url = ImageFromUrlTool()

registry.register(image_read)
registry.register(image_analyze)
registry.register(image_compare)
registry.register(image_to_base64)
registry.register(image_from_url)


# Convenience functions
def read_image(path: str) -> ToolResult:
    """Read an image file."""
    return image_read.execute(path=path)


def analyze_image(
    path: str,
    prompt: Optional[str] = None,
    extract_text: bool = False,
    identify_objects: bool = False,
) -> ToolResult:
    """Analyze an image."""
    return image_analyze.execute(
        path=path,
        prompt=prompt,
        extract_text=extract_text,
        identify_objects=identify_objects,
    )


def compare_images(paths: List[str], prompt: Optional[str] = None) -> ToolResult:
    """Compare multiple images."""
    return image_compare.execute(paths=paths, prompt=prompt)
