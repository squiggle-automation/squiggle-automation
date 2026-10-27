# tlsx

Connects to services over TLS and extracts domain names from the presented certificate, using
[tlsx](https://github.com/projectdiscovery/tlsx).

## Input data types

- `service`

## Output data types

- `domain`

## Config

None.

## Known issues

- No config for tlsx yet (e.g. SNI override, min/max TLS version, timeouts).
- Self-signed and otherwise invalid certificates are used the same way as valid ones - no
  trust/validity check is performed before extracting domains, which is intentional for
  reconnaissance but worth knowing if this output is used for anything trust-sensitive.
