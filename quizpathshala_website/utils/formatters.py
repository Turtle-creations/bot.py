from pathlib import Path


OPTION_LABELS = ("A", "B", "C", "D")


def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_profile(user: dict) -> str:
    total_answered = user["correct_answers"] + user["wrong_answers"]
    accuracy = (user["correct_answers"] / total_answered * 100) if total_answered else 0
    premium_status = "💎 Premium" if user.get("is_premium") else "🆓 Free"

    return (
        "<b>👤 Your Profile</b>\n\n"
        f"<b>Name:</b> {escape_html(user['full_name'])}\n"
        f"<b>Quiz Played:</b> {user['quiz_played']}\n"
        f"<b>Correct:</b> {user['correct_answers']}\n"
        f"<b>Wrong:</b> {user['wrong_answers']}\n"
        f"<b>Score:</b> {user['score']:.2f}\n"
        f"<b>Accuracy:</b> {accuracy:.1f}%\n"
        f"<b>Plan:</b> {escape_html(premium_status)}"
    )


def format_question_text(question: dict, question_number: int, total_questions: int) -> str:
    return "\n".join(
        [
            f"<b>Question {question_number}/{total_questions}</b>",
            f"<b>Time limit:</b> {question['time_limit']} sec",
            "",
            escape_html(question["question_text"]),
        ]
    )


def format_leaderboard(users: list[dict]) -> str:
    if not users:
        return "<b>🏆 Leaderboard</b>\n\nNo users found yet."

    lines = ["<b>🏆 Leaderboard</b>\n"]
    for index, user in enumerate(users, start=1):
        plan = "Premium" if user["is_premium"] else "Free"
        lines.append(
            f"{index}. {escape_html(user['full_name'])} - {user['score']:.2f} pts ({plan})"
        )

    return "\n".join(lines)


def format_help_text() -> str:
    return (
        "<b>❓ How to use the bot</b>\n\n"
        "1. Open 🎯 Quiz and choose an exam.\n"
        "2. Pick a set and question count.\n"
        "3. Answer each question from inline buttons.\n"
        "4. Use 👤 Profile to track your progress.\n"
        "5. Open 💎 Premium to see limits and upgrade options."
    )


def format_premium_text(status: str, quiz_access: str, pdf_remaining: str, limit: int) -> str:
    return (
        "<b>💎 Premium Access</b>\n\n"
        f"<b>Status:</b> {escape_html(status)}\n"
        f"<b>Quiz Access:</b> {escape_html(quiz_access)}\n"
        f"<b>Your Remaining Free PDFs:</b> {escape_html(pdf_remaining)}\n\n"
        "Premium users can access all quiz sets and get unlimited PDF generation."
    )


def resolve_image_path(raw_path: str | None, base_dir: Path) -> Path | None:
    if not raw_path:
        return None

    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / raw_path

    return path if path.exists() else None
