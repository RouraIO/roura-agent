# Image Understanding Module

The `roura_agent.tools.image` module provides image reading, analysis, and vision AI capabilities.

## Overview

This module enables Roura Agent to:

- Read and decode images from files and URLs
- Analyze images using vision AI models
- Compare multiple images
- Extract text and understand visual content

## Quick Start

### CLI Usage

```bash
# Read an image (displays info)
roura-agent image read screenshot.png

# Analyze an image with a prompt
roura-agent image analyze screenshot.png "What errors are shown?"

# Compare two images
roura-agent image compare before.png after.png "What changed?"
```

### Programmatic Usage

```python
from roura_agent.tools.image import read_image, analyze_image, compare_images

# Read image metadata
info = read_image("screenshot.png")
print(f"Size: {info.width}x{info.height}")
print(f"Format: {info.format}")

# Analyze with vision AI
result = await analyze_image(
    path="ui_mockup.png",
    prompt="Describe the UI layout and suggest improvements",
)
print(result)

# Compare images
diff = await compare_images(
    path1="before.png",
    path2="after.png",
    prompt="What visual changes were made?",
)
print(diff)
```

## Image Data Types

### ImageData

Container for image content.

```python
from roura_agent.tools.image import ImageData, ImageSource

@dataclass
class ImageData:
    content: bytes           # Raw image bytes
    source: ImageSource      # Source type
    path: Optional[str]      # File path if from file
    url: Optional[str]       # URL if from web
    mime_type: str           # e.g., "image/png"
```

### ImageSource

```python
from roura_agent.tools.image import ImageSource

class ImageSource(Enum):
    FILE = "file"
    URL = "url"
    BASE64 = "base64"
    CLIPBOARD = "clipboard"
```

### ImageInfo

Metadata about an image.

```python
from roura_agent.tools.image import ImageInfo

@dataclass
class ImageInfo:
    width: int
    height: int
    format: str              # PNG, JPEG, etc.
    mode: str                # RGB, RGBA, etc.
    size_bytes: int
    path: Optional[str]
```

## Reading Images

### From File

```python
from roura_agent.tools.image import read_image

# Get image info
info = read_image("photo.jpg")
print(f"Dimensions: {info.width}x{info.height}")
print(f"Format: {info.format}")
print(f"Size: {info.size_bytes} bytes")
```

### From URL

```python
from roura_agent.tools.image import ImageFromUrlTool

tool = ImageFromUrlTool()
result = await tool.execute(url="https://example.com/image.png")

if result.success:
    image_data = result.output["image"]
```

### To Base64

```python
from roura_agent.tools.image import ImageToBase64Tool

tool = ImageToBase64Tool()
result = tool.execute(path="image.png")

base64_string = result.output["base64"]
data_url = result.output["data_url"]
```

## Image Analysis

### ImageAnalyzer

The core analyzer that connects to vision AI.

```python
from roura_agent.tools.image import ImageAnalyzer, get_image_analyzer

# Get the configured analyzer
analyzer = get_image_analyzer()

# Analyze an image
result = await analyzer.analyze(
    image_path="screenshot.png",
    prompt="Describe what you see",
)
print(result)
```

### Setting Up Vision Callback

Connect to Claude's vision API:

```python
from roura_agent.tools.image import set_image_analyzer, create_vision_callback

# Create callback that uses Claude's vision
callback = create_vision_callback()

# Set up analyzer with callback
from roura_agent.tools.image import ImageAnalyzer
analyzer = ImageAnalyzer(vision_callback=callback)
set_image_analyzer(analyzer)
```

### Analyze Tool

```python
from roura_agent.tools.image import ImageAnalyzeTool

tool = ImageAnalyzeTool()
result = await tool.execute(
    path="ui_design.png",
    prompt="What accessibility issues do you see?",
)
print(result.output["analysis"])
```

## Comparing Images

### Compare Tool

```python
from roura_agent.tools.image import ImageCompareTool

tool = ImageCompareTool()
result = await tool.execute(
    path1="version1.png",
    path2="version2.png",
    prompt="Describe the differences between these two versions",
)
print(result.output["comparison"])
```

### Comparison Use Cases

```python
# UI regression testing
result = await compare_images(
    "baseline.png",
    "current.png",
    "Are there any visual regressions or layout shifts?",
)

# Design review
result = await compare_images(
    "mockup.png",
    "implementation.png",
    "How closely does the implementation match the design?",
)

# Before/after analysis
result = await compare_images(
    "before_fix.png",
    "after_fix.png",
    "Was the bug fixed? What changed?",
)
```

