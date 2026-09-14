import json
import re

from app.services import llm_client
from app.services.usage_limits import LimitExceeded

def generate_quiz(context: str, num_questions: int = 5):
    system_prompt = (
        "You are an educational assistant. Your task is to generate a quiz to test the user's understanding of the provided text. "
        "Return the output strictly in JSON format."
    )
    
    user_prompt = f"""
Based on the following content, generate {num_questions} multiple-choice questions to test the user's understanding.
The questions should vary in difficulty (easy, medium, hard).

Content:
{context[:2000]}

Output Format (JSON Array):
[
  {{
    "question": "Question text here",
    "options": ["First option text", "Second option text", "Third option text", "Fourth option text"],
    "correct_answer": "First option text",
    "explanation": "Why this answer is correct",
    "difficulty": "medium"
  }}
]

IMPORTANT: 
- The "correct_answer" field MUST contain the EXACT FULL TEXT of the correct option, NOT a letter like "A", "B", "C", or "D".
- The correct_answer must exactly match one of the options in the options array.
- Ensure the output is valid JSON. Do not include markdown formatting like ```json.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        content = llm_client.chat(messages, max_tokens=1500, temperature=0.5)

        # Clean up potential markdown formatting
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        content = content.strip()
        
        try:
            quiz_data = _loads_lenient(content)
            # Validate structure
            if isinstance(quiz_data, list):
                questions = quiz_data
            elif isinstance(quiz_data, dict) and "questions" in quiz_data:
                questions = quiz_data["questions"]
            else:
                return []
            
            # Post-process: Fix letter-based answers (A, B, C, D) to actual option text
            questions = fix_letter_based_answers(questions)
            return questions
            
        except json.JSONDecodeError:
            # Fallback: try to find JSON array in text
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                questions = _loads_lenient(match.group(0))
                questions = fix_letter_based_answers(questions)
                return questions
            return []

    except LimitExceeded:
        raise
    except Exception as e:
        print(f"Error generating quiz: {e}")
        return []


def _loads_lenient(text: str):
    """
    Parse model JSON. Math answers often contain LaTeX (e.g. \\sqrt) whose backslashes are invalid
    JSON escapes; on failure, escape backslashes that don't start a valid escape and retry.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(re.sub(r'\\(?![\\"/u])', r'\\\\', text))


def fix_letter_based_answers(questions: list) -> list:
    """
    Fix questions where correct_answer is a letter (A, B, C, D) instead of actual option text.
    Also handles cases like "B molecules are..." where the answer starts with a letter.
    """
    letter_to_index = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'a': 0, 'b': 1, 'c': 2, 'd': 3}
    
    for question in questions:
        correct_answer = question.get("correct_answer", "").strip()
        options = question.get("options", [])
        
        if not options:
            continue
        
        # First check: if the answer exactly matches one of the options, it's good
        if correct_answer in options:
            continue
        
        # Case-insensitive match
        answer_lower = correct_answer.lower()
        matched = False
        for opt in options:
            if opt.lower() == answer_lower:
                question["correct_answer"] = opt
                matched = True
                break
        
        if matched:
            continue
        
        # Check if correct_answer is a single letter (A, B, C, D)
        if correct_answer.upper() in ['A', 'B', 'C', 'D']:
            index = letter_to_index.get(correct_answer, 0)
            if index < len(options):
                question["correct_answer"] = options[index]
            continue
        
        # Handle "Option A", "Option B" format
        if correct_answer.lower().startswith("option "):
            letter = correct_answer[-1].upper()
            if letter in letter_to_index:
                index = letter_to_index[letter]
                if index < len(options):
                    question["correct_answer"] = options[index]
            continue
        
        # Handle answers starting with letter like "B molecules are..." or "C photosynthesis..."
        # Pattern: Single letter followed by space and text
        if len(correct_answer) > 2 and correct_answer[0].upper() in ['A', 'B', 'C', 'D'] and correct_answer[1] == ' ':
            letter = correct_answer[0].upper()
            index = letter_to_index[letter]
            if index < len(options):
                question["correct_answer"] = options[index]
            continue
        
        # Last resort: Find best matching option by checking if answer contains option text
        for i, opt in enumerate(options):
            if opt.lower() in answer_lower or answer_lower in opt.lower():
                question["correct_answer"] = opt
                break
    
    return questions
