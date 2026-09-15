====
Why?
====

What the platform does
=======================

The platform runs tools on data, and chains tools together automatically based on what each one needs and produces - so a single starting entity can set off a whole sequence of tool runs without anyone driving it step by step.

.. TODO: image

You define the kinds of entities you're working with and set up tools that each take some kinds of entities in and produce others out.
From there, it runs on its own.

The entities and tools themselves are just configuration.
The bundled example configures a few security-reconnaissance tools, but that's only one example, not something built into the platform.

How it works
=============

* First, you define "entity types", the data types of entities. Those a the "common language" between all your tools.
* Every tool ("executor") declares which entity types it needs as input and which it can produce as output. Executors are implemented with Docker (or in general, OCI-compatible) containers. Containers can be used for multiple executors.
* Whenever a new entity appears, either by manual input or as output by an executor, the platform identifies the executors that again need to be triggered.
* Executions are grouped together, so the tool is usually executed on multiple entities. It is also possible to wait a bit for the input queue to fill up to prevent that the same tool is executed a lot of times. This configuration can be different for every executor.
* The platform continues until no new entities are found.
* The output of an execution are not only entities, that are processed by the platform, but can also be files - we call it artifacts - for further use.

Example
=======

* A domain resolves to an IP address
* The IP gets port-scanned, a web service with TLS is discovered
* The domains from the TLS certificate are extracted, leading to new domains, which starts the chain over.
