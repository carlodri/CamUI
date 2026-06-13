# CamUI — Agent Guide

Full restructuring plan: `/home/carlo/.gemini/antigravity-cli/brain/315dee58-e24d-48ac-bf3c-80e37fbab8fe/restructuring_plan.md`

## Run

```bash
# pixi (preferred — manages env and dependencies)
pixi run dev             # python -m camui --ip 0.0.0.0 --port 8080
pixi run diagnostics     # python -m camui.diagnostics
pixi run dev-port        # PORT=9090 pixi run dev-port

# Package entry (after pip install -e . or pixi build)
python -m camui --ip 0.0.0.0 --port 8080

# Legacy (monolithic — still the most complete entry point)
python app.py --ip 0.0.0.0 --port 8080
```

## Hardware requirement

picamera2/libcamera only works on Raspberry Pi OS (Bookworm+) with a camera connected. The app will crash on any other machine. `src/camui/diagnostics.py` probes cameras safely for debugging.

## Mid-refactor — two codebases coexist

| What | Where | Status | Target |
|------|-------|--------|--------|
| Working app | `app.py`, `templates/`, `static/` at repo root | All logic in one monolithic file | Delete after migration |
| Refactored package | `src/camui/` | `camera.py` now created — import chain complete | All code lives here |

**Destination layout** (per restructuring plan):
```
src/camui/
├── __init__.py, __main__.py, app.py, camera.py
├── gallery.py, gpio.py, config.py
├── data/          ← static databases (read-only, packaged)
├── static/        ← CSS/JS/img + camera_profiles/ (dev fallback, read-write)
└── templates/     ← Jinja2
```

If you touch `CameraObject` or `StreamingOutput`, edit `src/camui/camera.py` — the legacy `app.py` (root) still has a copy but should not be updated further.

## Data layout

- **Runtime data** (gallery images, camera profiles, last-config): `$CAMUI_DATA_DIR` or `$CWD/gallery/` + `camera_profiles/` + `camera-last-config.json`
- **Static data** (camera DBs): `src/camui/data/` — loaded via `importlib.resources`
- **Templates/static**: `src/camui/templates/`, `src/camui/static/` (package) or root equivalents (legacy)

## Architecture notes

- `CameraObject` manages one camera: lifecycle, streaming (MJPEG), config profiles, still capture.
- Cameras keyed by `Num` in global `cameras` dict (supports multi-camera on Pi5).
- `ImageGallery` lists/paginates/edits JPGs (optional paired DNG for RAW).
- Two UI modes: desktop (`camera.html`) and mobile (`camera_mobile.html`).
- Pixi manages the Python env (`pixi.toml` → conda-forge). picamera2 comes from conda-forge.
- No tests, no linters, no typecheckers, no CI configured.
- Docker: `docker compose up` — needs `privileged: true` for `/dev/video*` access.

## Common gotchas

- picamera2 is imported lazily inside `initialize()` to avoid crashing at import time on non-Pi machines.
- `camera-last-config.json` is gitignored and auto-generated at startup.
- `camera_profiles/` lives inside `static/` in the legacy code but is really runtime user data; final destination is `$CAMUI_DATA_DIR/camera_profiles/`.
- `connected_cameras_config.json` at root is a runtime artifact, now gitignored but still tracked in git — run `git rm --cached connected_cameras_config.json` to stop tracking.
