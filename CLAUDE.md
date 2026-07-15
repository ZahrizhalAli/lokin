# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Lokin is a real-time voice AI framework (frame/pipeline based), forked from Pipecat (Daily) and repackaged under the `lokin` name.
The flagship bot built on top of it is an AI technical interviewer: it watches the candidate's shared screen and talks to them live over WebRTC.
Copyright headers in some files still say "Daily" — this is expected, not a mistake to fix.

## Commands

Dependency management and running use `uv` (not raw pip/venv commands):

```bash
uv sync                 # install deps + local package in editable mode
uv run app.py            # run the sample interviewer bot, served at http://localhost:7860
uv run replay.py sessions/<session-id>   # replay a recorded session offline through the LLM (no browser/mic/TTS)
```

Tests must be run as `uv run python -m pytest`, not `uv run pytest` — the bare `pytest` console-script entry point doesn't add the repo root to `sys.path`, so it fails with `ModuleNotFoundError: No module named 'lokin'` even though the package is installed editable in `.venv`. (System/conda pytest fails the same way, for the same underlying reason: `lokin` is only importable through this project's venv.)

```bash
uv run python -m pytest                                   # run everything
uv run python -m pytest tests/test_screen_share_injector.py   # single file
uv run python -m pytest tests/test_screen_share_injector.py::test_dedups_same_frame_by_pts  # single test
```

Note: `tests/test_integration_function_calling.py` currently fails to collect — it imports `lokin.services.anthropic`, `lokin.services.google`, and `lokin.tests.utils`, none of which exist in this fork (only `openai`, `azure`, `cartesia`, `deepgram`, `elevenlabs`, `whisper`, `openai_realtime` service backends are present). Don't assume this test module is runnable; run specific working test files instead.

There is no separate lint command configured.

## Architecture

### Frame/pipeline model

Everything flows as `Frame` objects (`lokin/frames/frames.py`) through a chain of `FrameProcessor`s (`lokin/processors/frame_processor.py`). Frames move `DOWNSTREAM` (input -> output) or `UPSTREAM` (output -> input, e.g. errors/control). `SystemFrame`s (e.g. `StartFrame`, `CancelFrame`) jump a priority queue ahead of regular frames within each processor so lifecycle/control signals aren't stuck behind backed-up data frames.

A `Pipeline` (`lokin/pipeline/pipeline.py`) links a list of processors in sequence, sandwiched between an internal `PipelineSource`/`PipelineSink` so frames can also escape upstream/downstream outside the chain. A `PipelineTask` (`lokin/pipeline/task.py`) wraps a `Pipeline` and owns its lifecycle: it injects the initial `StartFrame`, wires up RTVI, turn tracking, heartbeat/idle monitoring, and observers, and exposes `on_pipeline_started` / `on_pipeline_finished` / `on_pipeline_error` events. `PipelineRunner` (`lokin/pipeline/runner.py`) actually drives a `PipelineTask` to completion and handles SIGINT/SIGTERM.

Observers (`lokin/observers/`) are the read-only side channel: they get `on_push_frame`/`on_process_frame` callbacks for every frame without being in the processing chain themselves. `SessionRecorderObserver` is the main one in this repo (see below).

### The bot pipeline (`app.py`, `main.py`)

The interviewer bot's pipeline is:

```
transport.input() -> stt -> user_aggregator -> screen_injector -> llm -> tts -> transport.output() -> assistant_aggregator
```

- `ScreenShareContextInjector` (`lokin/processors/screen_share_injector.py`) is this project's key custom processor: it watches for screen-share video frames and, right before each LLM call, injects the latest screenshot into the `LLMContext` — but only if the screen actually changed (thumbnail diff), isn't stale, and respects a minimum injection interval. It evicts the previously injected screenshot so context doesn't accumulate old images.
- Transports, services (STT/TTS/LLM), and serializers are pluggable — swapping e.g. Deepgram STT for OpenAI STT, or adding a new telephony provider, means implementing the relevant base class (`base_transport.py`, `stt_service.py`, `tts_service.py`, `llm_service.py`, `base_serializer.py`) rather than changing pipeline code.

### Runner / transport wiring

`lokin/runner/run.py` is a dev-only FastAPI server that discovers a `bot(runner_args)` function in the entrypoint script and wires up transport-specific routes (currently only `webrtc` is actually set up in `_create_server_app`; `daily`/telephony transport classes exist under `lokin/transports/` but the runner's route setup doesn't call them). `lokin/runner/utils.py::create_transport()` maps a `RunnerArguments` subclass (`lokin/runner/types.py`) to a concrete transport instance via a `transport_params` factory dict supplied by the bot script — this is the extension point for adding a new transport to a bot.

### Session recording and replay

`SessionRecorderObserver` (`lokin/observers/session_recorder.py`) attaches as a `PipelineTask` observer and writes `sessions/<timestamp>/events.jsonl` plus an `images/` folder: transcriptions, bot responses, LLM context snapshots (screenshots stripped out to `image_ref` + files), and screen-share frames. `replay.py` re-feeds a recorded session's `screen_frame`/`llm_run` events back through a real `ScreenShareContextInjector` + `OpenAILLMService` pipeline (no browser/mic/TTS, no transport) using a virtual clock (`ReplayClock`) so recorded timing is reproduced. This is the primary way to iterate on prompt/injector behavior against a real past session instead of re-running a live interview every time.

### Prompts

System prompts live as markdown in `lokin/config/*.md` (`interviewer_prompt.md`, `presenter_prompt.md`) and are loaded via `lokin/utils/system_prompt_parser.py::load_prompt()`. Edit the prompt text there rather than inlining prompt strings in bot code.

### Web UI

`ui/dist/` contains only a prebuilt static bundle (no committed frontend source in this repo) served at `/client` (or `/prebuilt` via `webui/client.py` when mounted from `app.py`). Treat `ui/dist` as a build artifact, not source to hand-edit.
