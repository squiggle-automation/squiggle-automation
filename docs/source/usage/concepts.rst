========
Concepts
========

The building blocks
====================

**Entity type** - the data type of an entity, the common interface between different tools.

**Entity** - one piece of data the platform tracks, of some type that defines what data it carries.

**Executor** - a tool made usable by the platform: it declares which entity types it needs as input and which it produces as output. Executors are based on **containers** and have **config options** with global default values and values per executor. It is therefore possible to use the same container for different executors with different configuration.

**Execution** - one run of an executor (including logs, artifacts, ...).

**Approval** - some entity types can require a person to confirm a newly produced entity before it is used any further. In the example of an security assessment, this can ensure that the scope is respected. **Auto approval rules** can automatically approve or decline new entities that match a pattern.

**Worker profiles** - some executors might require more ressources, some might be very lightweight. Worker profiles allow categorize executors and control how many are scheduled in parallel. By default, the executor names ``low``, ``medium`` and ``high`` are used, but this can be changed (please note that this requires changes in the Docker Compose configuration).

**Project** - Entities, execution and auto approval rules belong to a project. The configuration like entity types, containers and executors is shared across all
projects and set up once (see :doc:`../getting-started/index`).

.. TODO: project vs global scope
