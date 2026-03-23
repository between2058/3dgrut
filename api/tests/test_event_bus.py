import asyncio
import pytest
from api.pipeline.event_bus import EventBus


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EventBus()
    events = []

    async def collect():
        async for event in bus.subscribe("job1"):
            events.append(event)
            if event.get("type") == "completed":
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    await bus.publish("job1", {"type": "progress", "percent": 50})
    await bus.publish("job1", {"type": "completed"})
    await task

    assert len(events) == 2
    assert events[0]["type"] == "progress"
    assert events[1]["type"] == "completed"


@pytest.mark.asyncio
async def test_no_crosstalk():
    bus = EventBus()
    events = []

    async def collect():
        async for event in bus.subscribe("job1"):
            events.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    await bus.publish("job2", {"type": "other_job"})
    await bus.publish("job1", {"type": "mine"})
    await task

    assert len(events) == 1
    assert events[0]["type"] == "mine"
