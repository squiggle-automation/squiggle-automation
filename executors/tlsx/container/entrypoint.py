#!/usr/bin/env python3

import json
import subprocess

from executor_helper import ExecutorHelper

# init helper and read input
executor = ExecutorHelper()
executor.read_input()

# tlsx operates on host:port targets - TLS is a TCP concept, so only tcp services make sense
services = executor.get_input_entities("service")
targets = [f"{s['address']}:{s['port']}" for s in services if s.get("protocol") == "tcp"]

if targets:
    with open("/data/tmp/targets.txt", "w") as f:
        for t in targets:
            f.write(t + "\n")

    # run tlsx - "-json -output" writes one JSON object per successful TLS handshake to
    # /data/artifacts/tlsx.json, so the raw tool output is preserved as an artifact. Hosts that
    # don't speak TLS at all are just skipped by tlsx, not reported as an error.
    result = subprocess.run(
        [
            "/root/tlsx",
            "-list",
            "/data/tmp/targets.txt",
            "-json",
            "-output",
            "/data/artifacts/tlsx.json",
            "-silent",
            "-disable-update-check",
        ]
    )
    if result.returncode != 0:
        executor.add_error(f"tlsx exited with code {result.returncode}")
        executor.exit_on_error()

    # parse the JSON-lines output and report every certificate domain (CN + SANs) as a "domain"
    # entity, deduplicated
    domains = set()
    try:
        with open("/data/artifacts/tlsx.json", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    cert = json.loads(line)
                except json.JSONDecodeError:
                    executor.add_warning(f"failed to parse tlsx output line: {line}")
                    continue

                subject_cn = cert.get("subject_cn")
                if subject_cn:
                    domains.add(subject_cn)
                for san in cert.get("subject_an", []):
                    domains.add(san)
    except FileNotFoundError:
        # no target actually completed a TLS handshake - not an error, just nothing to report
        pass

    for domain in sorted(domains):
        executor.add_output_entity("domain", {"domain": domain})

# write output file
executor.write_output()
