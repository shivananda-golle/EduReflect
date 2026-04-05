import requests
from typing import List, Dict
from app.utils.config import HF_API_TOKEN, GENERATOR_MODEL, REQUEST_TIMEOUT

HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {HF_API_TOKEN}",
    "Content-Type": "application/json"
}


def generate_chat_summary(messages: List[Dict[str, str]]) -> str:
    """
    Generate a concise summary of a chat conversation.
    """
    # Format conversation for summary
    conversation = "\n".join([
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
        for m in messages
    ])
    
    system_prompt = "You are a helpful assistant that creates concise summaries of educational conversations."
    
    user_prompt = f"""Please provide a brief 2-3 sentence summary of this educational conversation. 
Focus on the main topic discussed and key learning points.

Conversation:
{conversation}

Summary:"""

    payload = {
        "model": GENERATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 150,
        "temperature": 0.3
    }

    try:
        response = requests.post(HF_CHAT_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Summary generation failed: {str(e)}"