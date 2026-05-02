from telegram import Update
from telegram.ext import ContextTypes

from services.question_service import get_questions
from services.pdf_service import generate_pdf

async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # 👉 example: SSC exam
    questions = get_questions()   # tum apna logic lagao

    if not questions:
        await update.message.reply_text("⚠ No questions found")
        return

    file_path = generate_pdf(questions)

    await update.message.reply_document(document=open(file_path, "rb"))