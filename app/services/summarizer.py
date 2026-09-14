from typing import List, Dict

from app.services import llm_client
from app.services.usage_limits import LimitExceeded


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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        return llm_client.chat(messages, max_tokens=150, temperature=0.3)
    except LimitExceeded:
        raise
    except Exception as e:
        return f"Summary generation failed: {str(e)}"