<<<<<<< HEAD
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics
import os

def generate_pdf(questions, file_name="quiz.pdf"):

    os.makedirs("data", exist_ok=True)
    file_path = f"data/{file_name}"

    c = canvas.Canvas(file_path, pagesize=letter)

    # ✅ UNIVERSAL FONT (Hindi + English + Numbers OK)
    font_path = "fonts/NotoSans-Regular.ttf"
    pdfmetrics.registerFont(ttfonts.TTFont("CustomFont", font_path))

    c.setFont("CustomFont", 12)

    width, height = letter
    y = height - 40

    for i, q in enumerate(questions, 1):

        c.drawString(40, y, f"{i}. {q['question']}")
        y -= 20

        for opt in q["options"]:
            c.drawString(60, y, f"- {opt}")
            y -= 15

        y -= 10

        if y < 50:
            c.showPage()
            c.setFont("CustomFont", 12)
            y = height - 40

    c.save()

    return file_path
import os

=======
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import ttfonts
from reportlab.pdfbase import pdfmetrics
import os

def generate_pdf(questions, file_name="quiz.pdf"):

    os.makedirs("data", exist_ok=True)
    file_path = f"data/{file_name}"

    c = canvas.Canvas(file_path, pagesize=letter)

    # ✅ UNIVERSAL FONT (Hindi + English + Numbers OK)
    font_path = "fonts/NotoSans-Regular.ttf"
    pdfmetrics.registerFont(ttfonts.TTFont("CustomFont", font_path))

    c.setFont("CustomFont", 12)

    width, height = letter
    y = height - 40

    for i, q in enumerate(questions, 1):

        c.drawString(40, y, f"{i}. {q['question']}")
        y -= 20

        for opt in q["options"]:
            c.drawString(60, y, f"- {opt}")
            y -= 15

        y -= 10

        if y < 50:
            c.showPage()
            c.setFont("CustomFont", 12)
            y = height - 40

    c.save()

    return file_path
import os

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
print(os.path.exists("fonts/NotoSans-Regular.ttf"))