<<<<<<< HEAD
import random
import time

user_sessions = {}

# ---------------- START QUIZ ----------------

def start_quiz(user_id, questions):

    random.shuffle(questions)

    user_sessions[user_id] = {
        "questions": questions,
        "index": 0,
        "score": 0,
        "wrong": 0,
        "paused": False,
        "start_time": time.time(),
        "answered": False,
        "timer_running": False   # 🔥 ADD THIS
    }
# ---------------- CURRENT QUESTION ----------------

def get_current_question(user_id):

    session = user_sessions.get(user_id)

    if not session:
        return None

    if session["index"] >= len(session["questions"]):
        return None

    # 🔥 हर नए question पर reset
    session["answered"] = False

    return session["questions"][session["index"]]


# ---------------- TIME CHECK ----------------

def is_time_over(user_id):

    session = user_sessions.get(user_id)

    if not session or session.get("paused"):
        return False

    # 🔥 FIX: अगर quiz खत्म हो गया तो stop
    if session["index"] >= len(session["questions"]):
        return False

    q = session["questions"][session["index"]]

    limit = q.get("time", 30)

    return time.time() - session["start_time"] > limit
# ---------------- NEXT QUESTION ----------------

def next_question(user_id):

    session = user_sessions[user_id]

    session["index"] += 1
    session["start_time"] = time.time()
    session["answered"] = False   # 🔥 reset


# ---------------- CHECK ANSWER ----------------

def check_answer(user_id, selected):

    session = user_sessions[user_id]
    question = session["questions"][session["index"]]

    correct_ans = question["answer"]

    # 🔥 mark answered → timer stop
    session["answered"] = True

    if selected.strip().lower() == correct_ans.strip().lower():
        session["score"] += 1
        result = True
    else:
        session["score"] -= 0.25
        session["wrong"] += 1
        result = False

    # next question move
    session["index"] += 1
    session["start_time"] = time.time()

    return result, correct_ans


# ---------------- PAUSE / RESUME ----------------

def pause_quiz(user_id):

    if user_id in user_sessions:
        user_sessions[user_id]["paused"] = True


def resume_quiz(user_id):

    if user_id in user_sessions:
        user_sessions[user_id]["paused"] = False
        user_sessions[user_id]["start_time"] = time.time()


# ---------------- SCORE ----------------

def get_score(user_id):

    session = user_sessions[user_id]

=======
import random
import time

user_sessions = {}

# ---------------- START QUIZ ----------------

def start_quiz(user_id, questions):

    random.shuffle(questions)

    user_sessions[user_id] = {
        "questions": questions,
        "index": 0,
        "score": 0,
        "wrong": 0,
        "paused": False,
        "start_time": time.time(),
        "answered": False,
        "timer_running": False   # 🔥 ADD THIS
    }
# ---------------- CURRENT QUESTION ----------------

def get_current_question(user_id):

    session = user_sessions.get(user_id)

    if not session:
        return None

    if session["index"] >= len(session["questions"]):
        return None

    # 🔥 हर नए question पर reset
    session["answered"] = False

    return session["questions"][session["index"]]


# ---------------- TIME CHECK ----------------

def is_time_over(user_id):

    session = user_sessions.get(user_id)

    if not session or session.get("paused"):
        return False

    # 🔥 FIX: अगर quiz खत्म हो गया तो stop
    if session["index"] >= len(session["questions"]):
        return False

    q = session["questions"][session["index"]]

    limit = q.get("time", 30)

    return time.time() - session["start_time"] > limit
# ---------------- NEXT QUESTION ----------------

def next_question(user_id):

    session = user_sessions[user_id]

    session["index"] += 1
    session["start_time"] = time.time()
    session["answered"] = False   # 🔥 reset


# ---------------- CHECK ANSWER ----------------

def check_answer(user_id, selected):

    session = user_sessions[user_id]
    question = session["questions"][session["index"]]

    correct_ans = question["answer"]

    # 🔥 mark answered → timer stop
    session["answered"] = True

    if selected.strip().lower() == correct_ans.strip().lower():
        session["score"] += 1
        result = True
    else:
        session["score"] -= 0.25
        session["wrong"] += 1
        result = False

    # next question move
    session["index"] += 1
    session["start_time"] = time.time()

    return result, correct_ans


# ---------------- PAUSE / RESUME ----------------

def pause_quiz(user_id):

    if user_id in user_sessions:
        user_sessions[user_id]["paused"] = True


def resume_quiz(user_id):

    if user_id in user_sessions:
        user_sessions[user_id]["paused"] = False
        user_sessions[user_id]["start_time"] = time.time()


# ---------------- SCORE ----------------

def get_score(user_id):

    session = user_sessions[user_id]

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return session["score"], len(session["questions"])