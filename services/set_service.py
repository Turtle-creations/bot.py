from utils.file_manager import load_json, save_json

FILE = "data/exams.json"

# ---------------- REORDER SET SERIAL ----------------
def reorder_set_serials(sets):
    for i, s in enumerate(sets, start=1):
        s["serial"] = i
    return sets

# ---------------- GET SETS ----------------
def get_sets(exam_id):

    exams = load_json(FILE)

    for exam in exams:
        if exam["id"] == exam_id:
            return exam.get("sets", [])

    return []

# ---------------- ADD SET ----------------
def add_set(exam_id, set_name):

    exams = load_json(FILE)

    for exam in exams:

        if exam["id"] == exam_id:

            # duplicate check
            for s in exam.get("sets", []):
                if s["name"].lower() == set_name.strip().lower():
                    return False

            sets = exam.get("sets", [])

            new_id = max([s["id"] for s in sets], default=0) + 1
            new_serial = len(sets) + 1

            new_set = {
                "id": new_id,
                "serial": new_serial,
                "name": set_name.strip(),
                "questions": []
            }

            exam.setdefault("sets", []).append(new_set)

            save_json(FILE, exams)
            return True

    return None

# ---------------- DELETE SET ----------------
def delete_set(exam_id, set_id):

    exams = load_json(FILE)

    for exam in exams:

        if exam["id"] == exam_id:

            new_sets = []
            deleted = False

            for s in exam.get("sets", []):

                if str(s["id"]) == str(set_id):
                    deleted = True
                    continue

                new_sets.append(s)

            # 🔥 reorder after delete
            exam["sets"] = reorder_set_serials(new_sets)

            save_json(FILE, exams)

            return deleted

    return False

# ---------------- DELETE SET BY NAME ----------------
def delete_set_by_name(exam_id, set_name):

    exams = load_json(FILE)

    for exam in exams:

        if exam["id"] == exam_id:

            new_sets = []
            deleted = False

            for s in exam.get("sets", []):

                if s["name"].lower() == set_name.strip().lower():
                    deleted = True
                    continue

                new_sets.append(s)

            # 🔥 reorder after delete
            exam["sets"] = reorder_set_serials(new_sets)

            save_json(FILE, exams)

            return deleted

    return False