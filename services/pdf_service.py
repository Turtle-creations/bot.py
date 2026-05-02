from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

def generate_pdf(questions, filename="quiz.pdf"):

    file_path = f"data/{filename}"

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    y = height - 40

    for i, q in enumerate(questions, 1):

        text = f"{i}. {q['question']}"
        c.drawString(40, y, text)
        y -= 20

        for opt in q["options"]:
            c.drawString(60, y, f"- {opt}")
            y -= 15

        y -= 10

        if y < 50:
            c.showPage()
            y = height - 40

    c.save()

    return file_path