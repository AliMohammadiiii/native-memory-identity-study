"""Export only the finite synthetic native-identity study to a fresh directory."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mem0-license", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    copies = {}

    def copy(source, destination):
        target = out / destination
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git"))
            for item in sorted(source.rglob("*")):
                if item.is_file() and (target / item.relative_to(source)).is_file():
                    copies[str((target / item.relative_to(source)).relative_to(out))] = sha(item)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copies[destination] = sha(source)

    for key, module in (("benign", "native_benign_versioning_v1"),
                        ("intervention", "native_benign_identity_intervention_v1")):
        base = root / ".private" / module
        copy(base / "capture_01", "data/" + key)
        copy(base / "analysis_01", "results/" + key)
        src = root / "research" / module
        allowed = ("run.py", "adapters.py", "measure.py", "analyze.py", "test_measure.py",
                   "test_analysis.py", "plot_figures.py", "PROTOCOL.json", "README.md", "__init__.py")
        for name in allowed:
            if (src / name).is_file():
                copy(src / name, "research/" + module + "/" + name)
    copy(root / ".private/native_benign_identity_intervention_v1/figures_02", "figures")
    copy(root / "LICENSE", "LICENSE")
    copy(root / ".private/native_history_extension_20261016/source_01/agentmem/LICENSE", "licenses/agentmem-MIT.txt")
    copy(args.mem0_license, "licenses/mem0-Apache-2.0.txt")
    copy(Path(__file__), "scripts/build_release.py")
    copy(Path(__file__).with_name("reproduce.py"), "scripts/reproduce.py")
    for name in ("README.md", "LICENSE-DATA.md", "THIRD_PARTY_NOTICES.md", "DATA_DICTIONARY.md", "CITATION.cff"):
        copy(Path(__file__).with_name(name), name)
    requirements = (root / "research/native_memory_fault_audit_v1/requirements-native.txt").read_text()
    (out / "requirements-native.txt").write_text(requirements + "sqlite-vec==0.1.6\n")
    (out / "requirements-figures.txt").write_text("matplotlib==3.11.2\nnumpy==2.5.3\npypdf==6.19.0\n")
    (out / ".gitignore").write_text("__pycache__/\n*.pyc\n.DS_Store\noutputs/\n.venv/\n")
    (out / "research/__init__.py").write_text("")
    save(out / "PROVENANCE.json", {
        "schema_version": "native-memory-identity-public-release/1",
        "version": "1.0.0", "date": "2026-10-17",
        "repository": "https://github.com/AliMohammadiiii/native-memory-identity-study",
        "scope": "32 original synthetic native cells and 24 separate controlled-source cells",
        "captured_files_transformed": False,
        "byte_preserved_export_files": copies,
        "agentmem": {"repository": "https://github.com/oxgeneral/agentmem",
                     "commit": "14a5b85b143285029fb72958424d903d8fe4b08c",
                     "version": "0.3.0", "license": "MIT"},
        "mem0": {"distribution": "mem0ai", "version": "2.2.1", "license": "Apache-2.0",
                 "main_source_sha256": "f329ca4a17af1fbefb32ac10d4cc7ae7ddbdb7435a87eb74c30915cff98b8b7c"},
        "data_origin": "Four literal authored synthetic strings; no model responses or human labels",
        "model_or_embedding_api_calls": 0,
        "executor": "same owner and workstation; independent reproduction not inferred",
        "protocol_history": "Private-development wording is preserved verbatim. This separately authorized public export changes distribution only, not the experimental criteria.",
        "upstream_path_exception": "The /home/openclaw fixture in vendored tests/test_quality.py is verbatim public MIT upstream source, not a path on the research workstation. That test is not executed.",
        "manuscript": "Coauthored manuscript remains an author-review draft outside this code/data release; scientific submission approval is not inferred.",
        "publication_readiness": "NOT_ESTABLISHED"
    })
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    save(out / "RELEASE_MANIFEST.json", {"files": manifest, "hash_algorithm": "sha256", "self_excluded": True})
    print(json.dumps({"files": len(manifest), "bytes": sum(p.stat().st_size for p in out.rglob("*") if p.is_file()),
                      "copied_files_byte_preserved": len(copies)}))


if __name__ == "__main__":
    main()
