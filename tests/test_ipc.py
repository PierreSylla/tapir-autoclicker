import socket

from tapir import ipc


def test_command_round_trip(tmp_path):
    path = tmp_path / "tapir.sock"
    received = []
    ipc.serve(received.append, path)
    assert ipc.send("toggle", path) == "ok"
    assert ipc.send("show", path) == "ok"
    assert ipc.send("explode", path) == "unknown command"
    assert received == ["toggle", "show"]


def test_no_instance(tmp_path):
    assert ipc.send("toggle", tmp_path / "missing.sock") is None


def test_stale_socket_is_replaced(tmp_path):
    path = tmp_path / "tapir.sock"
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(path))
    dead.close()
    assert ipc.send("toggle", path) is None
    received = []
    ipc.serve(received.append, path)
    assert ipc.send("stop", path) == "ok"
    assert received == ["stop"]
