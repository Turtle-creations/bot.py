# -*- coding: utf-8 -*-

import asyncio
import random
import secrets
import time
from copy import deepcopy

from config import DEFAULT_QUESTION_TIME
from services.exam_service_db import exam_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)


class QuizService:
    MAX_PAUSES = 4

    def __init__(self):
        self.sessions: dict[int, dict] = {}

    def get_available_question_counts(self, user: dict, total_questions: int) -> list[int]:
        if total_questions <= 0:
            return []

        counts = [count for count in (5, 10, 20) if count <= total_questions]
        if total_questions not in counts:
            counts.append(total_questions)
        return sorted(set(counts))

    def can_start_quiz(self, user: dict) -> tuple[bool, str]:
        return True, ""

    def can_access_set(self, user_id: int, set_id: int) -> bool:
        set_ = exam_service.get_set(set_id)
        if not set_:
            return False
        if not int(set_.get("is_premium_locked", 0)):
            return True
        return premium_service.is_premium(user_id) or user_service.is_admin(user_id)

    def start_session(self, user_id: int, set_id: int, requested_count: int) -> dict | None:
        if not self.can_access_set(user_id, set_id):
            return None

        questions = [self._prepare_question(item) for item in exam_service.get_questions(set_id)]
        if not questions:
            return None

        user = user_service.get_user(user_id)
        available_counts = self.get_available_question_counts(user, len(questions))
        if not available_counts:
            return None

        count = min(requested_count, max(available_counts))
        random.shuffle(questions)
        questions = questions[:count]

        self._cancel_background_jobs(user_id)
        self.sessions[user_id] = {
            "set_id": set_id,
            "requested_count": count,
            "questions": questions,
            "index": 0,
            "started_at": time.time(),
            "deadline": time.time() + questions[0]["time_limit"],
            "paused": False,
            "pause_count": 0,
            "answered": False,
            "question_locked": False,
            "transitioning": False,
            "countdown_task": None,
            "advance_task": None,
            "question_message_id": None,
            "question_chat_id": None,
            "image_message_id": None,
            "active_question_token": self._new_token(),
            "correct_count": 0,
            "wrong_count": 0,
            "skipped_count": 0,
            "last_feedback": None,
            "processed_callbacks": set(),
        }

        user_service.record_quiz_start(user_id)
        logger.info(
            "Quiz session started | user_id=%s set_id=%s requested_count=%s actual_count=%s",
            user_id,
            set_id,
            requested_count,
            len(questions),
        )
        return self.sessions[user_id]

    def _prepare_question(self, question: dict) -> dict:
        item = deepcopy(question)
        item["time_limit"] = int(item.get("time_limit") or DEFAULT_QUESTION_TIME)
        correct_answer = str(item["correct_option"]).strip()
        shuffled_options = list(item["options"])
        random.shuffle(shuffled_options)
        item["options"] = [{"id": f"opt_{index}", "text": text} for index, text in enumerate(shuffled_options)]
        item["correct_index"] = next(
            (
                index
                for index, option in enumerate(item["options"])
                if option["text"].strip().lower() == correct_answer.lower()
            ),
            0,
        )
        item["correct_answer"] = correct_answer
        return item

    def get_session(self, user_id: int) -> dict | None:
        return self.sessions.get(user_id)

    def get_current_question(self, user_id: int) -> dict | None:
        session = self.sessions.get(user_id)
        if not session:
            return None
        if session["index"] >= len(session["questions"]):
            return None
        return session["questions"][session["index"]]

    def validate_question_callback(
        self,
        user_id: int,
        *,
        question_id: int,
        question_token: str,
        message_id: int | None = None,
    ) -> bool:
        session = self.sessions.get(user_id)
        question = self.get_current_question(user_id)
        if not session or not question:
            return False
        if question["question_id"] != question_id:
            return False
        if session.get("active_question_token") != question_token:
            return False
        if message_id is not None and session.get("question_message_id") != message_id:
            return False
        return True

    def mark_callback_processed(self, user_id: int, *, action_key: str) -> bool:
        session = self.sessions.get(user_id)
        if not session:
            return False

        processed = session.setdefault("processed_callbacks", set())
        if action_key in processed:
            return False

        processed.add(action_key)
        return True

    def complete_question(
        self,
        user_id: int,
        *,
        action: str,
        selected_index: int | None = None,
    ) -> dict | None:
        session = self.sessions.get(user_id)
        question = self.get_current_question(user_id)
        if not session or not question or session.get("question_locked"):
            return None
        if action != "timeout" and session.get("paused"):
            return None

        if action == "answer":
            if selected_index is None or selected_index < 0 or selected_index >= len(question["options"]):
                return None
        elif action not in {"skip", "timeout"}:
            return None

        session["answered"] = True
        session["question_locked"] = True
        session["transitioning"] = True
        self._cancel_countdown_task(user_id)

        correct_index = question["correct_index"]
        correct = False
        feedback = ""

        if action == "answer":
            selected_text = question["options"][selected_index]["text"]
            correct = selected_text.strip().lower() == question["correct_answer"].lower()
            if correct:
                session["correct_count"] += 1
                user_service.record_answer(user_id, True)
                feedback = "✅ Correct"
            else:
                session["wrong_count"] += 1
                user_service.record_answer(user_id, False)
                feedback = "❌ Wrong"
            logger.info(
                "Answer clicked | user_id=%s question_id=%s selected_index=%s selected_text=%s correct_answer=%s correct=%s",
                user_id,
                question["question_id"],
                selected_index,
                selected_text,
                question["correct_answer"],
                correct,
            )
        elif action == "skip":
            session["skipped_count"] += 1
            feedback = "⏩ Question skipped"
            logger.info(
                "Question skipped | user_id=%s question_id=%s",
                user_id,
                question["question_id"],
            )
        else:
            session["skipped_count"] += 1
            feedback = "⏰ Time's up!"
            logger.info(
                "Timer ended | user_id=%s question_id=%s marked_skipped=1",
                user_id,
                question["question_id"],
            )

        session["last_feedback"] = feedback
        locked_token = self.refresh_question_token(user_id)
        return {
            "action": action,
            "correct": correct,
            "selected_index": selected_index,
            "correct_index": correct_index,
            "feedback": feedback,
            "correct_answer": question["correct_answer"],
            "question_id": question["question_id"],
            "question_token": locked_token,
        }

    def pause_quiz(self, user_id: int) -> tuple[bool, str]:
        session = self.sessions.get(user_id)
        if not session:
            return False, "⚠️ No active quiz session found."
        if session.get("question_locked"):
            return False, "⚠️ This question is already locked."
        if session["pause_count"] >= self.MAX_PAUSES:
            return False, "⚠️ You used too many breaks. Complete the quiz."
        if session["paused"]:
            return False, "⚠️ Quiz is already paused."

        session["paused"] = True
        session["pause_count"] += 1
        session["remaining_time"] = max(0, int(session["deadline"] - time.time()))
        self._cancel_countdown_task(user_id)
        self.refresh_question_token(user_id)
        return True, f"⏸ Quiz paused. Breaks used: {session['pause_count']}/{self.MAX_PAUSES}"

    def resume_quiz(self, user_id: int) -> tuple[bool, str]:
        session = self.sessions.get(user_id)
        if not session:
            return False, "⚠️ No active quiz session found."
        if not session["paused"]:
            return False, "⚠️ Quiz is not paused."
        if session.get("question_locked"):
            return False, "⚠️ This question is already locked."

        remaining = max(session.get("remaining_time", 0), 1)
        session["paused"] = False
        session["started_at"] = time.time()
        session["deadline"] = time.time() + remaining
        self.refresh_question_token(user_id)
        return True, "▶ Quiz resumed"

    def end_quiz(self, user_id: int) -> dict | None:
        session = self.sessions.get(user_id)
        if not session:
            return None
        self._cancel_background_jobs(user_id)
        return self.close_session(user_id, "ended_by_user")

    def move_to_next_question(self, user_id: int) -> bool:
        session = self.sessions.get(user_id)
        if not session:
            return False

        self._cancel_countdown_task(user_id)
        session["index"] += 1
        session["answered"] = False
        session["question_locked"] = False
        session["transitioning"] = False
        session["paused"] = False
        session["question_message_id"] = None
        session["image_message_id"] = None
        session["last_feedback"] = None
        session["processed_callbacks"] = set()

        question = self.get_current_question(user_id)
        if not question:
            logger.info("Next question triggered | user_id=%s reached_end=1", user_id)
            return False

        session["started_at"] = time.time()
        session["deadline"] = time.time() + question["time_limit"]
        session["active_question_token"] = self._new_token()
        logger.info(
            "Next question triggered | user_id=%s question_id=%s index=%s",
            user_id,
            question["question_id"],
            session["index"],
        )
        return True

    def refresh_question_token(self, user_id: int) -> str | None:
        session = self.sessions.get(user_id)
        if not session:
            return None
        session["active_question_token"] = self._new_token()
        session["processed_callbacks"] = set()
        return session["active_question_token"]

    def session_progress(self, user_id: int) -> tuple[int, int]:
        session = self.sessions.get(user_id)
        if not session:
            return 0, 0
        return min(session["index"] + 1, len(session["questions"])), len(session["questions"])

    def remaining_seconds(self, user_id: int) -> int:
        session = self.sessions.get(user_id)
        if not session:
            return 0
        if session.get("paused"):
            return int(session.get("remaining_time", 0))
        return max(0, int(session["deadline"] - time.time()))

    def set_question_message(self, user_id: int, chat_id: int, message_id: int):
        session = self.sessions.get(user_id)
        if session:
            session["question_chat_id"] = chat_id
            session["question_message_id"] = message_id

    def set_image_message(self, user_id: int, message_id: int | None):
        session = self.sessions.get(user_id)
        if session:
            session["image_message_id"] = message_id

    def set_countdown_task(self, user_id: int, task: asyncio.Task | None):
        session = self.sessions.get(user_id)
        if session:
            self._cancel_countdown_task(user_id)
            session["countdown_task"] = task

    def set_advance_task(self, user_id: int, task: asyncio.Task | None):
        session = self.sessions.get(user_id)
        if session:
            self._cancel_advance_task(user_id)
            session["advance_task"] = task

    def finish_session(self, user_id: int):
        self._cancel_background_jobs(user_id)
        self.sessions.pop(user_id, None)

    def close_session(self, user_id: int, ended_reason: str) -> dict:
        summary = self.build_summary(user_id)
        if summary.get("set_id") is not None:
            user_service.record_quiz_attempt(
                user_id=user_id,
                set_id=summary["set_id"],
                requested_count=summary["requested_count"],
                correct_count=summary["correct"],
                wrong_count=summary["wrong"],
                skipped_count=summary["skipped"],
                ended_reason=ended_reason,
            )
        self.finish_session(user_id)
        return summary

    def build_summary(self, user_id: int) -> dict:
        session = self.sessions.get(user_id)
        if not session:
            return {"correct": 0, "wrong": 0, "skipped": 0, "set_id": None, "requested_count": 0}
        return {
            "correct": session["correct_count"],
            "wrong": session["wrong_count"],
            "skipped": session["skipped_count"],
            "set_id": session["set_id"],
            "requested_count": session["requested_count"],
        }

    def _cancel_background_jobs(self, user_id: int):
        self._cancel_countdown_task(user_id)
        self._cancel_advance_task(user_id)

    def _cancel_countdown_task(self, user_id: int):
        session = self.sessions.get(user_id)
        task = session.get("countdown_task") if session else None
        if task and not task.done():
            task.cancel()
        if session:
            session["countdown_task"] = None

    def _cancel_advance_task(self, user_id: int):
        session = self.sessions.get(user_id)
        task = session.get("advance_task") if session else None
        if task and not task.done():
            task.cancel()
        if session:
            session["advance_task"] = None

    def _new_token(self) -> str:
        return secrets.token_hex(4)


quiz_service = QuizService()
