<<<<<<< HEAD
from utils.file_manager import load_json, save_json

FILE = "data/users.json"


def save_user(user_id):

    users = load_json(FILE)

    if user_id not in users:
        users.append(user_id)

        save_json(FILE, users)

        print("User saved:", user_id)



# ---------------- GET USER ----------------
def get_user(user_id):

    users = load_json(FILE)

    for u in users:
        if u["id"] == user_id:
            return u

    return None


# ---------------- CREATE USER ----------------
def create_user(user_id, name):

    users = load_json(FILE)

    user = {
        "id": user_id,
        "name": name,
        "quiz_played": 0,
        "score": 0,
        "correct": 0,
        "wrong": 0
    }

    users.append(user)
    save_json(FILE, users)

    return user


# ---------------- GET OR CREATE ----------------
def get_or_create_user(user_id, name):

    user = get_user(user_id)

    if user:
        return user

    return create_user(user_id, name)

#------------lederboard -----------
def get_top_users(limit=10):
    users = load_json(FILE)

    # safe filtering
    users = [u for u in users if isinstance(u, dict)]

    # sort by score
    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    return users[:limit]

def get_badge(score):

    if score >= 1000:
        return "👑 Legend"

    elif score >= 500:
        return "🔥 Pro"

    elif score >= 200:
        return "💎 Expert"

    elif score >= 100:
        return "⭐ Intermediate"

    else:
        return "🆕 Beginner"
    
def get_user_rank(user_id):
    users = load_json(FILE)

    users = [u for u in users if isinstance(u, dict)]

    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, u in enumerate(users, 1):
        if u["id"] == user_id:
            return i

    return None

def get_rank_badge(rank):

    if rank == 1:
        return "🥇 Topper"

    elif rank <= 5:
        return "🔥 Top 5"

    elif rank <= 10:
        return "💎 Top 10"

    else:
        return ""

def get_user_rank(user_id):
    users = load_json(FILE)

    # safety (kabhi int aa jata hai)
    users = [u for u in users if isinstance(u, dict)]

    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, u in enumerate(users, 1):
        if u["id"] == user_id:
            return i

=======
from utils.file_manager import load_json, save_json

FILE = "data/users.json"


def save_user(user_id):

    users = load_json(FILE)

    if user_id not in users:
        users.append(user_id)

        save_json(FILE, users)

        print("User saved:", user_id)



# ---------------- GET USER ----------------
def get_user(user_id):

    users = load_json(FILE)

    for u in users:
        if u["id"] == user_id:
            return u

    return None


# ---------------- CREATE USER ----------------
def create_user(user_id, name):

    users = load_json(FILE)

    user = {
        "id": user_id,
        "name": name,
        "quiz_played": 0,
        "score": 0,
        "correct": 0,
        "wrong": 0
    }

    users.append(user)
    save_json(FILE, users)

    return user


# ---------------- GET OR CREATE ----------------
def get_or_create_user(user_id, name):

    user = get_user(user_id)

    if user:
        return user

    return create_user(user_id, name)

#------------lederboard -----------
def get_top_users(limit=10):
    users = load_json(FILE)

    # safe filtering
    users = [u for u in users if isinstance(u, dict)]

    # sort by score
    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    return users[:limit]

def get_badge(score):

    if score >= 1000:
        return "👑 Legend"

    elif score >= 500:
        return "🔥 Pro"

    elif score >= 200:
        return "💎 Expert"

    elif score >= 100:
        return "⭐ Intermediate"

    else:
        return "🆕 Beginner"
    
def get_user_rank(user_id):
    users = load_json(FILE)

    users = [u for u in users if isinstance(u, dict)]

    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, u in enumerate(users, 1):
        if u["id"] == user_id:
            return i

    return None

def get_rank_badge(rank):

    if rank == 1:
        return "🥇 Topper"

    elif rank <= 5:
        return "🔥 Top 5"

    elif rank <= 10:
        return "💎 Top 10"

    else:
        return ""

def get_user_rank(user_id):
    users = load_json(FILE)

    # safety (kabhi int aa jata hai)
    users = [u for u in users if isinstance(u, dict)]

    users.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, u in enumerate(users, 1):
        if u["id"] == user_id:
            return i

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return None