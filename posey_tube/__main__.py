"""Main entry point: ``python -m posey_tube``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

from aiohttp import web

from .config import load_config, load_token, ConfigError, DEFAULT_CONFIG_PATH, DEFAULT_SECRETS_PATH
from .api import create_app
from .gpio import GPIOController

_LOG = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="posey-tube GPIO HTTP API")
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("POSEY_TUBE_PORT", "8090")),
        help="Port to listen on (default: POSEY_TUBE_PORT or 8090)",
    )
    p.add_argument(
        "--config",
        default=None,
        help="Config TOML path (default: POSEY_TUBE_CONFIG or /etc/posey-tube/config.toml)",
    )
    p.add_argument(
        "--secrets",
        default=None,
        help="Secrets env path (default: POSEY_TUBE_SECRETS or /etc/posey-tube/secrets.env)",
    )
    p.add_argument(
        "--all-off",
        action="store_true",
        help="Turn all configured outputs off and exit (used by systemd ExecStopPost)",
    )
    return p.parse_args()


def _run_all_off(configs: list) -> int:
    """Drive all configured outputs off and exit. Returns 0 on success."""
    import asyncio
    from .gpio import GPIOController

    controller = GPIOController(configs)

    async def _run():
        await controller.all_off()

    asyncio.run(_run())
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = _parse_args()

    # Handle --all-off flag first (doesn't need token/secrets)
    if args.all_off:
        try:
            configs = load_config(args.config)
        except ConfigError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Unexpected error loading config: {e}", file=sys.stderr)
            return 2
        return _run_all_off(configs)

    # Load config and token for normal server mode
    try:
        configs = load_config(args.config)
        token = load_token(args.secrets)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error loading config: {e}", file=sys.stderr)
        return 2

    controller = GPIOController(configs)
    app = create_app(controller, token)

    # Ensure all outputs off on aiohttp cleanup (covers SIGTERM/SIGINT + normal shutdown)
    async def _on_cleanup(app: web.Application):
        await app["controller"].shutdown()

    app.on_cleanup.append(_on_cleanup)

    port = args.port
    _LOG.info("Starting posey-tube on 0.0.0.0:%d", port)

    # aiohttp's run_app handles SIGTERM/SIGINT and runs on_cleanup
    web.run_app(app, host="0.0.0.0", port=port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())