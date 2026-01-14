import json
import re
from pathlib import Path
from statistics import mean

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
def extract_question_and_dimension(markdown: str):
    """
    Extract question ID (e.g. q1) and dimension from the first heading line:
    Example: "# q1 — Black"
    """
    # Allow various dashes (em dash, hyphen, etc.)
    pattern = r"^#\s*(q\d+)\s*[—\-–]\s*([A-Za-z]+)"
    m = re.search(pattern, markdown, flags=re.MULTILINE)
    if not m:
        return None, None
    qid = m.group(1).strip()
    dimension = m.group(2).strip()
    return qid, dimension


def extract_embedded_json(markdown: str):
    """
    Extract the JSON inside ```json ... ``` code fences.
    Returns parsed Python object or None.
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


# --------------------------------------------------------------------
# Core processing
# --------------------------------------------------------------------
def load_results():
    """
    Load all markdown answer files and extract structured results.

    Returns:
        questions: dict
          {
            "q1": {
              "dimensions": {
                "Black": {
                  "overall": 3.2,
                  "criteria": {"PF": 3, "COV": 4, ...}
                },
                ...
              }
            },
            ...
          }
    """
    questions = {}

    for md_path in ANSWERS_DIR.glob("*.md"):
        text = md_path.read_text(encoding="utf-8")

        qid, dim_from_heading = extract_question_and_dimension(text)
        if not qid:
            # Skip files without proper heading
            continue

        data = extract_embedded_json(text)
        if not data:
            # Skip if no JSON
            continue

        # Prefer dimension_name from JSON, fall back to heading
        dimension_name = data.get("dimension_name") or dim_from_heading or "Unknown"

        # Extract overall score and criteria
        overall = data.get("overall_score")
        criteria_scores = data.get("criteria_scores", {})

        q_entry = questions.setdefault(qid, {"dimensions": {}})
        q_entry["dimensions"][dimension_name] = {
            "overall": overall,
            "criteria": criteria_scores,
        }

    return questions


def build_pivot_markdown(qid, qdata):
    """
    Build the markdown pivot table for a single question.
    """
    dimensions = qdata["dimensions"]

    # Determine which dimensions we actually have, in desired order
    available_dims = [d for d in DIMENSION_ORDER if d in dimensions] or sorted(dimensions.keys())

    # Collect all criteria keys across dimensions (e.g. PF, COV, SPEC, ACT, DIST, CLAR)
    all_criteria = set()
    for dim_info in dimensions.values():
        all_criteria.update(dim_info.get("criteria", {}).keys())

    # Sort criteria with a helpful order if possible
    preferred_criteria_order = ["PF", "COV", "SPEC", "ACT", "DIST", "CLAR"]
    criteria_order = [c for c in preferred_criteria_order if c in all_criteria]
    criteria_order += sorted(all_criteria - set(criteria_order))

    # Build pivot table rows: criteria vs dimensions + Average column
    lines = []

    lines.append(f"# {qid} — Summary\n")

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

    # Optional: overall score table
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


def main():
    SUMMARY_DIR.mkdir(exist_ok=True)

    questions = load_results()

    for qid, qdata in questions.items():
        summary_md = build_pivot_markdown(qid, qdata)
        out_path = SUMMARY_DIR / f"{qid}-summary.md"
        out_path.write_text(summary_md, encoding="utf-8")
        print(f"Wrote summary for {qid} -> {out_path}")


if __name__ == "__main__":
    main()
