# SQL Examples

The storage layer itself uses parameterized SQL, while `examples/queries.sql` contains readable PostgreSQL examples suitable for reviewing the data model or demonstrating SQL skills.

Examples include:

- latest source health with `DISTINCT ON`;
- latest observation per metric/entity;
- severity-filtered risk inbox;
- explicit VIRA weekly-flow queries;
- corporate-bond event timelines;
- strict point-in-time cutoff queries;
- macro context retrieval;
- AI token/cost audit aggregation.

These queries are analytical/control examples, not bank-internal SQL.
