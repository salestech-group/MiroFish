"""Text processing service."""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """Facade for the text-extraction and chunking pipeline."""

    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Extract and concatenate text from multiple files."""
        return FileParser.extract_from_multiple(file_paths)

    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """Split text into chunks.

        Args:
            text: The source text.
            chunk_size: Target characters per chunk.
            overlap: Overlap between consecutive chunks.

        Returns:
            A list of chunk strings.
        """
        return split_text_into_chunks(text, chunk_size, overlap)

    @staticmethod
    def preprocess_text(text: str) -> str:
        """Pre-process text by normalizing whitespace and line endings.

        - Collapse runs of blank lines to at most two newlines.
        - Normalize line endings to ``\\n``.
        - Strip leading/trailing whitespace from each line.

        Args:
            text: The source text.

        Returns:
            The cleaned text.
        """
        import re

        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Collapse 3+ consecutive newlines down to a blank-line separator.
        text = re.sub(r'\n{3,}', '\n\n', text)

        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Return basic text statistics: total chars, lines, and words."""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }

