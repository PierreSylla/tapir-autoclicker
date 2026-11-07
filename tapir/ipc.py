import argparse
import os
import socket
import sys
import threading
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
SOCKET_PATH = RUNTIME_DIR / "tapir.sock"
COMMANDS = ("toggle", "start", "stop", "show")


def send(command: str, path: Path = SOCKET_PATH) -> str | None:
    """Return the running instance's reply, or None when nothing answers."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(str(path))
            sock.sendall(command.encode() + b"\n")
            return sock.recv(64).decode().strip()
    except OSError:
        return None


def serve(handler, path: Path = SOCKET_PATH) -> None:
    """Accept commands on a background thread; handler runs on that thread."""
    # ponytail: two instances launched within the same few ms can both get here; add a lock file if that ever matters.
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen()
    threading.Thread(target=_accept_loop, args=(server, handler), name="tapir-ipc", daemon=True).start()


def _accept_loop(server: socket.socket, handler) -> None:
    while True:
        conn, _ = server.accept()
        with conn:
            conn.settimeout(1)
            try:
                command = conn.recv(64).decode().strip()
                known = command in COMMANDS
                if known:
                    handler(command)
                conn.sendall(b"ok\n" if known else b"unknown command\n")
            except (OSError, UnicodeDecodeError):
                pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="tapir", description="Autoclicker for Wayland.")
    parser.add_argument(
        "command", nargs="?", choices=("toggle", "start", "stop"), help="send a command to the running instance"
    )
    args = parser.parse_args()
    if args.command:
        if send(args.command) is None:
            print("tapir: no running instance", file=sys.stderr)
            return 1
        return 0
    if send("show") is not None:
        return 0
    from tapir.ui.app import run  # Qt takes long to import; CLI commands never need it

    return run()
