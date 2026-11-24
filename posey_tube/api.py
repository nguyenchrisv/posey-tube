"""HTTP API over aiohttp with token auth and per-pin locking."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from .gpio import GPIOController

_LOG = logging.getLogger(__name__)


async def _auth_middleware(app: web.Application, handler):
    """Token auth for all endpoints except /health."""

    async def middleware(request: web.Request):
        if request.path == "/health":
            return await handler(request)

        token = app["token"]
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.json_response({"error": "missing or invalid token"}, status=401)

        provided = auth.split(" ", 1)[1].strip()
        if not hmac.compare_digest(provided, token):
            # Never log the token
            _LOG.warning("Auth failed for %s %s", request.method, request.path)
            return web.json_response({"error": "invalid token"}, status=401)

        return await handler(request)

    return middleware


def _json_error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


def create_app(controller: GPIOController, token: str) -> web.Application:
    """Build the aiohttp application with all routes and middleware."""
    app = web.Application(middlewares=[_auth_middleware])
    app["token"] = token
    app["controller"] = controller

    # Routes
    app.router.add_get("/health", _health)
    app.router.add_get("/pins", _pins_all)
    app.router.add_get(r"/pins/{name}", _pin_one)
    app.router.add_post(r"/pins/{name}", _pin_write)
    app.router.add_post("/all-off", _all_off)

    return app


async def _health(request: web.Request) -> web.Response:
    from posey_tube import __version__

    return web.json_response({"ok": True, "version": __version__})


async def _pins_all(request: web.Request) -> web.Response:
    controller: GPIOController = request.app["controller"]
    pins = await controller.get_all_states()
    return web.json_response({"pins": pins})


async def _pin_one(request: web.Request) -> web.Response:
    controller: GPIOController = request.app["controller"]
    name = request.match_info["name"]
    try:
        state = await controller.get_state(name)
        return web.json_response(state)
    except KeyError:
        return _json_error(404, "unknown pin")


async def _pin_write(request: web.Request) -> web.Response:
    controller: GPIOController = request.app["controller"]
    name = request.match_info["name"]

    try:
        body = await request.json()
    except Exception:
        return _json_error(422, "invalid JSON body")

    if not isinstance(body, dict):
        return _json_error(422, "body must be a JSON object")

    has_on = "on" in body
    has_pulse = "pulse_ms" in body

    if has_on and has_pulse:
        return _json_error(422, "provide 'on' or 'pulse_ms', not both")
    if not has_on and not has_pulse:
        return _json_error(422, "body must contain 'on' (bool) or 'pulse_ms' (int)")

    try:
        if has_on:
            on = body["on"]
            if not isinstance(on, bool):
                return _json_error(422, "'on' must be a boolean")
            state = await controller.set_output(name, on)
            return web.json_response(state)

        pulse_ms = body["pulse_ms"]
        if not isinstance(pulse_ms, int):
            return _json_error(422, "'pulse_ms' must be an integer")
        if pulse_ms < 1 or pulse_ms > 10_000:
            return _json_error(422, "'pulse_ms' must be 1..10000")
        state = await controller.pulse_output(name, pulse_ms)
        return web.json_response(state)

    except KeyError:
        return _json_error(404, "unknown pin")
    except ValueError as e:
        return _json_error(409, str(e))
    except Exception as e:
        _LOG.exception("Unexpected error on pin write")
        return _json_error(500, f"internal error: {e}")


async def _all_off(request: web.Request) -> web.Response:
    controller: GPIOController = request.app["controller"]
    result = await controller.all_off()
    return web.json_response(result)