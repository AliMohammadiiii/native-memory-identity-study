"""Freeze and execute the fixed, model-free benign versioning streams."""

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import version
import inspect
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import traceback
from unittest.mock import patch

try:
    from .adapters import Agentmem, Mem0
except ImportError:
    from adapters import Agentmem, Mem0


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def source_binding(source, protocol):
    from mem0 import Memory
    path = Path(inspect.getfile(Memory))
    if version("mem0ai") != "2.2.1" or sha(path) != protocol["mem0_main_sha256"]:
        raise ValueError("mem0_source_binding_mismatch")
    if sha(source / "core.py") != protocol["source_core_sha256"]:
        raise ValueError("agentmem_source_binding_mismatch")
    return path


def operations(stream):
    # alias, operation, target alias, value key, namespace
    initial = [("sentinel", "add", None, "sentinel", "sentinel")]
    if stream == "existing_other_root":
        initial += [("other", "add", None, "green", "fixture")]
    elif stream == "existing_other_chain":
        initial += [("other_root", "add", None, "red", "fixture"),
                    ("other", "update", "other_root", "green", None)]
    elif stream == "different_namespace_value":
        initial += [("other", "add", None, "green", "other")]
    initial += [("subject", "add", None, "blue", "fixture")]
    sequences = {
        "normal_change": [("current", "update", "subject", "green", None)],
        "same_value": [("current", "update", "subject", "blue", None)],
        "repeat_current_value": [("current", "update", "subject", "green", None), ("current", "update", "current", "green", None)],
        "return_to_archived_value": [("current", "update", "subject", "green", None), ("current", "update", "current", "blue", None)],
        "existing_other_root": [("current", "update", "subject", "green", None)],
        "existing_other_chain": [("current", "update", "subject", "green", None)],
        "different_namespace_value": [("current", "update", "subject", "green", None)],
        "repeat_remember": [("current", "add", None, "blue", "fixture")],
    }
    return initial + sequences[stream]


