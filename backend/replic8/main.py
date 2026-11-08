"""Start the REPLIC8 backend: python -m REPLIC8 (or uvicorn replic8.main:create --factory).

Everything comes from environment variables (see backend/README.md). Nemotron is
optional at startup: without NVIDIA_API_KEY the gateway still serves published
tools, but onboarding and self-heal report that the model is not configured.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from .config import Settings
from .events import EventLog
from .executor import Executor
from .gateway import create_app
from .nemotron import ModelConfig, ModelError, NemotronClient
from .pipeline import Pipeline
from .registry import Registry
from .runtimes import LEGACY_IMAGE
from .sandbox import Sandbox

log = logging.getLogger("replic8")


def create(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    data = settings.data_dir
    registry = Registry(data)
    sandbox = Sandbox(data / "repos", settings.sandbox_images or frozenset({LEGACY_IMAGE}), settings.sandbox,
                      builds_root=data / "builds")
    executor = Executor(sandbox, data / "repos")
    try:
        model = NemotronClient(ModelConfig.from_env())
    except ModelError as exc:
        log.warning("Nemotron disabled: %s", exc)
        model = None
    events = EventLog(data)
    pipeline = Pipeline(settings, registry, sandbox, executor, model, events)
    return create_app(settings, registry, executor, pipeline=pipeline, events=events)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(create, factory=True, host=os.environ.get("REPLIC8_HOST", "127.0.0.1"),
                port=int(os.environ.get("REPLIC8_PORT", "8000")))


if __name__ == "__main__":
    main()
