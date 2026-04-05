import wikipedia
import re
from pathlib import Path

OUTPUT_DIR = Path("data/raw/wikipedia")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TOPICS = [
    # Core Science (what you want)
    "Physics",
    "Chemistry",
    "Biology",
    "Energy",
    "Force",

    # Physics details
    "Newton's laws of motion",
    "Classical mechanics",
    "Thermodynamics",
    "Electromagnetism",
    "Quantum mechanics",

    # Mathematics
    "Calculus",
    "Linear algebra",
    "Probability theory",
    "Differential equations",

    # General knowledge
    "Scientific method",
    "Solar System",
    "History of science",
    "Earth",
]

def clean_text(text: str) -> str:
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"\[[0-9]+\]", "", text)
    return text.strip()

def fetch_page(topic: str):
    try:
        # Search first (THIS IS THE FIX)
        results = wikipedia.search(topic)
        if not results:
            raise Exception("No search results")

        page = wikipedia.page(results[0], auto_suggest=False)
        return page.content

    except wikipedia.DisambiguationError as e:
        page = wikipedia.page(e.options[0], auto_suggest=False)
        return page.content

    except Exception as e:
        print(f"❌ Failed: {topic} ({e})")
        return None

for topic in TOPICS:
    content = fetch_page(topic)

    if content:
        content = clean_text(content)
        filename = topic.lower().replace(" ", "_") + ".txt"
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")
        print(f"✅ Saved: {topic}")
