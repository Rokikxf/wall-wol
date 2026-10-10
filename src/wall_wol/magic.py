"""Wake-on-LAN magic packets: building them and sending them over UDP.

A magic packet is 6 bytes of 0xFF followed by the target's MAC address 16
times (102 bytes). A network card with Wake-on-LAN switched on watches for that
pattern anywhere in a frame, even while the computer is off, so the UDP port
and the IP address barely matter: what matters is that the frame reaches the
card. That is why the packet is broadcast.
"""

import errno
import re
import socket

PACKET_SIZE = 102
DEFAULT_PORT = 9  # the discard port; 7 (echo) and 0 are also common

MAC_FORMS = re.compile(
    r"[0-9a-f]{2}([:-])[0-9a-f]{2}(\1[0-9a-f]{2}){4}"  # aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff
    r"|[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}"  # aabb.ccdd.eeff (Cisco)
    r"|[0-9a-f]{12}"  # aabbccddeeff
)

# Socket errors as Linux and Windows number them (Windows uses WSA codes for sockets).
UNREACHABLE = {errno.ENETUNREACH, errno.EHOSTUNREACH}
NOT_PERMITTED = {errno.EACCES, errno.EPERM, getattr(errno, "WSAEACCES", errno.EACCES)}


def parse_mac(value: str) -> str:
    """Normalise a MAC address to aa:bb:cc:dd:ee:ff, or raise ValueError.

    Group (multicast and broadcast) addresses are refused: no network card has one.
    """
    text = value.strip().lower()
    if not MAC_FORMS.fullmatch(text):
        raise ValueError(f"not a MAC address: {value!r}")
    octets = bytes.fromhex(re.sub(r"[^0-9a-f]", "", text))
    if octets[0] & 1:
        raise ValueError(f"{value!r} is a multicast or broadcast address, not a network card's")
    if not any(octets):
        raise ValueError(f"{value!r} is all zeros, not a network card's address")
    return ":".join(f"{octet:02x}" for octet in octets)


def magic_packet(mac: str) -> bytes:
    """The magic packet for a MAC address in aa:bb:cc:dd:ee:ff form."""
    return b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16


class Sender:
    """A UDP socket that may broadcast, connected to one destination.

    Connecting a UDP socket sends nothing. It makes the routing table choose the
    outgoing interface now, so source_ip shows which network the packets will
    leave on, and a missing route fails here rather than on the first send.
    """

    def __init__(self, ip: str, port: int) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._socket.connect((ip, port))
        except OSError:
            self._socket.close()
            raise

    @property
    def source_ip(self) -> str | None:
        ip = self._socket.getsockname()[0]
        return None if ip == "0.0.0.0" else ip

    def send(self, packet: bytes) -> None:
        self._socket.send(packet)

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "Sender":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def describe_send_error(exc: OSError, ip: str, port: int) -> tuple[str, str]:
    """The error code and message for a failed connect or send."""
    reason = exc.strerror or str(exc)
    if exc.errno in UNREACHABLE:
        return (
            "network_unreachable",
            f"No route to {ip}: no network on this host reaches it ({reason}).",
        )
    if exc.errno in NOT_PERMITTED:
        return (
            "send_not_permitted",
            f"Not allowed to send to {ip}:{port} ({reason}). A firewall may be blocking it.",
        )
    return "send_failed", f"Could not send to {ip}:{port}: {reason}"
