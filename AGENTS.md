# CamUI — Agent Guide

Full restructuring plan: `/home/carlo/.gemini/antigravity-cli/brain/315dee58-e24d-48ac-bf3c-80e37fbab8fe/restructuring_plan.md`

## Run

```bash
# pixi (preferred — manages env and dependencies)
pixi run dev             # python -m camui --ip 0.0.0.0 --port 8080
pixi run diagnostics     # python -m camui.diagnostics
pixi run dev-port        # PORT=9090 pixi run dev-port

# Package entry (after pip install -e . or pixi build)
#   pip install -e . && python -m camui --ip 0.0.0.0 --port 8080
```

## Hardware requirement

picamera2/libcamera only works on Raspberry Pi OS (Bookworm+) with a camera connected. The app will crash on any other machine. `src/camui/diagnostics.py` probes cameras safely for debugging.

## Code layout

```
src/camui/
├── __init__.py, __main__.py, app.py, camera.py
├── gallery.py, gpio.py, config.py
├── data/          ← static databases (read-only, packaged)
├── static/        ← CSS/JS/img + camera_profiles/ (dev fallback, read-write)
└── templates/     ← Jinja2
```

## Data layout

- **Runtime data** (gallery images, camera profiles, last-config): `$CAMUI_DATA_DIR` or `$CWD/gallery/` + `camera_profiles/` + `camera-last-config.json`
- **Static data** (camera DBs): `src/camui/data/` — loaded via `importlib.resources`
- **Templates/static**: `src/camui/templates/`, `src/camui/static/`

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
- `camera_profiles/` is runtime user data resolved to `$CAMUI_DATA_DIR/camera_profiles/`.
- `connected_cameras_config.json` at root is a runtime artifact, gitignored but still tracked in git — run `git rm --cached connected_cameras_config.json` to stop tracking.
