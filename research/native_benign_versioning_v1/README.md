# Benign native value/version interactions

This source-informed development study uses only normal sequential public calls.
It does not inject a fault or implement a source repair. Its fixed 32-cell matrix
is in `PROTOCOL.json`. Existing null results and historical outputs are inputs
to research judgment and are not replaced.

Use existing Python 3.12 with cached native dependencies. Validate without
calling a native storage operation:

```sh
uv run --offline --no-project --python EXISTING_NATIVE_PYTHON \
  --with-requirements research/native_memory_fault_audit_v1/requirements-native.txt \
  --with sqlite-vec==0.1.6 python -B \
  -m research.native_benign_versioning_v1.run \
  --source PRIVATE_PINNED_SOURCE/agentmem --out FRESH_CAPTURE --plan-only
```

Remove `--plan-only` for the fixed native execution after successful validation.
Use a fresh output directory. No model, embedding API, key or external service
is used. Mem0 receives a static local embedding double. agentmem has no embedding
function. Native execution blocks socket, httpx and requests connection entry
points. Telemetry is disabled.

Analyze only after native capture finishes:

```sh
python -B FRESH_CAPTURE/instrument/analyze.py \
  --capture FRESH_CAPTURE --out FRESH_ANALYSIS
python -B -m unittest research.native_benign_versioning_v1.test_measure
```

The analyzer verifies hashes and the unique fixed denominator. Unsupported
predecessor-graph properties remain NOT_APPLICABLE for Mem0 event history.
Raw successful calls, current-memory observations, physical records and cold
reopen are retained. No semantic accuracy, system ranking, production prevalence,
new diagnostic principle or publication readiness follows from these fixtures.
