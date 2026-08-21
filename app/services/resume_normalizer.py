import re
import unicodedata
from typing import Dict, List


class ResumeNormalizer:
    """
    Normalizes raw extracted resume text:
    - Unicode normalization (NFC)
    - Removes zero-width characters and control codes
    - Standardizes headers and whitespace
    - Segment text into candidate section blocks (Summary, Skills, Experience, Education, Projects, Certifications)
    """

    SECTION_PATTERNS = {
        "summary": r"(?:summary|objective|profile|about\s+me)",
        "skills": r"(?:skills|technical\s+skills|core\0competencies|technologies|expertise)",
        "experience": r"(?:work\s+experience|professional\s+experience|employment\s+history|experience)",
        "education": r"(?:education|academic\s+background|qualifications)",
        "projects": r"(?:projects|key\s+projects|featured\s+projects)",
        "certifications": r"(?:certifications|certificates|licenses)"
    }

    @classmethod
    def normalize_text(cls, raw_text: str) -> str:
        """Cleans and standardizes raw text."""
        if not raw_text:
            return ""

        # Unicode normalize
        normalized = unicodedata.normalize("NFKD", raw_text)

        # Remove control characters except newline and tab
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", normalized)

        # Replace 3 or more consecutive newlines with double newline
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # Remove trailing spaces on lines
        lines = [line.strip() for line in cleaned.splitlines()]
        return "\n".join(lines).strip()

    @classmethod
    def extract_sections(cls, text: str) -> Dict[str, str]:
        """Segments resume text into key sections based on regex header patterns."""
        normalized = cls.normalize_text(text)
        lines = normalized.splitlines()
        
        sections: Dict[str, List[str]] = {
            "header": [],
            "summary": [],
            "skills": [],
            "experience": [],
            "education": [],
            "projects": [],
            "certifications": [],
            "other": []
        }

        current_section = "header"

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check if line matches a known section header
            matched_header = False
            if len(line_str) < 50:  # Section headers are usually short
                for section_key, pattern in cls.SECTION_PATTERNS.items():
                    if re.search(r"^\s*" + pattern + r"\s*:?\s*$", line_str, re.IGNORECASE):
                        current_section = section_key
                        matched_header = True
                        break

            if not matched_header:
                sections[current_section].append(line_str)

        # Join line arrays into strings
        return {key: "\n".join(val) for key, val in sections.items() if val}
