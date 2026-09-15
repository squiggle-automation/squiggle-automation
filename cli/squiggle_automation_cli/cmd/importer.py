"""Upserts one object per JSON file in a folder, by name, via the API."""

import json
import sys
from pathlib import Path

from ..utils import api_request, load_credentials

DATATYPES = ["entitytypes", "configoptions", "containers", "executors", "workerprofiles"]


def cmd_import(args):
    print(f"Importing {args.datatype}")

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"'{folder}' is not a directory", file=sys.stderr)
        sys.exit(1)

    creds = load_credentials()
    url, token = creds["url"], creds["token"]

    files = sorted(folder.glob("*.json"))
    if not files:
        print(f"no .json files found in {folder}")
        return

    failures = 0
    for file in files:
        try:
            payload = json.loads(file.read_text())
        except json.JSONDecodeError as e:
            print(f"FAIL {file.name}: invalid JSON ({e})")
            failures += 1
            continue

        name = payload.get("name")
        if not name:
            print(f'FAIL {file.name}: missing "name" field')
            failures += 1
            continue

        # upsert by name: update if it already exists, otherwise create - re-running an import
        # is safe
        status, existing = api_request(url, token, "GET", f"{args.datatype}/{name}/")
        if status == 200:
            verb = "updated"
            status, result = api_request(url, token, "PUT", f"{args.datatype}/{name}/", payload)
        elif status == 404:
            verb = "created"
            status, result = api_request(url, token, "POST", f"{args.datatype}/", payload)
        else:
            print(f"FAIL {file.name}: lookup failed ({status}): {existing}")
            failures += 1
            continue

        if status in (200, 201):
            print(f"OK   {file.name} -> {verb} '{name}'")
        else:
            print(f"FAIL {file.name}: {verb} failed ({status}): {result}")
            failures += 1

    print(f"{len(files) - failures}/{len(files)} imported")
    print()
    if failures:
        sys.exit(1)
