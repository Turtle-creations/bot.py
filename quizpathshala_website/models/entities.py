from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class UserProfile:
    user_id: int
    full_name: str
    username: Optional[str]
    is_admin: bool
    is_premium: bool
    premium_expires_at: Optional[str]
    daily_question_date: Optional[str]
    daily_question_count: int
    quiz_played: int
    correct_answers: int
    wrong_answers: int
    score: float


@dataclass(slots=True)
class Question:
    question_id: int
    exam_id: int
    set_id: int
    question_text: str
    options: list[str]
    correct_option: str
    image_path: Optional[str]
    time_limit: int
