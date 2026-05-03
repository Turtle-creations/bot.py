# -*- coding: utf-8 -*-

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


WEEKDAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎯 Quiz", callback_data="menu:quiz"),
            InlineKeyboardButton("👤 Profile", callback_data="profile:view"),
        ],
        [
            InlineKeyboardButton("💎 Premium", callback_data="premium:view"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard:view"),
        ],
        [
            InlineKeyboardButton("📄 Generate PDF", callback_data="pdf:start"),
            InlineKeyboardButton("❓ Help", callback_data="help:view"),
        ],
        [InlineKeyboardButton("Customer Support", callback_data="support:start")],
    ]

    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin:panel")])

    return InlineKeyboardMarkup(rows)


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu:main")]])


def support_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="support:cancel")]])


def premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Buy Premium", callback_data="premium:subscribe")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
        ]
    )


def premium_plan_keyboard(plans: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"💎 {plan['name']}", callback_data=f"premium:plan:{plan['plan_type']}")]
        for plan in plans
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="premium:view")])
    return InlineKeyboardMarkup(rows)


def payment_link_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Pay with Razorpay", url=payment_url)],
            [InlineKeyboardButton("⬅️ Back", callback_data="premium:view")],
        ]
    )


def exam_keyboard(exams: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(exam["title"], callback_data=f"quiz:exam:{exam['exam_id']}")]
        for exam in exams
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def set_keyboard(exam_id: int, sets_: list[dict], show_lock_icons: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                (
                    f"🔒 {set_['title']}"
                    if show_lock_icons and int(set_.get("is_premium_locked", 0))
                    else set_["title"]
                ),
                callback_data=f"quiz:set:{exam_id}:{set_['set_id']}",
            )
        ]
        for set_ in sets_
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:quiz")])
    return InlineKeyboardMarkup(rows)


def question_count_keyboard(counts: list[int], exam_id: int, set_id: int) -> InlineKeyboardMarkup:
    rows = []
    row = []

    for count in counts:
        row.append(
            InlineKeyboardButton(
                str(count),
                callback_data=f"quiz:count:{exam_id}:{set_id}:{count}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"quiz:exam:{exam_id}")])
    return InlineKeyboardMarkup(rows)


def answer_keyboard(question_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("A", callback_data=f"quiz:answer:{question_id}:A")],
        [InlineKeyboardButton("B", callback_data=f"quiz:answer:{question_id}:B")],
        [InlineKeyboardButton("C", callback_data=f"quiz:answer:{question_id}:C")],
        [InlineKeyboardButton("D", callback_data=f"quiz:answer:{question_id}:D")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_keyboard(can_manage_admins: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ Add Exam", callback_data="admin:add_exam"),
            InlineKeyboardButton("🗑 Delete Exam", callback_data="admin:delete_exam"),
        ],
        [
            InlineKeyboardButton("➕ Add Set", callback_data="admin:add_set"),
            InlineKeyboardButton("🗑 Delete Set", callback_data="admin:delete_set"),
        ],
        [
            InlineKeyboardButton("🔒 Lock Set", callback_data="admin:lock_set"),
            InlineKeyboardButton("🔓 Unlock Set", callback_data="admin:unlock_set"),
        ],
        [
            InlineKeyboardButton("➕ Add Question", callback_data="admin:add_question"),
            InlineKeyboardButton("🗑 Delete Question", callback_data="admin:delete_question"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
            InlineKeyboardButton("⏰ Schedule Notify", callback_data="admin:schedule"),
        ],
        [
            InlineKeyboardButton("💎 Upgrade Premium", callback_data="admin:upgrade_premium"),
            InlineKeyboardButton("↩️ Downgrade Premium", callback_data="admin:downgrade_premium"),
        ],
        [
            InlineKeyboardButton("💰 View Premium Prices", callback_data="admin:view_premium_prices"),
            InlineKeyboardButton("✏️ Change Premium Price", callback_data="admin:change_premium_price"),
        ],
        [
            InlineKeyboardButton("📚 View Exams", callback_data="admin:view_exams"),
            InlineKeyboardButton("👑 View Premium Users", callback_data="admin:view_premium"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ]

    if can_manage_admins:
        rows.insert(
            2,
            [
                InlineKeyboardButton("👥 Add Admin", callback_data="admin:add_admin"),
                InlineKeyboardButton("🚫 Remove Admin", callback_data="admin:remove_admin"),
            ],
        )
        rows.insert(3, [InlineKeyboardButton("🛡 View Admins", callback_data="admin:view_admins")])

    return InlineKeyboardMarkup(rows)


def admin_exam_keyboard(exams: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(exam["title"], callback_data=f"{prefix}:{exam['exam_id']}")]
        for exam in exams
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:panel")])
    return InlineKeyboardMarkup(rows)


def admin_set_keyboard(sets_: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{set_['title']} {'(Locked)' if int(set_.get('is_premium_locked', 0)) else '(Unlocked)'}",
                callback_data=f"{prefix}:{set_['set_id']}",
            )
        ]
        for set_ in sets_
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:panel")])
    return InlineKeyboardMarkup(rows)


def admin_question_search_keyboard(questions: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for question in questions:
        snippet = question["question_text"]
        if len(snippet) > 60:
            snippet = f"{snippet[:57]}..."
        label = f"{question['exam_title']} / {question['set_title']} - {snippet}"
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}:{question['question_id']}")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="admin:panel")])
    return InlineKeyboardMarkup(rows)


def admin_user_keyboard(users: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(user["full_name"], callback_data=f"{prefix}:{user['user_id']}")]
        for user in users
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:panel")])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard(confirm_callback: str, cancel_callback: str = "admin:panel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=confirm_callback)],
            [InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)],
        ]
    )


