import json
import re
from pathlib import Path
from statistics import mean
from collections import defaultdict

# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------
ANSWERS_DIR = Path("./answers")
SUMMARY_DIR = Path("./summary")

# Preferred dimension (colour) column order
DIMENSION_ORDER = ["White", "Red", "Black", "Yellow", "Green", "Blue"]

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def extract_question_and_dimension_from_heading(markdown: str):
    """
    Extract question ID (e.g. finance-q001) and dimension from the first heading line:
    Example: "# finance-q001 — Black"
    """
    # Allow various dashes (em dash, hyphen, en dash)
    pattern = r"^#\s*([A-Za-z0-9_\-]+)\s*[—\-–]\s*([A-Za-z]+)"
    m = re.search(pattern, markdown, flags=re.MULTILINE)
    if not m:
        return None, None
    qid = m.group(1).strip()
    dimension = m.group(2).strip()
    return qid, dimension


def extract_embedded_json(markdown: str):
    """
    Extract the JSON inside ```json ... ``` code fences.

    Works with your format:

    <details>
    <summary>Raw Embedded JSON</summary>

    ```json
    { ... }
    ```
    </details>
    """
    m = re.search(r"```json\s*(.*?)\s*```", markdown, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    json_str = m.group(1)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def safe_mean(values):
    """Return mean of list, or None if empty."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    return mean(values)


def parse_filename_metadata(md_path: Path):
    """
    Parse (group, qid, colour) from filename pattern:
        ./answers/<group>/<something>.md

    For your case:
        ./answers/finance/finance-q001-BLACK.md

    We use:
        group  = 'finance'        (first directory under ./answers)
        qid    = 'finance-q001'   (stem without last '-COLOUR' part)
        colour = 'BLACK'          (last part of stem)
    """
    # Group is the first directory under ANSWERS_DIR
    rel = md_path.relative_to(ANSWERS_DIR)
    parts = rel.parts  # e.g. ('finance', 'finance-q001-BLACK.md')

    group = parts[0] if len(parts) >= 2 else "root"

    stem = md_path.stem  # e.g. "finance-q001-BLACK"
    stem_parts = stem.split("-")
    if len(stem_parts) >= 2:
        colour = stem_parts[-1]             # "BLACK"
        qid = "-".join(stem_parts[:-1])     # "finance-q001"
    else:
        # Fallback if no hyphen: treat whole stem as qid
        qid = stem
        colour = None

    return group, qid, colour


def normalise_dimension_name(name):
    if not name:
        return None
    # BLACK / black / Black -> "Black"
    return name.strip().title()


# --------------------------------------------------------------------
# Core processing
# --------------------------------------------------------------------
def load_results_grouped_by_group():
    """
    Load all markdown answer files (recursively) and extract structured results.

    Returns:
        results_by_group: dict
          {
            "finance": {
              "finance-q001": {
                "dimensions": {
                  "Black": {
                    "overall": 3.2,
                    "criteria": {...}
                  },
                  ...
                }
              },
              ...
            },
            ...
          }
    """
    # group -> qid -> { "dimensions": { dim_name: {...} } }
    results_by_group = defaultdict(lambda: {})

    for md_path in ANSWERS_DIR.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8")

        data = extract_embedded_json(text)
        if not data:
            # No JSON, skip file
            print(f"Skipping (no JSON): {md_path}")
            continue

        # Parse from filename
        group_from_path, qid_from_file, colour_from_file = parse_filename_metadata(md_path)

        # From heading
        qid_from_heading, dim_from_heading = extract_question_and_dimension_from_heading(text)

        # Decide final group / question / dimension
        group = group_from_path or "root"
        qid = qid_from_file or qid_from_heading
        if not qid:
            print(f"Skipping (no qid): {md_path}")
            continue

        dimension_name = (
            data.get("dimension_name")      # preferred: "Black"
            or dim_from_heading            # from heading "# finance-q001 — Black"
            or colour_from_file            # from filename "...-BLACK.md"
            or "Unknown"
        )
        dimension_name = normalise_dimension_name(dimension_name)

        # Extract scores from JSON
        overall = data.get("overall_score")
        criteria_scores = data.get("criteria_scores", {})

        group_questions = results_by_group[group]
        q_entry = group_questions.setdefault(qid, {"dimensions": {}})
        q_entry["dimensions"][dimension_name] = {
            "overall": overall,
            "criteria": criteria_scores,
        }

    return results_by_group


def build_question_pivot_markdown(group, qid, qdata):
    """
    Build the markdown pivot table for a single question in a group.
    """
    dimensions = qdata["dimensions"]

    # Which dimensions do we have, in preferred order
    available_dims = [d for d in DIMENSION_ORDER if d in dimensions] or sorted(dimensions.keys())

    # Collect all criteria keys across dimensions (PF, COV, SPEC, ACT, DIST, CLAR, ...)
    all_criteria = set()
    for dim_info in dimensions.values():
        all_criteria.update(dim_info.get("criteria", {}).keys())

    preferred_criteria_order = ["PF", "COV", "SPEC", "ACT", "DIST", "CLAR"]
    criteria_order = [c for c in preferred_criteria_order if c in all_criteria]
    criteria_order += sorted(all_criteria - set(criteria_order))

    lines = []
    lines.append(f"# {group} — {qid} — Summary\n")

    # Criteria pivot
    lines.append("## Criteria Pivot by Dimension\n")
    header = "| Criteria | " + " | ".join(available_dims) + " | Average |"
    sep = "|---|" + "|".join(["---"] * len(available_dims)) + "|---|"
    lines.append(header)
    lines.append(sep)

    for crit in criteria_order:
        row_values = []
        numeric_values = []
        for dim in available_dims:
            score = dimensions[dim]["criteria"].get(crit)
            if score is None:
                row_values.append("")
            else:
                row_values.append(str(score))
                numeric_values.append(float(score))

        avg_val = safe_mean(numeric_values)
        avg_str = f"{avg_val:.2f}" if avg_val is not None else ""

        line = "| " + crit + " | " + " | ".join(row_values) + f" | {avg_str} |"
        lines.append(line)

    # Overall scores table
    lines.append("\n## Overall Scores by Dimension\n")
    lines.append("| Dimension | Overall Score |")
    lines.append("|---|---|")
    overall_scores = []
    for dim in available_dims:
        overall = dimensions[dim].get("overall")
        if overall is not None:
            overall_scores.append(float(overall))
            lines.append(f"| {dim} | {overall:.2f} |")
        else:
            lines.append(f"| {dim} |  |")

    avg_overall = safe_mean(overall_scores)
    if avg_overall is not None:
        lines.append(f"| **Average** | **{avg_overall:.2f}** |")

    markdown = "\n".join(lines) + "\n"
    return markdown


def build_group_summary_markdown(group, questions):
    """
    Group-level summary across all questions in that group.
    Aggregates:
      - criteria averages per dimension across all questions
      - overall score averages per dimension across all questions
    """
    all_dims = set()
    all_criteria = set()

    # dim -> crit -> [scores...]
    dim_crit_scores = defaultdict(lambda: defaultdict(list))
    # dim -> [overall scores...]
    dim_overall_scores = defaultdict(list)

    for qid, qdata in questions.items():
        for dim_name, dim_info in qdata["dimensions"].items():
            all_dims.add(dim_name)
            criteria = dim_info.get("criteria", {})
            for crit, score in criteria.items():
                all_criteria.add(crit)
                if score is not None:
                    dim_crit_scores[dim_name][crit].append(float(score))

            overall = dim_info.get("overall")
            if overall is not None:
                dim_overall_scores[dim_name].append(float(overall))

    if not all_dims:
        return f"# {group} — Group Summary\n\n_No data found for this group._\n"

    available_dims = [d for d in DIMENSION_ORDER if d in all_dims] or sorted(all_dims)

    preferred_criteria_order = ["PF", "COV", "SPEC", "ACT", "DIST", "CLAR"]
    criteria_order = [c for c in preferred_criteria_order if c in all_criteria]
    criteria_order += sorted(all_criteria - set(criteria_order))

    lines = []
    lines.append(f"# {group} — Group Summary\n")
    lines.append(f"Total questions in group: **{len(questions)}**\n")

    # Criteria pivot
    lines.append("## Criteria Pivot by Dimension (All Questions)\n")
    header = "| Criteria | " + " | ".join(available_dims) + " | Average |"
    sep = "|---|" + "|".join(["---"] * len(available_dims)) + "|---|"
    lines.append(header)
    lines.append(sep)

    for crit in criteria_order:
        row_values = []
        numeric_values_for_all_dims = []
        for dim in available_dims:
            scores = dim_crit_scores[dim].get(crit, [])
            if not scores:
                row_values.append("")
            else:
                avg = safe_mean(scores)
                row_values.append(f"{avg:.2f}")
                numeric_values_for_all_dims.append(avg)

        avg_val = safe_mean(numeric_values_for_all_dims)
        avg_str = f"{avg_val:.2f}" if avg_val is not None else ""

        line = "| " + crit + " | " + " | ".join(row_values) + f" | {avg_str} |"
        lines.append(line)

    # Overall scores table
    lines.append("\n## Overall Scores by Dimension (All Questions)\n")
    lines.append("| Dimension | Average Overall Score |")
    lines.append("|---|---|")

    all_overall_avgs = []
    for dim in available_dims:
        scores = dim_overall_scores.get(dim, [])
        if scores:
            avg = safe_mean(scores)
            all_overall_avgs.append(avg)
            lines.append(f"| {dim} | {avg:.2f} |")
        else:
            lines.append(f"| {dim} |  |")

    grand_avg = safe_mean(all_overall_avgs)
    if grand_avg is not None:
        lines.append(f"| **All Dimensions** | **{grand_avg:.2f}** |")

    # List questions in group
    lines.append("\n## Questions in This Group\n")
    for qid in sorted(questions.keys()):
        lines.append(f"- {qid}")

    markdown = "\n".join(lines) + "\n"
    return markdown


def main():
    SUMMARY_DIR.mkdir(exist_ok=True)

    results_by_group = load_results_grouped_by_group()

    for group, questions in results_by_group.items():
        group_dir = SUMMARY_DIR / group
        group_dir.mkdir(parents=True, exist_ok=True)

        # 1) Group-level summary
        group_summary_md = build_group_summary_markdown(group, questions)
        group_summary_path = group_dir / f"{group}-summary.md"
        group_summary_path.write_text(group_summary_md, encoding="utf-8")
        print(f"Wrote group summary for {group} -> {group_summary_path}")

        # 2) Question-level summaries
        for qid, qdata in questions.items():
            q_summary_md = build_question_pivot_markdown(group, qid, qdata)
            q_summary_path = group_dir / f"{group}-{qid}-summary.md"
            q_summary_path.write_text(q_summary_md, encoding="utf-8")
            print(f"Wrote question summary for {group}/{qid} -> {q_summary_path}")


if __name__ == "__main__":
    main()
