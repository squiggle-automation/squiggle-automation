---
name: create-executor
description: Use when adding a new executor container under executors/ (a tool wrapper the platform runs against entities, e.g. nmap, dns-resolver, subfinder). Covers the entrypoint.py/Dockerfile pattern, config/output naming conventions, and how to add real container-level tests - not host-side unit tests.
---

# Creating a new executor

An executor is a Docker image under `executors/<name>/` that wraps one tool. The full I/O
contract (`/data/{input,output,tmp,artifacts}`, the `executor_helper` Python SDK, error-handling
rules) is documented in `docs/source/usage/executors.rst` - read that first if you haven't. This
skill is the practical workflow and conventions layered on top of it for *this* repo: how to
scaffold, name things consistently with existing executors, and - the part that's easy to skip -
how to actually verify the thing works by running the real container, not by guessing.

## 1. Scaffold the container

```
executors/<name>/
├── container/
│   ├── Dockerfile
│   └── entrypoint.py
├── README.md
└── tests/                      # see step 3 - omit only if truly untestable (step 3 explains)
```

Nothing needs registering anywhere - `executors/justfile`'s `build-all`/`test-all` discover
executors by globbing `*/container/` and `*/tests/*/`, so a correctly-shaped directory is
automatically picked up.

**`Dockerfile`** - three patterns depending on how the tool is distributed, all `FROM
executor-base`:

- **apt package** (e.g. `dns-resolver`, `nmap`):
  ```dockerfile
  FROM executor-base
  RUN apt update && apt install -y <package> && apt clean
  COPY entrypoint.py /root/entrypoint.py
  CMD ["/root/entrypoint.py"]
  ```
- **GitHub release binary**, ProjectDiscovery-style tools (`subfinder`, `tlsx`) - assets are
  named `<tool>_<version>_linux_<arch>.zip`:
  ```dockerfile
  FROM executor-base
  ARG TARGETARCH
  COPY entrypoint.py /root/entrypoint.py
  RUN mkdir /tmp/<tool> && cd /tmp/<tool> && \
      curl --location -o <tool>.zip $(curl -s https://api.github.com/repos/<org>/<tool>/releases/latest | jq -r '.assets[].browser_download_url' | grep linux_$TARGETARCH) && \
      unzip <tool>.zip && cp <tool> /root/<tool> && chmod +x /root/<tool> && rm -rf /tmp/<tool>
  CMD ["/root/entrypoint.py"]
  ```
- **git-cloned tool with no release binary** (`testssl`) - pin an explicit tag, never a branch
  or HEAD:
  ```dockerfile
  FROM executor-base
  RUN apt update && apt install -y git ca-certificates && apt clean && \
      git clone --depth 1 --branch <tag> https://github.com/<org>/<tool>.git /opt/<tool>
  COPY entrypoint.py /root/entrypoint.py
  CMD ["/root/entrypoint.py"]
  ```
  Expect to discover extra runtime dependencies (`bsdextrautils` for `hexdump`, `procps` for
  `ps`, `dnsutils` for `dig`, ...) the tedious way: run it, read the "Fatal error: you need to
  install X" message, add the package, rebuild, repeat. This is normal, not a sign something's
  wrong.

**`entrypoint.py`**: `#!/usr/bin/env python3` shebang, and **`chmod +x` it** - `CMD` executes it
directly, so a missing executable bit fails every container start with `permission denied`
("`OCI runtime create failed: ... permission denied`"). This has bitten every executor added
this way so far; check it before your first test run, not after.

## 2. Write entrypoint.py

```python
#!/usr/bin/env python3

from executor_helper import ExecutorHelper

executor = ExecutorHelper()
executor.read_input()

# 1. read all config first, then call exit_on_error() ONCE, so the user sees every
#    config problem in one run instead of one per re-run
config_foo = executor.get_config("mytool_foo", "default-value")
config_bar = executor.get_config_bool("mytool_bar", "false")   # string default, not a bool -
                                                                 # get_config_bool calls .lower()
                                                                 # on it if unset
executor.exit_on_error()

# 2. do the work
for entity in executor.get_input_entities("<input-entitytype>"):
    ...
    executor.add_output_entity("<output-entitytype>", {...})

# 3. write output exactly once - every path must end here or in exit_on_error()
executor.write_output()
```

**Config option names**: lowercase `snake_case`. Prefix with the tool name only when there are
several options for one executor (`nmap_scan_mode`, `nmap_min_rate`, ...) so they read together;
a single-option executor doesn't need a prefix (`dns_resolver`, not `dns_resolver_dns_resolver`).

