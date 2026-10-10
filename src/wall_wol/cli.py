"""Command-line entry point: arguments in, one JSON document out.

Every run that gets past argument parsing prints exactly one JSON document,
even when something unexpected goes wrong.
"""

import argparse
import ipaddress
import logging
import sys
import time
from typing import Any

from wall_wol import __version__
from wall_wol.envelope import Run, emit
from wall_wol.magic import DEFAULT_PORT, Sender, describe_send_error, magic_packet, parse_mac

TOOL_NAME = "wall-wol"
LIMITED_BROADCAST = ipaddress.IPv4Address("255.255.255.255")
log = logging.getLogger(TOOL_NAME)


def mac(value: str) -> str:
    """argparse type: a MAC address, normalised to aa:bb:cc:dd:ee:ff."""
    try:
        return parse_mac(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def destination(value: str) -> ipaddress.IPv4Address:
    """argparse type: 255.255.255.255 or a private IPv4 address, such as a LAN's broadcast."""
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an IPv4 address: {value!r}") from None
    if ip != LIMITED_BROADCAST and (not ip.is_private or ip.is_unspecified):
        raise argparse.ArgumentTypeError(
            f"{ip} is not 255.255.255.255 or a private address. Use the broadcast address "
            "of the device's network, e.g. 192.168.1.255 for 192.168.1.0/24."
        )
    return ip


def bounded_int(low: int, high: int):
    def parse(value: str) -> int:
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Wake devices with Wake-on-LAN magic packets. Prints what was sent as JSON.",
    )
    parser.add_argument(
        "macs",
        nargs="+",
        type=mac,
        metavar="MAC",
        help="MAC address of the device to wake, e.g. aa:bb:cc:dd:ee:ff",
    )
    parser.add_argument(
        "--broadcast",
        type=destination,
        default=LIMITED_BROADCAST,
        metavar="IP",
        help="where to send the packets: the broadcast address of the device's network, "
        "e.g. 192.168.1.255 (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=bounded_int(1, 65535),
        default=DEFAULT_PORT,
        help="UDP port (default: %(default)s)",
    )
    parser.add_argument(
        "--count",
        type=bounded_int(1, 10),
        default=3,
        metavar="N",
        help="packets per device, since UDP can lose some (default: %(default)s)",
    )
    parser.add_argument(
        "--interval-ms",
        type=bounded_int(0, 10_000),
        default=100,
        metavar="MS",
        help="pause between rounds of packets (default: %(default)s)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def collect(args: argparse.Namespace, run: Run) -> dict[str, Any] | None:
    """Send the packets and return the result object, or record an error and return None."""
    broadcast = str(args.broadcast)
    sent = dict.fromkeys(args.macs, 0)  # a repeated MAC is woken once, first-given order
    source_ip = None
    try:
        with Sender(broadcast, args.port) as sender:
            source_ip = sender.source_ip
            log.info("sending to %s:%d from %s", broadcast, args.port, source_ip)
            for round_number in range(args.count):
                if round_number:
                    time.sleep(args.interval_ms / 1000)
                for target in sent:
                    sender.send(magic_packet(target))
                    sent[target] += 1
    except OSError as exc:
        code, message = describe_send_error(exc, broadcast, args.port)
        run.error(code, message)
        if not any(sent.values()):
            return None
    log.info("sent %d packet(s)", sum(sent.values()))
    return {
        "source_ip": source_ip,
        "targets": [{"mac": target, "packets_sent": count} for target, count in sent.items()],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(name)s: %(message)s",
    )
    params = {
        "broadcast": str(args.broadcast),
        "port": args.port,
        "count": args.count,
        "interval_ms": args.interval_ms,
    }
    run = Run(TOOL_NAME, __version__, params)
    try:
        result = collect(args, run)
    except Exception as exc:
        log.exception("unexpected error")
        run.error("internal_error", f"{type(exc).__name__}: {exc}")
        result = None
    return emit(run.finish(result))
