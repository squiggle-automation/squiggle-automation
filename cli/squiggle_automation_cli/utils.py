"""Shared HTTP layer for talking to the squiggle-automation REST API, plus the stored credentials
(API URL + token) that `login` writes and every API-backed command reads."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CREDENTIALS_FILE = Path.home() / ".squiggle-automation-cli.json"


def load_credentials():
    if not CREDENTIALS_FILE.exists():
        print(f"not logged in - run '{sys.argv[0]} login' first", file=sys.stderr)
        sys.exit(1)
    return json.loads(CREDENTIALS_FILE.read_text())


def save_credentials(url, token):
    CREDENTIALS_FILE.write_text(json.dumps({"url": url, "token": token}, indent=2) + "\n")
    CREDENTIALS_FILE.chmod(0o600)  # holds a secret token - keep it readable by the owner only


def api_request(url, token, method, path, data=None):
    """
    Makes one request against /api/v1/<path>. Returns (status_code, parsed_body) - parsed_body
    is the decoded JSON, or the raw text if the response wasn't JSON (e.g. an HTML error page).
    Connection-level failures (wrong URL, server unreachable) are reported the same way, with
    status_code None, so callers only need one error path.
    """
    full_url = url.rstrip("/") + "/api/v1/" + path.lstrip("/")
    body = json.dumps(data).encode() if data is not None else None

    req = urllib.request.Request(full_url, data=body, method=method)
    req.add_header("Authorization", f"Token {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")
    except urllib.error.URLError as e:
        return None, str(e.reason)