**Output entity fields**: reuse an existing entity type's shape if the data fits (`service`:
`address`/`port`/`protocol`/`service`/`info`; `domain`: `domain`; `ipv4_address`/`ipv6_address`:
`address`). If a field is only sometimes known (nmap's `service`/`info`, populated only with
`-sV`), still include the key with an empty-string default rather than omitting it - keeps the
entity shape uniform across cases. Introducing a genuinely new entity type or field? Add it to
`notes/json_schemas.txt` too (a design reference, not enforced by code).

**Error handling** - match the failure to its actual severity, don't default to `add_error`:
- A single input item fails to process → `add_warning`, continue with the rest.
- One target/host in a multi-target loop fails (e.g. one of several nmap address families, one
  of several testssl.sh services) → log it (`add_warning`/`add_info` depending on how expected
  it is) and `continue` the loop, don't abort the whole run over one bad target.
- The tool's exit code isn't a reliable success signal for every tool (testssl.sh's exit code
  encodes finding severity, not failure) - check what a real run actually returns before wiring
  it to `add_error`; log-only (`add_info`) is sometimes the right call.
- Nothing to report at all is not an error - an empty `data: {}` output is a normal, successful
  result (see `nmap`'s "no open ports" and `tlsx`'s "host doesn't speak TLS" cases).

## 3. Test it against the real container - not a host-side unit test

The tool inside the container (nmap, subfinder, testssl.sh, ...) doesn't exist on the host, so
the only meaningful test is: build the real image, run it for real against a controlled target,
diff the real output. See the "Testing" section in `docs/source/usage/executors.rst` for the
full harness reference (`cli/cli.py`'s `executor build`/`executor test`, wrapped by `just
build`/`just test`/`just test-all`).

Workflow:

1. If the tool needs something to talk to, check whether an existing target in
   `executors/_testenvironment/targets/` already fits (`dns-zone` for anything doing DNS lookups,
   `scan-target` for a host with known open/closed ports, `tls-target` for anything reading a
   TLS certificate). Adding a new target: a `Dockerfile` + `docker-compose.yml` service entry
   with a **fixed IP** on the `executor-test` network (IPv4 `100.100.100.0/24`, IPv6
   `fd00:100:100:100::/64` - both already enabled) so fixtures can reference it directly, no
   runtime lookup needed. If the target cannot be easily implemented in a container, ask the user what to do.
2. `just build <name>`, then run the container manually against the target once (mount your own
   temp `input/output/tmp/artifacts` dirs, see any existing test's `input.json` for the shape,
   or just copy `just test`'s invocation) and **look at the real output** before writing
   `expected_output.json` - guessing the tool's exact output shape wastes a cycle almost every
   time (nmap's `tcpwrapped` vs. table-guessed service name, tlsx's exact JSON field names,
   testssl.sh's exit code, all only became known by actually running them).
3. Write `executors/<name>/tests/<case>/{input.json,expected_output.json}` - fixture per
   scenario, e.g. one "finds something" case and one "finds nothing" / negative case. Needs raw
   TLS/SYN capabilities? Add one empty marker file `executors/<name>/tests/cap_net_raw` (per
   executor, not per case).
4. `just test <name>` (all cases) or `just test <name> <case>` (one case). `KEEP_TMP=1 just test
   <name>` keeps the temp work dir (path printed right before the result) for inspecting
   `/data/artifacts` after a failure.
5. Before finishing: `just test-all` (full regression) and, from the repo root,
   `venv/bin/pre-commit run --all-files`.

**When a tool genuinely can't be tested deterministically** (`subfinder` needs live
certificate-transparency logs and the internet) - don't force a flaky test. Skip the `tests/`
directory entirely and say so explicitly in the README's Known Issues, the way `subfinder`'s
does. This is a deliberate, visible gap, not an oversight.

## 4. Write README.md

Every executor has one, same four sections (`executors/base/README.md` is the template,
`executors/dns-reverse-resolver/README.md` a filled-in minimal example, `executors/nmap/README.md`
a filled-in example with many config options):

```markdown
# <name>

<One or two sentences: what it does.>

## Input data types

- `<entitytype>` (`<fields it reads>`)

## Output data types

- `<entitytype>` (`<fields it writes>`) - or "None." if it only produces artifacts (see `testssl`)

## Config

- `<option>` (optional/required, default `...`) - what it controls.
  <or "None." if there's no config>

## Known issues

- Real limitations, honestly stated - missing validation, no test coverage and why, tool
  quirks that look like bugs but aren't. Not a TODO list for unrelated features.
```

## Checklist before calling it done

- [ ] `entrypoint.py` has the executable bit (`chmod +x`)
- [ ] Config option names are lowercase `snake_case`, prefixed only if there are several
- [ ] Every code path ends in `write_output()` or `exit_on_error()`
- [ ] At least one real container-level test case (or an explicit, documented reason there isn't
      one)
- [ ] `README.md` with all four sections
- [ ] `just test-all` passes
- [ ] `pre-commit run --all-files` passes (repo root, project venv)
