# Squiggle Automation

Squiggle Automation is a platform that chains tools together automatically.
You define entity types (the data your tools work with) and executors
(containerized tools that consume some entity types and produce others). The platform runs the right executor whenever a matching entity appears, propagating the results until nothing new is found.

It ships with a small example configuration for security-reconnaissance tooling, but the entities and executors are just configuration — the platform itself is domain-agnostic.

See the [documentation](docs/source/index.rst) for more details.

## Developed by HvS-Consulting

![Developed by HvS-Consulting](https://github.com/squiggle-automation/squiggle-automation/blob/main/src/squiggle_automation/static/squiggle_automation/img/hvs_color.png?raw=true)

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) — see the [LICENSE](LICENSE) file for the full text.

The [`executors/`](executors/) directory is an exception: it is licensed under the MIT License (see [executors/LICENSE](executors/LICENSE)).
Changes to the platform itself must be published under the AGPL when it is offered as a network service, but your own executors are separate programs and do not have to be published. See [executors/README.md](executors/README.md).
