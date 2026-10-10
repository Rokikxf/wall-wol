"""The command line: arguments, what goes on the wire, error codes and one valid document
every time. Real packets go only to a UDP socket on 127.0.0.1; everything else uses a fake
sender, so the tests never broadcast on the network they run on."""

import errno
import json
import shutil
import subprocess
import sysconfig

import pytest

from wall_wol import cli
from wall_wol.magic import magic_packet

PC = "3c:52:82:4a:1f:07"
LAPTOP = "d8:bb:c1:22:9e:40"


def invoke(capsys, *argv):
    code = cli.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def to(listener, *argv):
    """Options that send to the listener, without pauses."""
    return ["--broadcast", "127.0.0.1", "--port", str(listener.port), "--interval-ms", "0", *argv]


class Sent(list):
    """The packets a fake sender "sent"; .opened lists the (ip, port) it was opened for."""

    def __init__(self):
        super().__init__()
        self.opened = []


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.time, "sleep", calls.append)
    return calls


@pytest.fixture
def fake_sender(monkeypatch, sleeps):
    """Replace the socket. Call with connect_error=..., or fail_after=N and send_error=...
    to make it fail. Returns a Sent list."""

    def install(connect_error=None, fail_after=None, send_error=None):
        packets = Sent()

        class FakeSender:
            source_ip = "192.168.1.10"

            def __init__(self, ip, port):
                packets.opened.append((ip, port))
                if connect_error:
                    raise connect_error

            def send(self, packet):
                if len(packets) == fail_after:
                    raise send_error
                packets.append(packet)

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                pass

        monkeypatch.setattr(cli, "Sender", FakeSender)
        return packets

    return install


# --- real packets, over loopback ---


def test_packets_on_the_wire(capsys, listener, validator):
    code, doc = invoke(capsys, "3C-52-82-4A-1F-07", "d8bb.c122.9e40", *to(listener, "--count", "2"))

    validator.validate(doc)
    assert code == 0
    assert doc["result"] == {
        "source_ip": "127.0.0.1",
        "targets": [{"mac": PC, "packets_sent": 2}, {"mac": LAPTOP, "packets_sent": 2}],
    }
    assert listener.receive(4) == [magic_packet(PC), magic_packet(LAPTOP)] * 2
    assert listener.is_quiet()


def test_a_repeated_mac_is_woken_once(capsys, listener):
    _, doc = invoke(capsys, PC, PC.upper(), *to(listener, "--count", "1"))

    assert doc["result"]["targets"] == [{"mac": PC, "packets_sent": 1}]
    assert listener.receive(1) == [magic_packet(PC)]
    assert listener.is_quiet()


def test_installed_command(listener, validator):
    exe = shutil.which(cli.TOOL_NAME, path=sysconfig.get_path("scripts"))
    assert exe, 'console script not found: run pip install -e ".[dev]"'

    proc = subprocess.run([exe, PC, *to(listener, "--count", "1")], capture_output=True, text=True,
                          check=False)  # fmt: skip

    assert proc.returncode == 0, proc.stderr
    validator.validate(json.loads(proc.stdout))
    assert listener.receive(1) == [magic_packet(PC)]


# --- the documents in tests/fixtures ---


def test_wake(capsys, fake_sender, validator, example):
    packets = fake_sender()

    code, doc = invoke(capsys, PC, LAPTOP, "--broadcast", "192.168.1.255")

    validator.validate(doc)
    assert code == 0
    assert packets.opened == [("192.168.1.255", 9)]
    assert len(packets) == 6
    for field in ("status", "errors", "params", "result"):
        assert doc[field] == example("wake.json")[field], field


def test_defaults(capsys, fake_sender):
    packets = fake_sender()

    _, doc = invoke(capsys, PC)

    assert packets.opened == [("255.255.255.255", 9)]
    assert doc["params"] == {"broadcast": "255.255.255.255", "port": 9, "count": 3,
                             "interval_ms": 100}  # fmt: skip


def test_pauses_between_rounds_not_after_the_last(capsys, fake_sender, sleeps):
    fake_sender()

    invoke(capsys, PC, LAPTOP, "--count", "3", "--interval-ms", "250")

    assert sleeps == [0.25, 0.25]


def test_failure_part_way_is_partial(capsys, fake_sender, validator, example):
    fake_sender(fail_after=3, send_error=OSError(errno.ENOBUFS, "No buffer space available"))

    code, doc = invoke(capsys, PC, LAPTOP, "--broadcast", "192.168.1.255")

    validator.validate(doc)
    assert code == 0
    for field in ("status", "errors", "params", "result"):
        assert doc[field] == example("partial.json")[field], field


def test_no_route(capsys, fake_sender, validator, example):
    fake_sender(connect_error=OSError(errno.ENETUNREACH, "Network is unreachable"))

    code, doc = invoke(capsys, PC, LAPTOP, "--broadcast", "10.20.0.255")

    validator.validate(doc)
    assert code == 1
    for field in ("status", "errors", "params", "result"):
        assert doc[field] == example("unreachable.json")[field], field


def test_not_permitted(capsys, fake_sender, validator):
    fake_sender(connect_error=OSError(errno.EACCES, "Permission denied"))

    code, doc = invoke(capsys, PC)

    validator.validate(doc)
    assert code == 1
    assert doc["errors"][0]["code"] == "send_not_permitted"


def test_unexpected_exception_still_prints_valid_json(capsys, monkeypatch, validator):
    def fail(args, run):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(cli, "collect", fail)
    code, doc = invoke(capsys, PC)

    validator.validate(doc)
    assert code == 1
    assert doc["errors"][0]["code"] == "internal_error"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["not-a-mac"],
        ["01:00:5e:00:00:fb"],
        ["ff:ff:ff:ff:ff:ff"],
        [PC, "--broadcast", "8.8.8.255"],
        [PC, "--broadcast", "0.0.0.0"],
        [PC, "--broadcast", "224.0.0.1"],
        [PC, "--broadcast", "printers.lan"],
        [PC, "--port", "0"],
        [PC, "--count", "0"],
        [PC, "--count", "11"],
        [PC, "--interval-ms", "-1"],
    ],
    ids=["no-mac", "bad-mac", "multicast-mac", "broadcast-mac", "public-broadcast",
         "unspecified", "multicast-ip", "hostname", "port-0", "count-0", "count-11",
         "negative-interval"],
)  # fmt: skip
def test_bad_arguments(capsys, fake_sender, argv):
    packets = fake_sender()

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert capsys.readouterr().out == ""
    assert packets.opened == []
