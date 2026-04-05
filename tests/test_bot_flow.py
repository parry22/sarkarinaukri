"""
Tests for bot/onboarding.py and bot/message_templates.py

All external services (Supabase, WhatsApp API, Anthropic) are mocked.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

from database.models import (
    UserProfile,
    Notification,
    OnboardingStep,
    QualificationLevel,
    CategoryType,
    ExamCategory,
    GenderType,
    LanguagePref,
)
from bot import message_templates as tpl
from bot.onboarding import (
    handle_onboarding,
    _parse_dob,
    _match_state,
    _calculate_age,
    QUALIFICATION_MAP,
    CATEGORY_MAP,
    GENDER_MAP,
    EXAM_PREF_MAP,
    LANGUAGE_MAP,
    INDIAN_STATES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(**overrides) -> UserProfile:
    defaults = dict(
        phone="919999900000",
        name="Test User",
        onboarding_step=OnboardingStep.STARTED.value,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def make_notification(**overrides) -> Notification:
    defaults = dict(
        dedup_hash="test-hash",
        recruiting_body="SSC",
        post_name="SSC CGL 2026",
        exam_category=ExamCategory.SSC.value,
        min_qualification=QualificationLevel.GRADUATE.value,
        min_age=18,
        max_age=32,
        application_start_date=date(2026, 1, 1),
        application_end_date=date(2026, 6, 30),
        total_vacancies=5000,
        official_website="https://ssc.nic.in",
    )
    defaults.update(overrides)
    return Notification(**defaults)


# ===================================================================
# 1. Message template tests
# ===================================================================


class TestMessageTemplates:
    def test_welcome_message_contains_key_phrases(self):
        msg = tpl.welcome_message()
        assert "Namaste" in msg or "namaste" in msg.lower()
        assert "naam" in msg.lower()

    def test_ask_dob_mentions_format(self):
        msg = tpl.ask_dob()
        assert "DD/MM/YYYY" in msg

    def test_ask_qualification_lists_options(self):
        msg = tpl.ask_qualification()
        assert "8th" in msg
        assert "Graduate" in msg
        assert "Postgraduate" in msg

    def test_ask_exam_prefs_lists_all_categories(self):
        msg = tpl.ask_exam_prefs()
        assert "Railway" in msg
        assert "SSC" in msg
        assert "Banking" in msg
        assert "Defence" in msg
        assert "Teaching" in msg
        assert "State PSC" in msg
        assert "UPSC" in msg
        assert "Police" in msg

    def test_profile_complete_includes_eligible_count(self):
        msg = tpl.profile_complete(42)
        assert "42" in msg
        assert "eligible" in msg.lower() or "notifications" in msg.lower()

    def test_profile_complete_zero_count(self):
        msg = tpl.profile_complete(0)
        assert "0" in msg

    def test_help_message_lists_commands(self):
        msg = tpl.help_message()
        assert "status" in msg
        assert "alerts" in msg
        assert "help" in msg


# ===================================================================
# 2. Alert format tests
# ===================================================================


class TestAlertFormat:
    def test_alert_contains_required_fields(self):
        notif = make_notification(
            application_fee={"General": "100", "SC": None},
            documents_needed=["Aadhar", "Photo"],
        )
        user = make_user(
            age_years=25,
            qualification=QualificationLevel.GRADUATE.value,
        )
        msg = tpl.format_new_alert(notif, user)
        assert "SSC CGL 2026" in msg
        assert "5,000" in msg  # total_vacancies (now formatted with comma)
        assert "Graduate" in msg
        assert "ssc.nic.in" in msg
        # Documents no longer shown inline; source_url / apply link shown instead
        assert "Apply" in msg or "apply" in msg.lower()

    def test_alert_fee_format(self):
        notif = make_notification(
            application_fee={"General": "100", "OBC": "100", "SC": None}
        )
        user = make_user()
        msg = tpl.format_new_alert(notif, user)
        assert "General: ₹100" in msg
        # SC: None means free but template only shows keys with actual values
        # OBC: ₹100 should appear, SC: None is skipped (no fee entry = free)
        assert "OBC: ₹100" in msg

    def test_alert_no_fee(self):
        notif = make_notification(application_fee=None)
        user = make_user()
        msg = tpl.format_new_alert(notif, user)
        assert "N/A" in msg

    def test_alert_no_documents(self):
        # Documents field removed from new rich format — apply link is shown instead
        notif = make_notification(documents_needed=None)
        user = make_user()
        msg = tpl.format_new_alert(notif, user)
        assert "Apply" in msg or "🔗" in msg


# ===================================================================
# 3. Deadline reminder format
# ===================================================================


class TestDeadlineReminder:
    def test_reminder_format(self):
        notif = make_notification(application_end_date=date(2026, 6, 30))
        msg = tpl.format_deadline_reminder(notif, days_left=3)
        assert "3 DAYS LEFT" in msg
        assert "SSC CGL 2026" in msg
        assert "30 Jun 2026" in msg

    def test_reminder_no_end_date(self):
        notif = make_notification(application_end_date=None)
        msg = tpl.format_deadline_reminder(notif, days_left=5)
        assert "N/A" in msg


# ===================================================================
# 4. DOB validation
# ===================================================================


class TestDOBValidation:
    def test_valid_dob_slash(self):
        result = _parse_dob("15/08/1995")
        assert result == date(1995, 8, 15)

    def test_valid_dob_dash(self):
        result = _parse_dob("15-08-1995")
        assert result == date(1995, 8, 15)

    def test_invalid_dob_rejected(self):
        assert _parse_dob("not a date") is None
        assert _parse_dob("32/13/2000") is None
        assert _parse_dob("") is None

    def test_invalid_format_rejected(self):
        """YYYY-MM-DD format is not accepted by _parse_dob."""
        assert _parse_dob("1995-08-15") is None

    def test_calculate_age(self):
        # Use a fixed reference: if DOB is 2000-01-01, age depends on today
        dob = date(2000, 1, 1)
        age = _calculate_age(dob)
        # Age should be between 25 and 27 for reasonable test window
        assert 25 <= age <= 27


# ===================================================================
# 5. Qualification number mapping
# ===================================================================


class TestQualificationMap:
    def test_mapping_1_is_8th(self):
        assert QUALIFICATION_MAP["1"] == "8th"

    def test_mapping_2_is_10th(self):
        assert QUALIFICATION_MAP["2"] == "10th"

    def test_mapping_3_is_12th(self):
        assert QUALIFICATION_MAP["3"] == "12th"

    def test_mapping_4_is_iti(self):
        assert QUALIFICATION_MAP["4"] == "ITI"

    def test_mapping_5_is_diploma(self):
        assert QUALIFICATION_MAP["5"] == "Diploma"

    def test_mapping_6_is_graduate(self):
        assert QUALIFICATION_MAP["6"] == "Graduate"

    def test_mapping_7_is_postgraduate(self):
        assert QUALIFICATION_MAP["7"] == "Postgraduate"

    def test_invalid_key_returns_none(self):
        assert QUALIFICATION_MAP.get("0") is None
        assert QUALIFICATION_MAP.get("8") is None


# ===================================================================
# 6. Exam preference multi-select parsing
# ===================================================================


class TestExamPrefMap:
    def test_single_selection(self):
        assert EXAM_PREF_MAP["1"] == ExamCategory.RAILWAY.value

    def test_multi_select_parsing(self):
        """Simulate parsing '1,3,5' as the onboarding handler does."""
        raw = "1,3,5"
        tokens = [t.strip() for t in raw.split(",")]
        selected = [EXAM_PREF_MAP[t] for t in tokens]
        assert selected == ["Railway", "Banking", "Teaching"]

    def test_all_eight_options_mapped(self):
        assert len(EXAM_PREF_MAP) == 8
        for i in range(1, 9):
            assert str(i) in EXAM_PREF_MAP


# ===================================================================
# 7. State name validation
# ===================================================================


class TestStateValidation:
    def test_exact_match(self):
        assert _match_state("Uttar Pradesh") == "Uttar Pradesh"

    def test_case_insensitive(self):
        assert _match_state("uttar pradesh") == "Uttar Pradesh"

    def test_partial_match(self):
        assert _match_state("bihar") == "Bihar"

    def test_invalid_state_returns_none(self):
        assert _match_state("Atlantis") is None
        assert _match_state("") is None

    def test_delhi_recognised(self):
        assert _match_state("Delhi") == "Delhi"

    def test_all_states_in_list(self):
        """Sanity check that the list includes major states."""
        state_names = [s.lower() for s in INDIAN_STATES]
        assert "uttar pradesh" in state_names
        assert "bihar" in state_names
        assert "maharashtra" in state_names
        assert "delhi" in state_names
        assert "tamil nadu" in state_names


# ===================================================================
# 8. Onboarding flow step handlers (mocked DB + WhatsApp)
# ===================================================================


@pytest.fixture
def mock_send():
    """Patch send_text_message to capture sent messages."""
    with patch("bot.onboarding.send_text_message", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_update_user():
    """Patch _update_user to prevent DB calls."""
    with patch("bot.onboarding._update_user") as m:
        yield m


@pytest.fixture
def mock_eligible_count():
    """Patch fetch_eligible_notification_count to avoid Supabase."""
    with patch("bot.onboarding.fetch_eligible_notification_count", return_value=5) as m:
        yield m


PHONE = "919999900000"


class TestOnboardingNameStep:
    @pytest.mark.asyncio
    async def test_valid_name_advances_to_dob(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.STARTED.value)
        await handle_onboarding(PHONE, "Rajesh Kumar", user)
        mock_update_user.assert_called_once()
        call_args = mock_update_user.call_args[0]
        assert call_args[1]["name"] == "Rajesh Kumar"
        assert call_args[1]["onboarding_step"] == OnboardingStep.DOB.value

    @pytest.mark.asyncio
    async def test_too_short_name_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.NAME.value)
        await handle_onboarding(PHONE, "A", user)
        mock_update_user.assert_not_called()
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][1]
        assert "2-100" in sent_msg


class TestOnboardingDOBStep:
    @pytest.mark.asyncio
    async def test_valid_dob_advances_to_qualification(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.DOB.value)
        await handle_onboarding(PHONE, "15/08/1995", user)
        mock_update_user.assert_called_once()
        update_data = mock_update_user.call_args[0][1]
        assert update_data["date_of_birth"] == "1995-08-15"
        assert update_data["onboarding_step"] == OnboardingStep.QUALIFICATION.value

    @pytest.mark.asyncio
    async def test_invalid_dob_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.DOB.value)
        await handle_onboarding(PHONE, "not-a-date", user)
        mock_update_user.assert_not_called()
        sent_msg = mock_send.call_args[0][1]
        assert "DD/MM/YYYY" in sent_msg


class TestOnboardingQualificationStep:
    @pytest.mark.asyncio
    async def test_valid_qualification_advances(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.QUALIFICATION.value)
        await handle_onboarding(PHONE, "6", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["qualification"] == "Graduate"
        assert update_data["onboarding_step"] == OnboardingStep.STREAM.value

    @pytest.mark.asyncio
    async def test_invalid_qualification_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.QUALIFICATION.value)
        await handle_onboarding(PHONE, "9", user)
        mock_update_user.assert_not_called()


class TestOnboardingStateStep:
    @pytest.mark.asyncio
    async def test_valid_state_advances(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.STATE.value)
        await handle_onboarding(PHONE, "Bihar", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["state_domicile"] == "Bihar"
        assert update_data["onboarding_step"] == OnboardingStep.CATEGORY.value

    @pytest.mark.asyncio
    async def test_invalid_state_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.STATE.value)
        await handle_onboarding(PHONE, "Narnia", user)
        mock_update_user.assert_not_called()
        sent_msg = mock_send.call_args[0][1]
        assert "State nahi mila" in sent_msg


class TestOnboardingCategoryStep:
    @pytest.mark.asyncio
    async def test_obc_selection(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.CATEGORY.value)
        await handle_onboarding(PHONE, "2", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["category"] == CategoryType.OBC.value


class TestOnboardingGenderStep:
    @pytest.mark.asyncio
    async def test_female_selection(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.GENDER.value)
        await handle_onboarding(PHONE, "2", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["gender"] == GenderType.FEMALE.value

    @pytest.mark.asyncio
    async def test_invalid_gender_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.GENDER.value)
        await handle_onboarding(PHONE, "5", user)
        mock_update_user.assert_not_called()


class TestOnboardingPWDStep:
    @pytest.mark.asyncio
    async def test_pwd_yes(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.PWD.value)
        await handle_onboarding(PHONE, "1", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["pwd_status"] is True

    @pytest.mark.asyncio
    async def test_pwd_no(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.PWD.value)
        await handle_onboarding(PHONE, "2", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["pwd_status"] is False


class TestOnboardingExServicemanStep:
    @pytest.mark.asyncio
    async def test_ex_serviceman_yes(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.EX_SERVICEMAN.value)
        await handle_onboarding(PHONE, "1", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["ex_serviceman"] is True


class TestOnboardingExamPrefsStep:
    @pytest.mark.asyncio
    async def test_multi_select_parsing(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.EXAM_PREFS.value)
        await handle_onboarding(PHONE, "1,3,5", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["exam_preferences"] == ["Railway", "Banking", "Teaching"]
        assert update_data["onboarding_step"] == OnboardingStep.LANGUAGE.value

    @pytest.mark.asyncio
    async def test_single_selection(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.EXAM_PREFS.value)
        await handle_onboarding(PHONE, "2", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["exam_preferences"] == ["SSC"]

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.EXAM_PREFS.value)
        await handle_onboarding(PHONE, "1,9", user)
        mock_update_user.assert_not_called()


class TestOnboardingLanguageStep:
    @pytest.mark.asyncio
    async def test_language_completes_onboarding(
        self, mock_send, mock_update_user, mock_eligible_count
    ):
        user = make_user(onboarding_step=OnboardingStep.LANGUAGE.value)
        await handle_onboarding(PHONE, "3", user)
        update_data = mock_update_user.call_args[0][1]
        assert update_data["language_preference"] == LanguagePref.BOTH.value
        assert update_data["onboarding_step"] == OnboardingStep.COMPLETED.value
        # The sent message should include profile_complete with eligible count
        sent_msg = mock_send.call_args[0][1]
        assert "5" in sent_msg  # eligible_count=5 from mock

    @pytest.mark.asyncio
    async def test_invalid_language_rejected(self, mock_send, mock_update_user):
        user = make_user(onboarding_step=OnboardingStep.LANGUAGE.value)
        await handle_onboarding(PHONE, "7", user)
        mock_update_user.assert_not_called()


class TestOnboardingUnknownStep:
    @pytest.mark.asyncio
    async def test_unknown_step_sends_error(self, mock_send, mock_update_user):
        user = make_user(onboarding_step="nonexistent_step")
        await handle_onboarding(PHONE, "hello", user)
        mock_update_user.assert_not_called()
        sent_msg = mock_send.call_args[0][1]
        assert "help" in sent_msg.lower()


# ===================================================================
# 9. Weekly digest template
# ===================================================================


class TestWeeklyDigest:
    def test_empty_digest(self):
        user = make_user()
        msg = tpl.format_weekly_digest([], user)
        assert "koi nayi eligible notification nahi" in msg.lower()

    def test_digest_with_notifications(self):
        user = make_user(name="Rajesh")
        notifications = [
            make_notification(post_name="SSC CGL 2026", total_vacancies=5000),
            make_notification(
                dedup_hash="h2",
                post_name="RRB NTPC",
                total_vacancies=2000,
                application_end_date=date(2026, 7, 15),
            ),
        ]
        msg = tpl.format_weekly_digest(notifications, user)
        assert "Rajesh" in msg
        assert "2 Nayi Eligible Jobs" in msg
        assert "SSC CGL 2026" in msg
        assert "RRB NTPC" in msg


# ===================================================================
# 10. Profile summary template
# ===================================================================


class TestProfileSummary:
    def test_profile_summary_fields(self):
        user = make_user(
            name="Priya",
            qualification="Graduate",
            state_domicile="Bihar",
            category="OBC",
            gender="Female",
            pwd_status=False,
            ex_serviceman=False,
            exam_preferences=["SSC", "Banking"],
            language_preference="Both",
            subscription_tier="free_trial",
        )
        msg = tpl.profile_summary(user)
        assert "Priya" in msg
        assert "Graduate" in msg
        assert "Bihar" in msg
        assert "OBC" in msg
        assert "Female" in msg
        assert "SSC, Banking" in msg
