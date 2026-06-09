"""Frozen SSE event contract (locked at GATE 0).

The orchestrator EMITS these events, the FastAPI server RELAYS them over SSE, and the
Mission Control UI RENDERS them. Team A (UI) and Team B (server) build against these
shapes independently — neither blocks the other. Do not change a shape without a joint
decision (see docs/superpowers/COORDINATION.md).

Event flow, in order, per optimization run:
  version    -> a scored candidate version landed on the leaderboard
  hypothesis -> the agent's diagnosis (from its own traces via MCP) for the next mutation
  rejected   -> a mutation that did not improve the train score (reverted)
  promoted   -> the final best-so-far version, promoted on approval
"""
import asyncio
from typing import Literal, TypedDict


class VersionEvent(TypedDict):
    type: Literal["version"]
    version: int
    train: float          # train-split execution-match (0..1)
    test: float           # held-out test-split execution-match (0..1) — the headline number


class HypothesisEvent(TypedDict):
    type: Literal["hypothesis"]
    category: str         # dominant failure cluster, e.g. "join", "aggregation"
    mcp_summary: str      # the agent's natural-language read of its own failing traces


class RejectedEvent(TypedDict):
    type: Literal["rejected"]
    version: int


class PromotedEvent(TypedDict):
    type: Literal["promoted"]
    version: int
    test: float


class EventBus:
    """Minimal fan-out bus: the loop publishes, each SSE subscriber gets its own queue.

    The optimization loop runs in a worker thread while subscribers `await queue.get()`
    inside the event loop. `asyncio.Queue` is NOT thread-safe, so when a loop is bound
    (`bind_loop`, called on server startup) `publish` schedules the enqueue on the loop
    via `call_soon_threadsafe` — without it, a cross-thread `put_nowait` may never wake
    the waiting `get()` and SSE clients would silently freeze. With no loop bound (pure
    unit tests) it enqueues directly.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the event loop that owns the subscriber queues (call from startup)."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def publish(self, event: dict) -> None:
        for q in self._subscribers:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            else:
                q.put_nowait(event)