def cell(Adapter, root, stream, protocol):
    root.mkdir()
    store = Adapter(root)
    known, steps = {}, []
    try:
        for number, (alias, operation, target, key, namespace) in enumerate(operations(stream), 1):
            value = protocol["input_values"][key]
            before = store.snapshot(known) if known else None
            try:
                identifier, result = store.add(value, namespace) if operation == "add" else store.update(known[target], value)
                known[alias] = identifier
                outcome = dict(outcome="return", value=result, returned_id=identifier)
            except Exception as error:
                outcome = dict(outcome="exception", exception_type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
            after = store.snapshot(known)
            if after["sentinel_contents"] != [protocol["input_values"]["sentinel"]]:
                raise ValueError("sentinel_not_preserved")
            if list(after["sqlite_integrity"][0].values()) != ["ok"]:
                raise ValueError("sqlite_integrity_failed")
            step = dict(number=number, alias=alias, operation=operation, target_alias=target,
                        namespace=namespace, requested=value, native=outcome, before=before, after=after)
            steps.append(step)
            save(root / ("STEP_" + str(number).zfill(2) + ".json"), step)
            if outcome["outcome"] != "return":
                raise ValueError("unexpected_native_exception_preserved")
        final = steps[-1]["after"]
        store.close()
        store = Adapter(root)
        cold = store.snapshot(known)
        for key in ("current_contents", "physical_contents", "other_namespace_contents", "sentinel_contents"):
            if cold[key] != final[key]:
                raise ValueError("cold_reopen_drift:" + key)
        result = dict(stream=stream, aliases=known, steps=steps, final=final, cold=cold,
                      final_requested=steps[-1]["requested"], final_outcome=steps[-1]["native"]["outcome"])
        save(root / "CELL.json", result)
        return result
    finally:
        store.close()


def worker(out):
    protocol = json.loads((out / "FROZEN_PROTOCOL.json").read_text())
    binding = json.loads((out / "FROZEN_BINDINGS.json").read_text())
    source = out / "native_source" / "agentmem"
    if files(source) != binding["source_files"]:
        raise ValueError("source_copy_mismatch")
    blocked = []

    def deny(*args, **kwargs):
        blocked.append("network_attempt")
        raise RuntimeError("network_disabled")

    with contextlib.ExitStack() as stack:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection", "httpx.Client.send", "httpx.AsyncClient.send", "requests.sessions.Session.request"):
            stack.enter_context(patch(target, new=deny))
        sys.path.insert(0, str(source.parent))
        native = importlib.import_module("agentmem")
        if Path(native.__file__).resolve() != source / "__init__.py" or native.__version__ != "0.3.0":
            raise ValueError("unexpected_agentmem_import")
        source_binding(source, protocol)
        save(out / "ENVIRONMENT.json", dict(python=sys.version, platform=platform.platform(),
            sqlite=sqlite3.sqlite_version, sqlite_vec=version("sqlite-vec"), mem0=version("mem0ai"),
            qdrant_client=version("qdrant-client"), agentmem=native.__version__, embedding="Mem0 static 8D double; agentmem no embedding function",
            executor="same_owner_same_workstation", injected_faults=0))
        index = []
        for rep in range(1, protocol["fresh_repetitions"] + 1):
            for library in protocol["libraries"]:
                for stream in protocol["streams"]:
                    relative = Path("cells") / ("rep_" + str(rep)) / (library + "__" + stream)
                    location = out / relative
                    location.parent.mkdir(parents=True, exist_ok=True)
                    cell(Agentmem if library == "agentmem" else Mem0, location, stream, protocol)
                    index.append(dict(library=library, stream=stream, repetition=rep, path=str(relative)))
                    print("Benign native cells: " + str(len(index)) + "/" + str(protocol["cells"]), flush=True)
        source_binding(source, protocol)
    if blocked or files(source) != binding["source_files"]:
        raise ValueError("network_attempt_or_source_mutation")
    save(out / "RESULTS.json", dict(cells=index, blocked_network_attempts=blocked, native_source_unchanged=True,
                                    model_or_embedding_api_calls=0, injected_faults=0, publication_readiness="NOT_ESTABLISHED"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    os.environ["MEM0_TELEMETRY"] = "false"
    out = args.out.resolve()
    if args.worker:
        worker(out)
        return
    here = Path(__file__).resolve().parent
    protocol = json.loads((here / "PROTOCOL.json").read_text())
    source = args.source.resolve()
    mem0_source = source_binding(source, protocol)
    if len(protocol["libraries"]) * len(protocol["streams"]) * protocol["fresh_repetitions"] != protocol["cells"]:
        raise ValueError("finite_matrix_mismatch")
    if args.plan_only:
        print(json.dumps(dict(cells=protocol["cells"], source_bindings_valid=True, native_calls=0, model_calls=0, creates_files=False)))
        return
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(here, out / "instrument", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(here / "PROTOCOL.json", out / "FROZEN_PROTOCOL.json")
    shutil.copytree(source, out / "native_source" / "agentmem", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    shutil.copy2(mem0_source, out / "MEM0_NATIVE_MAIN.py")
    save(out / "FROZEN_BINDINGS.json", dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        protocol_sha256=sha(out / "FROZEN_PROTOCOL.json"), source_files=files(out / "native_source" / "agentmem"),
        code_files=files(out / "instrument"), mem0_main_sha256=sha(mem0_source),
        interpretation="Local prospective development freeze after primary source inspection. No public preregistration."))
    p = subprocess.run([sys.executable, "-B", str(out / "instrument" / "run.py"), "--out", str(out), "--worker"], capture_output=True, text=True)
    (out / "EXECUTION.log").write_text(p.stdout + p.stderr)
    save(out / "STATUS.json", dict(worker_exit_code=p.returncode, expected_cells=protocol["cells"], interpretation="PENDING_OFFLINE_ANALYSIS"))
    save(out / "MANIFEST.json", dict(files=files(out)))
    print(json.dumps(dict(worker_exit_code=p.returncode, model_calls=0, capture=str(out))))
    if p.returncode:
        print(p.stderr)
        raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()
