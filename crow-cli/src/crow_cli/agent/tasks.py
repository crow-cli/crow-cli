"""In-process task registry — shared state between the react loop and its
native tools (delegation interiority).

This is why everything lives in one package: a delegate is OUR task and OUR
session, so launch/cancel/result need no IPC — just a dict and an asyncio
queue. Milestone A (blocking delegation) uses the registry for tracking and
the cancel tree; Milestone B (park/wake) wakes the loop through the
per-owner wake queue.
"""

import asyncio
import itertools
from dataclasses import dataclass


@dataclass
class TaskInfo:
    task_id: str
    kind: str                 # "delegate"
    owner_session: str        # wire session id of the launching agent
    tool_call_id: str         # the launch's tool_call_id (one result per call)
    sub_session: str = ""     # the delegate's own session id
    status: str = "running"   # running | done | failed | cancelled
    result: str | None = None


class TaskRegistry:
    """Tracks outstanding async tasks per owning session.

    The react loop's exit condition (Milestone B) is "model done AND
    registry empty for this session"; until then it parks on the session's
    wake queue. Completions land there as synthetic messages — never as
    role=tool on the launch's tool_call_id (the wire contract is one result
    per call, and that call already got its "launched" result).
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._wake_queues: dict[str, asyncio.Queue] = {}
        self._counter = itertools.count(1)

    def launch(
        self,
        kind: str,
        owner_session: str,
        tool_call_id: str,
        sub_session: str = "",
    ) -> TaskInfo:
        info = TaskInfo(
            task_id=f"task-{next(self._counter)}",
            kind=kind,
            owner_session=owner_session,
            tool_call_id=tool_call_id,
            sub_session=sub_session,
        )
        self._tasks[info.task_id] = info
        return info

    def finish(self, task_id: str, result: str | None, status: str = "done") -> None:
        info = self._tasks.get(task_id)
        if info is None or info.status != "running":
            return
        info.status = status
        info.result = result
        queue = self._wake_queues.get(info.owner_session)
        if queue is not None:
            queue.put_nowait(info)

    def pending(self, owner_session: str | None = None) -> list[TaskInfo]:
        return [
            t
            for t in self._tasks.values()
            if t.status == "running"
            and (owner_session is None or t.owner_session == owner_session)
        ]

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def wake_queue(self, owner_session: str) -> asyncio.Queue:
        """The queue the react loop parks on; completions wake it."""
        return self._wake_queues.setdefault(owner_session, asyncio.Queue())
