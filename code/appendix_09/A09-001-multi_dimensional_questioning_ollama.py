import json
import re
import requests
from pathlib import Path

MODEL = "gemma3:1b"
OLLAMA_URL = "http://localhost:11434"
QUESTIONS_FILE = Path("./questions.json")                 # input schema WITH evaluation_question (uploaded)
PLAYBOOK_FILE = Path("./playbook_questions.json")         # list of {area, questions[]} (uploaded)
FRAMEWORK_FILE = Path("./question_framework.json")        # derived schema WITHOUT evaluation_question
PERSONALITIES_FILE = Path("./personalities.json")

PROMPTS_DIR = Path("./prompts")
RESPONSES_DIR = Path("./responses")


def load_json_file(filepath: Path):
    """Load JSON file and return its contents."""
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(filepath: Path, payload) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def extract_short_code(crit_name: str) -> str:
    """Extract short code in parentheses, e.g. '(PF)'."""
    m = re.search(r"\(([A-Za-z]+)\)\s*$", crit_name.strip())
    return m.group(1) if m else ""


def build_prompt(schema: dict, dimension_key: str, persona_text: str) -> str:
    """Constructs a complete persona-specific prompt for Ollama."""
    question = schema["evaluation_question"]["question"]
    qid = schema["evaluation_question"]["id"]
    scale = schema.get("scale", {})
    criteria = schema.get("criteria", [])
    expected = schema["output_format_requirement"]["expected_output_structure"]
    example = schema["output_format_requirement"]["output_example"]

    scale_text = "\n".join([f"  {k} = {v}" for k, v in sorted(scale.items())])

    crit_lines = []
    short_codes = []
    for c in criteria:
        name, desc = c.get("name", ""), c.get("description", "")
        code = extract_short_code(name)
        if code:
            short_codes.append(code)
        crit_lines.append(f"- {name}: {desc}")
    short_codes_text = ", ".join(short_codes)

    expected_shape = json.dumps(expected, ensure_ascii=False, indent=2)
    example_json = json.dumps(example, ensure_ascii=False, indent=2)

    prompt = f"""{persona_text.strip()}

You are acting as the {dimension_key.title()} dimension.

Question ID: {qid}
Question:
{question}

Scoring scale (1–5):
{scale_text}

Evaluation criteria:
{chr(10).join(crit_lines)}

Output format instructions:
- Return ONLY a JSON object. No extra prose or code fences.
- Replace descriptor strings with actual numeric or text values.
- Use integer scores 1–5 for {short_codes_text}.
- Compute "overall_score" as the arithmetic mean of the six criteria, rounded to 2 decimals.
- Set "dimension_name" to "{dimension_key.title()}".

JSON schema:
{expected_shape}

Example output:
{example_json}
"""
    return prompt


def ask_ollama(prompt: str) -> str:
    """Send the prompt to Ollama and return the model's text output."""
    try:
        response = requests.post(
            url=f"{OLLAMA_URL}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=240,
        )
        response.raise_for_status()
        return response.json().get("response", "No response or error code received.")
    except Exception as e:
        return f"Error: {e}"


def slugify(text: str) -> str:
    """Filesystem-friendly slug (lowercase, alnum + hyphens)."""
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip())
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-").lower()


if __name__ == "__main__":
    # 1) Load the uploaded inputs
    original_schema = load_json_file(QUESTIONS_FILE)
    playbook = load_json_file(PLAYBOOK_FILE)  # list of {area, questions: []}
    personalities = load_json_file(PERSONALITIES_FILE)

    # 2) Create question_framework.json (schema without "evaluation_question")
    framework_schema = dict(original_schema)
    framework_schema.pop("evaluation_question", None)
    save_json_file(FRAMEWORK_FILE, framework_schema)

    print(f"Created framework (no evaluation_question): {FRAMEWORK_FILE.resolve()}")

    # 3) Iterate playbook areas & questions, inject eval question into schema copy
    total_runs = 0
    for area_block in playbook:
        area = area_block.get("area", "General")
        area_slug = slugify(area) or "general"
        questions = area_block.get("questions", [])
        if not isinstance(questions, list):
            print(f"[WARN] 'questions' is not a list for area '{area}'. Skipping.")
            continue

        # Area-specific prompt/response directories
        prompts_area_dir = PROMPTS_DIR / area_slug
        responses_area_dir = RESPONSES_DIR / area_slug
        prompts_area_dir.mkdir(parents=True, exist_ok=True)
        responses_area_dir.mkdir(parents=True, exist_ok=True)

        for idx, qtext in enumerate(questions, start=1):
            qid = f"{area_slug}-q{idx:03d}"
            working_schema = dict(framework_schema)
            working_schema["evaluation_question"] = {"id": qid, "question": qtext}

            print(f"\n[{area}] Building prompts and collecting LLM responses for {qid}...")

            for dim, persona in personalities.items():
                prompt = build_prompt(working_schema, dim, persona)

                # Save prompt to file under area subdir
                prompt_file = prompts_area_dir / f"{qid}-{dim.title()}.prompt.txt"
                with open(prompt_file, "w", encoding="utf-8") as f:
                    f.write(prompt)

                print(f"  [{dim}] Running model...")
                raw_response = ask_ollama(prompt).strip()

                # Save model response under area subdir
                response_record = {
                    "question_id": qid,
                    "area": area,
                    "dimension": dim,
                    "prompt_file": str(prompt_file),
                    "response_text": raw_response,
                    "model": MODEL,
                }

                response_file = responses_area_dir / f"{qid}-{dim.title()}.json"
                with open(response_file, "w", encoding="utf-8") as f:
                    json.dump(response_record, f, ensure_ascii=False, indent=2)

                print(f"    -> Saved: {response_file.name}")
                total_runs += 1

    print("\nAll playbook questions processed successfully.")
    print(f"Framework stored at: {FRAMEWORK_FILE.resolve()}")
    print(f"Prompts root: {PROMPTS_DIR.resolve()}")
    print(f"Responses root: {RESPONSES_DIR.resolve()}")
    print(f"Total (question × dimensions) runs: {total_runs}")
