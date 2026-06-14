"""CLI entry point: python -m camui [--ip IP] [--port PORT]"""

import argparse
from camui.app import app, initialize


def main() -> None:
    parser = argparse.ArgumentParser(description="CamUI for PiCamera2")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--ip", type=str, default="0.0.0.0", help="IP address to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    initialize()
    app.run(host=args.ip, port=args.port)


if __name__ == "__main__":
    main()
