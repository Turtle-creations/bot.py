<<<<<<< HEAD
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

=======
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

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    context.user_data["mode"] = None