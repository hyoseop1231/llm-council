"""
Prompt Optimizer for LLM Council.
Inspired by prompt-refiner, implements cleaning, compression, and context management.
"""

import re
import html
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser


class HTMLStripper(HTMLParser):
    """Strip HTML tags from text."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, data):
        self.fed.append(data)

    def get_text(self):
        return ''.join(self.fed)


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return text

    # Decode HTML entities first
    text = html.unescape(text)

    # Strip HTML tags
    stripper = HTMLStripper()
    try:
        stripper.feed(text)
        return stripper.get_text()
    except Exception:
        # Fallback: simple regex strip
        return re.sub(r'<[^>]+>', '', text)


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace: collapse multiple spaces, trim lines."""
    if not text:
        return text

    # Replace multiple spaces/tabs with single space
    text = re.sub(r'[ \t]+', ' ', text)

    # Replace multiple newlines with double newline (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


def clean_unicode(text: str) -> str:
    """Remove problematic unicode characters."""
    if not text:
        return text

    # Remove zero-width characters
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)

    # Remove other invisible characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return text


def remove_empty_json_fields(text: str) -> str:
    """Remove empty JSON-like patterns from text."""
    if not text:
        return text

    # Remove patterns like "field": "", "field": null, "field": []
    text = re.sub(r'"[^"]+"\s*:\s*""[,\s]*', '', text)
    text = re.sub(r'"[^"]+"\s*:\s*null[,\s]*', '', text)
    text = re.sub(r'"[^"]+"\s*:\s*\[\s*\][,\s]*', '', text)
    text = re.sub(r'"[^"]+"\s*:\s*\{\s*\}[,\s]*', '', text)

    return text


def clean_text(text: str) -> str:
    """
    Apply all cleaning operations to text.
    Pipeline: HTML strip -> Unicode clean -> Empty JSON -> Whitespace normalize
    """
    if not text:
        return text

    text = strip_html(text)
    text = clean_unicode(text)
    text = remove_empty_json_fields(text)
    text = normalize_whitespace(text)

    return text


def deduplicate_sentences(text: str, similarity_threshold: float = 0.9) -> str:
    """
    Remove duplicate or near-duplicate sentences.
    Uses simple exact match for now (can be enhanced with fuzzy matching).
    """
    if not text:
        return text

    sentences = re.split(r'(?<=[.!?])\s+', text)
    seen = set()
    unique_sentences = []

    for sentence in sentences:
        # Normalize for comparison
        normalized = sentence.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_sentences.append(sentence)

    return ' '.join(unique_sentences)


def truncate_with_sentence_boundary(text: str, max_chars: int, preserve_end: bool = False) -> str:
    """
    Truncate text at sentence boundary to avoid cutting mid-sentence.

    Args:
        text: Text to truncate
        max_chars: Maximum characters allowed
        preserve_end: If True, keep the end of text instead of beginning
    """
    if not text or len(text) <= max_chars:
        return text

    if preserve_end:
        # Take from the end
        truncated = text[-max_chars:]
        # Find first sentence boundary
        match = re.search(r'[.!?]\s+', truncated)
        if match:
            return truncated[match.end():]
        return truncated
    else:
        # Take from the beginning
        truncated = text[:max_chars]
        # Find last sentence boundary
        match = re.search(r'[.!?]\s+(?=[A-Z])', truncated[::-1])
        if match:
            return truncated[:-(match.start())]
        # Fallback: find last period
        last_period = truncated.rfind('.')
        if last_period > max_chars * 0.5:  # At least half the content
            return truncated[:last_period + 1]
        return truncated + '...'


def compress_text(text: str, max_chars: Optional[int] = None, deduplicate: bool = True) -> str:
    """
    Compress text by cleaning and optionally truncating.

    Args:
        text: Text to compress
        max_chars: Optional maximum character limit
        deduplicate: Whether to remove duplicate sentences
    """
    if not text:
        return text

    # Clean first
    text = clean_text(text)

    # Deduplicate if requested
    if deduplicate:
        text = deduplicate_sentences(text)

    # Truncate if needed
    if max_chars and len(text) > max_chars:
        text = truncate_with_sentence_boundary(text, max_chars)

    return text


def optimize_search_results(search_results: str, max_chars: int = 8000) -> str:
    """
    Optimize Stage 0 search results for council consumption.
    Preserves key information while reducing token count.
    """
    if not search_results:
        return search_results

    # Clean and compress
    optimized = compress_text(search_results, max_chars=max_chars, deduplicate=True)

    return optimized


def optimize_file_content(content: str, filename: str, max_chars: int = 10000) -> str:
    """
    Optimize uploaded file content.
    Different strategies based on file type.
    """
    if not content:
        return content

    # Determine file type
    ext = filename.lower().split('.')[-1] if '.' in filename else ''

    if ext == 'pdf':
        # PDFs often have extraction artifacts
        content = clean_text(content)
        # Remove page markers
        content = re.sub(r'\n*Page \d+ of \d+\n*', '\n', content)
        content = re.sub(r'\n*-\s*\d+\s*-\n*', '\n', content)

    elif ext in ['html', 'htm']:
        content = strip_html(content)
        content = clean_text(content)

    elif ext == 'json':
        content = remove_empty_json_fields(content)
        content = normalize_whitespace(content)

    else:
        # Generic text file
        content = clean_text(content)

    # Truncate if too long
    if len(content) > max_chars:
        content = truncate_with_sentence_boundary(content, max_chars)

    return content


def optimize_conversation_history(
    history: List[Dict[str, str]],
    max_messages: int = 10,
    max_chars_per_message: int = 2000
) -> List[Dict[str, str]]:
    """
    Optimize conversation history to fit within context limits.

    Strategy:
    - Keep most recent messages
    - Truncate very long messages
    - Always preserve the last user message in full
    """
    if not history:
        return history

    # Keep only recent messages
    if len(history) > max_messages:
        history = history[-max_messages:]

    optimized = []
    for i, msg in enumerate(history):
        is_last = (i == len(history) - 1)

        content = msg.get('content', '')

        # Don't truncate the last message
        if not is_last and len(content) > max_chars_per_message:
            content = truncate_with_sentence_boundary(content, max_chars_per_message)

        optimized.append({
            'role': msg.get('role', 'user'),
            'content': content
        })

    return optimized


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation (approximately 4 chars per token for English).
    """
    if not text:
        return 0
    return len(text) // 4


def get_optimization_stats(original: str, optimized: str) -> Dict[str, Any]:
    """
    Get statistics about optimization effectiveness.
    """
    original_chars = len(original) if original else 0
    optimized_chars = len(optimized) if optimized else 0

    return {
        'original_chars': original_chars,
        'optimized_chars': optimized_chars,
        'chars_saved': original_chars - optimized_chars,
        'reduction_percent': round((1 - optimized_chars / original_chars) * 100, 1) if original_chars > 0 else 0,
        'estimated_tokens_saved': (original_chars - optimized_chars) // 4
    }
