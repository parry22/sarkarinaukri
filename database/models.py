from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional
from enum import Enum


class QualificationLevel(str, Enum):
    EIGHTH = "8th"
    TENTH = "10th"
    TWELFTH = "12th"
    ITI = "ITI"
    DIPLOMA = "Diploma"
    GRADUATE = "Graduate"
    POSTGRADUATE = "Postgraduate"


QUALIFICATION_HIERARCHY = [
    "8th", "10th", "12th", "ITI", "Diploma", "Graduate", "Postgraduate"
]


class CategoryType(str, Enum):
    GENERAL = "General"
    OBC = "OBC"
    SC = "SC"
    ST = "ST"
    EWS = "EWS"


class GenderType(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class ExamCategory(str, Enum):
    RAILWAY = "Railway"
    SSC = "SSC"
    BANKING = "Banking"
    DEFENCE = "Defence"
    TEACHING = "Teaching"
    STATE_PSC = "State_PSC"
    UPSC = "UPSC"
    POLICE = "Police"
    PSU = "PSU"
    HEALTHCARE = "Healthcare"
    INSURANCE = "Insurance"
    JUDICIARY = "Judiciary"
    POSTAL = "Postal"


class LanguagePref(str, Enum):
    HINDI = "Hindi"
    ENGLISH = "English"
    BOTH = "Both"


class SubscriptionTier(str, Enum):
    FREE_TRIAL = "free_trial"
    BASIC = "basic"
    PRO = "pro"
    PREMIUM = "premium"


class OnboardingStep(str, Enum):
    STARTED = "started"
    NAME = "name"
    DOB = "dob"
    QUALIFICATION = "qualification"
    STREAM = "stream"
    STATE = "state"
    CATEGORY = "category"
    GENDER = "gender"
    PWD = "pwd"
    EX_SERVICEMAN = "ex_serviceman"
    EXAM_PREFS = "exam_prefs"
    LANGUAGE = "language"
    COMPLETED = "completed"


class UserProfile(BaseModel):
    id: Optional[str] = None
    phone: str
    name: Optional[str] = None
    date_of_birth: Optional[date] = None
    age_years: Optional[int] = None
    qualification: Optional[str] = None
    qualification_stream: Optional[str] = None
    state_domicile: Optional[str] = None
    category: Optional[str] = None
    gender: Optional[str] = None
    pwd_status: bool = False
    ex_serviceman: bool = False
    exam_preferences: list[str] = Field(default_factory=list)
    state_psc_states: list[str] = Field(default_factory=list)
    language_preference: str = "Hindi"
    subscription_tier: str = "free_trial"
    subscription_expires_at: Optional[datetime] = None
    onboarding_step: str = "started"
    is_active: bool = True


class Notification(BaseModel):
    id: Optional[str] = None
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    dedup_hash: str
    recruiting_body: str
    post_name: str
    exam_category: str
    notification_type: str = "new_recruitment"
    min_qualification: Optional[str] = None
    qualification_stream: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    obc_relaxation: int = 3
    sc_st_relaxation: int = 5
    ews_relaxation: int = 0
    pwd_relaxation: int = 10
    ex_serviceman_relaxation: int = 5
    gender_restriction: Optional[list[str]] = None
    state_restriction: Optional[str] = None
    notification_date: Optional[date] = None
    application_start_date: Optional[date] = None
    application_end_date: Optional[date] = None
    exam_date: Optional[date] = None
    admit_card_date: Optional[date] = None
    total_vacancies: Optional[int] = None
    vacancy_breakdown: Optional[dict] = None
    application_fee: Optional[dict] = None
    official_website: Optional[str] = None
    summary_hindi: Optional[str] = None
    summary_english: Optional[str] = None
    documents_needed: Optional[list[str]] = None
    is_verified: bool = False
