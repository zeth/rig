"""Launch the C++ server, Python bot, and terminal human client together."""

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "build"))

from dodger_api_client import Client
from dodger_api_client.api.default import create_game

from client import get_game
from terminal import run as run_terminal


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0,
                        help="localhost port; 0 chooses an available port")
    parser.add_argument("--width", type=int, help="arena width, 8 to 80 (default: 20)")
    parser.add_argument("--height", type=int, help="arena height, 6 to 40 (default: 12)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be 0 through 65535")
    if args.port:
        port = args.port
    else:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    server_path = Path(__file__).resolve().parent / "build" / "dodger-server"
    server = subprocess.Popen([str(server_path), str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              text=True)
    bot = None
    try:
        for _ in range(100):
            try:
                get_game(base_url)
                break
            except urllib.error.URLError:
                if server.poll() is not None:
                    raise RuntimeError(server.stderr.read().strip())
                time.sleep(0.02)
        else:
            raise RuntimeError("Dodger server did not start")
        options = {}
        if args.width is not None:
            options["width"] = args.width
        if args.height is not None:
            options["height"] = args.height
        with Client(base_url=base_url, raise_on_unexpected_status=True) as client:
            created = create_game.sync_detailed(client=client, **options)
        if created.status_code != 200:
            raise RuntimeError(f"could not create game: {created.parsed}")
        bot = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("bot.py")), "--url", base_url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        run_terminal(base_url)
    finally:
        stop(bot)
        stop(server)
        server.stderr.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"Dodger: {error}", file=sys.stderr)
        sys.exit(1)
