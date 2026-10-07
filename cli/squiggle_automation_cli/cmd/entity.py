"""Gets and adds entities of one entity type in one project via the API."""

import json
import sys
from pathlib import Path

from ..utils import api_request, get_project, load_credentials

STATES = ["enabled", "waiting_approval", "disabled", "all"]


def parse_fields(fields):
    """
    Builds the entity data from key=value (string) and key:=json (typed, e.g. port:=443) items,
    the same convention httpie uses.
    """
    data = {}
    for field in fields:
        # key:=json if the first "=" belongs to a ":="
        if ":=" in field and field.index(":=") == field.index("=") - 1:
            key, value = field.split(":=", 1)
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"'{field}': invalid JSON ({e})")
        elif "=" in field:
            key, value = field.split("=", 1)
            data[key] = value
        else:
            raise ValueError(f"'{field}': expected key=value or key:=json")

        if not key:
            raise ValueError(f"'{field}': empty key")

    return data


def load_entities(path):
    """
    Yields (label, entity) for every entity in a .json file, every .json file of a folder, or
    stdin (path "-"). Each holds one entity ({"data": {...}}) or a list of them, which is what
    "entity get" prints. A file that is not valid JSON is yielded as the JSONDecodeError.
    """
    if path == "-":
        sources = [("stdin", sys.stdin.read())]
    else:
        path = Path(path)
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        sources = [(file.name, file.read_text()) for file in files]

    for name, text in sources:
        try:
            content = json.loads(text)
        except json.JSONDecodeError as e:
            yield name, e
            continue

        if isinstance(content, list):
            for i, entity in enumerate(content):
                yield f"{name}[{i}]", entity
        else:
            yield name, content


def cmd_entity_get(args):
    creds = load_credentials()
    url, token = creds["url"], creds["token"]
    project = get_project(args, creds)

    path = f"projects/{project}/entities/{args.entitytype}/"
    if args.state != "all":
        path += f"?state={args.state}"

    status, result = api_request(url, token, "GET", path)
    if status != 200:
        print(f"failed ({status}): {result}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


def cmd_entity_add(args):
    creds = load_credentials()
    url, token = creds["url"], creds["token"]
    project = get_project(args, creds)

    if args.file and args.fields:
        print("give either key=value fields or --file, not both", file=sys.stderr)
        sys.exit(1)

    if args.file:
        if args.file != "-" and not Path(args.file).exists():
            print(f"'{args.file}' does not exist", file=sys.stderr)
            sys.exit(1)
        entities = load_entities(args.file)
    elif args.fields:
        try:
            entities = [("entity", {"data": parse_fields(args.fields)})]
        except ValueError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
    else:
        print("give key=value fields or --file", file=sys.stderr)
        sys.exit(1)

    total = 0
    failures = 0
    for label, entity in entities:
        total += 1
        if isinstance(entity, json.JSONDecodeError):
            print(f"FAIL {label}: invalid JSON ({entity})")
            failures += 1
            continue

        # the API upserts by the identifier keys in data - re-running an add is safe
        status, result = api_request(url, token, "PUT", f"projects/{project}/entities/{args.entitytype}/", entity)
        if status in (200, 201):
            print(f"OK   {label} -> {'created' if status == 201 else 'updated'}")
        else:
            print(f"FAIL {label}: ({status}): {result}")
            failures += 1

    if not total:
        print(f"no entities found in {args.file}")
        return

    if total > 1:
        print(f"{total - failures}/{total} added")
    if failures:
        sys.exit(1)
