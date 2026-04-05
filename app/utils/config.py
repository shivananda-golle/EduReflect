
import os
from dotenv import load_dotenv

load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

# Models
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "meta-llama/Llama-3.2-1B-Instruct")

# Evidence / truncation
MAX_EVIDENCE_CHARS = int(os.getenv("MAX_EVIDENCE_CHARS", "2000"))

# Request timeouts (seconds)
# HF generation + first-time downloads can exceed 30s on some machines/networks.
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "120.0"))