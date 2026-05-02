from datetime import datetime, timedelta

from utils.file_manager import load_json, save_json


FILE = "data/subscriptions.json"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

PREMIUM_PLANS = [
    {"code": "weekly", "label": "7 Days", "days": 7},
    {"code": "monthly", "label": "30 Days", "days": 30},
    {"code": "quarterly", "label": "90 Days", "days": 90},
]


def _now():
    return datetime.now()


def _parse(dt_str):
    if not dt_str:
        return None

    try:
        return datetime.strptime(dt_str, DATE_FMT)
    except Exception:
        return None


def _format(dt):
    return dt.strftime(DATE_FMT)


def _all():
    data = load_json(FILE)
    return data if isinstance(data, list) else []


def _save(items):
    save_json(FILE, items)


def get_subscription(user_id):
    for item in _all():
        if item.get("user_id") == user_id:
            return item
    return None


def is_premium_active(user_id):
    sub = get_subscription(user_id)

    if not sub:
        return False

    expires_at = _parse(sub.get("expires_at"))
    return bool(expires_at and expires_at > _now())


def get_status_text(user_id):
    sub = get_subscription(user_id)

    if not sub:
        return "Free"

    expires_at = _parse(sub.get("expires_at"))

    if not expires_at:
        return "Free"

    if expires_at <= _now():
        return f"Expired on {expires_at.strftime('%d %b %Y, %I:%M %p')}"

    return f"Active until {expires_at.strftime('%d %b %Y, %I:%M %p')}"


def activate_subscription(user_id, name, days, activated_by=None):
    days = int(days)
    items = _all()
    now = _now()
    current = None

    for item in items:
        if item.get("user_id") == user_id:
            current = item
            break

    current_expiry = _parse(current.get("expires_at")) if current else None
    start = current_expiry if current_expiry and current_expiry > now else now
    expires_at = start + timedelta(days=days)

    payload = {
        "user_id": user_id,
        "name": name,
        "days": days,
        "is_active": True,
        "activated_at": _format(now),
        "expires_at": _format(expires_at),
        "activated_by": activated_by,
    }

    if current:
        current.update(payload)
    else:
        items.append(payload)

    _save(items)
    return payload


def get_active_subscribers():
    active = []

    for item in _all():
        expires_at = _parse(item.get("expires_at"))

        if expires_at and expires_at > _now():
            active.append(item)

    active.sort(key=lambda item: item.get("expires_at", ""))
    return active
