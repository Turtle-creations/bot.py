<<<<<<< HEAD
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

=======
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

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return result