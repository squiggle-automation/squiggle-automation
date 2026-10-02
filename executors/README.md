# Executors

Containerized tool wrappers that the platform runs against entities.

## License

Everything in this directory (including the shared `base` image and its `executor_helper` library) is licensed under the MIT License — see [LICENSE](LICENSE) — and **not** under the AGPL-3.0 that covers the rest of this repository.

Executors run as separate containers and talk to the platform only through its documented interface (input and output files).
Your own executors, built on `base` or written from scratch, are therefore your own work and may be licensed, kept private or sold as you see fit.
They do not need to be published.

The AGPL only applies to the platform itself: if you modify and run it as a network service, you must offer the source of your modified version to its
users.

Note that third-party tools wrapped by an executor (nmap, subfinder, ...) keep their own licenses.
