# Rules for AI agents working in this repo

**Team (Onyx):**

| Who | Role here | Commit author | Branch prefix | Sign-off |
|---|---|---|---|---|
| Gilfoyle (OpenClaw) | Engineer: core service, HTTP API | `Gilfoyle (OpenClaw)` | `gilfoyle/` | `— Gilfoyle` |
| Monica (Hermes Agent) | Engineer: config, deploy scripts | `Monica (Hermes Agent)` | `monica/` | `— Monica` |
| Dinesh (Hermes Agent) | Engineer: clients, integrations | `Dinesh (Hermes Agent)` | `dinesh/` | `— Dinesh` |
| Tobias (Hermes Agent) | Electronics: wiring spec and protection (`docs/WIRING.md`), no service code | `Tobias (Hermes Agent)` | `tobias/` | `— Tobias` |
| Winston (Hermes Agent) | QA: tests every PR after peer review; regression tests under `tests/` only | `Winston (Hermes Agent)` | `winston/` | `— Winston` |
| Jared | Product Owner: issues and acceptance criteria; no code | n/a | n/a | `— Jared` |
| Richard (Claude) | CTO: final review, merge, deploys to the Pi | n/a | `claude/` | n/a |

**Review order:** peer review by another engineer (findings grouped CRITICAL / WARNING / INFO), then Winston's QA report, then Richard's final review and merge. Start a peer review comment with `## Peer Review — APPROVED` or `## Peer Review — CHANGES REQUESTED`, and a QA report with `## QA: PASS` or `## QA: FAIL`. Stage labels: `needs-peer-review` → `needs-qa` → `ready-for-cto` (or `changes-requested`). Peer reviewers: Gilfoyle ↔ Monica; Dinesh's PRs go to Monica; Tobias's PRs go to Gilfoyle (checks the spec matches the code). Never push to a teammate's branch.

Read `docs/ARCHITECTURE.md` before starting any task. Follow these rules exactly.

## Project
posey-tube runs on a Raspberry Pi Zero W (Raspberry Pi OS Lite 32-bit, **Python 3.13**) and exposes configured GPIO pins as an HTTP API on the lab LAN.
- Code lives in the `posey_tube/` package (see the architecture doc). Pi setup goes in `deploy/`.
- Commands: `pip install -e ".[dev]"` then `python -m pytest -q` (all tests) · `python -m pytest tests/<file>.py` (one file).

## Workflow
- One git worktree per task, started from an up-to-date `main`. Do only the task you were given; minimal changes, no unrelated refactors.
- Run the tests after every change and fix failures before moving on. Add or update tests for every behaviour you change.
- If unsure between approaches, pick the simpler one and explain the alternative in the PR description.

## Commits, branches and PRs
- Conventional prefixes `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`; subject under ~50 characters.
- Never push to `main` (it's protected). One branch per task: `<your-prefix>/<task-name>`. PR description says `Closes #N` and includes:
  1. **What** changed and **why**
  2. **How you tested it**: commands and their summary lines
  3. **Self-review**: CRITICAL / WARNING / INFO, ending "X critical, Y warnings, Z info". Fix all CRITICAL first. **A violation of any rule in this file is always CRITICAL.**
  4. **Uncertainties**
- Keep PRs small: one issue per PR.

## Code rules
- **Allowed dependencies only:** `aiohttp` (HTTP server), `gpiozero` (GPIO), `pytest` + `pytest-asyncio` (dev). `lgpio` is provided by apt on the Pi and must not be a pip dependency. Everything else is the standard library. Adding any other package is CRITICAL.
- **Async** HTTP layer (aiohttp). Blocking GPIO calls are fine (they're fast); timers use asyncio, not threads.
- **Tests never touch real GPIO, the network or hardware.** Use gpiozero's `MockFactory` (set in a fixture) and aiohttp's test client. CI has no GPIO.
- **Safety invariants are CRITICAL if broken:** outputs start off; only configured pins are addressable; reserved pins are rejected; every output has `max_on_s` and is turned off when it expires; `/all-off` and shutdown turn every output off; `pulse_ms` ≤ 10 000. Each invariant has a test.
- **Secrets:** the API token comes only from `/etc/posey-tube/secrets.env` (`POSEY_TUBE_TOKEN`) or test fixtures with fake values. Never hard-code, log or return it. Compare with `hmac.compare_digest`.
- **Report only test results you just observed.** Before reporting counts, push, then run the tests on a clean checkout of the pushed branch and paste the summary line.
- Style: PEP 8, type hints on public functions, 4-space indentation.

## Hardware and hazards
- Agents never claim anything was wired, powered or tested on hardware. Christopher wires and does first power-on; Richard deploys.
- Pi GPIO is 3.3 V and not 5 V tolerant. Loads go through drivers (see `docs/WIRING.md`).
- Anything involving **mains voltage**, batteries or high current must be flagged as a **hazard** in the issue, PR and message. Mains only through certified, enclosed modules or smart plugs.

## Out of scope (don't modify unless the issue explicitly asks)
- `.github/`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `.gitignore`, `pyproject.toml` dependencies.

## Safety
- Never commit secrets, `.env` or `secrets.env` files.
- If an issue is ambiguous or conflicts with `docs/ARCHITECTURE.md`, the architecture wins; say so in the PR and tag Jared.
