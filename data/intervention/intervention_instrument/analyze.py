"""Offline, fail-closed tabulation of the finite identity intervention."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive(cell):
    required = ("final", "cold", "steps", "aliases", "final_outcome", "final_requested")
    if any(key not in cell for key in required):
        raise ValueError("missing_cell_field")
    final, cold = cell["final"], cell["cold"]
    for key in ("current_contents", "physical_contents", "sentinel_contents", "other_namespace_contents"):
        if final[key] != cold[key]:
            raise ValueError("cold_observation_drift:" + key)
    if final["sentinel_contents"] != ["memoryprobe unrelated keep"]:
        raise ValueError("sentinel_not_preserved")
    all_returned = all(step["native"]["outcome"] == "return" for step in cell["steps"])
    if not all_returned or cell["final_outcome"] != "return":
        raise ValueError("unexpected_native_exception")
    value = cell["final_requested"]
    missing = [value not in observation["current_contents"] for observation in (final, cold)]
    physical_missing = value not in final["physical_contents"]
    rows = final["physical_rows"]
    response = cell["steps"][-1]["native"]["value"]
    subject = cell["aliases"]["subject"]
    returned = cell["steps"][-1]["native"]["returned_id"]
    return {
        "requested_value_public": not missing[0], "requested_value_physical": not physical_missing,
        "requested_value_cold": not missing[1],
        "confirmed_current_loss": all(missing) and physical_missing,
        "stored_self_edges": sum(row["id"] == row["supersedes"] for row in rows),
        "response_self_predecessor": "supersedes" in response and response.get("id") == response["supersedes"],
        "subject_active_with_different_returned_id": returned != subject and any(
            row["id"] == subject and row["archived"] == 0 for row in rows),
        "all_native_calls_returned": all_returned,
        "sentinel_preserved": True, "cold_observations_match": True,
    }


def analyze(capture, out):
    manifest = json.loads((capture / "MANIFEST.json").read_text())
    protocol = json.loads((capture / "FROZEN_PROTOCOL.json").read_text())
    if sha(capture / "FROZEN_PROTOCOL.json") != manifest["protocol_sha256"]:
        raise ValueError("protocol_binding_mismatch")
    for category in ("prior_instrument", "intervention_instrument"):
        for name, digest in manifest[category].items():
            if sha(capture / category / name) != digest:
                raise ValueError("instrument_binding_mismatch")
    for arm, source in manifest["sources"].items():
        for name, digest in source.items():
            if sha(capture / "sources" / arm / "agentmem" / name) != digest:
                raise ValueError("source_binding_mismatch")
    records = []
    bindings = {}
    for arm in protocol["arms"]:
        worker_path = capture / ("WORKER_" + arm + ".json")
        worker = json.loads(worker_path.read_text())
        if worker.get("failure") or worker["blocked_network_attempts"] or worker["completed_cells"] != protocol["streams"]:
            raise ValueError("worker_not_complete")
        bindings[worker_path.name] = sha(worker_path)
        for stream in protocol["streams"]:
            path = capture / "cells" / arm / stream / "CELL.json"
            cell = json.loads(path.read_text())
            if cell["stream"] != stream:
                raise ValueError("cell_stream_mismatch")
            records.append({"arm": arm, "stream": stream, **derive(cell)})
            bindings[str(path.relative_to(capture))] = sha(path)
    if len(records) != manifest["cells"]:
        raise ValueError("cell_denominator_mismatch")
    summary = {arm: {key: sum(r[key] for r in records if r["arm"] == arm)
                     for key in ("confirmed_current_loss", "stored_self_edges", "response_self_predecessor",
                                 "subject_active_with_different_returned_id")}
               for arm in protocol["arms"]}
    out.mkdir(parents=True, exist_ok=False)
    with (out / "CELLS.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    result = {"schema_version": "benign-identity-intervention-analysis/1", "cells": len(records),
              "cells_per_arm": len(protocol["streams"]), "summary": summary,
              "new_model_calls": 0, "analysis_native_calls": 0,
              "stage": protocol["stage"], "publication_readiness": "NOT_ESTABLISHED",
              "source_and_instrument_bound": True,
              "interpretation": "Source intervention cells, not independent implementations, bug counts or production observations."}
    (out / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (out / "INPUT_BINDINGS.json").write_text(json.dumps({"manifest_sha256": sha(capture / "MANIFEST.json"),
        "protocol_sha256": manifest["protocol_sha256"], "cells_and_workers": bindings}, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(analyze(args.capture.resolve(), args.out.resolve()), sort_keys=True))
