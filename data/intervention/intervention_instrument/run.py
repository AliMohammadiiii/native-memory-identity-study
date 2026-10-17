"""Freeze and run a finite source intervention on the existing benign streams."""

import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def binding(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def worker(out, arm):
    manifest = json.loads((out / "MANIFEST.json").read_text())
    source = out / "sources" / arm / "agentmem"
    if binding(source) != manifest["sources"][arm]:
        raise ValueError("source_binding_mismatch")
    if binding(out / "prior_instrument") != manifest["prior_instrument"]:
        raise ValueError("prior_instrument_binding_mismatch")
    protocol = json.loads((out / "FROZEN_PROTOCOL.json").read_text())
    original = json.loads((out / "prior_instrument" / "PROTOCOL.json").read_text())
    blocked = []

    def deny(*args, **kwargs):
        blocked.append("network_attempt")
        raise RuntimeError("network_disabled")

    worker_record = {"arm": arm, "completed_cells": [], "blocked_network_attempts": blocked}
    try:
        with patch.object(socket.socket, "connect", deny), \
             patch.object(socket.socket, "connect_ex", deny), \
             patch.object(socket, "create_connection", deny):
            sys.path.insert(0, str(out / "prior_instrument"))
            sys.path.insert(0, str(source.parent))
            spec = importlib.util.spec_from_file_location("bound_benign_run", out / "prior_instrument" / "run.py")
            native_run = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(native_run)
            from agentmem import MemoryStore
            import inspect
            if Path(inspect.getfile(MemoryStore)).resolve() != source / "core.py":
                raise ValueError("unexpected_native_import")
            for stream in protocol["streams"]:
                native_run.cell(native_run.Agentmem, out / "cells" / arm / stream, stream, original)
                worker_record["completed_cells"].append(stream)
            if blocked:
                raise ValueError("unexpected_network_attempt")
    except Exception as error:
        worker_record["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        save(out / ("WORKER_" + arm + ".json"), worker_record)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--parent-capture", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--worker", choices=["unmodified", "distinct_id_guard", "dedup_branch_disabled"])
    args = ap.parse_args()
    out = args.out.resolve()
    if args.worker:
        worker(out, args.worker)
        return
    if args.source is None or args.parent_capture is None:
        ap.error("--source and --parent-capture are required")
    here = Path(__file__).resolve().parent
    protocol = json.loads((here / "PROTOCOL.json").read_text())
    source = args.source.resolve()
    parent = args.parent_capture.resolve()
    if sha(source / "core.py") != protocol["source_core_sha256"]:
        raise ValueError("source_core_binding_mismatch")
    prior = parent / "instrument"
    required = ["run.py", "adapters.py", "measure.py", "PROTOCOL.json"]
    for name in required:
        if not (prior / name).is_file():
            raise ValueError("missing_parent_instrument:" + name)
    parent_protocol = json.loads((prior / "PROTOCOL.json").read_text())
    if protocol["streams"] != parent_protocol["streams"]:
        raise ValueError("stream_contract_mismatch")
    original = (source / "core.py").read_text()
    needle = '        if result.get("deduplicated"):\n'
    if original.count(needle) != 1:
        raise ValueError("unique_intervention_site_required")
    replacements = {
        "unmodified": needle,
        "distinct_id_guard": '        if result.get("deduplicated") and result["id"] != old_id:\n',
        "dedup_branch_disabled": '        if False and result.get("deduplicated"):\n',
    }
    plan = {"cells": len(protocol["arms"]) * len(protocol["streams"]),
            "arms": protocol["arms"], "native_calls_in_plan": 0,
            "model_or_embedding_api_calls": 0, "publication_readiness": "NOT_ESTABLISHED"}
    if args.plan_only:
        print(json.dumps(plan, sort_keys=True))
        return
    out.mkdir(parents=True, exist_ok=False)
    (out / "sources").mkdir()
    (out / "cells").mkdir()
    (out / "prior_instrument").mkdir()
    (out / "intervention_instrument").mkdir()
    for name in required:
        shutil.copy2(prior / name, out / "prior_instrument" / name)
    for name in ("run.py", "analyze.py", "PROTOCOL.json", "README.md"):
        shutil.copy2(here / name, out / "intervention_instrument" / name)
    shutil.copy2(here / "PROTOCOL.json", out / "FROZEN_PROTOCOL.json")
    sources = {}
    for arm in protocol["arms"]:
        arm_source = out / "sources" / arm / "agentmem"
        shutil.copytree(source, arm_source, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        changed = original.replace(needle, replacements[arm], 1)
        (arm_source / "core.py").write_text(changed)
        (out / "cells" / arm).mkdir()
        sources[arm] = binding(arm_source)
        delta = "".join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                            fromfile="pinned/core.py", tofile=arm + "/core.py"))
        (out / (arm + ".patch")).write_text(delta)
        original_binding = binding(source)
        for name, digest in sources[arm].items():
            if name != "core.py" and original_binding[name] != digest:
                raise ValueError("unplanned_source_change:" + name)
    manifest = {"schema_version": "benign-identity-intervention-capture/1", **plan,
                "protocol_sha256": sha(out / "FROZEN_PROTOCOL.json"),
                "parent_capture_manifest_sha256": sha(parent / "MANIFEST.json"),
                "parent_instrument_binding": binding(prior),
                "prior_instrument": binding(out / "prior_instrument"),
                "intervention_instrument": binding(out / "intervention_instrument"),
                "sources": sources, "python": sys.version, "source_arms_frozen_before_native_execution": True}
    save(out / "MANIFEST.json", manifest)
    for arm in protocol["arms"]:
        command = [sys.executable, "-B", str(out / "intervention_instrument" / "run.py"),
                   "--out", str(out), "--worker", arm]
        result = subprocess.run(command, capture_output=True, text=True)
        (out / (arm + ".stdout.txt")).write_text(result.stdout)
        (out / (arm + ".stderr.txt")).write_text(result.stderr)
        if result.returncode:
            raise RuntimeError("arm_failed_preserve_capture:" + arm)
    print(json.dumps({**plan, "completed_cells": plan["cells"]}, sort_keys=True))


if __name__ == "__main__":
    main()
