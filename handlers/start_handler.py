from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from services.exam_service import get_all_exams
from handlers.notify_handler import get_notification
from keyboards.quiz_select_keyboard import exam_keyboard
from services.user_service import (
    get_or_create_user,
    get_badge,
    get_top_users,
    get_user_rank,
    get_rank_badge
)
from services.premium_service import (
    PREMIUM_PLANS,
    get_status_text,
    is_premium_active,
)
from utils.helpers import is_double_click


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("🎯 Quiz", callback_data="start_quiz")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("📢 Updates & notifications", callback_data="updates")],
        [InlineKeyboardButton("📄 PDFs", callback_data="pdfs")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium")],
        [InlineKeyboardButton("📘 User Guide", callback_data="guide")],
    ]

    await update.message.reply_text(
        "👋 Welcome to Quiz Bot\n\nSelect an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ---------------- BUTTON HANDLER ----------------
async def start_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    data = query.data

    await query.answer()

    # 🔒 DOUBLE CLICK PROTECTION
    if is_double_click(context, "start_click", 1):
        return

    # 🎯 QUIZ
    if data == "start_quiz":

        exams = get_all_exams()

        if not exams:
            await query.message.reply_text("⚠ No exams available")
            return

        await query.message.reply_text(
            "📚 Select Exam:",
            reply_markup=exam_keyboard(exams)
        )

    # 👤 PROFILE
    elif data == "profile":

        user_id = query.from_user.id
        name = query.from_user.first_name

        user = get_or_create_user(user_id, name)

        total = user["correct"] + user["wrong"]
        accuracy = (user["correct"] / total * 100) if total > 0 else 0

        badge = get_badge(user["score"])
        rank = get_user_rank(user_id)
        rank_badge = get_rank_badge(rank) if rank else ""

        msg = (
            f"👤 Profile\n\n"
            f"🧑 Name: {user['name']}\n"
            f"🏅 Rank: #{rank} {rank_badge}\n"
            f"🎯 Quiz Played: {user['quiz_played']}\n"
            f"✅ Correct: {user['correct']}\n"
            f"❌ Wrong: {user['wrong']}\n"
            f"📊 Accuracy: {accuracy:.2f}%\n"
            f"🏆 Score: {user['score']}\n"
            f"🎖 Badge: {badge}\n"
            f"💎 Premium: {get_status_text(user_id)}"
        )

        await query.message.reply_text(msg)

    # 🏆 LEADERBOARD
    elif data == "leaderboard":

        users = get_top_users(10)

        if not users:
            await query.message.reply_text("⚠ No users yet")
            return

        msg = "🏆 Leaderboard (Top 10)\n\n"

        for i, u in enumerate(users, 1):
            badge = get_badge(u["score"])
            rank_badge = get_rank_badge(i)

            msg += f"{i}. {u['name']} - {u['score']} pts {badge} {rank_badge}\n"

        await query.message.reply_text(msg)

    # 📢 UPDATES
    elif data == "updates":

        msg = get_notification()

        if not msg:
            await query.message.reply_text("📢 No updates yet")
            return

        await query.message.reply_text(f"📢 Latest Update:\n\n{msg}")

    # 📄 PDFs ✅ FIXED
    elif data == "pdfs":

        from utils.pdf_generator import generate_pdf
        from services.question_service import get_questions

        exams = get_all_exams()

        if not exams:
            await query.message.reply_text("⚠ No exams available")
            return

        exam = exams[0]

        if not exam.get("sets"):
            await query.message.reply_text("⚠ No sets found")
            return

        set_id = exam["sets"][0]["id"]

        questions = get_questions(exam["id"], set_id)

        if not questions:
            await query.message.reply_text("⚠ No questions found")
            return

        file_path = generate_pdf(questions)

        with open(file_path, "rb") as f:
            await query.message.reply_document(document=f)

    # 💎 PREMIUM
    elif data == "premium":
        user_id = query.from_user.id
        active_text = "Yes" if is_premium_active(user_id) else "No"

        lines = [
            "💎 Premium Membership",
            "",
            f"Current status: {get_status_text(user_id)}",
            f"Premium active: {active_text}",
            "",
            "Plans:",
        ]

        for plan in PREMIUM_PLANS:
            lines.append(f"- {plan['label']}")

        lines += [
            "",
            "Current premium support in app:",
            "- Premium status is saved in repo data",
            "- Admin can activate or extend access",
            "- Profile shows the live subscription status",
            "",
            "Contact admin to activate your plan.",
        ]

        await query.message.reply_text("\n".join(lines))

    # 📘 GUIDE
    elif data == "guide":

        msg = (
            "📘 User Guide\n\n"
            "1. 🎯 Quiz → exam select karke start karo\n"
            "2. ⏱ Timer ke andar answer do\n"
            "3. 👤 Profile me score dekho\n"
            "4. 📄 PDFs se practice karo\n"
            "5. 💎 Premium se full access lo"
        )

        await query.message.reply_text(msg)

    # ⚠️ FALLBACK
    else:
        await query.message.reply_text("⚠ Invalid option")
