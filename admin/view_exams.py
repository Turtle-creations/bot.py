from services.exam_service import get_exams


async def handle_view_exams(update, context):

    query = update.callback_query
    await query.answer()

    exams = get_exams()

    if not exams:

        await query.message.reply_text("No exams found")
        return

    text = "📚 Exams:\n\n"

    for e in exams:
        text += f"{e['id']}. {e['name']}\n"

    await query.message.reply_text(text)