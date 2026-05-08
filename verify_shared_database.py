import sys

from config import DATABASE_BACKEND, DATABASE_DSN
from db.database import database
from services.exam_service_db import exam_service


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    database.initialize()

    print(f"backend={DATABASE_BACKEND}")
    print(f"dsn={DATABASE_DSN}")

    tables = [
        "users",
        "exams",
        "exam_sets",
        "questions",
        "quiz_attempts",
        "payment_orders",
        "payments",
    ]

    with database.connection() as conn:
        for table_name in tables:
            count = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"]
            print(f"{table_name}_count={count}")

        sample_question = conn.execute(
            """
            SELECT q.question_id, q.question_text, e.title AS exam_title, s.title AS set_title
            FROM questions q
            JOIN exams e ON e.exam_id = q.exam_id
            JOIN exam_sets s ON s.set_id = q.set_id
            ORDER BY q.question_id DESC
            LIMIT 1
            """
        ).fetchone()

        if sample_question:
            print(f"sample_question_id={sample_question['question_id']}")
            print(f"sample_exam_title={sample_question['exam_title']}")
            print(f"sample_set_title={sample_question['set_title']}")
            print(f"sample_question_text={sample_question['question_text']}")
        else:
            print("sample_question_id=")

    exams = exam_service.get_exams()
    print(f"bot_visible_exam_count={len(exams)}")
    if exams:
        first_exam = exams[0]
        sets = exam_service.get_sets(first_exam["exam_id"])
        print(f"first_exam_title={first_exam['title']}")
        print(f"first_exam_set_count={len(sets)}")
        if sets:
            questions = exam_service.get_questions(sets[0]["set_id"])
            print(f"first_set_title={sets[0]['title']}")
            print(f"first_set_question_count={len(questions)}")


if __name__ == "__main__":
    main()
