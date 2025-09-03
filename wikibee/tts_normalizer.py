"""TTS text normalization for Wikipedia articles.

This module provides text normalization to improve TTS pronunciation by converting
written forms to more natural spoken forms. Patterns are based on systematic
analysis of Wikipedia articles across history, computer science, and mathematics.
"""

import re

from num2words import num2words


class TTSNormalizer:
    """Text normalizer for improving TTS pronunciation of Wikipedia content."""

    def __init__(self) -> None:
        """Initialize normalizer with pattern definitions."""
        # Phase 1: High-impact patterns (addresses ~80% of issues)
        self.phase1_patterns = [
            self._normalize_royal_names,
            self._normalize_century_ordinals,
            self._normalize_latin_abbreviations,
        ]

        # Phase 2: Medium-impact patterns
        self.phase2_patterns = [
            self._normalize_decades,
            self._normalize_war_numbering,
        ]

        # All patterns combined
        self.all_patterns = self.phase1_patterns + self.phase2_patterns

    def normalize(self, text: str, phase: str = "all") -> str:
        """Apply TTS normalization patterns to text.

        Args:
            text: Input text to normalize
            phase: Which patterns to apply ("phase1", "phase2", or "all")

        Returns:
            Normalized text with better TTS pronunciation
        """
        if phase == "phase1":
            patterns = self.phase1_patterns
        elif phase == "phase2":
            patterns = self.phase2_patterns
        else:  # "all"
            patterns = self.all_patterns

        # Apply patterns in sequence
        result = text
        for pattern_func in patterns:
            result = pattern_func(result)

        return result

    def _roman_to_int(self, roman: str) -> int:
        """Convert Roman numeral string to integer."""
        # First validate that it's a proper Roman numeral
        if not self._is_valid_roman(roman):
            raise ValueError(f"Invalid Roman numeral: {roman}")

        values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

        total = 0
        prev = 0

        for char in reversed(roman):
            value = values.get(char, 0)
            if value < prev:
                total -= value
            else:
                total += value
            prev = value

        return total

    def _is_valid_roman(self, roman: str) -> bool:
        """Check if Roman numeral is properly formed."""
        # Basic pattern for valid Roman numerals I-L (1-50)
        # This catches common invalid patterns like XIIII, VVIII, IIII
        valid_pattern = r"^M{0,4}(CM|CD|D?C{0,3})(XL|XC|L?X{0,3})(IX|IV|V?I{0,3})$"
        import re

        return bool(re.match(valid_pattern, roman))

    def _normalize_royal_names(self, text: str) -> str:
        """Convert royal/historical names with Roman numerals.

        Examples:
            Richard III → Richard the third
            Louis XVI → Louis the sixteenth
            Napoleon III → Napoleon the third
        """

        from typing import Match

        def replace_royal(match: Match[str]) -> str:
            name = match.group(1)
            roman = match.group(2)

            # Skip certain patterns that aren't royal names
            if name.startswith(("World War", "Section", "Chapter", "Part")):
                return match.group(0)

            try:
                num = self._roman_to_int(roman)
                # Only handle reasonable royal name ranges (I-L, 1-50)
                if num <= 50:
                    ordinal = str(num2words(num, to="ordinal"))
                    return f"{name} the {ordinal}"
                else:
                    return match.group(0)
            except (ValueError, TypeError):
                return match.group(0)  # Return original if conversion fails

        # Pattern: Name + space + Roman numeral (I-L, covers 1-50)
        # More restrictive pattern - typically person names
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+([IVX]+)\b"
        return re.sub(pattern, replace_royal, text)

    def _normalize_century_ordinals(self, text: str) -> str:
        """Convert ordinal numbers to word form.

        Examples:
            19th century → nineteenth century
            3rd Battalion → third Battalion
            2nd World War → second World War
        """

        from typing import Match

        def replace_ordinal(match: Match[str]) -> str:
            num_str = match.group(1)

            try:
                num = int(num_str)
                ordinal = str(num2words(num, to="ordinal"))
                return ordinal
            except (ValueError, TypeError):
                return match.group(0)  # Return original if conversion fails

        # Pattern: number + ordinal suffix (st, nd, rd, th)
        pattern = r"\b(\d+)(st|nd|rd|th)\b"
        return re.sub(pattern, replace_ordinal, text)

    def _normalize_latin_abbreviations(self, text: str) -> str:
        """Convert common Latin abbreviations to spoken form.

        Examples:
            e.g. → for example
            i.e. → that is
            etc. → et cetera
        """
        # Dictionary of abbreviations to expansions
        abbreviations = {
            r"\be\.g\.,": r"for example",  # e.g., → for example (remove comma)
            r"\be\.g\.": r"for example",  # e.g. → for example
            r"\bi\.e\.,": r"that is",  # i.e., → that is (remove comma)
            r"\bi\.e\.": r"that is",  # i.e. → that is
            r"\betc\.": r"et cetera",  # etc. → et cetera
            r"\bc\.\s*(\d{4})": r"circa \1",  # c. 1943 → circa 1943
        }

        result = text
        for pattern, replacement in abbreviations.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result

    def _normalize_decades(self, text: str) -> str:
        """Convert decade references to spoken form.

        Examples:
            1980s → nineteen eighties
            1960s → nineteen sixties
            1830s → eighteen thirties
            1900s → nineteen hundreds
            2000s → the two thousands
        """

        from typing import Match

        def replace_decade(match: Match[str]) -> str:
            year_str = match.group(1)

            try:
                year = int(year_str)
                if year >= 1000:
                    # Split into century and decade parts
                    century = year // 100
                    decade = (year % 100) // 10

                    if decade == 0:
                        # Handle special cases for century decades
                        if year == 2000:
                            return "two thousands"
                        else:
                            # 1800s → eighteen hundreds, 1900s → nineteen hundreds
                            century_word = str(num2words(century))
                            return f"{century_word} hundreds"
                    else:
                        # 1980s → nineteen eighties
                        century_word = str(num2words(century))
                        # Convert decade digit to proper word with -ies ending
                        decade_names = {
                            1: "tens",
                            2: "twenties",
                            3: "thirties",
                            4: "forties",
                            5: "fifties",
                            6: "sixties",
                            7: "seventies",
                            8: "eighties",
                            9: "nineties",
                        }
                        decade_word = decade_names.get(
                            decade, f"{str(num2words(decade * 10))}s"
                        )
                        return f"{century_word} {decade_word}"
                else:
                    # Fallback for years < 1000
                    return f"{str(num2words(year))}s"
            except (ValueError, TypeError):
                return match.group(0)

        # Pattern: 4-digit year + 's'
        pattern = r"\b(\d{4})s\b"
        return re.sub(pattern, replace_decade, text)

    def _normalize_war_numbering(self, text: str) -> str:
        """Convert war numbering to spoken form.

        Examples:
            World War II → World War Two
            World War I → World War One
        """
        # Specific war patterns
        war_patterns = {
            r"\bWorld War II\b": "World War Two",
            r"\bWorld War I\b": "World War One",
            r"\bWWII\b": "World War Two",
            r"\bWWI\b": "World War One",
        }

        result = text
        for pattern, replacement in war_patterns.items():
            result = re.sub(pattern, replacement, result)

        return result


# Convenience function for direct use
def normalize_for_tts(text: str, phase: str = "all") -> str:
    """Normalize text for better TTS pronunciation.

    Args:
        text: Text to normalize
        phase: Which normalization phase to apply

    Returns:
        Normalized text
    """
    normalizer = TTSNormalizer()
    return normalizer.normalize(text, phase)