## Built-in Tools

### ImageReadTool

Read image metadata without analysis.

```python
from roura_agent.tools.image import ImageReadTool

tool = ImageReadTool()
result = tool.execute(path="image.png")

info = result.output
# {
#     "width": 1920,
#     "height": 1080,
#     "format": "PNG",
#     "mode": "RGBA",
#     "size_bytes": 2048576,
# }
```

### ImageAnalyzeTool

Analyze image content with AI.

```python
from roura_agent.tools.image import ImageAnalyzeTool

tool = ImageAnalyzeTool()
result = await tool.execute(
    path="error_screenshot.png",
    prompt="What error is shown and how can it be fixed?",
)
```

### ImageCompareTool

Compare two images.

```python
from roura_agent.tools.image import ImageCompareTool

tool = ImageCompareTool()
result = await tool.execute(
    path1="expected.png",
    path2="actual.png",
    prompt="Are these images identical? If not, what differs?",
)
```

### ImageToBase64Tool

Convert image to base64.

```python
from roura_agent.tools.image import ImageToBase64Tool

tool = ImageToBase64Tool()
result = tool.execute(path="icon.png")

# Use in HTML
html = f'<img src="{result.output["data_url"]}" />'
```

### ImageFromUrlTool

Fetch image from URL.

```python
from roura_agent.tools.image import ImageFromUrlTool

tool = ImageFromUrlTool()
result = await tool.execute(url="https://example.com/photo.jpg")

image_data = result.output["image"]
```

## Supported Formats

| Format | Read | Analyze | Compare |
|--------|------|---------|---------|
| PNG | Yes | Yes | Yes |
| JPEG | Yes | Yes | Yes |
| GIF | Yes | Yes | Yes |
| WebP | Yes | Yes | Yes |
| BMP | Yes | Yes | Yes |
| TIFF | Yes | Limited | Limited |

## Vision API Integration

### With Claude

```python
from roura_agent.llm import get_provider, ProviderType
from roura_agent.tools.image import ImageAnalyzer

# Get Claude provider
provider = get_provider(ProviderType.ANTHROPIC)

# Create vision callback
def vision_callback(prompt: str, images: list[dict]) -> str:
    response = provider.chat_with_images(
        prompt=prompt,
        images=images,
        system_prompt="You are a helpful image analyst.",
    )
    return response.content

# Create analyzer
analyzer = ImageAnalyzer(vision_callback=vision_callback)
```

### Image Format for Vision API

```python
# Images are passed as:
{
    "type": "base64",
    "media_type": "image/png",
    "data": "base64_encoded_string...",
}
```

## Error Handling

```python
from roura_agent.tools.image import read_image
from roura_agent.tools.base import ToolResult

# Check for errors
result = read_image("nonexistent.png")
if not result.success:
    print(f"Error: {result.error}")

# Common errors:
# - File not found
# - Unsupported format
# - Image too large
# - Corrupt image data
```

## Best Practices

### 1. Check Image Size

```python
info = read_image(path)
if info.size_bytes > 10 * 1024 * 1024:  # 10MB
    print("Warning: Large image may be slow to analyze")
```

### 2. Use Specific Prompts

```python
# Good - specific
result = await analyze_image(
    path="ui.png",
    prompt="List all the buttons visible and their labels",
)

# Less effective - vague
result = await analyze_image(
    path="ui.png",
    prompt="Tell me about this image",
)
```

### 3. Handle Vision API Availability

```python
analyzer = get_image_analyzer()
if analyzer is None:
    print("Vision analysis not available")
    # Fall back to basic metadata
    info = read_image(path)
```

## API Reference

### Classes

| Class | Description |
|-------|-------------|
| `ImageData` | Container for image content |
| `ImageSource` | Image source types |
| `ImageInfo` | Image metadata |
| `ImageAnalyzer` | Vision AI analyzer |

### Tools

| Tool | Description |
|------|-------------|
| `ImageReadTool` | Read image metadata |
| `ImageAnalyzeTool` | Analyze with AI |
| `ImageCompareTool` | Compare two images |
| `ImageToBase64Tool` | Convert to base64 |
| `ImageFromUrlTool` | Fetch from URL |

### Functions

| Function | Description |
|----------|-------------|
| `read_image()` | Read image info |
| `analyze_image()` | Analyze with AI |
| `compare_images()` | Compare two images |
| `get_image_analyzer()` | Get analyzer instance |
| `set_image_analyzer()` | Set analyzer instance |
| `create_vision_callback()` | Create Claude vision callback |
