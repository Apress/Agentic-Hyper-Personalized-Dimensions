#!/usr/bin/env python3
"""
Convert Six Dimensions JSON responses into Markdown summaries.

New in this version:
- Recursively scans ./responses/** for JSON files (area subfolders supported)
- Writes Markdown to ./answers/<area-slug>/ to mirror the new structure
- Derives `area` from payload["area"] when present, otherwise from the
  first directory under ./responses/

Robust to minor format issues (falls back to dumping raw response_text if parsing fails).
"""

import re
import json
from pathlib import Path
from typing import Dict, Any

RESPONSES_ROOT = Path("./responses")
ANSWERS_ROOT = Path("./answers")

# Optional: expand the score code names into nicer labels if present.
SCORE_LABELS = {
    "PF": "Problem Framing",
    "COV": "Coverage",
    "SPEC": "Specificity",
    "ACT": "Actionability",
    "DIST": "Distinctiveness",
    "CLAR": "Clarity",
}

FENCE_REGEX = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip())
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-").lower() or "general"


def extract_inner_json(response_text: str) -> Dict[str, Any]:
    """
    Pull the first JSON object found inside a fenced code block from response_text.
    Returns a Python dict.

    Raises ValueError if not found or not valid JSON.
    """
    m = FENCE_REGEX.search(response_text or "")
    if not m:
        # If no fence, try to parse the whole string as JSON
        candidate = (response_text or "").strip()
    else:
        candidate = m.group(1).strip()

    if not candidate:
        raise ValueError("Empty response_text.")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse embedded JSON: {e}") from e


def md_escape(text: str) -> str:
    """Minimal escaping for Markdown; keep it simple and readable."""
    return (text or "").replace("<", "&lt;").replace(">", "&gt;").strip()


def render_scores_table(criteria_scores: Dict[str, Any]) -> str:
    if not isinstance(criteria_scores, dict) or not criteria_scores:
        return "_No criteria scores provided._\n"

    lines = ["| Criteria | Score |", "|---|---|"]
    for k, v in criteria_scores.items():
        label = SCORE_LABELS.get(k, k)
        lines.append(f"| {md_escape(label)} | {md_escape(str(v))} |")
    return "\n".join(lines) + "\n"


def render_list(title: str, items: Any) -> str:
    if not items:
        return f"**{title}:** _None provided._\n"
    out = [f"**{title}:**"]
    for it in items:
        out.append(f"- {md_escape(str(it))}")
    return "\n".join(out) + "\n"


def build_markdown(
    top_level: Dict[str, Any],
    embedded: Dict[str, Any],
) -> str:
    """
    Compose the final Markdown using both the top-level fields
    (question_id, dimension, prompt_file, model) and the parsed embedded JSON.
    """
    qid = top_level.get("question_id", "unknown-id")
    dim = top_level.get("dimension", "UNKNOWN")
    prompt_file = top_level.get("prompt_file", "")
    model = top_level.get("model", "")

    dim_name = embedded.get("dimension_name", dim.title())
    criteria = embedded.get("criteria_scores", {}) or {}
    overall = embedded.get("overall_score", "")
    just = embedded.get("justification", {}) or {}
    summary = just.get("summary", "")
    strengths = just.get("strengths", [])
    weaknesses = just.get("weaknesses", [])

    md = []
    md.append(f"# {md_escape(qid)} — {md_escape(dim_name)}")
    md.append("")
    if model or prompt_file:
        md.append("> Metadata")
        if model:
            md.append(f"> - **Model:** {md_escape(str(model))}")
        if prompt_file:
            md.append(f"> - **Prompt:** `{md_escape(str(prompt_file))}`")
        md.append("")

    if overall != "":
        md.append(f"**Overall Score:** {md_escape(str(overall))}")
        md.append("")

    if summary:
        md.append("## Summary")
        md.append(md_escape(summary))
        md.append("")

    md.append("## Criteria Scores")
    md.append(render_scores_table(criteria))

    md.append("## Analysis Highlights")
    md.append(render_list("Strengths", strengths))
    md.append(render_list("Weaknesses", weaknesses))

    # Provide the raw embedded JSON in a collapsible block for traceability
    md.append("<details>")
    md.append("<summary>Raw Embedded JSON</summary>")
    md.append("")
    md.append("```json")
    md.append(json.dumps(embedded, indent=2, ensure_ascii=False))
    md.append("```")
    md.append("</details>")
    md.append("")

    return "\n".join(md)


def infer_area_from_path(json_path: Path) -> str:
    """
    Infer area by taking the first component under RESPONSES_ROOT.
    e.g. responses/healthcare/x.json -> 'healthcare'
    If the JSON sits directly inside responses/, returns 'general'.
    """
    try:
        rel = json_path.relative_to(RESPONSES_ROOT)
    except ValueError:
        return "general"
    parts = rel.parts
    return parts[0] if len(parts) >= 2 else "general"


def convert_file(json_path: Path) -> Path:
    """
    Convert a single JSON file to Markdown. Returns the output markdown path.
    Writes to answers/<area-slug>/... mirroring the new structure.
    """
    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    response_text = payload.get("response_text", "")
    # Resolve area
    area = (payload.get("area") or infer_area_from_path(json_path) or "general")
    area_slug = slugify(area)

    try:
        embedded = extract_inner_json(response_text)
        md_text = build_markdown(payload, embedded)
    except ValueError:
        # Fallback: dump raw response_text as-is
        md_text = "\n".join([
            f"# {payload.get('question_id','unknown-id')} — {payload.get('dimension','UNKNOWN')}",
            "",
            "> _Warning: Could not parse embedded JSON. Showing raw response text._",
            "",
            "```",
            (response_text or "").strip(),
            "```",
            "",
        ])

    # Build output filename
    qid = payload.get("question_id", json_path.stem)
    dim = payload.get("dimension", "UNKNOWN")
    safe_qid = re.sub(r"[^A-Za-z0-9._-]+", "_", (qid or "unknown").strip())
    safe_dim = re.sub(r"[^A-Za-z0-9._-]+", "_", (dim or "UNKNOWN").strip())
    out_name = f"{safe_qid}-{safe_dim}.md"

    out_dir = ANSWERS_ROOT / area_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name
    out_path.write_text(md_text, encoding="utf-8")
    return out_path


def main():
    if not RESPONSES_ROOT.exists():
        raise SystemExit(f"Input directory not found: {RESPONSES_ROOT.resolve()}")

    # Recursively find *.json anywhere under responses/
    json_files = sorted(RESPONSES_ROOT.rglob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON files found in {RESPONSES_ROOT.resolve()}")

    print(f"Found {len(json_files)} file(s). Converting to Markdown...")
    ANSWERS_ROOT.mkdir(parents=True, exist_ok=True)

    for jp in json_files:
        outp = convert_file(jp)
        print(f"✔ Wrote {outp}")

    print(f"Done. Markdown files are in: {ANSWERS_ROOT.resolve()}")


if __name__ == "__main__":
    main()
