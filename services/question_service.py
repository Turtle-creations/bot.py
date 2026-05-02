from utils.file_manager import load_json, save_json

FILE = "data/exams.json"

def add_question(exam_id, set_id, question, options, answer, image_path=None, time_limit=None):
    
    exams = load_json(FILE)

    for exam in exams:
        if exam["id"] == exam_id:

            for s in exam.get("sets", []):
                if s["id"] == set_id:

                    for q in s.get("questions", []):
                        if q["question"].strip().lower() == question.strip().lower():
                            return False

                    new_q = {
                        "question": question.strip(),
                        "options": options,
                        "answer": answer.strip()
                    }
                    
                    # ✅ IMAGE SUPPORT
                    if image_path:
                       new_question["image"] = image_path


                    if time_limit:
                        try:
                            new_q["time"] = int(time_limit)
                        except:
                            pass

                    s.setdefault("questions", []).append(new_q)

                    save_json(FILE, exams)
                    return True

    return None

def get_questions(exam_id, set_id):
    exams = load_json(FILE)

    for exam in exams:
        if exam["id"] == exam_id:
            for s in exam.get("sets", []):
                if s["id"] == set_id:
                    return s.get("questions", [])

    return []

def delete_question(exam_id, set_id, question_text):
    exams = load_json(FILE)

    for exam in exams:
        if exam["id"] == exam_id:

            for s in exam.get("sets", []):
                if s["id"] == set_id:

                    new_list = []
                    deleted = False

                    for q in s.get("questions", []):
                        if q["question"].strip().lower() == question_text.strip().lower():
                            deleted = True
                            continue
                        new_list.append(q)

                    s["questions"] = new_list
                    save_json(FILE, exams)
                    return deleted

    return False