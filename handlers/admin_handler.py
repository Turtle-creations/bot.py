from telegram import Update
from telegram.ext import ContextTypes

from keyboards.admin_keyboard import admin_menu
from admin.add_exam import handle_add_exam
from admin.view_exams import handle_view_exams
from admin.delete_exam import handle_delete_exam

from services.set_service import add_set, get_sets, delete_set
from services.exam_service import get_exam_id_by_name
from services.question_service import add_question, delete_question
from services.premium_service import activate_subscription, get_active_subscribers

from utils.helpers import is_double_click
from utils.image_handler import save_image


# ---------------- ADMIN PANEL ----------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None

    await update.message.reply_text(
        "⚙ Admin Panel",
        reply_markup=admin_menu()
    )


# ---------------- ADMIN BUTTONS ----------------
async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    await query.answer()

    if is_double_click(context, "admin_click", 1):
        return

    context.user_data["mode"] = None

    if data == "add_exam":
        context.user_data["mode"] = "add_exam"
        await query.message.reply_text("✏ Send exam name")

    elif data == "view_exams":
        await handle_view_exams(update, context)

    elif data == "delete_exam":
        context.user_data["mode"] = "delete_exam"
        await query.message.reply_text("🗑 Send Exam ID or Name")

    elif data == "add_set":
        context.user_data["mode"] = "add_set"
        await query.message.reply_text("Example:\nSSC Set-1")

    elif data == "view_sets":
        context.user_data["mode"] = "view_sets"
        await query.message.reply_text("Send Exam Name")

    elif data == "delete_set":
        context.user_data["mode"] = "delete_set"
        await query.message.reply_text("Example:\nSSC Set-1")

    elif data == "add_question":
        context.user_data["mode"] = "add_question"
        context.user_data["awaiting_image"] = True
        await query.message.reply_text(
            "Format:\n\n"
            "SSC Set-1\n"
            "Question\n"
            "Option1\n"
            "Option2\n"
            "Option3\n"
            "Option4\n"
            "Correct option\n"
            "(optional) time"
        )

    elif data == "view_questions":
        context.user_data["mode"] = "view_questions"
        await query.message.reply_text("Send Exam Name")

    elif data == "delete_question":
        context.user_data["mode"] = "delete_question"
        await query.message.reply_text(
            "Send:\n\nSSC Set-1\nQuestion text"
        )

    elif data == "grant_premium":
        context.user_data["mode"] = "grant_premium"
        await query.message.reply_text(
            "Send:\n\nUser ID\nName\nDays\n\nExample:\n123456789\nRahul\n30"
        )

    elif data == "view_premium":
        users = get_active_subscribers()

        if not users:
            await query.message.reply_text("⚠ No active premium users")
            return

        msg = "💎 Premium Users\n\n"

        for item in users:
            msg += (
                f"ID: {item['user_id']}\n"
                f"Name: {item.get('name', 'Unknown')}\n"
                f"Expires: {item.get('expires_at', '-')}\n\n"
            )

        await query.message.reply_text(msg.strip())


# ---------------- IMAGE HANDLER ----------------
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("awaiting_image"):
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    path = save_image(file, photo.file_id)

    context.user_data["image_path"] = path

    await update.message.reply_text("✅ Image saved")


# ---------------- ADMIN TEXT ----------------
async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("notify_mode"):
        return

    mode = context.user_data.get("mode")

    if not mode:
        return

    text = update.message.text.strip()

    # -------- ADD EXAM --------
    if mode == "add_exam":

        result = await handle_add_exam(update, context)

        if result is True:
            await update.message.reply_text("✅ Exam added")
        elif result is False:
            await update.message.reply_text("❌ Exam already exists")
        else:
            await update.message.reply_text("❌ Error")

    # -------- DELETE EXAM --------
    elif mode == "delete_exam":

        result = await handle_delete_exam(update, context)

        if result:
            await update.message.reply_text("🗑 Exam deleted")
        else:
            await update.message.reply_text("❌ Exam not found")

    # -------- ADD SET --------
    elif mode == "add_set":

        try:
            exam_name, set_name = text.split(maxsplit=1)

            exam_id = get_exam_id_by_name(exam_name)

            if not exam_id:
                await update.message.reply_text("❌ Exam not found")
                return

            result = add_set(exam_id, set_name)

            if result is True:
                await update.message.reply_text("✅ Set added")
            elif result is False:
                await update.message.reply_text("❌ Set already exists")
            else:
                await update.message.reply_text("❌ Error")

        except:
            await update.message.reply_text("⚠ Format error")

    # -------- ADD QUESTION --------
    elif mode == "add_question":

        try:
            lines = text.split("\n")

            if len(lines) < 7:
                await update.message.reply_text("⚠ Format error")
                return

            first_line = lines[0]
            exam_name = first_line.rsplit(" ", 1)[0]
            set_name = first_line.rsplit(" ", 1)[1]

            question = lines[1]
            options = lines[2:6]
            answer = lines[6]
            time_limit = int(lines[7]) if len(lines) >= 8 else None

            exam_id = get_exam_id_by_name(exam_name)

            sets = get_sets(exam_id)

            set_id = None
            for s in sets:
                if s["name"].lower() == set_name.lower():
                    set_id = s["id"]

            if not set_id:
                await update.message.reply_text("❌ Set not found")
                return

            image_path = context.user_data.get("image_path")

            result = add_question(
                exam_id,
                set_id,
                question,
                options,
                answer,
                time_limit,
                image_path=image_path
            )

            # reset image
            context.user_data["image_path"] = None

            if result is True:
                await update.message.reply_text("✅ Question added")
            elif result is False:
                await update.message.reply_text("❌ Duplicate question")
            else:
                await update.message.reply_text("❌ Error")

        except Exception as e:
            print("ERROR:", e)
            await update.message.reply_text("⚠ Format error")

    # -------- GRANT PREMIUM --------
    elif mode == "grant_premium":

        try:
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            if len(lines) < 3:
                await update.message.reply_text("⚠ Format error")
                return

            user_id = int(lines[0])
            name = lines[1]
            days = int(lines[2])

            sub = activate_subscription(
                user_id=user_id,
                name=name,
                days=days,
                activated_by=update.effective_user.id,
            )

            await update.message.reply_text(
                "✅ Premium activated\n\n"
                f"User: {sub['name']}\n"
                f"Days: {sub['days']}\n"
                f"Expires: {sub['expires_at']}"
            )
            context.user_data["mode"] = None

        except Exception as e:
            print("PREMIUM ERROR:", e)
            await update.message.reply_text("⚠ Format error")
