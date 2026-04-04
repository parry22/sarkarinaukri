"""
Tests for scraping/parsers/date_parser.py

No external services needed - purely testing string parsing.
"""

import pytest
from datetime import date

from scraping.parsers.date_parser import (
    extract_all_dates,
    extract_dates,
    _parse_single_date,
    _replace_hindi_months,
)


# ===================================================================
# 1. Individual date format parsing
# ===================================================================


class TestDateFormats:
    def test_day_month_name_year(self):
        """'15 May 2026' format."""
        results = extract_all_dates("The date is 15 May 2026 for the exam.")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_day_month_name_year_long(self):
        """'15 January 2026' full month name."""
        results = extract_all_dates("Starting from 15 January 2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 1, 15)

    def test_dd_mm_yyyy_dash(self):
        """'15-05-2026' format."""
        results = extract_all_dates("Date: 15-05-2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_dd_mm_yyyy_slash(self):
        """'15/05/2026' format."""
        results = extract_all_dates("Date: 15/05/2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_dd_mm_yyyy_dot(self):
        """'15.05.2026' format."""
        results = extract_all_dates("Date: 15.05.2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_iso_format(self):
        """'2026-05-15' ISO format."""
        results = extract_all_dates("Date: 2026-05-15")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_day_month_comma_year(self):
        """'15 May, 2026' with comma."""
        results = extract_all_dates("Apply by 15 May, 2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)


# ===================================================================
# 2. Multiple dates in one text
# ===================================================================


class TestMultipleDates:
    def test_two_dates_extracted(self):
        text = "Apply from 01 May 2026 to 31 May 2026"
        results = extract_all_dates(text)
        assert len(results) >= 2
        dates = [r[0] for r in results]
        assert date(2026, 5, 1) in dates
        assert date(2026, 5, 31) in dates

    def test_three_dates_extracted(self):
        text = (
            "Start date: 01-01-2026. "
            "Last date to apply: 15-02-2026. "
            "Exam date: 20-03-2026."
        )
        results = extract_all_dates(text)
        assert len(results) >= 3

    def test_dates_sorted_by_position(self):
        text = "First 10 January 2026 then 20 February 2026"
        results = extract_all_dates(text)
        assert results[0][0] < results[1][0]  # Jan before Feb


# ===================================================================
# 3. Context-based date classification
# ===================================================================


class TestDateClassification:
    def test_application_end_date_from_last_date_keyword(self):
        text = "Last date to apply: 31 May 2026"
        classified = extract_dates(text)
        assert "application_end_date" in classified
        assert classified["application_end_date"] == date(2026, 5, 31)

    def test_application_start_date_from_keyword(self):
        text = "Application start date: 01 May 2026"
        classified = extract_dates(text)
        assert "application_start_date" in classified
        assert classified["application_start_date"] == date(2026, 5, 1)

    def test_exam_date_from_keyword(self):
        text = "The examination date is 15 July 2026"
        classified = extract_dates(text)
        assert "exam_date" in classified
        assert classified["exam_date"] == date(2026, 7, 15)

    def test_admit_card_keyword(self):
        text = "Admit card available from 01 July 2026"
        classified = extract_dates(text)
        assert "admit_card_date" in classified
        assert classified["admit_card_date"] == date(2026, 7, 1)

    def test_multiple_classified_dates(self):
        text = (
            "Application start date: 01 May 2026. "
            "Last date to apply: 31 May 2026. "
            "Exam date: 15 July 2026."
        )
        classified = extract_dates(text)
        assert classified.get("application_start_date") == date(2026, 5, 1)
        assert classified.get("application_end_date") == date(2026, 5, 31)
        assert classified.get("exam_date") == date(2026, 7, 15)

    def test_empty_text_returns_empty(self):
        assert extract_dates("") == {}
        assert extract_dates("   ") == {}

    def test_no_dates_in_text(self):
        assert extract_dates("This text has no dates at all.") == {}


# ===================================================================
# 4. Hindi date parsing
# ===================================================================


class TestHindiDates:
    def test_hindi_month_replacement(self):
        result = _replace_hindi_months("15 मई 2026")
        assert "May" in result

    def test_hindi_date_extraction(self):
        text = "अंतिम तिथि 15 मई 2026 है"
        results = extract_all_dates(text)
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 15)

    def test_hindi_january(self):
        text = "10 जनवरी 2026"
        results = extract_all_dates(text)
        assert len(results) >= 1
        assert results[0][0] == date(2026, 1, 10)

    def test_hindi_date_with_context_classification(self):
        text = "अंतिम तिथि 31 मई 2026"
        classified = extract_dates(text)
        assert "application_end_date" in classified
        assert classified["application_end_date"] == date(2026, 5, 31)

    def test_hindi_september_alternate_spelling(self):
        """Both सितंबर and सितम्बर should work."""
        text1 = "15 सितंबर 2026"
        text2 = "15 सितम्बर 2026"
        r1 = extract_all_dates(text1)
        r2 = extract_all_dates(text2)
        assert len(r1) >= 1
        assert len(r2) >= 1
        assert r1[0][0] == date(2026, 9, 15)
        assert r2[0][0] == date(2026, 9, 15)


# ===================================================================
# 5. Edge cases
# ===================================================================


class TestDateEdgeCases:
    def test_single_digit_day(self):
        results = extract_all_dates("Date: 5 May 2026")
        assert len(results) >= 1
        assert results[0][0] == date(2026, 5, 5)

    def test_parse_single_date_helper(self):
        assert _parse_single_date("15 May 2026") == date(2026, 5, 15)
        assert _parse_single_date("not a date") is None

    def test_duplicate_positions_not_repeated(self):
        """Same date at same position should not produce duplicates."""
        text = "Date: 15 May 2026"
        results = extract_all_dates(text)
        positions = [r[2] for r in results]
        # No duplicate positions
        assert len(positions) == len(set(positions))
