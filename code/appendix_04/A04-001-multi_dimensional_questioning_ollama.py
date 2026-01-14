import json
import re
import requests
from pathlib import Path

MODEL = "gemma3:1b"
OLLAMA_URL = "http://localhost:11434"
QUESTIONS_FILE = Path("./questions.json")
PERSONALITIES_FILE = Path("./personalities.json")

PROMPTS_DIR = Path("./prompts")
RESPONSES_DIR = Path("./responses")


def load_json_file(filepath: Path) -> dict:
    """Load JSON file and return its contents."""
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


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


if __name__ == "__main__":
    schema = load_json_file(QUESTIONS_FILE)
    personalities = load_json_file(PERSONALITIES_FILE)

    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

    qid = schema["evaluation_question"]["id"]
    print("Building prompts and collecting LLM responses...")

    for dim, persona in personalities.items():
        prompt = build_prompt(schema, dim, persona)

        # Save prompt to file
        prompt_file = PROMPTS_DIR / f"{qid}-{dim.title()}.prompt.txt"
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        print(f"[{dim}] Running model...")
        raw_response = ask_ollama(prompt).strip()

        # Save model response
        response_record = {
            "question_id": qid,
            "dimension": dim,
            "prompt_file": str(prompt_file),
            "response_text": raw_response,
            "model": MODEL,
        }

        response_file = RESPONSES_DIR / f"{qid}-{dim.title()}.json"
        with open(response_file, "w", encoding="utf-8") as f:
            json.dump(response_record, f, ensure_ascii=False, indent=2)

        print(f"  -> Saved: {response_file.name}")

    print("\nAll dimensions processed successfully.")
    print(f"Prompts stored in: {PROMPTS_DIR.resolve()}")
    print(f"Responses stored in: {RESPONSES_DIR.resolve()}")
