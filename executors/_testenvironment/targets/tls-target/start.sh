#!/usr/bin/env bash
set -euo pipefail

socat OPENSSL-LISTEN:8443,cert=/etc/tls-target.pem,verify=0,fork,reuseaddr SYSTEM:'true'
