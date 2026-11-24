# posey-tube Deployment

This directory contains the files needed to deploy posey-tube on a Raspberry Pi Zero W.

## Files

- `install.sh` — Idempotent installation script (run with sudo)
- `posey-tube.service` — systemd unit file
- `config.example.toml` — Example pin configuration
- `README.md` — This file

## Installation

Run on the Pi Zero W as a normal user with sudo:

```bash
# Clone the repo (or copy the deploy/ directory)
git clone https://github.com/nguyenchrisv/posey-tube.git
cd posey-tube

# Run the install script
sudo ./deploy/install.sh
```

The script will:
1. Install system dependencies (`python3-lgpio`, `python3-venv`, `git`)
2. Create the `posey-tube` service user in the `gpio` group
3. Clone the repo to `/opt/posey-tube`
4. Create a virtual environment at `/opt/posey-tube/venv` with `--system-site-packages` (so `lgpio` from apt is available)
5. Install the package in editable mode (`pip install -e .[dev]`)
6. Create `/etc/posey-tube/` (owned by root:gpio, 0750)
6. Copy `config.example.toml` to `/etc/posey-tube/config.toml` if missing
7. Create `/etc/posey-tube/secrets.env` (mode 600) if missing
8. Install the systemd unit to `/etc/systemd/system/posey-tube.service`

## Configuration

### 1. Edit the pin configuration

```bash
sudo nano /etc/posey-tube/config.toml
```

Define your pins under `[pins.<name>]`:

```toml
[pins.my_relay]
bcm = 17
direction = "out"
active_high = false
max_on_s = 600
label = "My relay"
```

See `config.example.toml` for all options.

### 2. Set the API token

The token is stored in `/etc/posey-tube/secrets.env` (mode 600, owned by root:gpio).
Run this command and paste/type your token when prompted:

```bash
sudo install -m 600 /dev/null /etc/posey-tube/secrets.env
sudo sh -c 'read -rsp "Posey-tube API token: " token && echo "POSEY_TUBE_TOKEN=${token}" > /etc/posey-tube/secrets.env'
```

The file must contain exactly:
```
POSEY_TUBE_TOKEN=your-secret-token-here
```

## Starting the Service

```bash
# Enable and start
sudo systemctl enable --now posey-tube

# Check status
systemctl status posey-tube

# View logs
journalctl -u posey-tube -f
```

## Testing

```bash
# Health check (no auth required)
curl http://localhost:8090/health

# List pins (requires token)
curl -H "Authorization: Bearer your-token" http://localhost:8090/pins

# Turn on a pin
curl -X POST -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"on": true}' \
     http://localhost:8090/pins/relay1

# Turn off a pin
curl -X POST -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"on": false}' \
     http://localhost:8090/pins/relay1

# Pulse a pin for 500 ms
curl -X POST -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"pulse_ms": 500}' \
     http://localhost:8090/pins/relay1

# Turn all outputs off
curl -X POST -H "Authorization: Bearer your-token" \
     http://localhost:8090/all-off
```

## Updating

Re-run the install script to update to the latest version:

```bash
sudo ./deploy/install.sh
# or from the repo root:
cd /opt/posey-tube && sudo ./deploy/install.sh
```

The script is idempotent: it will pull the latest code, reinstall the package, and reload systemd. Your config and secrets are preserved.

## Rollback

If an update breaks something, you can rollback to the previous commit:

```bash
cd /opt/posey-tube
sudo -u posey-tube git log --oneline -5
sudo -u posey-tube git checkout <previous-commit>
sudo systemctl restart posey-tube
```

Or restore a previous config from backup (you should back up `/etc/posey-tube/` regularly).

## Uninstalling

```bash
sudo systemctl disable --now posey-tube
sudo rm /etc/systemd/system/posey-tube.service
sudo systemctl daemon-reload
sudo rm -rf /opt/posey-tube /etc/posey-tube
sudo userdel posey-tube
```

## Manual `--all-off` CLI

The service provides a CLI flag to turn all configured outputs off:

```bash
# As root or posey-tube user:
sudo -u posey-tube /opt/posey-tube/venv/bin/python -m posey_tube --all-off
```

This is used by the systemd `ExecStopPost` to ensure outputs are off on service stop/restart.

## Security Notes

- The API token is **never** logged or returned in responses.
- Token comparison uses `hmac.compare_digest` (constant-time).
- Service runs as unprivileged `posey-tube` user in the `gpio` group.
- systemd hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `DeviceAllow` for GPIO only.
- Config directory is `root:gpio 0750`; secrets file is `600`.

## Hardware Safety

- Pi GPIO is **3.3 V logic, not 5 V tolerant**.
- Loads (relays, motors, fans) **must** go through a driver (MOSFET/relay module with flyback diode).
- **Mains voltage is out of scope** for hand-wired loads. Use certified enclosed relay modules or smart plugs.
- Christopher wires and powers hardware for the first time.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `systemctl status posey-tube` shows failed | Check `journalctl -u posey-tube -n 50` for errors |
| "Config file not found" | Ensure `/etc/posey-tube/config.toml` exists |
| "Secrets file not found" | Ensure `/etc/posey-tube/secrets.env` exists with `POSEY_TUBE_TOKEN=` |
| "unknown pin" in API | Pin name must match config.toml exactly |
| 401 Unauthorized | Token missing, wrong, or `Authorization: Bearer <token>` header missing |
| 409 Conflict | Writing to an input pin |
| 422 Unprocessable | Invalid JSON, bad `on`/`pulse_ms` values, or both fields provided |
| GPIO permission denied | Ensure service user is in `gpio` group; `ls -l /dev/gpiochip*` |

## Support

- Issues: https://github.com/nguyenchrisv/posey-tube/issues
- Architecture doc: `docs/ARCHITECTURE.md`
- Safety invariants: `AGENTS.md`