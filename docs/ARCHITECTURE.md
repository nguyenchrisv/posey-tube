# posey-tube architecture

posey-tube is Onyx's **GPIO gateway**: a Raspberry Pi Zero W on the lab Wi-Fi that lets other lab services (Bay Board, scripts on onyx-ops/dev-01) read inputs and drive outputs over HTTP. Wi-Fi/Bluetooth device bridging stays in `golden-gate`; posey-tube is wired I/O only.

## Hardware and OS
- Raspberry Pi Zero W v1.1: single-core ARMv6, 512 MB RAM, 2.4 GHz Wi-Fi only, no Ethernet.
- Raspberry Pi OS Lite **32-bit** (Trixie, **Python 3.13**). The Zero W can't run 64-bit, and current Node builds don't support ARMv6, so the service is Python.
- GPIO access via **gpiozero** with the **lgpio** pin factory (`python3-lgpio` from apt; the venv uses `--system-site-packages`).
- Hostname `posey-tube`, DHCP reservation on the router, SSH by key only, LAN only. Agents can't reach it; Richard deploys.

## Electrical rules (Tobias owns the wiring spec)
- Pi GPIO is **3.3 V logic, not 5 V tolerant**. Keep per-pin current within the spec (Tobias sets the number in `docs/WIRING.md`; design to ≤ 8 mA per pin and well under the total budget).
- Loads (relays, motors, fans, LED strips) are never driven directly from a pin: use a driver (MOSFET or relay module with transistor driver and flyback diode).
- **Mains voltage is out of scope** for anything hand-wired. Mains loads only through a certified, enclosed relay module or a smart plug, and are flagged as a hazard in the issue, PR and message. Christopher wires and powers hardware for the first time.

## Software shape
```
posey_tube/
  config.py   # loads /etc/posey-tube/config.toml (pins) and secrets.env (API token)
  pins.py     # Pin model: name, BCM number, direction, active_high, default off, max_on_s
  gpio.py     # backend over gpiozero; tests use gpiozero's MockFactory
  api.py      # aiohttp app
  __main__.py # python -m posey_tube
deploy/       # systemd unit, install script, example config
tests/
```

### Pin configuration (`/etc/posey-tube/config.toml`)
```toml
[pins.relay1]
bcm = 17
direction = "out"     # "out" | "in"
active_high = false   # many relay boards are active-low
max_on_s = 600        # auto-off safety timer; required for outputs
label = "Desk lamp relay"

[pins.door]
bcm = 27
direction = "in"
pull = "up"           # "up" | "down" | "none"
```
- Only configured pins exist. Unknown names are 404; nothing addresses raw BCM numbers over the API.
- Reserved pins (I2C 2/3, UART 14/15, ID EEPROM 0/1) are rejected at config load unless the issue explicitly allows them.
- Every output is **off at start-up, on shutdown and on crash** (systemd `ExecStopPost` runs the all-off command).
- Every output has `max_on_s`; when it expires, the pin turns off and the event is logged.

### HTTP API (port 8090, JSON)
| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/health` | | `{"ok": true, "version": ...}` (no auth) |
| GET | `/pins` | | all pins with state |
| GET | `/pins/{name}` | | one pin: `{"name","direction","on","since","label"}` |
| POST | `/pins/{name}` | `{"on": true}` or `{"pulse_ms": 500}` | new state; outputs only (inputs → 409) |
| POST | `/all-off` | | turns every output off |

- All endpoints except `/health` need `Authorization: Bearer <token>`; the token comes from `POSEY_TUBE_TOKEN` in `/etc/posey-tube/secrets.env`. Compare with `hmac.compare_digest`; never log it.
- `pulse_ms` is capped at 10 000 ms. Writes are serialised per pin.
- Inputs report `on` as the logical (pull-adjusted) state. Push events (webhooks/SSE) are a later issue.
