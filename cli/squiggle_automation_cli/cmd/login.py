"""
Prompts for and verifies credentials, then persists them via api.save_credentials. On a re-run,
the stored values are shown in the prompts and kept if the input is left empty (like
`aws configure`).
"""

import getpass
import sys

from ..utils import CREDENTIALS_FILE, api_request, load_credentials, save_credentials


def mask_token(token):
    """First and last 3 characters only - short tokens are masked completely."""
    if len(token) <= 6:
        return "..."
    return f"{token[:3]}*****"


def prompt(label, current, display=None, secret=False):
    """Prompts for a value, showing the current one - empty input keeps it."""
    if current is not None:
        label = f"{label} [{display if display is not None else current}]"
    value = (getpass.getpass if secret else input)(f"{label}: ").strip()
    return value or current


def cmd_login(args):
    old = load_credentials(required=False)
    old_token = old.get("token")
    old_project = old.get("project")

    try:
        url = prompt("URL", old.get("url"))
        token = prompt("Token", old_token, mask_token(old_token) if old_token else None, secret=True)
        project = prompt(
            "Default project id (optional, - to clear)",
            str(old_project) if old_project is not None else None,
        )
    except KeyboardInterrupt:
        print()
        sys.exit(0)

    if not url or not token:
        print("URL and token are required", file=sys.stderr)
        sys.exit(1)

    # verify the credentials actually work before saving them
    status, data = api_request(url, token, "GET", "projects/")
    if status != 200:
        print(f"login failed ({status}): {data}", file=sys.stderr)
        sys.exit(1)

    # verify that the project is valid
    if project and project != "-":
        if not project.isdigit():
            print(f"invalid project id '{project}'", file=sys.stderr)
            sys.exit(1)
        project = int(project)
        status, data = api_request(url, token, "GET", f"projects/{project}/")
        if status != 200:
            print(f"project {project} not found", file=sys.stderr)
            sys.exit(1)
    else:
        project = None

    save_credentials(url, token, project)
    print(f"saved credentials to {CREDENTIALS_FILE}")
