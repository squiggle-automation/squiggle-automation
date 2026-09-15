"""Reads/writes a ConfigValue via the API's global (ConfigOption) or per-executor config
endpoints."""

import sys

from ..utils import api_request, load_credentials


def cmd_config_set(args):
    creds = load_credentials()
    url, token = creds["url"], creds["token"]

    if args.executor:
        # partial update - only this option's key is touched, everything else the executor
        # already has set is left alone
        status, result = api_request(
            url, token, "PATCH", f"executors/{args.executor}/config/", {args.option: args.value}
        )
    else:
        status, result = api_request(url, token, "PUT", f"configoptions/{args.option}/value/", {"value": args.value})

    if status not in (200, 201):
        print(f"failed ({status}): {result}", file=sys.stderr)
        sys.exit(1)

    where = f"executor '{args.executor}'" if args.executor else "globally"
    if args.value is None:
        print(f"cleared '{args.option}' {where}")
    else:
        print(f"set '{args.option}' {where}")


def cmd_config_get(args):
    creds = load_credentials()
    url, token = creds["url"], creds["token"]

    if args.executor:
        # this endpoint returns every config option relevant to the executor's container at
        # once - pick out the one asked for
        status, result = api_request(url, token, "GET", f"executors/{args.executor}/config/")
        if status == 200:
            if args.option not in result:
                available = ", ".join(sorted(result)) or "(none)"
                print(
                    f"'{args.option}' is not a config option of the '{args.executor}' executor's container "
                    f"- available: {available}",
                    file=sys.stderr,
                )
                sys.exit(1)
            value = result[args.option]
        else:
            print(f"failed ({status}): {result}", file=sys.stderr)
            sys.exit(1)
    else:
        status, result = api_request(url, token, "GET", f"configoptions/{args.option}/value/")
        if status != 200:
            print(f"failed ({status}): {result}", file=sys.stderr)
            sys.exit(1)
        value = result["value"]

    print(value if value is not None else "(not set)")
