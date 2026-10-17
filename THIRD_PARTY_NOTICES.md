# Third-party source notices

## agentmem

- Repository: https://github.com/oxgeneral/agentmem
- Pinned commit: `14a5b85b143285029fb72958424d903d8fe4b08c`
- Package metadata: agentmem-lite 0.3.0
- Copyright 2025 agentmem contributors
- License: MIT, reproduced in `licenses/agentmem-MIT.txt`

The package source is preserved in `data/benign/native_source/agentmem/` and
`data/intervention/sources/*/agentmem/`. The unmodified copies retain their
original bytes. Each modified variant changes one condition in `core.py`;
the exact changes are recorded in `data/intervention/*.patch` and the capture
manifest. Modifications are experimental source controls made for this study,
not upstream releases or an upstream-endorsed production repair.

The upstream source includes tests, documentation, metadata, and benchmark
examples. Their presence is for exact source binding, not a claim that the
study executed upstream tests or reproduced upstream benchmark results. The
upstream `/home/openclaw` test fixture path is not from this workstation.

## Mem0

- Repository: https://github.com/mem0ai/mem0
- Installed distribution: mem0ai 2.2.1
- Copyright notice in upstream license: Taranjeet Singh (2023)
- License: Apache License 2.0, reproduced verbatim from the installed
  distribution in `licenses/mem0-Apache-2.0.txt`
- Unmodified captured file: `data/benign/MEM0_NATIVE_MAIN.py`
- SHA-256: `f329ca4a17af1fbefb32ac10d4cc7ae7ddbdb7435a87eb74c30915cff98b8b7c`

Other dependency source is not vendored. Native API calls use the installed
distribution and are bound to the exact source hash by the instrument.
