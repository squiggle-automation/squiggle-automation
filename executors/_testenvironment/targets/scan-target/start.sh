#!/usr/bin/env bash
set -euo pipefail

socat TCP4-LISTEN:80,fork,reuseaddr SYSTEM:'true' &
socat TCP4-LISTEN:8443,fork,reuseaddr SYSTEM:'true' &
socat TCP6-LISTEN:80,fork,reuseaddr,ipv6only=1 SYSTEM:'true' &
socat TCP6-LISTEN:8443,fork,reuseaddr,ipv6only=1 SYSTEM:'true' &

# UDP 9010 open: replies to any datagram (incl. nmap's empty probe), so a UDP scan sees a
# real response and reports "open" rather than "open|filtered". Nothing listens on other UDP
# ports, so those get an ICMP port-unreachable and are reported "closed".
socat UDP4-LISTEN:9010,fork SYSTEM:'echo hi' &

# TCP 2222 open, sends a real OpenSSH version banner unprompted (as SSH servers do) - nmap's
# -sV NULL probe reads it and matches it against its service-probe database, so this is a
# genuine banner-grab rather than a table/port-number guess.
socat TCP4-LISTEN:2222,fork,reuseaddr SYSTEM:'printf "SSH-2.0-OpenSSH_9.6\r\n"; sleep 1' &

wait -n
