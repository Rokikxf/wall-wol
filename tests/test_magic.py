"""MAC addresses, the magic packet itself, and the socket that sends it."""

import errno

import pytest

from wall_wol.magic import PACKET_SIZE, Sender, describe_send_error, magic_packet, parse_mac


@pytest.mark.parametrize(
    "text",
    ["3c:52:82:4a:1f:07", "3C:52:82:4A:1F:07", "3c-52-82-4a-1f-07", "3c52.824a.1f07",
     "3c52824a1f07", " 3c:52:82:4a:1f:07 "],
    ids=["colons", "upper-case", "dashes", "cisco-dots", "bare", "spaces-around"],
)  # fmt: skip
def test_mac_forms(text):
    assert parse_mac(text) == "3c:52:82:4a:1f:07"


@pytest.mark.parametrize(
    "text, reason",
    [
        ("3c:52:82:4a:1f", "not a MAC address"),
        ("3c:52:82:4a:1f:07:00", "not a MAC address"),
        ("3c:52-82:4a:1f:07", "not a MAC address"),  # mixed separators
        ("3g:52:82:4a:1f:07", "not a MAC address"),
        ("3c:5:82:4a:1f:07", "not a MAC address"),
        ("01:00:5e:00:00:fb", "multicast or broadcast"),
        ("ff:ff:ff:ff:ff:ff", "multicast or broadcast"),
        ("00:00:00:00:00:00", "all zeros"),
    ],
    ids=["too-short", "too-long", "mixed", "not-hex", "short-octet", "multicast", "broadcast",
         "zeros"],
)  # fmt: skip
def test_bad_macs(text, reason):
    with pytest.raises(ValueError, match=reason):
        parse_mac(text)


def test_magic_packet():
    packet = magic_packet("00:11:22:33:44:55")

    assert len(packet) == PACKET_SIZE
    assert packet.hex() == "ff" * 6 + "001122334455" * 16


def test_sender_reports_the_source_address_and_sends(listener):
    with Sender("127.0.0.1", listener.port) as sender:
        assert sender.source_ip == "127.0.0.1"
        sender.send(b"hello")

    assert listener.receive(1) == [b"hello"]


@pytest.mark.parametrize(
    "number, code",
    [
        (errno.ENETUNREACH, "network_unreachable"),
        (errno.EHOSTUNREACH, "network_unreachable"),
        (errno.EACCES, "send_not_permitted"),
        (getattr(errno, "WSAEACCES", errno.EPERM), "send_not_permitted"),
        (errno.ENOBUFS, "send_failed"),
    ],
    ids=["no-network", "no-host-route", "eacces", "windows-eacces", "other"],
)
def test_send_errors(number, code):
    error = OSError(number, "Some reason")

    assert describe_send_error(error, "192.168.1.255", 9)[0] == code
