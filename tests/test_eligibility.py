"""
Tests for matching/eligibility_matcher.py

All tests use in-memory UserProfile and Notification objects.
No external services (Supabase, WhatsApp, etc.) are needed.
"""

import pytest
from datetime import date

from database.models import (
    UserProfile,
    Notification,
    CategoryType,
    ExamCategory,
    QualificationLevel,
)
from matching.eligibility_matcher import (
    is_eligible,
    find_eligible_users,
    find_eligible_notifications,
    count_eligible_notifications,
    _qualification_rank,
    _get_category_relaxation,
    _check_age,
    _check_qualification,
    _check_state_domicile,
    _check_gender,
    _check_exam_preference,
)


# ---------------------------------------------------------------------------
# Helpers to build test fixtures
# ---------------------------------------------------------------------------


def make_user(**overrides) -> UserProfile:
    """Create a UserProfile with sensible defaults, overridden by kwargs."""
    defaults = dict(
        phone="919999900000",
        name="Test User",
        date_of_birth=date(2000, 1, 1),
        age_years=25,
        qualification=QualificationLevel.GRADUATE.value,
        state_domicile="Uttar Pradesh",
        category=CategoryType.GENERAL.value,
        gender="Male",
        pwd_status=False,
        ex_serviceman=False,
        exam_preferences=[ExamCategory.SSC.value],
        state_psc_states=[],
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def make_notification(**overrides) -> Notification:
    """Create a Notification with sensible defaults, overridden by kwargs."""
    defaults = dict(
        dedup_hash="test-hash-001",
        recruiting_body="SSC",
        post_name="SSC CGL 2026",
        exam_category=ExamCategory.SSC.value,
        min_qualification=QualificationLevel.GRADUATE.value,
        min_age=18,
        max_age=32,
        obc_relaxation=3,
        sc_st_relaxation=5,
        ews_relaxation=0,
        pwd_relaxation=10,
        ex_serviceman_relaxation=5,
        gender_restriction=None,
        state_restriction=None,
        application_start_date=date(2026, 1, 1),
        application_end_date=date(2026, 6, 30),
    )
    defaults.update(overrides)
    return Notification(**defaults)


# ===================================================================
# 1. Basic eligibility - SSC CGL (Graduate, 25 years, General, Male)
# ===================================================================


class TestBasicEligibility:
    def test_user_eligible_for_ssc_cgl(self):
        user = make_user()
        notif = make_notification()
        assert is_eligible(user, notif) is True

    def test_user_eligible_all_checks_pass(self):
        """Verify each individual check passes for the standard user."""
        user = make_user()
        notif = make_notification()
        assert _check_exam_preference(user, notif) is True
        assert _check_age(user, notif) is True
        assert _check_qualification(user, notif) is True
        assert _check_gender(user, notif) is True
        assert _check_state_domicile(user, notif) is True


# ===================================================================
# 2. Age-related tests
# ===================================================================


class TestAgeCheck:
    def test_age_exceeds_limit_general_category(self):
        """General-category user aged 35 cannot apply for max_age=32."""
        user = make_user(age_years=35)
        notif = make_notification(max_age=32)
        assert is_eligible(user, notif) is False

    def test_age_exactly_at_limit(self):
        user = make_user(age_years=32)
        notif = make_notification(max_age=32)
        assert is_eligible(user, notif) is True

    def test_age_below_minimum(self):
        user = make_user(age_years=16)
        notif = make_notification(min_age=18)
        assert is_eligible(user, notif) is False

    def test_age_unknown_returns_false(self):
        user = make_user(age_years=None)
        notif = make_notification(max_age=32)
        assert _check_age(user, notif) is False

    def test_no_age_limits_always_passes(self):
        user = make_user(age_years=60)
        notif = make_notification(min_age=None, max_age=None)
        assert _check_age(user, notif) is True

    # --- OBC relaxation ---

    def test_obc_gets_3_year_relaxation(self):
        """OBC user aged 35 should pass max_age=32 with 3-year relaxation."""
        user = make_user(age_years=35, category=CategoryType.OBC.value)
        notif = make_notification(max_age=32, obc_relaxation=3)
        assert is_eligible(user, notif) is True

    def test_obc_still_fails_when_too_old(self):
        """OBC user aged 36 should NOT pass max_age=32 + 3 relaxation = 35."""
        user = make_user(age_years=36, category=CategoryType.OBC.value)
        notif = make_notification(max_age=32, obc_relaxation=3)
        assert is_eligible(user, notif) is False

    # --- SC/ST relaxation ---

    def test_sc_gets_5_year_relaxation(self):
        user = make_user(age_years=37, category=CategoryType.SC.value)
        notif = make_notification(max_age=32, sc_st_relaxation=5)
        assert is_eligible(user, notif) is True

    def test_st_gets_5_year_relaxation(self):
        user = make_user(age_years=37, category=CategoryType.ST.value)
        notif = make_notification(max_age=32, sc_st_relaxation=5)
        assert is_eligible(user, notif) is True

    def test_sc_fails_when_exceeds_relaxation(self):
        user = make_user(age_years=38, category=CategoryType.SC.value)
        notif = make_notification(max_age=32, sc_st_relaxation=5)
        assert is_eligible(user, notif) is False

    # --- PWD relaxation ---

    def test_pwd_gets_additional_relaxation(self):
        """PWD General user aged 40 should pass max_age=32 + 10 pwd = 42."""
        user = make_user(age_years=40, pwd_status=True)
        notif = make_notification(max_age=32, pwd_relaxation=10)
        assert is_eligible(user, notif) is True

    def test_pwd_obc_gets_combined_relaxation(self):
        """OBC + PWD: max_age=32 + 3(OBC) + 10(PWD) = 45."""
        user = make_user(
            age_years=44,
            category=CategoryType.OBC.value,
            pwd_status=True,
        )
        notif = make_notification(max_age=32, obc_relaxation=3, pwd_relaxation=10)
        assert is_eligible(user, notif) is True

    def test_pwd_obc_fails_beyond_combined_limit(self):
        user = make_user(
            age_years=46,
            category=CategoryType.OBC.value,
            pwd_status=True,
        )
        notif = make_notification(max_age=32, obc_relaxation=3, pwd_relaxation=10)
        assert is_eligible(user, notif) is False

    # --- Ex-serviceman relaxation ---

    def test_ex_serviceman_gets_additional_relaxation(self):
        """Ex-serviceman General user aged 36: max_age=32 + 5(exsm) = 37."""
        user = make_user(age_years=36, ex_serviceman=True)
        notif = make_notification(max_age=32, ex_serviceman_relaxation=5)
        assert is_eligible(user, notif) is True

    def test_ex_serviceman_sc_pwd_combined(self):
        """SC + PWD + Ex-serviceman: 32 + 5(SC) + 10(PWD) + 5(exsm) = 52."""
        user = make_user(
            age_years=50,
            category=CategoryType.SC.value,
            pwd_status=True,
            ex_serviceman=True,
        )
        notif = make_notification(
            max_age=32,
            sc_st_relaxation=5,
            pwd_relaxation=10,
            ex_serviceman_relaxation=5,
        )
        assert is_eligible(user, notif) is True


# ===================================================================
# 3. Qualification tests
# ===================================================================


class TestQualification:
    def test_qualification_too_low(self):
        """10th pass cannot apply for Graduate-required post."""
        user = make_user(qualification=QualificationLevel.TENTH.value)
        notif = make_notification(min_qualification=QualificationLevel.GRADUATE.value)
        assert is_eligible(user, notif) is False

    def test_higher_qualification_always_qualifies(self):
        """Postgraduate is higher than Graduate in the hierarchy."""
        user = make_user(qualification=QualificationLevel.POSTGRADUATE.value)
        notif = make_notification(min_qualification=QualificationLevel.GRADUATE.value)
        assert is_eligible(user, notif) is True

    def test_exact_qualification_match(self):
        user = make_user(qualification=QualificationLevel.GRADUATE.value)
        notif = make_notification(min_qualification=QualificationLevel.GRADUATE.value)
        assert _check_qualification(user, notif) is True

    def test_8th_pass_for_8th_required(self):
        user = make_user(qualification=QualificationLevel.EIGHTH.value)
        notif = make_notification(min_qualification=QualificationLevel.EIGHTH.value)
        assert _check_qualification(user, notif) is True

    def test_iti_vs_12th(self):
        """ITI is ranked above 12th in the hierarchy."""
        user = make_user(qualification=QualificationLevel.ITI.value)
        notif = make_notification(min_qualification=QualificationLevel.TWELFTH.value)
        assert _check_qualification(user, notif) is True

    def test_no_qualification_requirement_passes(self):
        user = make_user(qualification=QualificationLevel.EIGHTH.value)
        notif = make_notification(min_qualification=None)
        assert _check_qualification(user, notif) is True

    def test_unknown_user_qualification_fails(self):
        user = make_user(qualification=None)
        notif = make_notification(min_qualification=QualificationLevel.GRADUATE.value)
        assert _check_qualification(user, notif) is False

    def test_qualification_rank_helper(self):
        assert _qualification_rank("Graduate") == 5
        assert _qualification_rank("8th") == 0
        assert _qualification_rank(None) == -1
        assert _qualification_rank("PhD") == -1  # unrecognised


# ===================================================================
# 4. State domicile / State PSC tests
# ===================================================================


class TestStateDomicile:
    def test_correct_state_matches(self):
        user = make_user(state_domicile="Uttar Pradesh")
        notif = make_notification(state_restriction="Uttar Pradesh")
        assert _check_state_domicile(user, notif) is True

    def test_wrong_state_rejected(self):
        user = make_user(state_domicile="Bihar")
        notif = make_notification(state_restriction="Uttar Pradesh")
        assert _check_state_domicile(user, notif) is False

    def test_no_state_restriction_passes(self):
        user = make_user(state_domicile="Bihar")
        notif = make_notification(state_restriction=None)
        assert _check_state_domicile(user, notif) is True

    def test_case_insensitive_match(self):
        user = make_user(state_domicile="uttar pradesh")
        notif = make_notification(state_restriction="Uttar Pradesh")
        assert _check_state_domicile(user, notif) is True

    def test_state_psc_requires_psc_preference(self):
        """State PSC notification also checks state_psc_states list."""
        user = make_user(
            state_domicile="Uttar Pradesh",
            state_psc_states=["Uttar Pradesh"],
            exam_preferences=[ExamCategory.STATE_PSC.value],
        )
        notif = make_notification(
            state_restriction="Uttar Pradesh",
            exam_category=ExamCategory.STATE_PSC.value,
        )
        assert _check_state_domicile(user, notif) is True

    def test_state_psc_missing_from_preference_list(self):
        """User lives in UP but did not add UP to state_psc_states."""
        user = make_user(
            state_domicile="Uttar Pradesh",
            state_psc_states=["Bihar"],
            exam_preferences=[ExamCategory.STATE_PSC.value],
        )
        notif = make_notification(
            state_restriction="Uttar Pradesh",
            exam_category=ExamCategory.STATE_PSC.value,
        )
        assert _check_state_domicile(user, notif) is False


# ===================================================================
# 5. Gender restriction tests
# ===================================================================


class TestGender:
    def test_no_gender_restriction_passes(self):
        user = make_user(gender="Male")
        notif = make_notification(gender_restriction=None)
        assert _check_gender(user, notif) is True

    def test_empty_gender_restriction_passes(self):
        user = make_user(gender="Male")
        notif = make_notification(gender_restriction=[])
        assert _check_gender(user, notif) is True

    def test_male_only_notification_rejects_female(self):
        user = make_user(gender="Female")
        notif = make_notification(gender_restriction=["Male"])
        assert _check_gender(user, notif) is False

    def test_female_only_notification_accepts_female(self):
        user = make_user(gender="Female")
        notif = make_notification(gender_restriction=["Female"])
        assert _check_gender(user, notif) is True

    def test_gender_restriction_case_insensitive(self):
        user = make_user(gender="male")
        notif = make_notification(gender_restriction=["Male"])
        assert _check_gender(user, notif) is True

    def test_unknown_gender_fails(self):
        user = make_user(gender=None)
        notif = make_notification(gender_restriction=["Male"])
        assert _check_gender(user, notif) is False


# ===================================================================
# 6. Exam preference tests
# ===================================================================


class TestExamPreference:
    def test_matching_preference(self):
        user = make_user(exam_preferences=[ExamCategory.SSC.value])
        notif = make_notification(exam_category=ExamCategory.SSC.value)
        assert _check_exam_preference(user, notif) is True

    def test_preference_mismatch(self):
        """User wants Banking but notification is Railway."""
        user = make_user(exam_preferences=[ExamCategory.BANKING.value])
        notif = make_notification(exam_category=ExamCategory.RAILWAY.value)
        assert _check_exam_preference(user, notif) is False

    def test_multiple_preferences_one_matches(self):
        user = make_user(
            exam_preferences=[
                ExamCategory.BANKING.value,
                ExamCategory.SSC.value,
                ExamCategory.UPSC.value,
            ]
        )
        notif = make_notification(exam_category=ExamCategory.SSC.value)
        assert _check_exam_preference(user, notif) is True

    def test_no_preferences_fails(self):
        user = make_user(exam_preferences=[])
        notif = make_notification(exam_category=ExamCategory.SSC.value)
        assert _check_exam_preference(user, notif) is False


# ===================================================================
# 7. Edge cases
# ===================================================================


class TestEdgeCases:
    def test_notification_no_age_limits(self):
        user = make_user(age_years=55)
        notif = make_notification(min_age=None, max_age=None)
        assert is_eligible(user, notif) is True

    def test_notification_no_qualification_requirement(self):
        user = make_user(qualification=QualificationLevel.EIGHTH.value)
        notif = make_notification(min_qualification=None)
        assert is_eligible(user, notif) is True

    def test_all_restrictions_none(self):
        """Notification with no restrictions except exam category."""
        user = make_user()
        notif = make_notification(
            min_age=None,
            max_age=None,
            min_qualification=None,
            gender_restriction=None,
            state_restriction=None,
        )
        assert is_eligible(user, notif) is True


# ===================================================================
# 8. Batch functions
# ===================================================================


class TestBatchFunctions:
    def test_count_eligible_notifications(self):
        user = make_user()
        notifications = [
            make_notification(dedup_hash="a"),
            make_notification(dedup_hash="b", exam_category=ExamCategory.BANKING.value),
            make_notification(dedup_hash="c"),
        ]
        # User prefers SSC only, so Banking notification should not match
        count = count_eligible_notifications(user, notifications)
        assert count == 2

    def test_find_eligible_users(self):
        notif = make_notification()
        users = [
            make_user(phone="91001", age_years=25),
            make_user(phone="91002", age_years=50),  # too old
            make_user(phone="91003", age_years=30),
        ]
        eligible = find_eligible_users(notif, users)
        assert len(eligible) == 2
        phones = {u.phone for u in eligible}
        assert "91001" in phones
        assert "91003" in phones
        assert "91002" not in phones

    def test_find_eligible_notifications(self):
        user = make_user(
            exam_preferences=[ExamCategory.SSC.value, ExamCategory.BANKING.value]
        )
        notifications = [
            make_notification(dedup_hash="ssc1"),
            make_notification(dedup_hash="bank1", exam_category=ExamCategory.BANKING.value),
            make_notification(dedup_hash="rail1", exam_category=ExamCategory.RAILWAY.value),
        ]
        eligible = find_eligible_notifications(user, notifications)
        assert len(eligible) == 2
        hashes = {n.dedup_hash for n in eligible}
        assert "ssc1" in hashes
        assert "bank1" in hashes
        assert "rail1" not in hashes

    def test_find_eligible_users_empty_list(self):
        notif = make_notification()
        assert find_eligible_users(notif, []) == []

    def test_find_eligible_notifications_empty_list(self):
        user = make_user()
        assert find_eligible_notifications(user, []) == []
