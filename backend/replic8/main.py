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
from .established import Catalog, EstablishedImporter
from .events import EventLog
from .executor import Executor
from .gateway import create_app
from .nemotron import ModelConfig, ModelError, NemotronClient
from .pipeline import Pipeline
from .registry import Registry
from .runtimes import pin_local_image
from .sandbox import Sandbox
from .workspaces import Tenant, WorkspaceStore, WorkspaceValidator

log = logging.getLogger("replic8")


def create(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    data = settings.data_dir
    registry = Registry(data)
    # Images are digest-pinned (REPLIC8_SANDBOX_IMAGES); without that setting, pin the
    # locally built runtime image to its exact digest at startup.
    images = settings.sandbox_images or frozenset({pin_local_image()})
    log.info("sandbox images: %s", ", ".join(sorted(images)))
    sandbox = Sandbox(data / "repos", images, settings.sandbox, builds_root=data / "builds")
    executor = Executor(sandbox, data / "repos")
    try:
        model = NemotronClient(ModelConfig.from_env())
    except ModelError as exc:
        log.warning("Nemotron disabled: %s", exc)
        model = None
    events = EventLog(data)
    pipeline = Pipeline(settings, registry, sandbox, executor, model, events)

    # Workspaces: each one gets its own registry, event log and catalog under
    # <data_dir>/workspaces/<id>/, and shares the sandbox, model and repo clones.
    store = WorkspaceStore(data)

    def build_workspace(workspace_id, folder) -> Tenant:
        ws_registry, ws_events, ws_catalog = Registry(folder), EventLog(folder), Catalog(folder)
        return Tenant(id=workspace_id, registry=ws_registry, events=ws_events,
                      validator=WorkspaceValidator(settings, ws_registry, workspace_id, store),
                      catalog=ws_catalog, importer=EstablishedImporter(settings, ws_catalog, ws_registry, ws_events),
                      pipeline=Pipeline(settings, ws_registry, sandbox, executor, model, ws_events),
                      is_workspace=True)

    return create_app(settings, registry, executor, pipeline=pipeline, events=events,
                      workspaces=store, build_workspace=build_workspace)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(create, factory=True, host=os.environ.get("REPLIC8_HOST", "127.0.0.1"),
                port=int(os.environ.get("REPLIC8_PORT", "8000")))


if __name__ == "__main__":
    main()
