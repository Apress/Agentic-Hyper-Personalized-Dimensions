#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Merge multi-dimension answers for a specific question gathered from singles/*.json
into a single, resolved group response using an integrator LLM.

Outputs:
  - group/Group-Question-01.json
  - group/Group-Question-01.md
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ----------------------------
# Config (match your environment)
# ----------------------------
MODEL = "gemma3:1b"
OLLAMA_URL = "http://localhost:11434"
PERSONALITIES_ORDER = ["WHITE", "BLACK", "RED", "YELLOW", "GREEN", "BLUE"]

# ----------------------------
# Integrator persona
# ----------------------------
INTEGRATOR_PERSONA = """
You are the BLUE dimension integrator for a multi-dimension review (WHITE facts, BLACK risks, RED emotions, YELLOW benefits, GREEN ideas, BLUE process).
Your task:
1) Evaluate each dimension's answer to determine the best (most accurate, detailed and informative) response.
2) Produce a consolidated GROUP RESPONSE takes the best of each dimension and combines it into a single cohesive answer.
3) Strictly limit the reponse to the task

""".strip()



# Prompt size guards (keep local models stable)
MAX_ANSWER_CHARS_PER_BLOCK = 6000
MAX_TOTAL_CONTEXT = 32000

# ----------------------------
# HTTP plumbing (same ask() pattern)
# ----------------------------
import requests

def ask(personality: str, question: str) -> str:
    r = requests.post(
        url=f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL, "prompt": f"{personality}\n\n{question}\n", "stream": False},
        timeout=180,
    )
    return r.json().get("response", "No response or error code received.")


# ----------------------------
# I/O helpers
# ----------------------------
def load_singles_for_q(singles_dir: Path, qid: int) -> Dict:
    """
    Aggregate singles/QXX-*.json for the given question_id into:
      {"question_id": qid, "question": "...", "answers": {DIM: text, ...}, "model": "..."}
    """
    answers: Dict[str, str] = {}
    question_texts: List[str] = []
    models: List[str] = []

    for p in sorted(singles_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(data.get("question_id", -1)) != qid:
            continue
        dim = str(data.get("dimension", "")).upper().strip()
        ans = str(data.get("answer", "")).strip()
        if not dim or not ans:
            continue
        answers[dim] = ans
        question_texts.append(str(data.get("question", "")).strip())
        if "model" in data:
            models.append(str(data["model"]))

    if not answers:
        return {}

    # Choose the most common question text (in case of minor variations)
    question_text = max(set(question_texts), key=question_texts.count) if question_texts else ""
    model = models[0] if models else MODEL

    return {"question_id": qid, "question": question_text, "answers": answers, "model": model}

def truncate(text: str, cap: int) -> str:
    text = text.strip()
    return text if len(text) <= cap else text[:cap] + " …[truncated]"

def build_integrator_prompt(question_text: str, answers_by_dim: Dict[str, str]) -> str:
    # Order dimensions for readability
    dims = [d for d in PERSONALITIES_ORDER if d in answers_by_dim] + \
           [d for d in answers_by_dim.keys() if d not in PERSONALITIES_ORDER]

    blocks = []
    budget = MAX_TOTAL_CONTEXT
    header = f"Question:\n\"\"\"{question_text.strip()}\"\"\"\n\n"
    blocks.append(header)
    budget -= len(header)

    for d in dims:
        seg = f"--- {d} ---\n{truncate(answers_by_dim[d], MAX_ANSWER_CHARS_PER_BLOCK)}\n\n"
        take = seg if len(seg) <= budget else seg[:max(0, budget)]
        blocks.append(take)
        budget -= len(take)
        if budget <= 0:
            break

    return "".join(blocks)

# ----------------------------
# Main
# ----------------------------
def combine_question(qid):
    answers_dir = Path("../answers")
    out_dir = Path("../group")
    out_dir.mkdir(parents=True, exist_ok=True)

    rec = load_singles_for_q(answers_dir, qid)
    if not rec:
        print(f"No singles found for question_id={qid} in {answers_dir}")
        sys.exit(2)

    qid = rec["question_id"]
    question_text = rec["question"]
    answers_by_dim = rec["answers"]

    if not answers_by_dim:
        print("No dimension answers found for the specified question.")
        sys.exit(3)

    # Build prompt and query LLM integrator
    prompt = build_integrator_prompt(question_text, answers_by_dim)
    data = ask(INTEGRATOR_PERSONA, prompt)

    # Prepare outputs
    base_name = f"Group-Question-{qid:02d}"
    json_file = out_dir / f"{base_name}.json"
    md_file = out_dir / f"{base_name}.md"

    # Enrich JSON with context and model used
    result = {
        "question_id": qid,
        "question": question_text,
        "dimensions_present": sorted(answers_by_dim.keys()),
        "model": MODEL,
        "answer": data
    }
    json_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {json_file}")

    md_file.write_text(data)
    print(f"Wrote: {md_file}")

if __name__ == "__main__":
    for qid in range(1,8):
        combine_question(qid)
