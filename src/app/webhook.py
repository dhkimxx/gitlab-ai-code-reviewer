from __future__ import annotations

from flask import Flask, request

from src.app.config import AppSettings
from src.app.orchestrator import WebhookOrchestrator


def register_webhook_routes(
    app: Flask,
    *,
    settings: AppSettings,
    orchestrator: WebhookOrchestrator,
) -> None:
    @app.route("/webhook", methods=["POST"])
    def webhook() -> tuple[str, int]:
        received_token = request.headers.get("X-Gitlab-Token")
        if received_token != settings.gitlab_webhook_secret_token:
            return "Unauthorized", 403

        payload = request.json or {}
        object_kind = payload.get("object_kind")

        if object_kind == "merge_request":
            if (
                not settings.enable_merge_request_review
                and not settings.enable_refactor_suggestion_review
            ):
                return "merge_request handling disabled", 200
            return orchestrator.handle_merge_request_event(payload)

        if object_kind == "push":
            if not settings.enable_push_review:
                return "push handling disabled", 200
            return orchestrator.handle_push_event(payload)

        return "OK", 200
