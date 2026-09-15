# tlsx

Connects to services over TLS and extracts domain names from the presented certificate, using
[tlsx](https://github.com/projectdiscovery/tlsx).

## Input data types

- `service` (`address`, `port`, `protocol`) - only `protocol: "tcp"` entries are used; TLS is a
  TCP concept, `udp` entries are silently skipped.

## Output data types

- `domain` (`domain`) - one entity per certificate common name and Subject Alternative Name
  (deduplicated). A host that doesn't speak TLS at all is skipped, not an error.

## Config

None.

## Known issues

- No config for tlsx yet (e.g. SNI override, min/max TLS version, timeouts).
- Self-signed and otherwise invalid certificates are used the same way as valid ones - no
  trust/validity check is performed before extracting domains, which is intentional for
  reconnaissance but worth knowing if this output is used for anything trust-sensitive.
