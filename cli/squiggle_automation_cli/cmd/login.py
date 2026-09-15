"""Prompts for and verifies credentials, then persists them via api.save_credentials."""

import getpass
import sys

from ..utils import CREDENTIALS_FILE, api_request, save_credentials


def cmd_login(args):
    try:
        url = input("URL: ").strip()
        token = getpass.getpass("Token: ").strip()
    except KeyboardInterrupt:
        print()
        sys.exit(0)

    # verify the credentials actually work before saving them
    status, data = api_request(url, token, "GET", "projects/")
    if status != 200:
        print(f"login failed ({status}): {data}", file=sys.stderr)
        sys.exit(1)

    save_credentials(url, token)
    print(f"saved credentials to {CREDENTIALS_FILE}")
