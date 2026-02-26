"""
middleware.py — Request ID injection and structured request logging.

Attach to Flask app by calling init_middleware(app) during app setup.

Each request gets a unique X-Request-ID header (generated if not provided by client).
Request details are logged as structured JSON for easy parsing by log aggregators.
"""

import uuid
import time
import json
import logging
from flask import g, request

logger = logging.getLogger(__name__)


def init_middleware(app):
    """Register before/after request hooks for request ID and structured logging."""

    @app.before_request
    def add_request_id():
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        g.start_time = time.time()

    @app.after_request
    def log_and_tag_request(response):
        duration_ms = round((time.time() - g.start_time) * 1000, 2)

        # Structured log entry — parseable by tools like Datadog, CloudWatch, Loki
        log_entry = {
            "request_id": g.request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "ip": request.remote_addr,
            "user_agent": (request.headers.get("User-Agent") or "")[:200],
        }

        # Include user_id if set by auth middleware
        user_id = getattr(g, 'user_id', None)
        if user_id:
            log_entry["user_id"] = user_id

        if response.status_code >= 500:
            logger.error("request", extra={"json": log_entry})
        elif response.status_code >= 400:
            logger.warning("request", extra={"json": log_entry})
        else:
            logger.info("request %s %s → %d (%.1fms)",
                        request.method, request.path, response.status_code, duration_ms)

        # Propagate request ID back to the client
        response.headers['X-Request-ID'] = g.request_id
        return response
