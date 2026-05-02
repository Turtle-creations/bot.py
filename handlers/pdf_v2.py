from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from keyboards.app_keyboards import pdf_exam_keyboard, pdf_set_keyboard
from services.exam_service_db import exam_service
from services.pdf_service_db import pdf_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)


async def pdf_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = user_service.ensure_user(query.from_user)
    data = query.data

    if data == "pdf:start":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("⚠️ No exams are available right now.")
            return

        await query.message.reply_text(
            "<b>📄 Generate PDF</b>\n\nSelect an exam.",
            parse_mode=ParseMode.HTML,
            reply_markup=pdf_exam_keyboard(exams),
        )
        return

    parts = data.split(":")
    action = parts[1]

    if action == "exam":
        exam_id = int(parts[2])
        sets_ = exam_service.get_sets(exam_id)
        if not sets_:
            await query.message.reply_text("⚠️ No sets are available for this exam.")
            return

        await query.message.reply_text(
            "<b>📄 Generate PDF</b>\n\nSelect a set.",
            parse_mode=ParseMode.HTML,
            reply_markup=pdf_set_keyboard(exam_id, sets_),
        )
        return

    if action == "set":
        exam_id = int(parts[2])
        set_id = int(parts[3])

        if not premium_service.is_premium(user["user_id"]) and not user_service.can_generate_free_pdf(user):
            await query.message.reply_text(
                "❌ Free users can generate only 1 PDF. Upgrade to 💎 Premium for unlimited PDFs."
            )
            return

        questions = exam_service.get_questions(set_id)
        if not questions:
            await query.message.reply_text("⚠️ No questions found for this set.")
            return

        exam = next((item for item in exam_service.get_exams() if item["exam_id"] == exam_id), None)
        set_ = next((item for item in exam_service.get_sets(exam_id) if item["set_id"] == set_id), None)

        try:
            file_path = pdf_service.generate_questions_pdf(
                exam_title=exam["title"] if exam else "Exam",
                set_title=set_["title"] if set_ else "Set",
                questions=questions,
            )
        except Exception:
            logger.exception(
                "PDF generation failed | user_id=%s exam_id=%s set_id=%s",
                user["user_id"],
                exam_id,
                set_id,
            )
            await query.message.reply_text(
                "❌ PDF could not be generated right now. Please try again later or contact support."
            )
            return

        if not premium_service.is_premium(user["user_id"]):
            user_service.record_pdf_generation(user["user_id"])

        with file_path.open("rb") as pdf_file:
            await query.message.reply_document(
                document=pdf_file,
                caption="✅ PDF generated successfully.",
            )
