#!/usr/bin/env python3

import json
import subprocess

from executor_helper import ExecutorHelper

# init helper and read input
executor = ExecutorHelper()
executor.read_input()

# write domain list for subfinder
domains = executor.get_input_entities("domain")
with open("/data/tmp/domains.txt", "w") as f:
    for d in domains:
        f.write(d["fqdn"] + "\n")

# run subfinder - "-json -output" writes one JSON object per discovered host to
# /data/artifacts/subfinder.json, so the raw tool output is preserved as an artifact
result = subprocess.run(
    [
        "/root/subfinder",
        "-list",
        "/data/tmp/domains.txt",
        "-json",
        "-output",
        "/data/artifacts/subfinder.json",
        "-disable-update-check",
    ]
)
if result.returncode != 0:
    executor.add_error(f"subfinder exited with code {result.returncode}")
    executor.exit_on_error()

# parse the JSON-lines output and report every discovered host as a "domain" entity
hosts = set()
try:
    with open("/data/artifacts/subfinder.json", "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                hosts.add(json.loads(line)["host"])
            except (json.JSONDecodeError, KeyError):
                executor.add_warning(f"failed to parse subfinder output line: {line}")
except FileNotFoundError:
    executor.add_error("subfinder output file not found")
    executor.exit_on_error()

for host in sorted(hosts):
    executor.add_output_entity("domain", {"fqdn": host})

# write output file
executor.write_output()
