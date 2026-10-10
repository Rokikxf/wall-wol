# wall-wol

Wakes computers over the network with Wake-on-LAN magic packets, and prints
what it sent as JSON. It is the remote power-on tool of the wall IT asset
management system, but it works on its own from the command line. It builds
the packets itself, with nothing but the Python standard library.

## Requirements

- Python 3.13, and no other packages.
- A device that supports Wake-on-LAN and has it switched on (see
  [Preparing a device](#preparing-a-device)).
- The sender must be on the same network (LAN or VLAN) as the device: routers
  do not forward broadcasts.

## Usage

```
wall-wol MAC [MAC ...] [--broadcast IP] [--port 9] [--count 3]
         [--interval-ms 100] [-v] [--version]
```

| Option             | Meaning                                                                 |
|--------------------|-------------------------------------------------------------------------|
| `MAC`              | The device's MAC address: `aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`, `aabb.ccdd.eeff` or `aabbccddeeff`. |
| `--broadcast IP`   | Where to send the packets (default `255.255.255.255`). Use the broadcast address of the device's network, e.g. `192.168.1.255` for `192.168.1.0/24`; see below. Only private addresses are accepted. |
| `--port`           | UDP port (default 9). Some devices listen on 7 instead.                 |
| `--count N`        | Packets per device (default 3), because UDP can lose packets.           |
| `--interval-ms MS` | Pause between rounds of packets (default 100).                          |

```console
$ wall-wol 3c:52:82:4a:1f:07 --broadcast 192.168.1.255
{
  "schema_version": "1.0",
  "tool": {"name": "wall-wol", "version": "0.1.0"},
  "started_at": "2026-10-10T19:05:12.481Z",
  "duration_ms": 201,
  "status": "ok",
  "errors": [],
  "params": {"broadcast": "192.168.1.255", "port": 9, "count": 3, "interval_ms": 100},
  "result": {
    "source_ip": "192.168.1.10",
    "targets": [{"mac": "3c:52:82:4a:1f:07", "packets_sent": 3}]
  }
}
```

More examples are in [tests/fixtures/](tests/fixtures/): `wake.json`,
`partial.json` and `unreachable.json`.

**A sent packet is not proof that the device woke up.** Wake-on-LAN has no
reply. To find out, ping the device a minute later, for example with
wall-healthcheck.

### How it works

A magic packet is 6 bytes of `FF` followed by the device's MAC address 16
times: 102 bytes. A network card with Wake-on-LAN switched on keeps listening
while the computer is off, and powers it on when it sees that pattern. The
computer has no IP address while it is off, so the packet is broadcast to
every device on the network, in a UDP datagram.

### Which broadcast address

`255.255.255.255` (the default) works on a computer with one network card. On a
computer with several, the operating system sends it out through the card with
the default route, which may not be on the device's network. The directed
broadcast address of the device's network, such as `192.168.1.255`, always
leaves through the card on that network.

`source_ip` in the result shows the local address the packets left from. If it
is not on the device's network, the packets went the wrong way. For example, on
a VirtualBox VM with a NAT adapter and a bridged adapter, `255.255.255.255`
leaves from the NAT address (`10.0.2.15`), and the LAN never sees it.

## Preparing a device

Wake-on-LAN must be switched on in up to three places:

1. **Firmware (BIOS/UEFI):** an option such as *Wake on LAN*, *Power on by
   PCI-E* or *Remote wake up*. Some business laptops wake only on mains power.
2. **The network card:**
   - Windows: Device Manager → the network adapter → *Power Management*: tick
     *Allow this device to wake the computer*. On *Advanced*, enable *Wake on
     Magic Packet*.
   - Linux: `sudo ethtool -s eth0 wol g` (`ethtool eth0` shows `Wake-on: g`
     when it is on). Make it permanent with your network manager, e.g.
     `nmcli connection modify <name> 802-3-ethernet.wake-on-lan magic`.
3. **Windows Fast Startup:** with it on, a PC that was shut down may not wake.
   Turn it off in *Control Panel → Power Options → Choose what the power buttons
   do*.

Wake-on-LAN needs a wired connection. Most Wi-Fi cards cannot be woken.

Magic packets are not authenticated: anyone on the network can send one. The
optional SecureOn password is not supported, because few cards implement it,
and it would be sent in clear text anyway.

## Output

Every run that gets past argument parsing prints exactly one JSON document to
stdout, described by [schema.json](schema.json) (schema version 1.0). Logs go
to stderr; `-v` turns on progress messages.

| Exit code | Meaning                                                    |
|-----------|------------------------------------------------------------|
| 0         | `status` is `ok`, or `partial` (sending stopped part-way)  |
| 1         | `status` is `error` (details in `errors`)                  |
| 2         | invalid arguments: nothing on stdout, usage on stderr      |

| Error code             | Cause                                                       |
|------------------------|-------------------------------------------------------------|
| `network_unreachable`  | No network on this computer reaches the broadcast address.  |
| `send_not_permitted`   | The operating system refused, usually because of a firewall. |
| `send_failed`          | Any other socket error. If it happens after some packets were sent, the status is `partial`, and `packets_sent` shows how many went out. |
| `internal_error`       | A bug in wall-wol. The traceback is on stderr.              |

The rules shared by all wall-\* tools are in [CONTRACT.md](CONTRACT.md).

## Development

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux: . .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

The tests never broadcast on the network they run on. Real packets go only to
a UDP socket the tests open on 127.0.0.1, which checks them byte for byte.
Everything else, including the error cases, uses a fake socket.

CI runs the same checks on every push and pull request.

## Releasing

1. Set `__version__` in `src/wall_wol/__init__.py`, and move the
   `Unreleased` entries in `CHANGELOG.md` under the new version.
2. Commit, then tag and push the tag:

   ```bash
   git tag v0.1.0
   git push origin main v0.1.0
   ```

CI fails a tag that does not match `__version__`. The hub installs an exact
release:

```bash
pip install "wall-wol @ git+https://github.com/Rokikxf/wall-wol@v0.1.0"
```
