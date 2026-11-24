# posey-tube

Onyx's GPIO gateway: a Raspberry Pi Zero W on the lab Wi-Fi that exposes configured GPIO pins (relays, inputs) as a small token-protected HTTP API, so lab services like Bay Board can switch and read things.

Named after the Posey Tube between Oakland and Alameda. Wi-Fi/Bluetooth device bridging lives in [golden-gate](https://github.com/nguyenchrisv/golden-gate).

- Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Agent rules: [AGENTS.md](AGENTS.md)
- Dev: `pip install -e ".[dev]" && python -m pytest -q`

**Safety:** Pi GPIO is 3.3 V. Loads go through driver boards; mains only through certified enclosed modules or smart plugs.
