"""
Roura Agent Server - HTTP API for desktop and external clients.

Provides:
- REST API for agent interactions
- WebSocket for streaming responses
- Screenshot and file handling
- Memory management endpoints

© Roura.io
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .constants import VERSION
from .logging import get_logger

logger = get_logger(__name__)

# Try to import server dependencies
try:
    from fastapi import FastAPI, HTTPException, WebSocket, UploadFile, File
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    SERVER_AVAILABLE = True
except ImportError:
    SERVER_AVAILABLE = False
    logger.warning("Server dependencies not installed. Install with: pip install roura-agent[server]")


if SERVER_AVAILABLE:
    # =========================================================================
    # Pydantic Models
    # =========================================================================

    class MessageRequest(BaseModel):
        """Request to send a message to the agent."""
        content: str
        attachments: Optional[list[str]] = None
        context: Optional[dict[str, Any]] = None
        project_path: Optional[str] = None

    class MessageResponse(BaseModel):
        """Response from the agent."""
        id: str
        content: str
        tool_calls: Optional[list[dict]] = None
        finished: bool
        created_at: str

    class MemoryNoteRequest(BaseModel):
        """Request to add a memory note."""
        content: str
        category: str = "note"
        tags: list[str] = []
        project_path: str

    class ConfigRequest(BaseModel):
        """Request to update configuration."""
        key: str
        value: Any

    class ProjectRequest(BaseModel):
        """Request to open a project."""
        path: str

    # =========================================================================
    # Server Application
    # =========================================================================

    def create_app() -> FastAPI:
        """Create the FastAPI application."""
        app = FastAPI(
            title="Roura Agent API",
            description="HTTP API for Roura Agent desktop and external clients",
            version=VERSION,
        )

        # CORS for desktop app
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["tauri://localhost", "http://localhost:*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # =====================================================================
        # Health & Info Endpoints
        # =====================================================================

        @app.get("/")
        async def root():
            return {"status": "ok", "name": "Roura Agent", "version": VERSION}

        @app.get("/version")
        async def version():
            return {"version": VERSION}

        @app.get("/health")
        async def health():
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        # =====================================================================
        # Agent Endpoints
        # =====================================================================

        @app.post("/chat", response_model=MessageResponse)
        async def chat(request: MessageRequest):
            """Send a message and get a response."""
            # This would integrate with the agent core
            response_id = str(uuid.uuid4())
            return MessageResponse(
                id=response_id,
                content=f"Received: {request.content}",
                tool_calls=None,
                finished=True,
                created_at=datetime.now().isoformat(),
            )

        @app.websocket("/ws/chat")
        async def websocket_chat(websocket: WebSocket):
            """WebSocket endpoint for streaming chat."""
            await websocket.accept()

            try:
                while True:
                    data = await websocket.receive_text()
                    request = json.loads(data)

                    # Process message and stream response
                    response_id = str(uuid.uuid4())

                    # Send start event
                    await websocket.send_json({
                        "type": "start",
                        "id": response_id,
                    })

                    # Simulate streaming response
                    content = f"Processing: {request.get('content', '')}"
                    for i, char in enumerate(content):
                        await websocket.send_json({
                            "type": "delta",
                            "id": response_id,
                            "content": char,
                        })
                        await asyncio.sleep(0.01)

                    # Send completion
                    await websocket.send_json({
                        "type": "done",
                        "id": response_id,
                        "content": content,
                    })

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                await websocket.close()

        # =====================================================================
        # Memory Endpoints
        # =====================================================================

        @app.get("/memory")
        async def get_memory(project_path: str):
            """Get memory for a project."""
            from .memory import get_project_memory

            memory = get_project_memory(Path(project_path))
            if not memory:
                return {"entries": [], "preferences": {}}

            memory.load()
            return {
                "entries": [e.to_dict() for e in memory._entries],
                "preferences": memory._preferences,
            }

        @app.post("/memory/note")
        async def add_note(request: MemoryNoteRequest):
            """Add a memory note."""
            from .memory import get_project_memory

            memory = get_project_memory(Path(request.project_path))
            if not memory:
                raise HTTPException(status_code=404, detail="Project not found")

            entry = memory.add(
                content=request.content,
                category=request.category,
                tags=request.tags,
            )
            if entry:
                memory.save()
                return entry.to_dict()
            else:
                raise HTTPException(status_code=403, detail="Memory access denied by consent")

        @app.delete("/memory/note/{entry_id}")
        async def delete_note(entry_id: str, project_path: str):
            """Delete a memory note."""
            from .memory import get_project_memory

            memory = get_project_memory(Path(project_path))
            if not memory:
                raise HTTPException(status_code=404, detail="Project not found")

            if memory.remove(entry_id):
                memory.save()
                return {"status": "deleted"}
            else:
                raise HTTPException(status_code=404, detail="Note not found")

        # =====================================================================
        # Configuration Endpoints
        # =====================================================================

        @app.get("/config")
        async def get_config():
            """Get all configuration."""
            config_path = Path.home() / ".config" / "roura-agent" / "config.json"
            if not config_path.exists():
                return {}
            return json.loads(config_path.read_text())

        @app.get("/config/{key}")
        async def get_config_key(key: str):
            """Get a configuration value."""
            config_path = Path.home() / ".config" / "roura-agent" / "config.json"
            if not config_path.exists():
                return {"value": None}
            config = json.loads(config_path.read_text())
            return {"key": key, "value": config.get(key)}

        @app.post("/config")
        async def set_config(request: ConfigRequest):
            """Set a configuration value."""
            config_dir = Path.home() / ".config" / "roura-agent"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.json"

            config = {}
            if config_path.exists():
                config = json.loads(config_path.read_text())

            config[request.key] = request.value
            config_path.write_text(json.dumps(config, indent=2))

            return {"status": "ok", "key": request.key}

        # =====================================================================
        # Project Endpoints
        # =====================================================================

        @app.get("/projects/recent")
        async def recent_projects():
            """Get recent projects."""
            projects_path = Path.home() / ".config" / "roura-agent" / "recent_projects.json"
            if not projects_path.exists():
                return []
            return json.loads(projects_path.read_text())

        @app.post("/projects/open")
        async def open_project(request: ProjectRequest):
            """Open a project."""
            project_path = Path(request.path)
            if not project_path.exists():
                raise HTTPException(status_code=404, detail="Project path not found")

            # Update recent projects
            projects_path = Path.home() / ".config" / "roura-agent" / "recent_projects.json"
            projects_path.parent.mkdir(parents=True, exist_ok=True)

            projects = []
            if projects_path.exists():
                projects = json.loads(projects_path.read_text())

            # Remove existing entry
            projects = [p for p in projects if p.get("path") != request.path]

            # Add to front
            projects.insert(0, {
                "name": project_path.name,
                "path": request.path,
                "last_opened": datetime.now().isoformat(),
            })

            # Keep last 10
            projects = projects[:10]

            projects_path.write_text(json.dumps(projects, indent=2))

            return projects[0]

        # =====================================================================
        # File Endpoints
        # =====================================================================

        @app.post("/upload")
        async def upload_file(file: UploadFile = File(...)):
            """Upload a file (for drag-drop support)."""
            upload_dir = Path.home() / ".config" / "roura-agent" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_id = str(uuid.uuid4())
            file_ext = Path(file.filename).suffix if file.filename else ""
            save_path = upload_dir / f"{file_id}{file_ext}"

            content = await file.read()
            save_path.write_bytes(content)

            return {
                "id": file_id,
                "filename": file.filename,
                "path": str(save_path),
                "size": len(content),
            }

        @app.post("/screenshot")
        async def capture_screenshot():
            """Capture a screenshot."""
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name

            # macOS screenshot
            result = subprocess.run(
                ["screencapture", "-x", temp_path],
                capture_output=True,
            )

            if result.returncode != 0:
                raise HTTPException(status_code=500, detail="Screenshot capture failed")

            import base64
            with open(temp_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()

            Path(temp_path).unlink()

            return {
                "data": image_data,
                "format": "png",
            }

        return app

    def run_server(host: str = "127.0.0.1", port: int = 8765):
        """Run the server."""
        app = create_app()
        uvicorn.run(app, host=host, port=port)


def main():
    """CLI entry point for server."""
    if not SERVER_AVAILABLE:
        print("Server dependencies not installed.")
        print("Install with: pip install roura-agent[server]")
        return 1

    parser = argparse.ArgumentParser(description="Roura Agent Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")

    args = parser.parse_args()

    logger.info(f"Starting Roura Agent server on {args.host}:{args.port}")
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
