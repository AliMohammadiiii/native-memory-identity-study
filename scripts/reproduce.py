"""Validate or reproduce the released native identity study without model calls."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    subprocess.run([sys.executable, "-B", *map(str, args)], cwd=ROOT, check=True)


def verify():
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    for name, digest in manifest["files"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError("release_file_mismatch:" + name)
    return len(manifest["files"])


def same_file(first, second):
    if sha(first) != sha(second):
        raise ValueError("regenerated_file_differs:" + second.name)


def analyze(benign, intervention, output, exact):
    run(benign / "instrument/analyze.py", "--capture", benign, "--out", output / "benign")
    run(intervention / "intervention_instrument/analyze.py", "--capture", intervention, "--out", output / "intervention")
    for key in ("benign", "intervention"):
        names = [p.name for p in (ROOT / "results" / key).iterdir()] if exact else ["CELL_TABLE.csv" if key == "benign" else "CELLS.csv"]
        for name in names:
            same_file(ROOT / "results" / key / name, output / key / name)


def figures(benign, intervention, output):
    run(ROOT / "research/native_benign_identity_intervention_v1/plot_figures.py",
        "--benign-capture", benign, "--benign-analysis", output / "benign",
        "--intervention-capture", intervention, "--intervention-analysis", output / "intervention",
        "--out", output / "figures")
    exports = []
    for prefix in ("01_stream_outcomes", "02_identity_intervention", "03_native_witness"):
        for suffix in ("pdf", "svg", "png"):
            name = prefix + "." + suffix
            same_file(ROOT / "figures" / name, output / "figures" / name)
            exports.append(name)
    return exports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "analyze", "figures", "native"), default="analyze")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/reproduction_01")
    args = parser.parse_args()
    bound = verify()
    if args.mode == "verify":
        print(json.dumps({"bound_files_verified": bound, "model_calls": 0}))
        return
    output = args.out.resolve()
    if output == ROOT or output.is_relative_to(ROOT / "data") or output.is_relative_to(ROOT / "results"):
        raise ValueError("output_must_not_replace_evidence")
    output.mkdir(parents=True, exist_ok=False)
    benign, intervention = ROOT / "data/benign", ROOT / "data/intervention"
    if args.mode == "native":
        benign, intervention = output / "benign_capture", output / "intervention_capture"
        source = ROOT / "data/benign/native_source/agentmem"
        run(ROOT / "research/native_benign_versioning_v1/run.py", "--source", source,
            "--out", benign, "--plan-only")
        run(ROOT / "research/native_benign_versioning_v1/run.py", "--source", source, "--out", benign)
        run(ROOT / "research/native_benign_identity_intervention_v1/run.py", "--source", source,
            "--parent-capture", benign, "--out", intervention, "--plan-only")
        run(ROOT / "research/native_benign_identity_intervention_v1/run.py", "--source", source,
            "--parent-capture", benign, "--out", intervention)
    analyze(benign, intervention, output, exact=args.mode != "native")
    exports = figures(benign, intervention, output) if args.mode == "figures" else []
    if args.mode != "native":
        run("-m", "unittest", "research.native_benign_versioning_v1.test_measure",
            "research.native_benign_identity_intervention_v1.test_analysis")
    result = {"mode": args.mode, "bound_files_verified": bound, "selected_outcomes_match": True,
              "original_cells": 32, "separate_intervention_cells": 24,
              "byte_identical_figure_exports": exports,
              "native_cells_executed": 56 if args.mode == "native" else 0,
              "model_or_embedding_api_calls": 0, "independent_execution": "NOT_INFERRED"}
    (output / "VALIDATION.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
