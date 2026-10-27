#!/usr/bin/env python3

import os
import shlex
import subprocess
import xml.etree.ElementTree as ET

from executor_helper import ExecutorHelper

# init helper and read input
executor = ExecutorHelper()
executor.read_input()

# get config parameters
config_custom_options = executor.get_config("nmap_custom_options")
config_max_retries = executor.get_config("nmap_max_retries")
config_max_rtt_timeout = executor.get_config("nmap_max_rtt_timeout")
config_min_hostgroup = executor.get_config("nmap_min_hostgroup")
config_min_rate = executor.get_config("nmap_min_rate")
config_no_dns = executor.get_config_bool("nmap_no_dns", "false")
config_ping = executor.get_config_bool("nmap_ping", False)
config_ports = executor.get_config("nmap_ports")
config_return_ip_entities = executor.get_config_bool("nmap_return_ip_entities", "false")
config_scan_mode = executor.get_config_choices("nmap_scan_mode", "syn", choices=["syn", "connect", "udp"])
config_script_scan = executor.get_config_bool("nmap_script_scan", False)
config_service_detection = executor.get_config_bool("nmap_service_detection", False)
config_timing = executor.get_config_choices("nmap_timing", choices=["0", "1", "2", "3", "4", "5"])
config_top_ports = executor.get_config("nmap_top_ports")

if config_ports and config_top_ports:
    executor.add_error("nmap_ports and nmap_top_ports are mutually exclusive")
if not config_ports and not config_top_ports:
    executor.add_error("nmap_ports or nmap_top_ports is required")

executor.exit_on_error()

# nmap can't mix address families in one run (IPv6 targets need "-6"), so IPv4 and IPv6
# targets are scanned separately; ipv4_range entries (CIDR notation) go into the same
# target file as ipv4_address entries, nmap accepts both in one -iL file
ipv4_targets = [i["ipv4_address"] for i in executor.get_input_entities("ipv4_address")]
ipv4_targets += [i["cidr"] for i in executor.get_input_entities("ipv4_range")]

ipv6_targets = [i["ipv6_address"] for i in executor.get_input_entities("ipv6_address")]

scans = [
    ("ipv4", ipv4_targets, []),
    ("ipv6", ipv6_targets, ["-6"]),
]

for family, targets, extra_args in scans:
    if not targets:
        continue

    target_file = f"/data/tmp/{family}.txt"
    with open(target_file, "w") as f:
        for t in targets:
            f.write(t + os.linesep)

    # "-oA" writes normal, XML and grepable output to /data/artifacts/nmap-<family>.*, so the
    # raw tool output is preserved as an artifact and the XML file can be parsed below
    artifacts_prefix = f"/data/artifacts/nmap-{family}"
    nmap_command = [
        "nmap",
        "-v",
        "-iL",
        target_file,
        "-oA",
        artifacts_prefix,
        *extra_args,
    ]

    if config_scan_mode == "syn":
        nmap_command.append("-sS")
    elif config_scan_mode == "connect":
        nmap_command.append("-sT")
    elif config_scan_mode == "udp":
        nmap_command.append("-sU")

    if config_service_detection:
        nmap_command.append("-sV")
    if config_script_scan:
        nmap_command.append("-sC")

    if not config_ping:
        nmap_command.append("-Pn")

    if config_ports:
        nmap_command.append("-p")
        nmap_command.append(config_ports)
    elif config_top_ports:
        nmap_command.append("--top-ports")
        nmap_command.append(config_top_ports)

    if config_timing:
        nmap_command.append(f"-T{config_timing}")
    if config_min_rate:
        nmap_command.extend(["--min-rate", config_min_rate])
    if config_max_retries:
        nmap_command.extend(["--max-retries", config_max_retries])
    if config_no_dns:
        nmap_command.append("-n")
    if config_max_rtt_timeout:
        nmap_command.extend(["--max-rtt-timeout", config_max_rtt_timeout])
    if config_min_hostgroup:
        nmap_command.extend(["--min-hostgroup", config_min_hostgroup])

    if config_custom_options:
        nmap_command.extend(shlex.split(config_custom_options))

    result = subprocess.run(nmap_command)
    if result.returncode != 0:
        executor.add_error(f"nmap ({family}) exited with code {result.returncode}")
        continue

    # parse the XML output and report every open port as a "service" entity
    tree = ET.parse(f"{artifacts_prefix}.xml")
    for host in tree.getroot().findall("host"):
        address_el = host.find(f"address[@addrtype='{family}']")
        if address_el is None:
            continue
        address = address_el.get("addr")

        ports_el = host.find("ports")
        if ports_el is None:
            continue

        host_has_open_port = False

        for port_el in ports_el.findall("port"):
            state_el = port_el.find("state")
            if state_el is None or state_el.get("state") != "open":
                continue

            host_has_open_port = True

            service_entity = {
                "ip_address": address,
                "port": int(port_el.get("portid")),
                "protocol": port_el.get("protocol"),
                "service": "",
                "info": "",
            }

            # built the same way Metasploit's own nmap XML importer does (db_manager/import/nmap.rb):
            # service name prefixed with "tunnel/" for wrapped services (e.g. "ssl/http"), and
            # info as "product version extrainfo" - all three only present once -sV actually
            # probed the service, so this stays empty on a plain (non -sV) scan
            service_el = port_el.find("service")
            if service_el is not None:
                name = service_el.get("name")
                if name:
                    tunnel = service_el.get("tunnel")
                    service_entity["service"] = f"{tunnel}/{name}" if tunnel else name

                info_parts = [service_el.get(attr) for attr in ("product", "version", "extrainfo")]
                info = " ".join(part for part in info_parts if part)
                if info:
                    service_entity["info"] = info

            executor.add_output_entity("service", service_entity)

        if config_return_ip_entities and host_has_open_port:
            entitytype = f"{family}_address"
            executor.add_output_entity(entitytype, {entitytype: address})

# write output file
executor.write_output()
