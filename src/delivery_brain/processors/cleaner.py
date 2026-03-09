"""
Text Cleaner for Delivery Brain

Provides text cleaning and normalization functions.
License-compliant dependencies:
- ftfy (Apache-2.0) for encoding fixes
- Standard library re, unicodedata
"""

import re
import unicodedata
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class TextCleaner:
    """Text cleaning and normalization utility"""

    # Common patterns
    URL_PATTERN = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\-.?=&#%]*'
    )
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )
    PHONE_PATTERN = re.compile(
        r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'
    )
    MULTIPLE_SPACES = re.compile(r' +')
    MULTIPLE_NEWLINES = re.compile(r'\n{3,}')
    CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

    def __init__(self,
                 remove_extra_whitespace: bool = True,
                 fix_encoding: bool = True,
                 remove_special_chars: bool = False,
                 lowercase: bool = False,
                 remove_urls: bool = False,
                 remove_emails: bool = False,
                 remove_phone_numbers: bool = False,
                 normalize_unicode: bool = True,
                 remove_control_chars: bool = True,
                 min_line_length: int = 0):
        """
        Initialize text cleaner.

        Args:
            remove_extra_whitespace: Collapse multiple spaces/newlines
            fix_encoding: Fix mojibake and encoding issues
            remove_special_chars: Remove non-alphanumeric characters
            lowercase: Convert to lowercase
            remove_urls: Remove URLs
            remove_emails: Remove email addresses
            remove_phone_numbers: Remove phone numbers
            normalize_unicode: Normalize Unicode characters
            remove_control_chars: Remove control characters
            min_line_length: Minimum characters per line to keep
        """
        self.remove_extra_whitespace = remove_extra_whitespace
        self.fix_encoding = fix_encoding
        self.remove_special_chars = remove_special_chars
        self.lowercase = lowercase
        self.remove_urls = remove_urls
        self.remove_emails = remove_emails
        self.remove_phone_numbers = remove_phone_numbers
        self.normalize_unicode = normalize_unicode
        self.remove_control_chars = remove_control_chars
        self.min_line_length = min_line_length

        self._ftfy_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check for optional dependencies"""
        try:
            import ftfy
            self._ftfy_available = True
        except ImportError:
            logger.debug("ftfy not available - encoding fixes limited")

    def clean(self, text: str) -> str:
        """
        Clean and normalize text.

        Args:
            text: Input text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Fix encoding issues first
        if self.fix_encoding:
            text = self._fix_encoding(text)

        # Remove control characters
        if self.remove_control_chars:
            text = self.CONTROL_CHARS.sub('', text)

        # Normalize Unicode
        if self.normalize_unicode:
            text = unicodedata.normalize('NFKC', text)

        # Remove URLs
        if self.remove_urls:
            text = self.URL_PATTERN.sub('[URL]', text)

        # Remove emails
        if self.remove_emails:
            text = self.EMAIL_PATTERN.sub('[EMAIL]', text)

        # Remove phone numbers
        if self.remove_phone_numbers:
            text = self.PHONE_PATTERN.sub('[PHONE]', text)

        # Remove special characters
        if self.remove_special_chars:
            text = self._remove_special_chars(text)

        # Clean whitespace
        if self.remove_extra_whitespace:
            text = self._clean_whitespace(text)

        # Filter short lines
        if self.min_line_length > 0:
            text = self._filter_short_lines(text)

        # Lowercase
        if self.lowercase:
            text = text.lower()

        return text.strip()

    def _fix_encoding(self, text: str) -> str:
        """Fix encoding issues (mojibake)"""
        if self._ftfy_available:
            import ftfy
            return ftfy.fix_text(text)

        # Fallback: basic fixes
        replacements = {
            'â€™': "'",
            'â€œ': '"',
            'â€': '"',
            'â€"': '—',
            'â€"': '–',
            'Ã©': 'é',
            'Ã¨': 'è',
            'Ã ': 'à',
            'Ã¢': 'â',
            'Ã®': 'î',
            'Ã´': 'ô',
            'Ã»': 'û',
            'Ã§': 'ç',
            '\ufeff': '',  # BOM
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        return text

    def _remove_special_chars(self, text: str) -> str:
        """Remove special characters, keeping alphanumeric and basic punctuation"""
        # Keep letters, numbers, spaces, and basic punctuation
        cleaned = re.sub(r'[^\w\s.,!?;:\'"()\-–—/\\@#$%&*+=<>\[\]{}]', '', text)
        return cleaned

    def _clean_whitespace(self, text: str) -> str:
        """Clean up whitespace"""
        # Replace tabs with spaces
        text = text.replace('\t', ' ')

        # Collapse multiple spaces
        text = self.MULTIPLE_SPACES.sub(' ', text)

        # Collapse multiple newlines (keep max 2)
        text = self.MULTIPLE_NEWLINES.sub('\n\n', text)

        # Strip whitespace from each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text

    def _filter_short_lines(self, text: str) -> str:
        """Filter out short lines"""
        lines = text.split('\n')
        filtered = [
            line for line in lines
            if len(line.strip()) >= self.min_line_length or not line.strip()
        ]
        return '\n'.join(filtered)

    def clean_for_embedding(self, text: str) -> str:
        """
        Clean text specifically for embedding.
        More aggressive cleaning for vector similarity.
        """
        # Start with basic cleaning
        text = self.clean(text)

        # Additional cleaning for embeddings
        # Remove excessive punctuation
        text = re.sub(r'[.!?]{2,}', '.', text)

        # Remove bullet points and list markers
        text = re.sub(r'^[\s]*[-*•→►▸]\s*', '', text, flags=re.MULTILINE)

        # Remove section markers
        text = re.sub(r'\[.*?\]', '', text)

        # Normalize dashes
        text = re.sub(r'[–—]', '-', text)

        return text.strip()

    def extract_sentences(self, text: str) -> List[str]:
        """
        Extract sentences from text.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Simple sentence splitting
        # For more accurate splitting, use nltk or spacy
        text = self.clean(text)

        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def detect_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the text.

        Returns language code (e.g., 'en', 'es', 'fr') or None
        """
        try:
            from langdetect import detect, LangDetectException
            # Use first 1000 chars for detection
            sample = text[:1000] if len(text) > 1000 else text
            return detect(sample)
        except ImportError:
            logger.debug("langdetect not available")
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")

        return None


# Convenience functions
def clean_text(text: str, **kwargs) -> str:
    """Clean text with default settings"""
    cleaner = TextCleaner(**kwargs)
    return cleaner.clean(text)


def clean_for_embedding(text: str) -> str:
    """Clean text for embedding"""
    cleaner = TextCleaner()
    return cleaner.clean_for_embedding(text)
