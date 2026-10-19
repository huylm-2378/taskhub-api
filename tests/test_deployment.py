import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from logging_setup import JsonFormatter
from middleware import RequestLoggingMiddleware


def test_frontend_preflight_and_bearer_auth(anonymous_client):
    origin = "http://localhost:5173"
    response = anonymous_client.options("/api/projects", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    # CORS does not bypass the existing authentication dependency.
    response = anonymous_client.get("/api/projects", headers={"Origin": origin})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == origin
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    assert len(response.headers["x-request-id"]) == 32


def test_unlisted_origin_is_not_allowed(anonymous_client):
    headers = {"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"}
    response = anonymous_client.options("/health", headers=headers)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    response = anonymous_client.get("/health", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_access_log_correlates_response_without_request_secrets(anonymous_client, caplog):
    with caplog.at_level(logging.INFO, logger="taskhub.requests"):
        response = anonymous_client.get("/health?token=private-query", headers={
            "Authorization": "Bearer private-token", "X-Request-ID": "untrusted-id",
        })
    record = next(r for r in caplog.records if r.name == "taskhub.requests")
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == response.headers["x-request-id"]
    assert entry["request_id"] != "untrusted-id"
    assert entry["route"] == "/health"
    assert entry["method"] == "GET" and entry["status"] == 200
    assert entry["duration_ms"] >= 0
    assert "private-query" not in json.dumps(entry)
    assert "private-token" not in json.dumps(entry)


def test_500_has_cors_and_correlated_error_log(caplog):
    api = FastAPI()

    @api.get("/broken/{item_id}")
    def broken(item_id: str):
        raise RuntimeError("private-database-password")

    app = RequestLoggingMiddleware(CORSMiddleware(api, allow_origins=["https://frontend.example"]))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/broken/private-id", headers={"Origin": "https://frontend.example"})
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    record = next(r for r in caplog.records if r.name == "taskhub.requests")
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == response.headers["x-request-id"]
    assert entry["status"] == 500 and entry["level"] == "ERROR"
    assert entry["route"] == "/broken/{item_id}"
    assert entry["error_type"] == "RuntimeError"
    assert entry["traceback"][-1]["function"] == "broken"
    assert "private-database-password" not in json.dumps(entry)
    assert "private-id" not in json.dumps(entry)


def test_request_ids_differ(anonymous_client):
    first = anonymous_client.get("/health").headers["x-request-id"]
    second = anonymous_client.get("/health").headers["x-request-id"]
    assert first != second
