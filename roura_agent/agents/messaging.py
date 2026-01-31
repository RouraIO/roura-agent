"""
Roura Agent Messaging - Inter-agent communication and task coordination.

© Roura.io
"""
from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

from rich.console import Console

if TYPE_CHECKING:
    from .base import AgentResult


class MessagePriority(Enum):
    """Priority levels for agent messages."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class MessageStatus(Enum):
    """Status of a message in the system."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentMessage:
    """
    A message between agents.

    Messages are the primary way agents communicate and delegate work.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent: str = ""
    to_agent: str = ""  # Empty means broadcast/orchestrator decides
    task: str = ""
    context: Optional[dict] = None
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    result: Optional[AgentResult] = None
    parent_id: Optional[str] = None  # For task chains
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task": self.task,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "parent_id": self.parent_id,
        }


class MessageBus:
    """
    Central message bus for agent communication.

    Features:
    - Async message passing between agents
    - Priority queue for urgent tasks
    - Message history and tracking
    - Broadcast capability
    - Task chaining (one agent can spawn subtasks)
    """

    _instance: Optional[MessageBus] = None

    def __init__(self, console: Optional[Console] = None):
        self._console = console or Console()
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._handlers: dict[str, Callable] = {}  # agent_name -> handler
        self._history: list[AgentMessage] = []
        self._pending: dict[str, AgentMessage] = {}  # id -> message
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls, console: Optional[Console] = None) -> MessageBus:
        """Get the singleton message bus."""
        if cls._instance is None:
            cls._instance = cls(console)
        return cls._instance

    def register_handler(
        self,
        agent_name: str,
        handler: Callable[[AgentMessage], AgentResult],
    ) -> None:
        """Register a message handler for an agent."""
        with self._lock:
            self._handlers[agent_name] = handler

    def unregister_handler(self, agent_name: str) -> None:
        """Unregister an agent's message handler."""
        with self._lock:
            self._handlers.pop(agent_name, None)

    def send(
        self,
        from_agent: str,
        task: str,
        to_agent: str = "",
        priority: MessagePriority = MessagePriority.NORMAL,
        context: Optional[dict] = None,
        parent_id: Optional[str] = None,
    ) -> AgentMessage:
        """
        Send a message/task to another agent.

        Args:
            from_agent: Name of the sending agent
            task: The task description
            to_agent: Target agent (empty = orchestrator decides)
            priority: Task priority
            context: Additional context dict
            parent_id: Parent message ID for task chains

        Returns:
            The created message object
        """
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            task=task,
            priority=priority,
            context=context or {},
            parent_id=parent_id,
        )

        with self._lock:
            self._pending[message.id] = message
            # Priority queue uses (priority, timestamp, message) for ordering
            # Negate priority so higher priority = lower number = processed first
            self._queue.put((
                -priority.value,
                message.created_at.timestamp(),
                message,
            ))

        self._console.print(
            f"[dim]📨 {from_agent} → {to_agent or 'orchestrator'}: "
            f"{task[:50]}...[/dim]"
        )

        return message

    def broadcast(
        self,
        from_agent: str,
        task: str,
        exclude: Optional[list[str]] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> list[AgentMessage]:
        """
        Broadcast a message to all registered agents.

        Args:
            from_agent: Name of the sending agent
            task: The task description
            exclude: Agent names to exclude
            priority: Task priority

        Returns:
            List of created messages
        """
        exclude = exclude or []
        messages = []

        with self._lock:
            for agent_name in self._handlers:
                if agent_name not in exclude and agent_name != from_agent:
                    msg = self.send(
                        from_agent=from_agent,
                        to_agent=agent_name,
                        task=task,
                        priority=priority,
                    )
                    messages.append(msg)

        return messages

    def get_pending(self) -> list[AgentMessage]:
        """Get all pending messages."""
        with self._lock:
            return [
                m for m in self._pending.values()
                if m.status == MessageStatus.PENDING
            ]

    def get_message(self, message_id: str) -> Optional[AgentMessage]:
        """Get a message by ID."""
        with self._lock:
            return self._pending.get(message_id)

    def cancel(self, message_id: str) -> bool:
        """Cancel a pending message."""
        with self._lock:
            if message_id in self._pending:
                msg = self._pending[message_id]
                if msg.status == MessageStatus.PENDING:
                    msg.status = MessageStatus.CANCELLED
                    return True
        return False

    def process_next(self) -> Optional[AgentMessage]:
        """
        Process the next message in the queue.

        Returns the processed message or None if queue is empty.
        """
        try:
            _, _, message = self._queue.get_nowait()
        except queue.Empty:
            return None

        if message.status == MessageStatus.CANCELLED:
            return message

        message.status = MessageStatus.PROCESSING

        # Find handler
        handler = None
        with self._lock:
            if message.to_agent and message.to_agent in self._handlers:
                handler = self._handlers[message.to_agent]
            elif not message.to_agent and "orchestrator" in self._handlers:
                # Route to orchestrator if no specific target
                handler = self._handlers["orchestrator"]

        if handler:
            try:
                result = handler(message)
                message.result = result
                message.status = (
                    MessageStatus.COMPLETED if result.success
                    else MessageStatus.FAILED
                )
            except Exception as e:
                message.status = MessageStatus.FAILED
                from .base import AgentResult
                message.result = AgentResult(success=False, error=str(e))
        else:
            message.status = MessageStatus.FAILED
            from .base import AgentResult
            message.result = AgentResult(
                success=False,
                error=f"No handler for agent: {message.to_agent or 'orchestrator'}",
            )

        message.completed_at = datetime.now()

        # Move to history
        with self._lock:
            self._history.append(message)
            self._pending.pop(message.id, None)

        return message

    def process_all(self) -> list[AgentMessage]:
        """Process all pending messages."""
        processed = []
        while True:
            msg = self.process_next()
            if msg is None:
                break
            processed.append(msg)
        return processed

    def start_worker(self) -> None:
        """Start background worker thread for processing messages."""
        if self._running:
            return

        self._running = True

        def worker():
            while self._running:
                try:
                    _, _, message = self._queue.get(timeout=0.1)
                    if message.status != MessageStatus.CANCELLED:
                        self.process_next()
                except queue.Empty:
                    continue
                except Exception:
                    continue

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def stop_worker(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)

    def get_history(self, limit: int = 50) -> list[AgentMessage]:
        """Get message history."""
        with self._lock:
            return self._history[-limit:]

    def clear_history(self) -> None:
        """Clear message history."""
        with self._lock:
            self._history.clear()


# Global message bus instance
_message_bus: Optional[MessageBus] = None


def get_message_bus(console: Optional[Console] = None) -> MessageBus:
    """Get the global message bus."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus.get_instance(console)
    return _message_bus


def send_to_agent(
    from_agent: str,
    to_agent: str,
    task: str,
    priority: MessagePriority = MessagePriority.NORMAL,
    context: Optional[dict] = None,
) -> AgentMessage:
    """
    Convenience function to send a task to another agent.

    Usage in an agent:
        from roura_agent.agents.messaging import send_to_agent

        # In execute():
        send_to_agent(
            from_agent=self.name,
            to_agent="test",
            task="Write tests for the new function",
        )
    """
    bus = get_message_bus()
    return bus.send(
        from_agent=from_agent,
        to_agent=to_agent,
        task=task,
        priority=priority,
        context=context,
    )
