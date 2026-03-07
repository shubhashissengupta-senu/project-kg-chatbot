"""
Tests for document parsers.
"""

import pytest
from pathlib import Path
from datetime import datetime

from src.ingestion.parsers.scrum_parser import ScrumMeetingParser
from src.ingestion.parsers.client_review_parser import ClientReviewParser
from src.ingestion.parsers.base_parser import BaseParser


class TestScrumParser:
    """Tests for ScrumMeetingParser"""

    def test_can_parse_scrum_file(self):
        """Test file type detection"""
        parser = ScrumMeetingParser()

        assert parser.can_parse(Path("Scrum_Meeting_01.md")) == True
        assert parser.can_parse(Path("scrum_notes.md")) == True
        assert parser.can_parse(Path("client_review.md")) == False
        assert parser.can_parse(Path("scrum.txt")) == False

    def test_extract_date_patterns(self):
        """Test date extraction"""
        parser = ScrumMeetingParser()

        content = "**Date:** Monday, December 1, 2025"
        date = parser.extract_date(content)

        assert date is not None
        assert date.year == 2025
        assert date.month == 12
        assert date.day == 1

    def test_normalize_status(self):
        """Test status normalization"""
        parser = ScrumMeetingParser()

        assert parser.normalize_status("green") == "Green"
        assert parser.normalize_status("On Track") == "Green"
        assert parser.normalize_status("amber") == "Amber"
        assert parser.normalize_status("In Progress") == "InProgress"
        assert parser.normalize_status("complete") == "Complete"


class TestClientReviewParser:
    """Tests for ClientReviewParser"""

    def test_can_parse_client_file(self):
        """Test file type detection"""
        parser = ClientReviewParser()

        assert parser.can_parse(Path("Client_Review_01.md")) == True
        assert parser.can_parse(Path("client_review_notes.md")) == True
        assert parser.can_parse(Path("scrum_meeting.md")) == False

    def test_assess_sentiment(self):
        """Test sentiment assessment"""
        parser = ClientReviewParser()

        positive_content = "We are impressed with the progress. Excellent work by the team."
        assert parser._assess_sentiment(positive_content) in ["Positive", "CautiouslyPositive"]

        negative_content = "We are concerned about the delays. There are several issues."
        assert parser._assess_sentiment(negative_content) in ["Negative", "Concerned"]


class TestBaseParser:
    """Tests for BaseParser utilities"""

    def test_extract_tables(self):
        """Test table extraction"""
        class ConcreteParser(BaseParser):
            def parse(self, filepath):
                pass
            def can_parse(self, filepath):
                return True

        parser = ConcreteParser()

        content = """
| Name | Role |
|------|------|
| Alice | Dev |
| Bob | Test |
"""
        tables = parser.extract_tables(content)

        assert len(tables) == 1
        assert len(tables[0]) == 2
        assert tables[0][0][0] == "Name"

    def test_extract_bullet_points(self):
        """Test bullet point extraction"""
        class ConcreteParser(BaseParser):
            def parse(self, filepath):
                pass
            def can_parse(self, filepath):
                return True

        parser = ConcreteParser()

        content = """
- First item
- Second item
* Third item
"""
        bullets = parser.extract_bullet_points(content)

        assert len(bullets) == 3
        assert "First item" in bullets


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
