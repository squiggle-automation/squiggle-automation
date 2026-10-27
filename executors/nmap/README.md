# nmap

Run port scans with nmap.

IPv4 and IPv6 addresses are scanned in two separate nmap runs (nmap can't mix address families
in one run), each using the same scan options.

## Input data types

- `ipv4_address`
- `ipv4_range`
- `ipv6_address`

## Output data types

- `service`
- `ipv4_address` / `ipv6_address` - only with `nmap_return_ip_entities` enabled, one entity per
  scanned host that has at least one open port.

## Config

- `nmap_scan_mode` (optional, default `syn`) - `syn`, `connect` or `udp`.
- `nmap_ports` / `nmap_top_ports` - exactly one of the two is required; mutually exclusive.
- `nmap_ping` (optional, default `false`) - enable host discovery; disabled by default (`-Pn`,
  every address is scanned regardless of whether it responds to discovery probes).
- `nmap_service_detection` (optional, default `false`) - `-sV`.
- `nmap_script_scan` (optional, default `false`) - `-sC`.
- `nmap_timing` (optional) - `0`-`5`, maps to `-T<N>`.
- `nmap_min_rate` (optional) - `--min-rate`.
- `nmap_max_retries` (optional) - `--max-retries`.
- `nmap_no_dns` (optional, default `false`) - `-n`.
- `nmap_max_rtt_timeout` (optional) - `--max-rtt-timeout`, nmap time syntax (e.g. `500ms`).
- `nmap_min_hostgroup` (optional) - `--min-hostgroup`.
- `nmap_custom_options` (optional) - extra raw nmap flags, split on whitespace and appended to
  the command line as-is.
- `nmap_return_ip_entities` (optional, default `false`) - additionally report each scanned host
  that has at least one open port as an `ipv4_address`/`ipv6_address` entity.

## Known issues

- No timeouts per scan target yet
- Scanning issues are not yet detected and written into info/warning logs
