"""Validate the fixed native benign-call matrix and generate a bounded report."""

import argparse
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path

try:
    from .measure import graph_diagnostics, effect
except ImportError:
    from measure import graph_diagnostics, effect


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def analyze(capture, output):
    if output.exists():
        raise ValueError("fresh_analysis_required")
    protocol = json.loads((capture / "FROZEN_PROTOCOL.json").read_text())
    binding = json.loads((capture / "FROZEN_BINDINGS.json").read_text())
    manifest = json.loads((capture / "MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        p = (capture / name).resolve()
        if not p.is_relative_to(capture) or sha(p) != expected:
            raise ValueError("capture_binding_mismatch:" + name)
    for name in ("analyze.py", "measure.py"):
        if sha(Path(__file__).parent / name) != binding["code_files"][name]:
            raise ValueError("analyzer_not_frozen")
    index = json.loads((capture / "RESULTS.json").read_text())
    keys = [(r["library"], r["stream"], r["repetition"]) for r in index["cells"]]
    expected = {(lib, stream, rep) for lib in protocol["libraries"] for stream in protocol["streams"] for rep in range(1, protocol["fresh_repetitions"] + 1)}
    if len(keys) != protocol["cells"] or len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError("matrix_missing_or_duplicate_cells")
    if index["blocked_network_attempts"] or not index["native_source_unchanged"]:
        raise ValueError("invalid_execution_boundary")
    rows, details, signatures = [], [], {}
    counts = {lib: Counter() for lib in protocol["libraries"]}
    for item in index["cells"]:
        cell = json.loads((capture / item["path"] / "CELL.json").read_text())
        final, cold = cell["final"], cell["cold"]
        verdict = effect(cell["final_outcome"], cell["final_requested"], final["current_contents"], final["physical_contents"], cold["current_contents"])
        if verdict in ("UNKNOWN", "OBSERVATION_DISAGREEMENT", "API_EXCEPTION"):
            raise ValueError("measurement_invalid:" + item["path"] + ":" + verdict)
        for step in cell["steps"]:
            if step["native"]["outcome"] != "return":
                raise ValueError("unexpected_native_exception")
            if step["after"]["sentinel_contents"] != [protocol["input_values"]["sentinel"]]:
                raise ValueError("sentinel_changed")
        for key in ("current_contents", "physical_contents", "sentinel_contents", "other_namespace_contents"):
            if final[key] != cold[key]:
                raise ValueError("cold_drift")
        graph = graph_diagnostics(final["physical_rows"]) if item["library"] == "agentmem" else None
        if graph is not None and graph != graph_diagnostics(cold["physical_rows"]):
            raise ValueError("cold_graph_drift")
        other_before, other_after = None, None
        if "other" in cell["aliases"]:
            other = str(cell["aliases"]["other"])
            before = cell["steps"][-1]["before"]["histories"][other]
            after = final["histories"][other]
            if item["library"] == "agentmem":
                other_before = [r["content"] for r in before]
                other_after = [r["content"] for r in after]
            else:
                other_before = [{k: r.get(k) for k in ("event", "old_memory", "new_memory")} for r in before]
                other_after = [{k: r.get(k) for k in ("event", "old_memory", "new_memory")} for r in after]
        changed = other_before != other_after if other_before is not None else None
        loss = verdict == "SUCCESS_WITH_REQUESTED_VALUE_UNAVAILABLE"
        if item["stream"] in ("normal_change", "return_to_archived_value", "different_namespace_value", "repeat_remember") and loss:
            raise ValueError("normal_or_negative_control_failed:" + item["path"])
        row = dict(library=item["library"], stream=item["stream"], repetition=item["repetition"],
            successful_final_call=True, requested_value_visible=not loss,
            public_current_records=len(final["current_contents"]),
            self_edges=len(graph["self_edges"]) if graph is not None else "NOT_APPLICABLE",
            cycle_nodes=len(graph["cycle_nodes"]) if graph is not None else "NOT_APPLICABLE",
            other_history_changed=changed if changed is not None else "NOT_APPLICABLE",
            cold_reopen_matches=True, verdict=verdict)
        rows.append(row)
        details.append(dict(**item, measurement=row, graph=graph, other_history_before=other_before,
            other_history_after=other_after, requested=cell["final_requested"], current=final["current_contents"],
            primary_claim_scope="Public current-value availability after successful benign calls; no diagnostic-superiority claim."))
        counts[item["library"]]["cells"] += 1
        counts[item["library"]]["requested_value_unavailable"] += int(loss)
        counts[item["library"]]["self_edge_cells"] += int(graph is not None and bool(graph["self_edges"]))
        counts[item["library"]]["other_history_changed_cells"] += int(bool(changed))
        signatures[(item["library"], item["stream"], item["repetition"])] = dict(
            verdict=verdict, current=final["current_contents"], other=final["other_namespace_contents"],
            self_edges=row["self_edges"], cycle_nodes=row["cycle_nodes"], changed_history=changed)
    agree = all(signatures[(lib, stream, 1)] == signatures[(lib, stream, 2)] for lib in protocol["libraries"] for stream in protocol["streams"])
    if not agree:
        raise ValueError("repetitions_differ_preserve_for_diagnosis")
    output.mkdir(parents=True)
    affected = sorted({r["stream"] for r in rows if not r["requested_value_visible"]})
    decision = dict(schema_version="native-benign-versioning-analysis/1", cells=len(rows),
        streams_per_interface=len(protocol["streams"]), fresh_repetitions=protocol["fresh_repetitions"],
        counts={lib: dict(values) for lib, values in counts.items()}, affected_streams=affected,
        repetition_signatures_match=agree, model_or_embedding_api_calls=0, injected_faults=0,
        source_unchanged=True, evidence_status="SUPPORTED_IN_SCOPE" if affected else "NOT_SUPPORTED",
        claim="A successful benign native update can hide its requested current value in the pinned source configuration.",
        novelty_status="UNRESOLVED_SEPARATE_PRIMARY_AUDIT_REQUIRED", scientific_contribution="PROMISING_EXPLORATORY" if affected else "NOT_SUPPORTED",
        publication_readiness="NOT_ESTABLISHED", native_interfaces_compared_not_ranked=True,
        uncertainty="Source-informed selected streams, one configuration per interface, same executor/workstation. No field prevalence, statistical independence or human reproduction claim.")
    save(output / "DECISION.json", decision)
    save(output / "DETAILS.json", details)
    save(output / "CLAIM_LEDGER.json", [
        dict(claim=decision["claim"], status=decision["evidence_status"], evidence="CELL_TABLE.csv; bound CELL.json and STEP files; native source"),
        dict(claim="A requested-value loss is visible through native public reads without fault injection", status=decision["evidence_status"], evidence="DETAILS.json requested/current and native snapshots"),
        dict(claim="The primitive deduplication or version-chain principle is new", status="NOT_ESTABLISHED", evidence="Established mechanisms; separate prior-art audit required"),
        dict(claim="A change in another chain's history violates an upstream immutable-history guarantee", status="NOT_ESTABLISHED", evidence="Diagnostic only; no multi-parent or immutable-history guarantee was assumed"),
        dict(claim="One library is generally more reliable than another", status="NOT_ESTABLISHED", evidence="Selected streams and different interfaces do not identify general reliability"),
        dict(claim="Paper ready for submission or independent reproduction", status="NOT_ESTABLISHED", evidence="Author and scientific contribution reviews remain separate")])
    with (output / "CELL_TABLE.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    save(output / "INPUT_BINDING.json", dict(capture_manifest_sha256=sha(capture / "MANIFEST.json"),
        protocol_sha256=sha(capture / "FROZEN_PROTOCOL.json"), analyzer_sha256=sha(Path(__file__)),
        measurement_sha256=sha(Path(__file__).parent / "measure.py")))
    report(output, decision, rows)
    save(output / "MANIFEST.json", dict(files={p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}))
    return decision


def report(output, d, rows):
    text = f"""# Benign native updates: content and version identity

The fixed matrix completed {d['cells']} cells without injected faults or model calls. Two fresh repetitions agree on every recorded normalized diagnostic. These are selected development streams, not independent samples of production use.

The requested value became unavailable after a successful final call in these streams: {', '.join(d['affected_streams']) or 'none'}.

The result is a bounded native-behavior witness. It does not revive the previous unsupported claim of a superior diagnostic representation. Comprehensive state checking can detect this behavior. The new question concerns benign calls and practical current-memory availability, rather than response formatting or authored storage faults.

## Scope and measurement

agentmem uses native recall with current_only enabled and a keyword shared by all fixture records. Its sqlite-vec dependency is active, with no embedding function. Physical active rows and the predecessor graph are read separately. Mem0 uses the native get_all current-memory interface, local Qdrant and native SQLite event history. An eight-dimensional static embedding double exercises storage; it does not evaluate semantic retrieval. The two histories are not converted into a common graph metric.

Every cell retains native call responses, snapshots before and after operations, actual stores, unrelated sentinel observations and a cold reopen. The primary endpoint requires agreement among the native public current read, physical current records and cold public read. Missing observations do not count as findings.

## Interpretation

A same-value update need not create a new version. A benign no-op, a fresh version or an explicit rejection would be different possible interface choices. Removing the requested value after a successful call is the measured behavior of interest. A predecessor self edge is reported separately from database integrity: valid SQLite pages do not establish a valid application-level version graph.

The existing-other-chain stream also records before/after native history, but changes there are diagnostic observations. This study does not impose an undocumented immutable multi-parent history contract. Repeated add/remember can have different native deduplication semantics and is not assigned a shared idempotency requirement.

Mechanism originality, prevalence in other systems, user harm and publication significance remain unresolved. A matching normal control in Mem0 does not establish general superiority. Source inspection selected these cases; no held-out or confirmatory claim is made. The earlier negative comparison and historical manuscripts remain unchanged.

Scientific status: {d['scientific_contribution']}. Exact-case novelty: unresolved. Submission positioning: HOLD pending separate contribution and source review.
"""
    (output / "REPORT.md").write_text(text)
    headers = ["Interface", "Stream", "Rep.", "Requested value visible", "Self edges", "Other history changed"]
    body = ""
    for r in rows:
        values = [r["library"], r["stream"].replace("_", " "), str(r["repetition"]),
                  "Yes" if r["requested_value_visible"] else "No", str(r["self_edges"]), str(r["other_history_changed"])]
        body += "<tr>" + "".join("<td>" + html.escape(v) + "</td>" for v in values) + "</tr>"
    prose = ""
    for block in text.split("\n\n"):
        tag = "h1" if block.startswith("# ") else "h2" if block.startswith("## ") else "p"
        value = block[2:] if tag == "h1" else block[3:] if tag == "h2" else block
        prose += "<" + tag + ">" + html.escape(value) + "</" + tag + ">"
    style = "body{font:17px/1.6 system-ui;color:#172b35;background:#f4f3ef;margin:0}main{max-width:1050px;margin:auto;padding:32px}h1{line-height:1.2}h2{font-size:24px;margin-top:30px}.note{padding:18px;background:#fff0ce;border-left:5px solid #906b12}table{border-collapse:collapse;width:100%;font-size:13px;background:white}th,td{padding:9px;text-align:left;border-bottom:1px solid #cad4d9}th{background:#e1e9eb}tr:nth-child(even){background:#f0f5f6}.table{overflow:auto}"
    banner = f"{d['cells']} selected native cells · no fault injection · no model calls<br>Behavior evidence: {d['evidence_status']}. Publication readiness: not established."
    (output / "REPORT.html").write_text("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Benign native versioning</title><style>" + style + "</style><main><div class='note'>" + banner + "</div>" + prose + "<h2>Complete fixed matrix</h2><div class='table'><table><thead><tr>" + "".join("<th>" + x + "</th>" for x in headers) + "</tr></thead><tbody>" + body + "</tbody></table></div></main></html>")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    d = analyze(args.capture.resolve(), args.out.resolve())
    print(json.dumps({k: d[k] for k in ("cells", "counts", "affected_streams", "repetition_signatures_match", "injected_faults", "model_or_embedding_api_calls", "evidence_status")}))


if __name__ == "__main__":
    main()
