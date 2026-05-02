from services.exam_service import delete_exam


async def handle_delete_exam(update, context):

    text = update.message.text

    ok = delete_exam(text)

    if ok:

        await update.message.reply_text(
            "🗑 Exam deleted successfully"
        )

    else:

        await update.message.reply_text(
            "❌ Exam not found"
        )

    context.user_data["mode"] = None