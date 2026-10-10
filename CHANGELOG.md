# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/). Changes to the output format also
state the new `schema_version` (see [CONTRACT.md](CONTRACT.md)).

## [Unreleased]

## [0.1.0] - 2026-10-10

First release. Output schema version 1.0.

### Added

- Wake-on-LAN magic packets, built with the standard library only, sent over
  UDP to a broadcast address (default `255.255.255.255:9`) and repeated
  (`--count`, `--interval-ms`) because UDP can lose them.
- MAC addresses in colon, dash, Cisco dot and bare form; multicast, broadcast
  and all-zero addresses are refused.
- Only `255.255.255.255` or private destination addresses are accepted.
- `source_ip` in the result: the local address the packets left from, which
  shows when they went out on the wrong network card.
- Errors `network_unreachable`, `send_not_permitted` and `send_failed`, and a
  partial result with `packets_sent` when sending stops part-way.
- Tests that check the packets byte for byte through a UDP socket on
  127.0.0.1, without broadcasting on the network.