def skip_image_keyboard(callback_data: str = "admin:qadd_skip_image") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip Image", callback_data=callback_data)]])


def correct_answer_keyboard(
    options: list[str],
    prefix: str = "admin:qadd_correct",
) -> InlineKeyboardMarkup:
    rows = []
    for index, option in enumerate(options, start=1):
        rows.append([InlineKeyboardButton(f"✅ {option}", callback_data=f"{prefix}:{index}")])
    return InlineKeyboardMarkup(rows)


def pdf_exam_keyboard(exams: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(exam["title"], callback_data=f"pdf:exam:{exam['exam_id']}")]
        for exam in exams
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def pdf_set_keyboard(exam_id: int, sets_: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(set_["title"], callback_data=f"pdf:set:{exam_id}:{set_['set_id']}")]
        for set_ in sets_
    ]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="pdf:start")])
    return InlineKeyboardMarkup(rows)


def notification_schedule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Daily", callback_data="admin:notify:daily")],
            [InlineKeyboardButton("🗓 Weekly", callback_data="admin:notify:weekly")],
            [InlineKeyboardButton("📋 View Saved Notifications", callback_data="admin:notify:view")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin:panel")],
        ]
    )


def notification_weekday_keyboard(selected_days: set[int] | list[int]) -> InlineKeyboardMarkup:
    selected = set(selected_days)
    rows = []
    day_order = list(WEEKDAY_LABELS.items())

    for index in range(0, len(day_order), 2):
        row = []
        for day_value, label in day_order[index:index + 2]:
            prefix = "✅ " if day_value in selected else ""
            row.append(
                InlineKeyboardButton(
                    f"{prefix}{label}",
                    callback_data=f"admin:notify:day:{day_value}",
                )
            )
        rows.append(row)

    rows.append([InlineKeyboardButton("➡️ Continue", callback_data="admin:notify:days_done")])
    rows.append([InlineKeyboardButton("⬅️ Cancel", callback_data="admin:notify:menu")])
    return InlineKeyboardMarkup(rows)


def notification_hour_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for hour in range(24):
        row.append(
            InlineKeyboardButton(
                f"{hour:02d}",
                callback_data=f"admin:notify:hour:{hour:02d}",
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton("⬅️ Cancel", callback_data="admin:notify:menu")])
    return InlineKeyboardMarkup(rows)


def notification_minute_keyboard(selected_hour: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{selected_hour}:00",
                callback_data="admin:notify:minute:00",
            ),
            InlineKeyboardButton(
                f"{selected_hour}:15",
                callback_data="admin:notify:minute:15",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{selected_hour}:30",
                callback_data="admin:notify:minute:30",
            ),
            InlineKeyboardButton(
                f"{selected_hour}:45",
                callback_data="admin:notify:minute:45",
            ),
        ],
        [InlineKeyboardButton("⬅️ Cancel", callback_data="admin:notify:menu")],
    ]
    return InlineKeyboardMarkup(rows)


def saved_notifications_keyboard(notifications: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in notifications:
        type_label = "Daily" if item["kind"] == "daily" else "Weekly"
        schedule_bits = [type_label, item.get("send_time") or "--:--"]
        if item["kind"] == "weekly" and item.get("days_text"):
            schedule_bits.append(item["days_text"])
        status = "Active" if item.get("is_active") else "Inactive"
        label = f"📩 #{item['notification_id']} {' | '.join(schedule_bits)} | {status}"
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"admin:notify:view:{item['notification_id']}",
                )
            ]
        )

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:notify:menu")])
    return InlineKeyboardMarkup(rows)


def notification_detail_keyboard(notification_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📨 Test Notification Now", callback_data=f"admin:notify:test_send:{notification_id}")],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"admin:notify:delete:{notification_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin:notify:view")],
        ]
    )


def notification_delete_confirm_keyboard(notification_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"admin:notify:confirm_delete:{notification_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin:notify:cancel_delete:{notification_id}")],
        ]
    )


def quiz_question_keyboard(
    options: list[dict],
    question_id: int,
    question_token: str,
    *,
    locked: bool = False,
    selected_index: int | None = None,
    correct_index: int | None = None,
    paused: bool = False,
) -> InlineKeyboardMarkup:
    rows = []

    for index, option in enumerate(options):
        prefix = ""
        callback = f"quiz:pick:{question_id}:{question_token}:{index}"

        if locked or paused:
            callback = "quiz:noop"
        if locked:
            if correct_index == index:
                prefix = "✅ "
            elif selected_index == index:
                prefix = "❌ "
            else:
                prefix = "▫️ "

        rows.append([InlineKeyboardButton(f"{prefix}{option['text']}", callback_data=callback)])

    if locked:
        control_row = [
            InlineKeyboardButton("❌ End Quiz", callback_data=f"quiz:end:{question_id}:{question_token}")
        ]
    else:
        control_row = [
            InlineKeyboardButton("⏩ Skip", callback_data=f"quiz:skip:{question_id}:{question_token}"),
            InlineKeyboardButton("❌ End Quiz", callback_data=f"quiz:end:{question_id}:{question_token}"),
        ]
        if paused:
            control_row.insert(
                0,
                InlineKeyboardButton("▶ Resume", callback_data=f"quiz:resume:{question_id}:{question_token}"),
            )
        else:
            control_row.insert(
                0,
                InlineKeyboardButton("⏸ Pause", callback_data=f"quiz:pause:{question_id}:{question_token}"),
            )

    rows.append(control_row)
    return InlineKeyboardMarkup(rows)
