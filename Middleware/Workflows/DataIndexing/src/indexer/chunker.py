"""L1 — chunk text the way the video does: recursive split, 500 tokens,
100 tokens overlap.

"Tokens" here are approximated with a word count scaled to the
cl100k_base rough ratio only for sizing display; the split itself works
on characters (target 500 * ~4 chars per token = 2000 chars, overlap
400 chars), which keeps this module dependency-free and deterministic.
The 500/100 numbers match the video's RecursiveCharacterTextSplitter
settings (chunk_size=500, chunk_overlap=100, encoding cl100k_base).
"""

import re

CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 100
_CHARS_PER_TOKEN = 4

CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * _CHARS_PER_TOKEN       # 2000
CHUNK_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * _CHARS_PER_TOKEN  # 400

# Split order: blank line, line break, sentence end, word, character —
# the same preference order as LangChain's RecursiveCharacterTextSplitter.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_on(text, sep):
    if sep == "":
        return list(text)
    return text.split(sep)


def split_text(text, chunk_size=CHUNK_SIZE_CHARS, overlap=CHUNK_OVERLAP_CHARS):
    """Split `text` into overlapping chunks. Returns a list of strings;
    every chunk is <= chunk_size chars (except a single over-long word),
    and consecutive chunks overlap by ~`overlap` chars."""
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Prefer a clean break: last separator at/before `end`.
            cut = -1
            for sep in _SEPARATORS[:-1]:
                idx = text.rfind(sep, start, end)
                if idx > start:
                    cut = idx + len(sep)
                    break
            if cut > start:
                end = cut
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
        # Align the new chunk start to a word boundary. The overlap
        # start can land mid-word, which would split that word across
        # chunks — its tail then appears as a bogus word in the next
        # chunk (e.g. "word1011" -> "011"). Advance to the next
        # whitespace inside the overlap window. The straddled word is
        # fully present in the previous chunk, so nothing is lost.
        # If the window has no whitespace (one giant word), keep the
        # start as-is.
        if start < end:
            m = re.search(r"\s", text[start:end])
            if m:
                start = start + m.start() + 1
    return [c for c in chunks if c]


def approx_tokens(text):
    """Rough token estimate (words * 1.3, cl100k_base ballpark)."""
    return int(len(re.findall(r"\S+", text)) * 1.3)
