import random
import time
from copy import deepcopy

from config import DEFAULT_QUESTION_TIME
from services.exam_service_db import exam_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service


class WebQuizService:
    QUIZ_COUNT_OPTIONS = (20, 50, 100)
    MAX_QUESTIONS_PER_QUIZ = 100

    def __init__(self) -> None:
        self.sessions: dict[int, dict] = {}

    def list_exam_catalog(self, user_id: int) -> list[dict]:
        catalog = []
        for exam in exam_service.get_exams():
            sets = []
            for set_item in exam_service.get_sets(exam["exam_id"]):
                locked = bool(int(set_item.get("is_premium_locked", 0)))
                has_access = (not locked) or premium_service.is_premium(user_id) or user_service.is_admin(user_id)
                sets.append(
                    {
                        **set_item,
                        "locked": locked,
                        "has_access": has_access,
                    }
                )
            catalog.append({**exam, "sets": sets})
        return catalog

    def can_access_set(self, user_id: int, set_id: int) -> bool:
        set_item = exam_service.get_set(set_id)
        if not set_item:
            return False
        if not int(set_item.get("is_premium_locked", 0)):
            return True
        return premium_service.is_premium(user_id) or user_service.is_admin(user_id)

    def start_quiz(self, user_id: int, set_id: int, requested_count: int) -> tuple[dict | None, str | None]:
        if not self.can_access_set(user_id, set_id):
            return None, "This quiz set is premium-only."

        question_pool = [self._prepare_question(item) for item in exam_service.get_questions(set_id)]
        if not question_pool:
            return None, "No questions are available in this set yet."

        actual_count = min(max(int(requested_count), 1), len(question_pool), self.MAX_QUESTIONS_PER_QUIZ)
        random.shuffle(question_pool)
        questions = question_pool[:actual_count]

        self.sessions[user_id] = {
            "set_id": set_id,
            "requested_count": requested_count,
            "questions": questions,
            "index": 0,
            "current_question_started_at": time.time(),
            "locked": False,
            "last_result": None,
            "correct_count": 0,
            "wrong_count": 0,
            "skipped_count": 0,
        }
        user_service.record_quiz_start(user_id)
        return self.sessions[user_id], None

    def get_session(self, user_id: int) -> dict | None:
        return self.sessions.get(user_id)

    def get_current_question(self, user_id: int) -> dict | None:
        session = self.get_session(user_id)
        if not session:
            return None
        index = session["index"]
        if index >= len(session["questions"]):
            return None
        question = deepcopy(session["questions"][index])
        question["remaining_seconds"] = self.remaining_seconds(user_id)
        question["number"] = index + 1
        question["total"] = len(session["questions"])
        return question

    def answer_question(self, user_id: int, selected_index: int | None, action: str = "answer") -> dict | None:
        session = self.get_session(user_id)
        question = self.get_current_question(user_id)
        if not session or not question or session["locked"]:
            return None

        result = {
            "action": action,
            "correct": False,
            "selected_index": selected_index,
            "correct_index": question["correct_index"],
            "correct_answer": question["correct_answer"],
            "explanation": question.get("explanation"),
        }

        if action == "answer" and selected_index is not None and 0 <= selected_index < len(question["options"]):
            selected_option = question["options"][selected_index]
            result["selected_text"] = selected_option["text"]
            if selected_option["text"].strip().lower() == question["correct_answer"].strip().lower():
                session["correct_count"] += 1
                user_service.record_answer(user_id, True)
                result["correct"] = True
            else:
                session["wrong_count"] += 1
                user_service.record_answer(user_id, False)
        else:
            session["skipped_count"] += 1
            result["action"] = "skip" if action == "skip" else "timeout"

        session["locked"] = True
        session["last_result"] = result
        return result

    def next_question(self, user_id: int) -> bool:
        session = self.get_session(user_id)
        if not session:
            return False
        session["index"] += 1
        session["locked"] = False
        session["last_result"] = None
        session["current_question_started_at"] = time.time()
        return session["index"] < len(session["questions"])

    def submit_quiz(self, user_id: int, ended_reason: str = "submitted") -> dict:
        session = self.get_session(user_id)
        if not session:
            return self._summary_payload(0, 0, 0, None, 0)

        summary = self._summary_payload(
            session["correct_count"],
            session["wrong_count"],
            session["skipped_count"],
            session["set_id"],
            len(session["questions"]),
        )
        user_service.record_quiz_attempt(
            user_id=user_id,
            set_id=session["set_id"],
            requested_count=len(session["questions"]),
            correct_count=summary["correct"],
            wrong_count=summary["wrong"],
            skipped_count=summary["skipped"],
            ended_reason=ended_reason,
        )
        self.sessions.pop(user_id, None)
        return summary

    def remaining_seconds(self, user_id: int) -> int:
        session = self.get_session(user_id)
        if not session:
            return 0
        index = session["index"]
        if index >= len(session["questions"]):
            return 0
        question = session["questions"][index]
        elapsed = int(time.time() - session["current_question_started_at"])
        return max(0, int(question["time_limit"]) - elapsed)

    def _prepare_question(self, question: dict) -> dict:
        item = deepcopy(question)
        item["time_limit"] = int(item.get("time_limit") or DEFAULT_QUESTION_TIME)
        options = [{"id": f"opt_{index}", "text": value} for index, value in enumerate(item["options"])]
        random.shuffle(options)
        item["options"] = options
        item["correct_answer"] = str(item["correct_option"]).strip()
        item["correct_index"] = next(
            (index for index, option in enumerate(options) if option["text"].strip().lower() == item["correct_answer"].lower()),
            0,
        )
        return item

    def _summary_payload(
        self,
        correct: int,
        wrong: int,
        skipped: int,
        set_id: int | None,
        requested_count: int,
    ) -> dict:
        attempted = correct + wrong
        score = correct - (wrong * 0.25)
        accuracy = (correct / attempted * 100) if attempted else 0.0
        return {
            "correct": correct,
            "wrong": wrong,
            "skipped": skipped,
            "attempted": attempted,
            "score": score,
            "accuracy": accuracy,
            "negative_marking": wrong * 0.25,
            "set_id": set_id,
            "requested_count": requested_count,
        }


web_quiz_service = WebQuizService()
