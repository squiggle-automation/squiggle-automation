"""
Builds, pushes and container-tests executor images by shelling out to docker/podman. See
docs/source/usage/cli.rst for the command-level contract (cwd-relative paths, no "base"
special-casing, the executor-test network assumption).
"""

import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# used when ./config.json is missing, or omits a section/key
DEFAULT_CONFIG = {
    "container": {
        "prefix": "executor",
        "registry": None,
    },
    "testing": {"attach_network": None},
}


def load_config():
    """Reads ./config.json (if present), merged over DEFAULT_CONFIG."""
    config = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}

    path = Path("config.json")
    if path.is_file():
        for section, values in json.loads(path.read_text()).items():
            config.setdefault(section, {}).update(values)

    return config


def image_tag(name, config):
    registry = config["container"]["registry"]
    prefix = config["container"]["prefix"]

    if prefix:
        name = f"{prefix}-{name}"
    if registry:
        name = f"{registry}/{name}"

    return name


def container_runtime():
    override = os.environ.get("CONTAINER_RUNTIME")
    if override:
        return override
    return "podman" if shutil.which("podman") else "docker"


def executor_names():
    """Every subdirectory of the current directory that has a container/ subdirectory."""
    return sorted(d.parent.name for d in Path(".").glob("*/container") if d.is_dir())


def build_executor(name, config):
    """Builds ./<name>/container, tagged <registry>/<prefix>-<name>. Returns True on success."""
    container_dir = Path(name) / "container"
    if not container_dir.is_dir():
        print(f"'{container_dir}' does not exist", file=sys.stderr)
        return False

    tag = image_tag(name, config)
    print(f"## building {tag} from {container_dir}")
    result = subprocess.run([container_runtime(), "build", "-t", tag, "."], cwd=container_dir)
    return result.returncode == 0


def push_executor(name, config, dry_run):
    """
    Pushes the image that `build` produced. Returns True on success.
    """
    container_dir = Path(name) / "container"
    if not container_dir.is_dir():
        print(f"'{container_dir}' does not exist", file=sys.stderr)
        return False

    tag = image_tag(name, config)

    if dry_run:
        print(f"# would push {tag}")
        return True

    # flush before the runtime's own (inherited) progress output can interleave
    print(f"## pushing {tag}", flush=True)
    result = subprocess.run([container_runtime(), "push", tag])
    return result.returncode == 0


def canonicalize_test_output(data):
    """
    Canonicalize an output/expected_output document for comparison: sort log message lists,
    and sort each entity-type's list of entities by their (sorted) key/value pairs. This makes
    entity key order and entity list order irrelevant to the comparison.
    """
    return {
        "errors": sorted(data.get("errors", [])),
        "warnings": sorted(data.get("warnings", [])),
        "infos": sorted(data.get("infos", [])),
        "data": {
            entitytype: sorted(entities, key=lambda e: sorted(e.items()))
            for entitytype, entities in data.get("data", {}).items()
        },
    }


