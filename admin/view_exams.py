<<<<<<< HEAD
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

=======
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

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    await query.message.reply_text(text)