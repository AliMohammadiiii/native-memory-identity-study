"""Make publication-size figures from bound native captures, without new calls."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np


INK = "#203947"
MUTED = "#627482"
GREEN = "#237C70"
RUST = "#B74C38"
BLUE = "#386CA5"
GRID = "#DFE6EA"
PALE = "#F2F5F7"
STREAMS = ["normal_change", "same_value", "repeat_current_value", "return_to_archived_value",
           "existing_other_root", "existing_other_chain", "different_namespace_value", "repeat_remember"]
LABELS = ["Update to a new value", "Update to the same value", "Repeat the current value",
          "Return to an archived value", "Match another active root", "Match another active chain",
          "Match a different namespace", "Repeat add / remember"]
ARMS = ["unmodified", "distinct_id_guard", "dedup_branch_disabled"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def checked_values(cell):
    value = cell["final_requested"]
    if cell["final_outcome"] != "return" or any(s["native"]["outcome"] != "return" for s in cell["steps"]):
        raise ValueError("unsuccessful_native_cell")
    flags = [value in cell["final"]["current_contents"], value in cell["final"]["physical_contents"],
             value in cell["cold"]["current_contents"]]
    if len(set(flags)) != 1:
        raise ValueError("public_physical_cold_disagreement")
    if cell["final"]["sentinel_contents"] != ["memoryprobe unrelated keep"]:
        raise ValueError("sentinel_changed")
    return flags[0]


def save_figure(fig, name, out):
    fig.savefig(out / (name + ".pdf"), facecolor="white", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / (name + ".svg"), facecolor="white", metadata={"Date": None})
    fig.savefig(out / (name + ".png"), dpi=360, facecolor="white")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = []
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text():
            box = text.get_window_extent(renderer)
            if box.width and box.height:
                bounds.append({"text": text.get_text(), "font_points": text.get_fontsize(),
                               "inside_canvas": bool(box.x0 >= -1 and box.y0 >= -1 and box.x1 <= fig.bbox.width + 1 and box.y1 <= fig.bbox.height + 1)})
    plt.close(fig)
    return bounds


def heading(fig, title, subtitle):
    fig.text(.035, .94, title, color=INK, fontsize=13.5, weight="bold", va="top")
    fig.text(.035, .87, subtitle, color=MUTED, fontsize=8.8, va="top")


def stream_figure(rows, out):
    fig = plt.figure(figsize=(6.4, 3.9))
    heading(fig, "Current-value availability in the fixed streams",
            "32 native cells  |  8 streams × 2 configurations × 2 fresh repetitions")
    ax = fig.add_axes([.43, .19, .53, .59])
    ax.set_xlim(-.25, 1.75)
    ax.set_ylim(-.65, 8.15)
    for y in range(8):
        ax.axhspan(y - .46, y + .46, color=PALE if y % 2 == 0 else "white", zorder=0)
    for j, stream in enumerate(STREAMS):
        y = 7 - j
        for lib, xbase in (("agentmem", 0), ("mem0", 1.15)):
            for rep, offset in ((1, 0), (2, .35)):
                item = next(r for r in rows if r["library"] == lib and r["stream"] == stream and r["repetition"] == rep)
                visible = item["visible"]
                ax.scatter(xbase + offset, y, marker="o" if visible else "X", s=72 if visible else 95,
                           color=GREEN if visible else RUST, linewidths=.7, edgecolors="white", zorder=3)
    ax.axvline(.75, color=GRID, lw=.8)
    ax.text(.175, 8.03, "agentmem", ha="center", fontsize=10, weight="bold", color=INK)
    ax.text(1.325, 8.03, "Mem0", ha="center", fontsize=10, weight="bold", color=INK)
    for x, label in ((0, "1"), (.35, "2"), (1.15, "1"), (1.5, "2")):
        ax.text(x, 7.62, label, ha="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(range(8), list(reversed(LABELS)), color=INK, fontsize=9)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    handles = [Line2D([], [], marker="o", ls="", color=GREEN, markersize=6.2, label="Requested value present"),
               Line2D([], [], marker="X", ls="", color=RUST, markersize=7.2, label="Requested value absent")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .07), ncol=2,
               frameon=False, handletextpad=.45, columnspacing=2.2, fontsize=8.6)
    fig.text(.035, .027, "One symbol per fresh store. Selected development streams; no population failure-rate estimate.",
             fontsize=8.0, color=MUTED)
    return save_figure(fig, "01_stream_outcomes", out)


def intervention_figure(summary, out):
    fig, axes = plt.subplots(1, 4, figsize=(6.4, 3.2), sharey=True)
    fig.subplots_adjust(left=.26, right=.965, top=.65, bottom=.25, wspace=.38)
    heading(fig, "A narrow identity guard changes the stored outcome",
            "24 intervention cells  |  same 8 streams per source arm  |  one fresh store per cell")
    titles = ["Current value\nabsent", "Stored\nself edge", "Old subject\nstill active", "Response ID =\npredecessor"]
    keys = ["confirmed_current_loss", "stored_self_edges", "subject_active_with_different_returned_id", "response_self_predecessor"]
    for index, (ax, title, key) in enumerate(zip(axes, titles, keys)):
        ax.set_title(title, fontsize=8.8, color=INK if index < 3 else BLUE, pad=13, weight="bold")
        for y, arm in zip((2, 1, 0), ARMS):
            value = summary[arm][key]
            color = RUST if index < 3 else BLUE
            ax.hlines(y, 0, 8, color=GRID, lw=.7, zorder=0)
            ax.hlines(y, 0, value, color=color, lw=2, zorder=1)
            ax.scatter(value, y, s=36, marker="o", facecolors=color if value else "white",
                       edgecolors=color if value else MUTED, lw=1.1, zorder=3)
            ax.annotate(str(value) + "/8", (value, y), xytext=(6, 7), textcoords="offset points",
                        fontsize=8.4, color=color if value else MUTED)
        ax.set_xlim(-.65, 8.9)
        ax.set_ylim(-.45, 2.6)
        ax.set_xticks([0, 4, 8])
        ax.tick_params(axis="x", labelsize=8, colors=MUTED, length=3, pad=3)
        ax.tick_params(axis="y", length=0, pad=9, labelcolor=INK, labelsize=8.7)
        ax.set_xlabel("Streams", fontsize=8.2, color=MUTED, labelpad=5)
        for name, spine in ax.spines.items():
            spine.set_visible(name == "bottom")
            spine.set_color(GRID)
    axes[0].set_yticks([2, 1, 0], ["Unmodified", "Different-ID\nguard", "Whole branch\ndisabled"])
    fig.text(.035, .075, "State observations", fontsize=8.5, color=RUST, weight="bold")
    fig.text(.27, .075, "Response field is a separate diagnostic, not an established second defect.", fontsize=8.0, color=MUTED)
    fig.text(.035, .025, "Fixed, source-informed intervention. Counts are not independent bugs or production reliability estimates.", fontsize=8, color=MUTED)
    return save_figure(fig, "02_identity_intervention", out)


def card(ax, box, title, body, color, fill="white"):
    x, y, w, h = box
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.01,rounding_size=.014",
                          facecolor=fill, edgecolor=color, lw=1.1, transform=ax.transAxes)
    ax.add_patch(patch)
    ax.text(x + .018, y + h - .05, title, fontsize=9.8, weight="bold", color=color,
            va="top", transform=ax.transAxes)
    ax.text(x + .018, y + h - .125, body, fontsize=8.7, linespacing=1.5, color=INK,
            va="top", transform=ax.transAxes)


def witness_figure(original, guarded, out):
    fig = plt.figure(figsize=(6.4, 3.8))
    heading(fig, "Same response, different stored states",
            "Representative same-value captures  |  original source and different-ID guard")
    ax = fig.add_axes([.025, .10, .95, .70])
    ax.set_axis_off()
    original_step = original["steps"][-1]
    guard_step = guarded["steps"][-1]
    before = original_step["before"]
    identifier = original["aliases"]["subject"]
    if original_step["native"]["value"] != guard_step["native"]["value"]:
        raise ValueError("witness_responses_differ")
    old = next(r for r in before["physical_rows"] if r["id"] == identifier)
    original_row = next(r for r in original["final"]["physical_rows"] if r["id"] == identifier)
    guarded_row = next(r for r in guarded["final"]["physical_rows"] if r["id"] == identifier)
    def predecessor(row):
        return "none" if row["supersedes"] is None else str(row["supersedes"])
    body = f"Record ID: {identifier}\nArchived: {old['archived']}\nPredecessor: {predecessor(old)}\nCurrent records: {len(before['public_current'])}"
    card(ax, (.01, .28, .24, .50), "Before the call", body, MUTED, PALE)
    response = original_step["native"]["value"]
    card(ax, (.315, .36, .285, .34), "Successful response",
         f"Same text requested\nid = {response['id']}\nsupersedes = {response['supersedes']}", BLUE, "#F1F5FA")
    for cell, row, y, title, color, fill in (
        (original, original_row, .54, "Unmodified", RUST, "#FCF3EF"),
        (guarded, guarded_row, .015, "Different-ID guard", GREEN, "#EFF7F3")):
        body = f"Archived: {row['archived']}\nPredecessor: {predecessor(row)}\nCurrent records: {len(cell['final']['public_current'])}\nAfter cold reopen: {len(cell['cold']['public_current'])}"
        card(ax, (.69, y, .295, .42), title, body, color, fill)
    for start, end, color in (((.255, .53), (.307, .53), MUTED), ((.607, .57), (.682, .75), RUST), ((.607, .49), (.682, .22), GREEN)):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=10,
                                    lw=1.2, color=color, transform=ax.transAxes))
    fig.text(.035, .057, "Solid arrows show call order in separate fresh stores; branch identity is inspected in source.", fontsize=8, color=MUTED)
    fig.text(.035, .018, "Existing cells shown again; no extra executions or complete repair validation.", fontsize=8, color=MUTED)
    return save_figure(fig, "03_native_witness", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benign-capture", required=True, type=Path)
    ap.add_argument("--benign-analysis", required=True, type=Path)
    ap.add_argument("--intervention-capture", required=True, type=Path)
    ap.add_argument("--intervention-analysis", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.color": INK,
                         "axes.labelcolor": INK, "axes.edgecolor": GRID, "axes.linewidth": .7,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
                         "svg.hashsalt": "native-benign-figures-v1", "savefig.dpi": 360,
                         "figure.dpi": 160, "path.simplify": False})
    inputs = {}
    matrix = []
    table = list(csv.DictReader((args.benign_analysis / "CELL_TABLE.csv").open()))
    if len(table) != 32 or len({(r["library"], r["stream"], r["repetition"]) for r in table}) != 32:
        raise ValueError("original_matrix_incomplete")
    for lib in ("agentmem", "mem0"):
        for stream in STREAMS:
            for rep in (1, 2):
                path = args.benign_capture / "cells" / ("rep_" + str(rep)) / (lib + "__" + stream) / "CELL.json"
                cell = read(path)
                visible = checked_values(cell)
                row = next(r for r in table if r["library"] == lib and r["stream"] == stream and int(r["repetition"]) == rep)
                if row["requested_value_visible"] != str(visible):
                    raise ValueError("original_table_drift")
                matrix.append({"library": lib, "stream": stream, "repetition": rep, "visible": visible})
                inputs["benign/" + str(path.relative_to(args.benign_capture))] = sha(path)
    intervention = []
    for arm in ARMS:
        for stream in STREAMS:
            path = args.intervention_capture / "cells" / arm / stream / "CELL.json"
            cell = read(path)
            visible = checked_values(cell)
            final = cell["final"]
            response = cell["steps"][-1]["native"]["value"]
            subject = cell["aliases"]["subject"]
            returned = cell["steps"][-1]["native"]["returned_id"]
            intervention.append({"arm": arm, "stream": stream,
                "confirmed_current_loss": not visible,
                "stored_self_edges": sum(r["id"] == r["supersedes"] for r in final["physical_rows"]),
                "subject_active_with_different_returned_id": returned != subject and any(r["id"] == subject and r["archived"] == 0 for r in final["physical_rows"]),
                "response_self_predecessor": "supersedes" in response and response.get("id") == response["supersedes"]})
            inputs["intervention/" + str(path.relative_to(args.intervention_capture))] = sha(path)
    summary = {arm: {key: sum(r[key] for r in intervention if r["arm"] == arm) for key in
                    ("confirmed_current_loss", "stored_self_edges", "subject_active_with_different_returned_id", "response_self_predecessor")}
               for arm in ARMS}
    reported = read(args.intervention_analysis / "RESULT.json")
    if summary != reported["summary"]:
        raise ValueError("intervention_summary_drift")
    for label, path in (("benign_table", args.benign_analysis / "CELL_TABLE.csv"),
                        ("intervention_result", args.intervention_analysis / "RESULT.json"),
                        ("benign_manifest", args.benign_capture / "MANIFEST.json"),
                        ("intervention_manifest", args.intervention_capture / "MANIFEST.json")):
        inputs[label] = sha(path)
    original = read(args.intervention_capture / "cells/unmodified/same_value/CELL.json")
    guarded = read(args.intervention_capture / "cells/distinct_id_guard/same_value/CELL.json")
    layout = {"01_stream_outcomes": stream_figure(matrix, out),
              "02_identity_intervention": intervention_figure(summary, out),
              "03_native_witness": witness_figure(original, guarded, out)}
    payload = {"original_cells": matrix, "intervention_cells": intervention, "intervention_summary": summary}
    (out / "FIGURE_DATA.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    spec = {"DATA_STATUS": "PROVIDED", "STYLE_STATUS": "ESTIMATED", "REPRODUCIBILITY_STATUS": "CODED",
            "EXPORT_STATUS": "NEEDS_JOURNAL_CHECK", "INTEGRITY_STATUS": "PASS_WITH_WARNINGS",
            "target": "Generic author-review paper; no selected venue", "width_inches": 6.4,
            "uncertainty": "No inferential intervals. Fixed deterministic development streams are not population samples.",
            "figures": [
                {"id": "01_stream_outcomes", "claim": "Requested content is absent in the two selected same-value agentmem streams, with both repetitions shown.", "denominator": "32 original cells", "type": "individual-cell outcome map"},
                {"id": "02_identity_intervention", "claim": "The unequal-ID guard preserves current content and distinct-ID archiving in the fixed streams, while whole-branch disabling retains old active subjects.", "denominator": "8 streams per arm; 24 separate intervention cells", "type": "aligned count dot plots"},
                {"id": "03_native_witness", "claim": "The same successful returned fields coexist with different captured persisted states in the unmodified and guarded same-value cells.", "denominator": "two representative already counted cells", "type": "observed state and call-order diagram"}]}
    (out / "FIGURE_SPEC.json").write_text(json.dumps(spec, indent=2) + "\n")
    (out / "TEXT_LAYOUT.json").write_text(json.dumps(layout, indent=2) + "\n")
    (out / "QUALITY_REPORT.json").write_text(json.dumps({"source_checks": "PASS", "all_56_cells_reopened": True,
        "denominators_kept_separate": True, "no_data_transform_beyond_tabulation": True,
        "canvas_text_bounds": {k: all(t["inside_canvas"] for t in v) for k, v in layout.items()},
        "visual_inspection": "PENDING", "journal_style": "ESTIMATED", "model_calls": 0}, indent=2) + "\n")
    shutil.copy2(Path(__file__), out / "plot_figures.py")
    (out / "INPUT_BINDINGS.json").write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
    captions = {
        "01_stream_outcomes": {"caption": "Public current-value availability in every original selected native cell. Each symbol is one fresh store; columns identify the two configurations and their two repetitions. Presence and absence agree with separate physical and cold observations. The fixed development matrix does not estimate deployment failure rates or general system superiority.", "alt_text": "Eight operation streams by four repetition columns. Both agentmem repetitions lack the current requested value for same-value and repeat-current-value updates. All other displayed cells retain it."},
        "02_identity_intervention": {"caption": "Separate source intervention on the same eight streams per arm. Counts use the full 0 to 8 scale. Stored loss and self edges disappear under both changes; whole-branch disabling retains the old subject in two different-ID streams. Identical returned ID and predecessor fields remain a separate response diagnostic and are not independently classified as another defect. No inferential intervals are shown for these deterministic authored cells.", "alt_text": "Four aligned count plots for three source arms. Unmodified source has two loss and self-edge cells. The guard has zero of each and zero old-subject retention. Disabled branch has two old-subject-retention cells. Each arm has two self-valued predecessor responses."},
        "03_native_witness": {"caption": "Representative captured same-value call sequence in separate fresh stores. The returned ID and predecessor fields are identical in the two arms; the unmodified source archives and self-links the record, while the guarded source retains an active record without a persisted self edge. Current reads after cold reopening agree with each captured state. Arrows indicate call order; branch interpretation is grounded in inspected source. These are views of existing cells, not new executions or a complete repair validation.", "alt_text": "An initial active record with no predecessor leads to the same successful response in both arms. The unmodified state is archived with zero current records; the guarded state remains active with one current record. Cold reads preserve the difference."}}
    (out / "CAPTIONS.json").write_text(json.dumps(captions, indent=2) + "\n")
    assets = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    (out / "MANIFEST.json").write_text(json.dumps({"files": assets, "input_files": len(inputs),
        "new_native_calls": 0, "new_model_calls": 0}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"figures": 3, "formats": ["PDF", "SVG", "PNG"], "reopened_native_cells": len(matrix) + len(intervention),
                      "canvas_text_checks": {k: all(t["inside_canvas"] for t in v) for k, v in layout.items()}}))


if __name__ == "__main__":
    main()
