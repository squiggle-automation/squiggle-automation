# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Python conventions

- Do not use `__all__` in `__init__.py` files. Re-export symbols with plain
  `from .module import Name` statements only (see `core/views/__init__.py`,
  `core/forms/__init__.py` for the existing pattern).

## Frontend conventions

- No inline `<script>` blocks or inline event handler attributes (`onclick=`
  etc.) in templates — write JS in its own file under
  `<app>/static/<app>/js/`, loaded via `<script src="{% static ... %}">`
  (e.g. `core/static/core/js/clipboard.js`, loaded from a `{% block extra_js %}`
  in the template that needs it, see `squiggle_automation/templates/squiggle_automation/base.html`).
  This keeps the door open for a strict Content-Security-Policy later (no
  `unsafe-inline` needed for scripts). Text that needs translation should be
  passed into the JS via `data-*` attributes on the relevant element, set
  with `{% trans %}` in the template — the `.js` file itself must stay free
  of Django template tags, since it isn't rendered through the template engine.

## Workflow

- Never run `git add` (or otherwise stage changes) — changes must be left
  unstaged, so that they can be reviewed and staged manually. Note that
  `pre-commit run --all-files` only sees files known to git, so newly created
  files are not checked by it until they are staged manually; run the
  formatters directly on those files instead.
- Run `pre-commit run --all-files` (from the repo root, using the project's
  `venv`) before finishing a task, and fix any issues it reports (formatting,
  import order, etc. — see `.pre-commit-config.yaml`).
- Tests must be run via `manage.py test` (not `pytest` or other runners).
- Add or update tests for any code changes.
- Tests must not contain hard-coded passwords. Use
  `squiggle_automation.testutils.random_password()` to generate one instead
  (see `core/tests/test_autoapprovalrule.py`, `management/tests/test_password.py`
  for the pattern with a single value vs. matching/mismatching pairs).
