from services.exam_service import add_exam

async def handle_add_exam(update, context):
    text = update.message.text.strip()

    # ❌ empty check
    if not text:
        return None

    # ❌ length check
    if len(text) < 3:
        return None

    # ✅ save exam
    result = add_exam(text)

    return result