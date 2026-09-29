# Decision: JSON storage

Status: accepted
Applies-To: store.py

## Context

The application stores one small dictionary on a local machine.

## Decision

The save/load functions persist the dictionary as a JSON file.

## Alternatives

- SQLite: transactions are useful, but the current single-writer usage does not require them.

## Consequences

- Positive: the data is readable without a database viewer.
- Negative: whole-file writes cannot support concurrent transactions.
