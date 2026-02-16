"""Base pipeline implementation for frame processing."""

from lokin.processors.frame_processor import FrameProcessor


class BasePipeline(FrameProcessor):
    """Base class for all pipeline implementations."""

    def __init__(self, **kwargs):
        """Initialize the base pipeline."""
        super().__init__(**kwargs)
