from utils.file_manager import load_json, save_json

FILE = "data/exams.json"

# ---------------- REORDER SERIAL ----------------
def reorder_exam_serials(exams):
    for i, exam in enumerate(exams, start=1):
        exam["serial"] = i
    return exams

# ---------------- GET ALL ----------------
def get_all_exams():
    return load_json(FILE)

# ---------------- GET EXAM ID ----------------
def get_exam_id_by_name(name):
    exams = load_json(FILE)

    for exam in exams:
        if exam["name"].strip().lower() == name.strip().lower():
            return exam["id"]

    return None

# ---------------- ADD EXAM ----------------
def add_exam(name):

    if not name or not name.strip():
        return None

    exams = load_json(FILE)

    # duplicate check
    for exam in exams:
        if exam["name"].lower() == name.strip().lower():
            return False

    new_id = max([e["id"] for e in exams], default=100) + 1
    new_serial = len(exams) + 1

    new_exam = {
        "id": new_id,
        "serial": new_serial,
        "name": name.strip(),
        "sets": []
    }

    exams.append(new_exam)
    save_json(FILE, exams)

    return True

# ---------------- DELETE EXAM ----------------
def delete_exam(value):

    exams = load_json(FILE)

    new_list = []
    deleted = False

    for exam in exams:
        if str(exam["id"]) == str(value) or exam["name"].lower() == str(value).lower():
            deleted = True
            continue
        new_list.append(exam)

    # 🔥 reorder after delete
    new_list = reorder_exam_serials(new_list)

    save_json(FILE, new_list)

    return deleted



def get_exams():
    return get_all_exams()