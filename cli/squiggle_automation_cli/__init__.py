import argparse

from .cmd.config import cmd_config_get, cmd_config_set
from .cmd.executor import cmd_executor_build, cmd_executor_push, cmd_executor_test
from .cmd.importer import DATATYPES, cmd_import
from .cmd.login import cmd_login


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login", help="store the API URL and token for later commands")

    import_parser = subparsers.add_parser("import", help="import objects from JSON files via the API")
    import_parser.add_argument("datatype", choices=DATATYPES)
    import_parser.add_argument("folder", help="directory containing one .json file per object")

    config_parser = subparsers.add_parser("config", help="manage config values")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_set_parser = config_subparsers.add_parser("set", help="set (or, without a value, clear) a config value")
    config_set_parser.add_argument("option", help="config option name")
    config_set_parser.add_argument("value", nargs="?", default=None, help="value to set; omit to clear")
    config_set_parser.add_argument("--executor", help="set for this executor only, instead of the global default value")
    config_get_parser = config_subparsers.add_parser("get", help="print the current value of a config option")
    config_get_parser.add_argument("option", help="config option name")
    config_get_parser.add_argument(
        "--executor", help="the value as resolved for this executor, instead of the global default value"
    )

    executor_parser = subparsers.add_parser("executor", help="build/push/test executor container images")
    executor_subparsers = executor_parser.add_subparsers(dest="executor_command", required=True)

    executor_build_parser = executor_subparsers.add_parser(
        "build", help="build one executor image, or every executor in the current directory"
    )
    executor_build_parser.add_argument("name", nargs="?", help="directory name to build (omit with --all)")
    executor_build_parser.add_argument(
        "--all", action="store_true", help="build every executor directory in the current directory"
    )

    executor_push_parser = executor_subparsers.add_parser(
        "push", help="push one built executor image, or every executor in the current directory"
    )
    executor_push_parser.add_argument("name", nargs="?", help="directory name to push (omit with --all)")
    executor_push_parser.add_argument(
        "--all", action="store_true", help="push every executor directory in the current directory"
    )
    executor_push_parser.add_argument("--dry-run", action="store_true", help="only print which images would be pushed")

    executor_test_parser = executor_subparsers.add_parser(
        "test", help="test one executor image, or every executor in the current directory"
    )
    executor_test_parser.add_argument("name", nargs="?", help="directory name to test (omit with --all)")
    executor_test_parser.add_argument("case", nargs="?", default="", help="run only this test case")
    executor_test_parser.add_argument(
        "--all", action="store_true", help="test every executor directory in the current directory"
    )

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "config" and args.config_command == "set":
        cmd_config_set(args)
    elif args.command == "config" and args.config_command == "get":
        cmd_config_get(args)
    elif args.command == "executor" and args.executor_command == "build":
        cmd_executor_build(args)
    elif args.command == "executor" and args.executor_command == "push":
        cmd_executor_push(args)
    elif args.command == "executor" and args.executor_command == "test":
        cmd_executor_test(args)


if __name__ == "__main__":
    main()
