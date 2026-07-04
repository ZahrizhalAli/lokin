"""Offline tests for ScreenShareContextInjector context management.

These tests drive the injector's decision logic directly (no pipeline, no
network): a fake clock controls interval/staleness checks and solid-color
RGB frames stand in for screen captures.
"""

import asyncio

from lokin.frames.frames import InputImageRawFrame, LLMContextFrame
from lokin.processors.aggregators.llm_context import LLMContext
from lokin.processors.screen_share_injector import ScreenShareContextInjector

SIZE = (64, 64)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_screen_frame(color: int, pts: int) -> InputImageRawFrame:
    frame = InputImageRawFrame(
        image=bytes([color, color, color]) * (SIZE[0] * SIZE[1]),
        size=SIZE,
        format="RGB",
    )
    frame.transport_source = "screenVideo"
    frame.pts = pts
    return frame


def make_injector():
    clock = FakeClock()
    injector = ScreenShareContextInjector(time_fn=clock)
    return injector, clock


def image_messages(context: LLMContext):
    def is_image(message):
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return False
        return any(item.get("type") == "image_url" for item in content)

    return [m for m in context.get_messages() if is_image(m)]


async def inject(injector, context):
    await injector._maybe_inject_screen(LLMContextFrame(context=context))


def test_injects_latest_screen_frame():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 2.0
        await inject(injector, context)

        assert len(image_messages(context)) == 1

    asyncio.run(run())


def test_evicts_previous_screenshot_on_change():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 2.0
        await inject(injector, context)
        first = image_messages(context)[0]

        context.add_message({"role": "user", "content": "next question"})
        injector._remember_screen_frame(make_screen_frame(255, pts=2))
        clock.now = 4.0
        await inject(injector, context)

        images = image_messages(context)
        assert len(images) == 1
        assert images[0] is not first

    asyncio.run(run())


def test_skips_injection_when_screen_unchanged():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 2.0
        await inject(injector, context)
        first = image_messages(context)[0]

        # Same pixels, new frame/pts: previous screenshot stays, no duplicate.
        injector._remember_screen_frame(make_screen_frame(0, pts=2))
        clock.now = 4.0
        await inject(injector, context)

        images = image_messages(context)
        assert len(images) == 1
        assert images[0] is first
        assert injector._last_injected_pts == 2

    asyncio.run(run())


def test_respects_min_injection_interval():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 2.0
        await inject(injector, context)

        injector._remember_screen_frame(make_screen_frame(255, pts=2))
        clock.now = 2.5  # only 0.5s after the last injection
        await inject(injector, context)

        assert len(image_messages(context)) == 1

    asyncio.run(run())


def test_skips_stale_screen_frame():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 10.0  # screen share stopped a while ago
        await inject(injector, context)

        assert len(image_messages(context)) == 0

    asyncio.run(run())


def test_dedups_same_frame_by_pts():
    async def run():
        injector, clock = make_injector()
        context = LLMContext()

        injector._remember_screen_frame(make_screen_frame(0, pts=1))
        clock.now = 2.0
        await inject(injector, context)
        clock.now = 4.0
        await inject(injector, context)

        assert len(image_messages(context)) == 1

    asyncio.run(run())
