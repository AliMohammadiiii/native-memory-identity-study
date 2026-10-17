# Data dictionary

The released observations are deterministic authored operation streams, not
sampled users or annotated semantic facts. There are no missing planned cells.

## Original capture

`data/benign/cells/rep_{1,2}/{library}__{stream}/CELL.json` contains one complete
cell. `STEP_*.json` repeats the corresponding sequential step for inspection.
`RESULTS.json` enumerates the fixed 32 cells. `FROZEN_PROTOCOL.json` defines
the exact streams, values, scope, and interpretation rules.

## Separate source intervention

`data/intervention/cells/{arm}/{stream}/CELL.json` contains one of the 24
separate intervention cells. `sources/` contains the exact three source arms.
`WORKER_*.json` records completed streams and blocked network attempts.

## Common cell fields

| Field | Meaning |
| --- | --- |
| `stream` | Authored operation-stream identifier |
| `aliases` | Logical names mapped to native returned record IDs |
| `steps` | Ordered operations with before/after observations and native outcomes |
| `steps[].requested` | Literal requested synthetic value |
| `steps[].native` | Returned value and ID, or preserved exception information |
| `final` | Final observations before closing the store |
| `cold` | Observations after closing and reopening the same store |
| `final_requested` | Literal value requested by the last operation |
| `final_outcome` | Native outcome, required to be `return` in these completed cells |
| `current_contents` | Values returned by the public current-memory interface |
| `physical_contents` | Independently read values in active native storage records |
| `physical_rows` | Native rows or vector-store records used for the physical observation |
| `histories` | Native history for known IDs, with library-specific semantics |
| `sentinel_contents` | Unrelated sentinel values checked after each operation |
| `sqlite_integrity` | SQLite integrity-check result |

## Endpoints and denominators

Confirmed current loss requires a successful final call and absence of its
requested value from public, physical, and cold-current observations.
Missing or disagreeing observations do not count as confirmed loss.

`results/benign/CELL_TABLE.csv` has one row per original cell. Its
`self_edges` and `cycle_nodes` are `NOT_APPLICABLE` for Mem0 event history.
Agentmem graph diagnostics use actual persisted `id`/`supersedes` rows.

`results/intervention/CELLS.csv` has one row per source-intervention cell.
`confirmed_current_loss` is the three-observation endpoint.
`stored_self_edges` counts physical rows whose predecessor equals their ID.
`response_self_predecessor` describes only the returned response.
`subject_active_with_different_returned_id` records the initial subject still
being active when the final returned ID differs. These diagnostics are not
interchangeable violation counts.

Do not pool the 32 original cells and 24 intervention cells into independent
systems, bug counts, or a population failure-rate denominator.

## Storage and bindings

SQLite `.db`/`.sqlite` files and local Qdrant collection files retain the original
stores. Read them with copies or read-only handles. Historical JSON manifests
bind sources and instruments; `RELEASE_MANIFEST.json` additionally binds every
exported file. No original capture bytes are redacted or normalized.
