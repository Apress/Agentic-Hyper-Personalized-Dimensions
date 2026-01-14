import json
import requests
from pathlib import Path

QUESTIONS = [
    "In the context of modern healthcare, should AI systems be allowed to make medical diagnoses alongside human doctors? Consider accuracy, patient trust, liability, and the role of human oversight.",
    "Should governments impose a carbon tax on all businesses as a strategy to combat climate change? Discuss economic impact, fairness, risks of unintended consequences, and long-term benefits.",
    "Should a global company transition permanently to a remote-first workplace model? Explore implications for productivity, culture, innovation, employee well-being, and global competitiveness.",
    "How should a large retailer ethically monetise customer behaviour data? Address privacy regulations, trust, risks, opportunities, and potential innovative approaches to value creation.",
    "Should humanity invest heavily in colonising Mars within this century? Evaluate feasibility, risks, costs, societal inspiration, and alternative ways of ensuring humanity’s long-term survival.",
    "Should countries introduce a universal basic income (UBI) for all citizens? Discuss financial feasibility, social impact, risks of dependency, potential benefits, and innovative funding models.",
    "How would you monetise dark data (unknown data without current practical use in business processes)? Consider risks, potential opportunities, ethical implications, and creative approaches.",
]

MODEL = "gemma3:1b"
OLLAMA_URL = "http://localhost:11434"

PERSONALITIES = {
    "DEFAULT": "",
    "WHITE": """
You are the white dimension agent. 
You are a factual-intelligence agent. 
You gather and present verified information, flag knowledge gaps, quantify uncertainties, and maintain clear
   distinctions between confirmed data and conjecture—ensuring all reasoning is grounded in evidence and precision.
""",
    "RED": """
You are the red dimension agent.
Your sole purpose is to surface immediate feelings, intuitions, hunches, and gut reactions—your own and those you can
   reasonably anticipate in others. 
These inputs are legitimate without justification: do not provide reasons, data, arguments, or analysis.
Keep it fast, direct, and emotionally transparent.
""",
    "BLACK": """
You are the black dimension agent.
You embody cautious, critical thinking.
Your role is to anticipate potential risks, obstacles, flaws, and consequences in any proposal, plan, or idea.
Your thinking is deliberate and structured—not dismissive—and aims to make decisions resilient, realistic, and sustainable.
""",
    "YELLOW": """
You are the yellow dimension agent.    
You are an opportunity-driven evaluation agent.
You uncover and build upon benefits, envision value, and present grounded positive possibilities—always anchored in reason and plausibility.    
""",
    "GREEN": """
You are the green dimension agent.    
You are an innovation-focused idea generator.
You thrive on breaking mental patterns, exploring radical and diverse alternatives, and using playful provocations to
   spark breakthroughs—knowing practical refinement comes later.    
""",
    "BLUE": """
You are the blue dimension agent.
You are a metacognitive facilitator.
You manage the thinking process—setting goals, structuring sessions, monitoring flow, summarizing insights, and
   ensuring each thinking mode is used effectively and in turn.    
""",
}

def ask(personality: str, question: str) -> str:
    r = requests.post(
        url=f"{OLLAMA_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": f"{personality}\n\nAnswer the following question within a one page result: {question}\n",
            "stream": False,
        },
        timeout=120,
    )
    try:
        return r.json().get("response", "No response or error code received.")
    except Exception:
        return f"Error: Non-JSON response ({r.status_code}). Text: {r.text[:400]}"

if __name__ == "__main__":
    out_dir = Path("../responses")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect once
    answers_by_question = {i + 1: {} for i in range(len(QUESTIONS))}
    print("Collecting LLM outputs...")
    for q_idx, question in enumerate(QUESTIONS, start=1):
        for dimension, persona in PERSONALITIES.items():
            print(f"[Q{q_idx:02}] {dimension}")
            answers_by_question[q_idx][dimension] = ask(persona, question).strip()

    # Write one JSON per (question × dimension)
    print("Writing single (question×dimension) JSON files...")
    for q_idx, question in enumerate(QUESTIONS, start=1):
        for dimension in PERSONALITIES.keys():
            record = {
                "question_id": q_idx,
                "question": question,
                "dimension": dimension,
                "answer": answers_by_question[q_idx].get(dimension, ""),
                "model": MODEL,
            }
            filename = out_dir / f"Q{q_idx:02}-{dimension}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            print(f"  -> {filename.name}")

    print("Done.")
