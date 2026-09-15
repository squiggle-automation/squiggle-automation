# subfinder

Enumerates subdomains for a domain using [subfinder](https://github.com/projectdiscovery/subfinder).

## Input data types

- `domain`

## Output data types

- `domain`

## Config

None.

## Known issues

- No config for subfinder yet (like API keys)
- No automated tests: subfinder depends on live certificate-transparency logs and the internet, which isn't reproducible in the container test environment
- dns_resolver config not used
