"""Resume watcher cancellation and frozen no-progress threshold regressions."""

import asyncio

import pytest

from src.runtime.scheduler import ResumeLiveness


async def test_resume_watch_cancel_when_progress_wait_completes():
    scope = ResumeLiveness("run", "cycle")
    watcher = asyncio.create_task(scope.watch())
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        scope.changed.set()
        await asyncio.sleep(0)
        assert watcher.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert watcher.done(), "completed progress wait swallowed watcher cancellation"
        assert watcher.cancelled()
        assert scope.expired is None
        assert scope.no_progress < 60
    finally:
        if not watcher.done():
            watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


async def test_resume_watch_still_expires_without_progress():
    now = [0.0]
    scope = ResumeLiveness("run", "cycle", clock=lambda: now[0])
    watcher = asyncio.create_task(scope.watch())
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        now[0] = 61
        scope.changed.set()
        with pytest.raises(TimeoutError, match="RESUME_NO_PROGRESS_TIMEOUT"):
            await watcher
        assert scope.no_progress == 61
        assert scope.orchestration == 61
    finally:
        if not watcher.done():
            watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
