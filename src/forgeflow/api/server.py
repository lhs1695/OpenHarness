"""Uvicorn entrypoint — builds the app from environment config."""

from __future__ import annotations

from forgeflow.api.app import build_app
from forgeflow.application.factory import create_service_from_env

app = build_app(create_service_from_env())
