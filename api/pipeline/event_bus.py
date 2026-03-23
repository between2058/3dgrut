import asyncio
from collections import defaultdict
from typing import AsyncIterator


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, job_id: str, event: dict):
        for queue in self._subscribers.get(job_id, []):
            await queue.put(event)

    async def subscribe(self, job_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[job_id].append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers[job_id].remove(queue)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