def test_executor_case(name, case_dir, tests_dir, runtime, config):
    """Runs one test case's container, diffs its output against expected_output.json."""
    case_name = case_dir.name
    # flush before the container's own (inherited, unbuffered) stdout/stderr can interleave
    print(f"## {name} / {case_name}", flush=True)

    keep = bool(os.environ.get("KEEP_TMP"))
    work_dir = Path(tempfile.mkdtemp())

    try:
        input_dir, output_dir, tmp_dir, artifacts_dir = (
            work_dir / "input",
            work_dir / "output",
            work_dir / "tmp",
            work_dir / "artifacts",
        )
        for d in (input_dir, output_dir, tmp_dir, artifacts_dir):
            d.mkdir()

        shutil.copyfile(case_dir / "input.json", input_dir / "data.json")

        # a single marker for the whole executor, not per case - all cases of an executor run
        # the same image with the same capability needs
        cap_args = ["--cap-add", "NET_RAW"] if (tests_dir / "cap_net_raw").exists() else []

        # attach_network can be unset/empty ("testing" wants no network attached at all)
        attach_network = config["testing"].get("attach_network")
        network_args = ["--network", attach_network] if attach_network else []

        result = subprocess.run(
            [
                runtime,
                "run",
                "--rm",
                *network_args,
                "-v",
                f"{input_dir}:/data/input",
                "-v",
                f"{output_dir}:/data/output",
                "-v",
                f"{tmp_dir}:/data/tmp",
                "-v",
                f"{artifacts_dir}:/data/artifacts",
                *cap_args,
                image_tag(name, config),
            ]
        )
        if result.returncode != 0:
            success = False
            message = f"FAIL: {name}/{case_name} - container run failed"
        elif not (output_dir / "data.json").exists():
            success = False
            message = f"FAIL: {name}/{case_name} - no output/data.json written"
        else:
            expected = canonicalize_test_output(json.loads((case_dir / "expected_output.json").read_text()))
            actual = canonicalize_test_output(json.loads((output_dir / "data.json").read_text()))

            if expected == actual:
                success = True
                message = f"PASS: {name}/{case_name}"
            else:
                sys.stdout.writelines(
                    difflib.unified_diff(
                        json.dumps(expected, indent=2, sort_keys=True).splitlines(keepends=True),
                        json.dumps(actual, indent=2, sort_keys=True).splitlines(keepends=True),
                        fromfile="expected_output.json",
                        tofile="output/data.json",
                    )
                )
                success = False
                message = f"FAIL: {name}/{case_name} - output does not match expected_output.json"

        # right before the result, so it's easy to spot when scrolling past a long test run
        if keep:
            print()
            print(f"keeping work dir: {work_dir}")
            print()

        print(message)
        return success
    finally:
        if not keep:
            shutil.rmtree(work_dir, ignore_errors=True)


def test_executor(name, tests_dir, case_filter, config):
    """Runs one or all test case for one executor. Returns True iff all of them passed."""
    runtime = container_runtime()

    if case_filter:
        case_dirs = [tests_dir / case_filter]
    else:
        case_dirs = sorted(d for d in tests_dir.iterdir() if d.is_dir())

    results = [test_executor_case(name, case_dir, tests_dir, runtime, config) for case_dir in case_dirs]
    total = len(results)
    passed = sum(results)

    print()
    print(f"{passed}/{total} passed")
    return passed == total


def cmd_executor_build(args):
    if args.all and args.name:
        print("cannot use --all together with a name", file=sys.stderr)
        sys.exit(2)
    if not args.all and not args.name:
        print("usage: cli.py executor build --all | <name>", file=sys.stderr)
        sys.exit(2)

    config = load_config()

    if args.name:
        if not build_executor(args.name, config):
            sys.exit(1)
        return

    names = executor_names()
    if not names:
        print("no executors found in the current directory")
        return

    failed = [name for name in names if not build_executor(name, config)]

    print()
    print(f"{len(names) - len(failed)}/{len(names)} built")
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


def cmd_executor_push(args):
    if args.all and args.name:
        print("cannot use --all together with a name", file=sys.stderr)
        sys.exit(2)
    if not args.all and not args.name:
        print("usage: cli.py executor push [--dry-run] --all | <name>", file=sys.stderr)
        sys.exit(2)

    config = load_config()

    if args.name:
        if not push_executor(args.name, config, args.dry_run):
            sys.exit(1)
        return

    names = executor_names()
    if not names:
        print("no executors found in the current directory")
        return

    failed = [name for name in names if not push_executor(name, config, args.dry_run)]

    print()
    print(f"{len(names) - len(failed)}/{len(names)} {'would be pushed' if args.dry_run else 'pushed'}")
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


def cmd_executor_test(args):
    if args.all and (args.name or args.case):
        print("cannot use --all together with a name/case", file=sys.stderr)
        sys.exit(2)
    if not args.all and not args.name:
        print("usage: cli.py executor test --all | <name> [<case>]", file=sys.stderr)
        sys.exit(2)

    config = load_config()

    if args.name:
        tests_dir = Path(args.name) / "tests"
        if not tests_dir.is_dir():
            print(f"no tests found for '{args.name}' ({tests_dir} does not exist)", file=sys.stderr)
            sys.exit(1)
        if not test_executor(args.name, tests_dir, args.case, config):
            sys.exit(1)
        return

    tests_dirs = sorted(d for d in Path(".").glob("*/tests") if d.is_dir())
    if not tests_dirs:
        print("no executor tests found in the current directory")
        return

    failed = [d.parent.name for d in tests_dirs if not test_executor(d.parent.name, d, None, config)]

    print()
    if not failed:
        print("all executors passed")
    else:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
