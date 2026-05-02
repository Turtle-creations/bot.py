from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import BASE_DIR, IMAGE_DIR
from keyboards.app_keyboards import admin_keyboard, back_to_main_keyboard
from services.exam_service_db import exam_service
from services.notification_service_db import notification_service
from services.premium_service_db import premium_service
from services.user_service_db import user_service


def _is_admin(user_id: int) -> bool:
    return user_service.is_admin(user_id)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = user_service.ensure_user(update.effective_user)
    if not user_service.is_admin(user["user_id"]):
        await update.effective_message.reply_text("You are not allowed to open the admin panel.")
        return

    context.user_data["admin_mode"] = None
    await update.effective_message.reply_text(
        "<b>Admin Panel</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_service.ensure_user(query.from_user)
    if not _is_admin(query.from_user.id):
        await query.message.reply_text("Admin access only.")
        return

    action = query.data.split(":", 1)[1]
    context.user_data["admin_mode"] = None

    if action == "panel":
        await query.message.reply_text(
            "<b>Admin Panel</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    prompts = {
        "add_exam": "Send exam title",
        "delete_exam": "Send exam ID",
        "add_set": "Send: exam_id | set title",
        "delete_set": "Send set ID",
        "add_question": (
            "Send question in this format:\n\n"
            "exam_id | set_id\n"
            "Question text\n"
            "Option A\n"
            "Option B\n"
            "Option C\n"
            "Option D\n"
            "Correct option (A/B/C/D)\n"
            "Image path or leave blank\n"
            "Time limit in seconds"
        ),
        "delete_question": "Send question ID",
        "broadcast": "Send the broadcast message",
        "schedule": (
            "Send schedule in one line:\n"
            "daily|HH:MM|Message\n"
            "or\n"
            "weekly|0-6|HH:MM|Message\n"
            "0=Monday, 6=Sunday"
        ),
        "upgrade_premium": "Send: user_id | days",
        "downgrade_premium": "Send user_id",
    }

    if action in prompts:
        context.user_data["admin_mode"] = action
        await query.message.reply_text(prompts[action])
        return

    if action == "view_exams":
        exams = exam_service.get_exams()
        if not exams:
            await query.message.reply_text("No exams found.", reply_markup=back_to_main_keyboard())
            return

        lines = ["<b>Exams</b>\n"]
        for exam in exams:
            lines.append(
                f"{exam['exam_id']}. {exam['title']} | sets={exam['set_count']} | questions={exam['question_count']}"
            )

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if action == "view_premium":
        premium_users = premium_service.list_premium_users()
        if not premium_users:
            await query.message.reply_text(
                "No active premium users found.",
                reply_markup=back_to_main_keyboard(),
            )
            return

        lines = ["<b>Premium Users</b>\n"]
        for item in premium_users:
            lines.append(
                f"{item['user_id']} - {item['full_name']} - expires {item['premium_expires_at']}"
            )

        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_main_keyboard(),
        )


async def admin_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_service.ensure_user(update.effective_user)
    if not _is_admin(update.effective_user.id):
        return

    mode = context.user_data.get("admin_mode")
    if not mode or not update.effective_message:
        return

    text = update.effective_message.text.strip()

    try:
        if mode == "add_exam":
            exam_service.add_exam(text)
            await update.effective_message.reply_text("Exam created successfully.")

        elif mode == "delete_exam":
            exam_service.delete_exam(int(text))
            await update.effective_message.reply_text("Exam deleted successfully.")

        elif mode == "add_set":
            exam_id_text, set_title = [part.strip() for part in text.split("|", 1)]
            exam_service.add_set(int(exam_id_text), set_title)
            await update.effective_message.reply_text("Set created successfully.")

        elif mode == "delete_set":
            exam_service.delete_set(int(text))
            await update.effective_message.reply_text("Set deleted successfully.")

        elif mode == "add_question":
            lines = [line.strip() for line in text.splitlines()]
            if len(lines) < 9:
                raise ValueError("Question payload is incomplete")

            exam_id_text, set_id_text = [part.strip() for part in lines[0].split("|", 1)]
            image_value = lines[7] or context.user_data.get("pending_question_image")
            exam_service.add_question(
                exam_id=int(exam_id_text),
                set_id=int(set_id_text),
                question_text=lines[1],
                options=lines[2:6],
                correct_option=lines[6],
                image_path=image_value,
                time_limit=int(lines[8]),
            )
            context.user_data["pending_question_image"] = None
            await update.effective_message.reply_text("Question added successfully.")

        elif mode == "delete_question":
            exam_service.delete_question(int(text))
            await update.effective_message.reply_text("Question deleted successfully.")

        elif mode == "broadcast":
            sent, failed = await notification_service.broadcast(text)
            await update.effective_message.reply_text(
                f"Broadcast completed. Sent: {sent}, Failed: {failed}"
            )

        elif mode == "schedule":
            parts = text.split("|", 3)
            if parts[0] == "daily" and len(parts) == 3:
                _, send_time, message = parts
                notification_service.create_schedule("daily", message.strip(), send_time.strip())
            elif parts[0] == "weekly" and len(parts) == 4:
                _, day, send_time, message = parts
                notification_service.create_schedule(
                    "weekly",
                    message.strip(),
                    send_time.strip(),
                    day_of_week=int(day.strip()),
                )
            else:
                raise ValueError("Schedule format is invalid")

            await update.effective_message.reply_text("Notification schedule saved.")

        elif mode == "upgrade_premium":
            user_id_text, days_text = [part.strip() for part in text.split("|", 1)]
            result = premium_service.upgrade_user(int(user_id_text), int(days_text))
            if not result:
                await update.effective_message.reply_text("User not found.")
            else:
                await update.effective_message.reply_text(
                    f"Premium activated for {result['full_name']} until {result['premium_expires_at']}."
                )

        elif mode == "downgrade_premium":
            result = premium_service.downgrade_user(int(text))
            await update.effective_message.reply_text(
                f"Premium removed for {result['full_name']}."
            )

    except Exception as exc:
        await update.effective_message.reply_text(f"Admin action failed: {exc}")
    finally:
        context.user_data["admin_mode"] = None


async def admin_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not _is_admin(update.effective_user.id):
        return

    if context.user_data.get("admin_mode") != "add_question":
        return

    photo = update.effective_message.photo[-1]
    file = await photo.get_file()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    relative_path = Path("data") / "images" / f"{photo.file_unique_id}.jpg"
    absolute_path = BASE_DIR / relative_path

    await file.download_to_drive(str(absolute_path))
    context.user_data["pending_question_image"] = str(relative_path).replace("\\", "/")

    await update.effective_message.reply_text(
        "Question image uploaded. Now send the question payload and leave the image path line blank to use this image."
    )
