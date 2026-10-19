"""Launch the C++ server, Python bot, and terminal human client together."""

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

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
    server_path = Path(__file__).resolve().parents[1] / "build" / "dodger-server"
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
