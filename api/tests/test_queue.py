import asyncio
import pytest
from api.pipeline.queue import JobQueue


@pytest.mark.asyncio
async def test_queue_sequential_execution():
    queue = JobQueue(max_gpu_jobs=1)
    order = []

    async def job(name):
        async with queue.acquire_gpu(name):
            order.append(f"{name}_start")
            await asyncio.sleep(0.02)
            order.append(f"{name}_end")

    # Run sequentially to test basic lock behavior
    await job("a")
    await job("b")
    assert order == ["a_start", "a_end", "b_start", "b_end"]


@pytest.mark.asyncio
async def test_gpu_busy_property():
    queue = JobQueue(max_gpu_jobs=1)
    assert not queue.gpu_busy

    async with queue.acquire_gpu("test"):
        assert queue.gpu_busy

    assert not queue.gpu_busy


@pytest.mark.asyncio
async def test_position_tracking():
    queue = JobQueue(max_gpu_jobs=1)
    # Before entering queue
    assert queue.position("any") == 0
