import requests

MODEL = "gemma3:1b"
OLLAMA_URL = "http://127.0.0.1:11434"


def ask(question):
    r = requests.post(url=f"{OLLAMA_URL}/api/generate",
                      json={"model": MODEL, "prompt": question, "stream": False},
                     )
    return r.json().get("response", "No response or error code received.")


# Examples
if __name__ == "__main__":
    print(f"'{MODEL}' answer:", ask("What AI agent are you?"))
