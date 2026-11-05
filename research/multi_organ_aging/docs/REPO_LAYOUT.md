# Repository Layout — Multi-organ Aging

## Canonical implementation

All active development is under:

`research/multi_organ_aging/`

Server symlink/path:

`/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging`

This is the only tree that should receive new analysis stages, configuration changes, tests and thesis-method updates.

## Legacy implementation

`master_degree/multi_organ_aging/`

is an earlier prototype retained temporarily for provenance. It should be treated as **read-only legacy code**. Do not add new stages there.

Before merging the research branch to `main`, the legacy tree can be archived or removed in a dedicated cleanup PR after confirming that no unique method/document is still needed.

## Data policy

Never commit:
- individual-level KoGES data,
- controlled-data extracts,
- credentials,
- direct participant identifiers.

Generated aggregate summaries and code/configuration may be committed when they contain no participant-level sensitive data.
