import os
import PyPDF2
from docx import Document
from typing import Dict, Any
from app.services.generator import generate_answer
from app.services.usage_limits import LimitExceeded

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text

def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    doc = Document(file_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def process_document(file_path: str, question: str = "") -> Dict[str, Any]:
    """Process uploaded document and optionally answer questions about it"""
    
    # Extract text based on file type
    if file_path.lower().endswith('.pdf'):
        full_text = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.docx'):
        full_text = extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file type")
    
    # Generate summary
    summary_prompt = f"Please provide a concise 2-3 sentence summary of the following document:\n\n{full_text[:4000]}..."
    
    try:
        summary = generate_answer(summary_prompt, [], answer_format="brief")[0]
    except LimitExceeded:
        raise
    except Exception:
        summary = f"Document processed successfully. Length: {len(full_text)} characters."
    
    result = {"summary": summary, "full_text": full_text}
    
    # If question is provided, answer it using document content
    if question:
        documents = [full_text[:4000]]
        try:
            answer = generate_answer(question, documents, answer_format="brief")[0]
            result["answer"] = answer
        except LimitExceeded:
            raise
        except Exception:
            result["answer"] = "Unable to generate answer from document."
    
    return result