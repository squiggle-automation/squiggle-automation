# dnsx

Resolves domains to addresses, or addresses back to domains, using [dnsx](https://github.com/projectdiscovery/dnsx).

This container can be used for normal DNS queries (A, AAAA, CNAME, NS, TXT, SRV, MX, AXFR) or reverse DNS (PTR).
TXT responses are stored in the artifact, but not processed to new entities.

## Input data types

- Forward (`dnsx_mode: forward`): `domain`
- Reverse (`dnsx_mode: reverse`): `ipv4_address`, `ipv6_address`

## Output data types

- Forward (`dnsx_mode: forward`): `ipv4_address`, `ipv6_address`, `domain`
- Reverse (`dnsx_mode: reverse`): `domain`

## Config

- `dnsx_mode` (**required**) - `forward` or `reverse`
- `dnsx_custom_options` (optional) - extra raw dnsx flags
- `dns_resolver` (optional, default `8.8.8.8`) - IP address of the resolver to query

## Known issues

- The AXFR "chain" was observed to repeat the same set of records twice for a single-NS zone in
  testing - not something this executor relies on being exactly 1, but the `forward-axfr` test
  fixture pins the exact count it saw, so a future dnsx release changing that duplication would
  need the fixture updated too (not a sign of a real bug).
