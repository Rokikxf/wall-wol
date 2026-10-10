import json
import socket
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def schema():
    return json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def validator(schema):
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


@pytest.fixture(scope="session")
def example():
    """Load an output example from tests/fixtures by file name, e.g. example("wake.json")."""
    return lambda name: json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))


class Listener:
    """A UDP socket on 127.0.0.1 that collects what the tool sends to it."""

    def __init__(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]

    def receive(self, count: int) -> list[bytes]:
        self.socket.settimeout(5)
        return [self.socket.recv(2048) for _ in range(count)]

    def is_quiet(self) -> bool:
        """True if nothing more arrives within 200 ms."""
        self.socket.settimeout(0.2)
        try:
            self.socket.recv(2048)
        except TimeoutError:
            return True
        return False


@pytest.fixture
def listener():
    receiver = Listener()
    yield receiver
    receiver.socket.close()
