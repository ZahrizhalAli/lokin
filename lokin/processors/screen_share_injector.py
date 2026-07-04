"""Screen share context injection for LLM pipelines."""

import asyncio
import io
import time
from typing import Callable, Optional

import numpy as np
from PIL import Image

from lokin.frames.frames import InputImageRawFrame, LLMContextFrame
from lokin.processors.aggregators.llm_context import LLMContext, LLMContextMessage
from lokin.processors.frame_processor import FrameDirection, FrameProcessor


def _grayscale_thumbnail(frame: InputImageRawFrame) -> np.ndarray:
    if frame.format and frame.format.startswith("image/"):
        image = Image.open(io.BytesIO(frame.image))
    else:
        image = Image.frombytes(frame.format, frame.size, frame.image)
    return np.asarray(image.convert("L").resize((64, 64)), dtype=np.float32)


class ScreenShareContextInjector(FrameProcessor):
    """Inject the latest screen share frame into the LLM context.

    Keeps at most one screenshot in the context: the previously injected
    image message is evicted when a new one is injected, so long sessions
    don't accumulate stale screenshots. Injection is also skipped when the
    screen content hasn't meaningfully changed since the last injected
    frame, in which case the previous screenshot stays in the context.

    Args:
        min_interval_secs: Minimum time between two injections.
        stale_after_secs: Don't inject a frame older than this (e.g. the
            user stopped sharing their screen).
        change_threshold: Mean absolute pixel difference (0-1 range, on a
            64x64 grayscale thumbnail) below which two frames are
            considered identical.
        time_fn: Clock used for interval/staleness checks. Defaults to
            ``time.monotonic``; session replay passes a virtual clock.
    """

    def __init__(
        self,
        *,
        min_interval_secs: float = 1.5,
        stale_after_secs: float = 5.0,
        change_threshold: float = 0.005,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        super().__init__(name="ScreenShareContextInjector")
        self._min_interval_secs = min_interval_secs
        self._stale_after_secs = stale_after_secs
        self._change_threshold = change_threshold
        self._time_fn = time_fn
        self._latest_frame: Optional[InputImageRawFrame] = None
        self._latest_frame_time: float = 0.0
        self._last_injected_pts: Optional[int] = None
        self._last_injected_time: float = 0.0
        self._last_injected_frame: Optional[InputImageRawFrame] = None
        self._last_injected_message: Optional[LLMContextMessage] = None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputImageRawFrame) and frame.transport_source == "screenVideo":
            self._remember_screen_frame(frame)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMContextFrame):
            await self._maybe_inject_screen(frame)
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)

    def _remember_screen_frame(self, frame: InputImageRawFrame):
        self._latest_frame = frame
        self._latest_frame_time = self._time_fn()

    async def _maybe_inject_screen(self, frame: LLMContextFrame):
        latest = self._latest_frame
        if not latest:
            return

        if latest.pts is not None and self._last_injected_pts == latest.pts:
            return

        now = self._time_fn()
        if now - self._latest_frame_time > self._stale_after_secs:
            return

        if now - self._last_injected_time < self._min_interval_secs:
            return

        if self._last_injected_frame and await asyncio.to_thread(
            self._frames_similar, self._last_injected_frame, latest
        ):
            # Screen hasn't changed: the screenshot already in the context is
            # still accurate, so don't spend tokens on a duplicate.
            self._last_injected_pts = latest.pts
            return

        message = await LLMContext.create_image_message(
            format=latest.format,
            size=latest.size,
            image=latest.image,
            text="User screen share",
        )
        self._evict_last_injected(frame.context)
        frame.context.add_message(message)

        self._last_injected_message = message
        self._last_injected_frame = latest
        self._last_injected_pts = latest.pts
        self._last_injected_time = now

    def _evict_last_injected(self, context: LLMContext):
        if self._last_injected_message is None:
            return
        try:
            context.get_messages().remove(self._last_injected_message)
        except ValueError:
            # Already gone (e.g. context was rewritten or summarized).
            pass

    def _frames_similar(self, a: InputImageRawFrame, b: InputImageRawFrame) -> bool:
        try:
            diff = np.abs(_grayscale_thumbnail(a) - _grayscale_thumbnail(b)).mean() / 255.0
            return diff < self._change_threshold
        except Exception:
            # If frames can't be compared, treat them as changed.
            return False
