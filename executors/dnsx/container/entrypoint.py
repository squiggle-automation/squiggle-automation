#!/usr/bin/env python3

import ipaddress
import json
import shlex
import subprocess

from executor_helper import ExecutorHelper

DNSX = "/root/dnsx"


def add_entities_from_record(record):
    """
    Adds DNS record to entity, depending on record type.

    TXT is not handled
    """
    for address in record.get("a", []):
        executor.add_output_entity("ipv4_address", {"ipv4_address": address})
    for address in record.get("aaaa", []):
        executor.add_output_entity("ipv6_address", {"ipv6_address": address})
    for field in ("cname", "ns", "mx", "srv"):
        for value in record.get(field, []):
            # these records could contain domains or ips
            value = value.rstrip(".")
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                executor.add_output_entity("domain", {"fqdn": value})
                continue
            entitytype = "ipv4_address" if address.version == 4 else "ipv6_address"
            executor.add_output_entity(entitytype, {entitytype: value})


# init helper and read input
executor = ExecutorHelper()
executor.read_input()

# get config parameters
config_mode = executor.get_config_choices("dnsx_mode", choices=["forward", "reverse"], required=True)
config_custom_options = executor.get_config("dnsx_custom_options")
config_resolver = executor.get_config("dns_resolver", "8.8.8.8")

executor.exit_on_error()

# get input entities, depending on mode
if config_mode == "forward":
    targets = [d["fqdn"] for d in executor.get_input_entities("domain")]
else:
    targets = [i["ipv4_address"] for i in executor.get_input_entities("ipv4_address")]
    targets += [i["ipv6_address"] for i in executor.get_input_entities("ipv6_address")]

# run dnsx
with open("/data/tmp/targets.txt", "w") as f:
    for t in targets:
        f.write(t + "\n")

dnsx_command = [
    DNSX,
    "-list",
    "/data/tmp/targets.txt",
    "-json",
    "-output",
    "/data/artifacts/dnsx.jsonl",
    "-resolver",
    config_resolver,
    "-disable-update-check",
]
if config_mode == "forward":
    dnsx_command += ["-a", "-aaaa", "-cname", "-ns", "-txt", "-srv", "-mx", "-axfr"]
else:
    dnsx_command += ["-ptr"]

if config_custom_options:
    dnsx_command.extend(shlex.split(config_custom_options))

result = subprocess.run(dnsx_command)
executor.add_info(f"dnsx exited with code {result.returncode}")

# parse the JSON lines and report resolved records as entities
with open("/data/artifacts/dnsx.jsonl", "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            executor.add_warning(f"failed to parse dnsx output line: {line}")
            continue

        if config_mode == "forward":
            add_entities_from_record(record)

            # a successful zone transfer returns the rest of the zone as a "chain" of
            # further records (same shape as a top-level result) - an open AXFR is also
            # worth flagging on its own, most DNS servers should refuse it
            chain = (record.get("axfr") or {}).get("chain") or []
            if chain:
                executor.add_info(f"zone transfer (AXFR) succeeded for {record.get('host')}")
                for chained_record in chain:
                    add_entities_from_record(chained_record)
        else:
            for domain in record.get("ptr", []):
                executor.add_output_entity("domain", {"fqdn": domain.rstrip(".")})

# write output file
executor.write_output()
