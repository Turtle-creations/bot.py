from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_FILE = OUTPUT_DIR / "quiz_bot_app_summary.pdf"
FONT_PATH = ROOT / "fonts" / "NotoSans-Regular.ttf"


def build_styles():
    styles = getSampleStyleSheet()
    base_font = "Helvetica"

    if FONT_PATH.exists():
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_PATH)))
        base_font = "NotoSans"

    return {
        "title": ParagraphStyle(
            "TitleCompact",
            parent=styles["Title"],
            fontName=base_font,
            fontSize=18,
            leading=21,
            textColor=colors.HexColor("#17324D"),
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCompact",
            parent=styles["Normal"],
            fontName=base_font,
            fontSize=8.5,
            leading=10.5,
            textColor=colors.HexColor("#5B6775"),
            spaceAfter=8,
        ),
        "heading": ParagraphStyle(
            "HeadingCompact",
            parent=styles["Heading2"],
            fontName=base_font,
            fontSize=10.5,
            leading=12,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=4,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "BodyCompact",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=8.4,
            leading=10.2,
            textColor=colors.black,
            spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "BulletCompact",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=8.2,
            leading=9.8,
            leftIndent=10,
            firstLineIndent=0,
            bulletIndent=0,
            spaceAfter=1,
        ),
    }


def section(title, content, styles):
    parts = [Paragraph(title, styles["heading"])]
    parts.extend(content)
    return parts


def bullet(text, styles):
    return Paragraph(text, styles["bullet"], bulletText="-")


def body(text, styles):
    return Paragraph(text, styles["body"])


def build_story(styles):
    story = [
        Paragraph("Quiz Bot App Summary", styles["title"]),
        Paragraph(
            "Repo-based one-page overview generated from code and data files only.",
            styles["subtitle"],
        ),
    ]

    story += section(
        "What It Is",
        [
            body(
                "A Telegram quiz bot for exam practice that lets users choose an exam, pick a set, answer timed multiple-choice questions, view their profile, and see leaderboards.",
                styles,
            ),
            body(
                "The same bot also includes admin flows for managing exams, sets, questions, images, notifications, and quiz PDFs.",
                styles,
            ),
        ],
        styles,
    )

    story += section(
        "Who It Is For",
        [
            body(
                "Primary persona: students preparing for competitive exams such as SSC, JE, and Railway through Telegram-based practice quizzes.",
                styles,
            )
        ],
        styles,
    )

    story += section(
        "What It Does",
        [
            bullet("Shows a start menu with quiz, profile, leaderboard, updates, PDFs, premium, and user guide actions.", styles),
            bullet("Lets users select an exam, then a set, then a question count before starting a quiz.", styles),
            bullet("Runs per-question timers, checks answers, scores +1 / -0.25, and advances through a session.", styles),
            bullet("Displays profile stats including rank, badge, score, correct answers, wrong answers, and accuracy.", styles),
            bullet("Builds a top-10 leaderboard from stored user scores.", styles),
            bullet("Allows admins to add, view, and delete exams, sets, and questions, including optional question images.", styles),
            bullet("Stores notifications and generates quiz PDFs from question data using ReportLab.", styles),
        ],
        styles,
    )

    story += section(
        "How It Works",
        [
            bullet("Entry point: `bot.py` creates a `python-telegram-bot` `Application`, registers command, callback, photo, and text handlers, then starts polling.", styles),
            bullet("Interaction layer: `handlers/` routes `/start`, `/admin`, `/notify`, quiz callbacks, and text-mode flows using `context.user_data` flags.", styles),
            bullet("Business logic: `services/` manages exams, sets, questions, quiz sessions, users, and PDF creation; active quiz state lives in in-memory `user_sessions`.", styles),
            bullet("Persistence: JSON files under `data/` hold exams, users, notifications, and generated quiz PDFs via `utils/file_manager.py`.", styles),
            bullet("Media and documents: uploaded admin images are saved under `data/images`, and PDF output uses ReportLab plus the bundled Noto Sans font.", styles),
        ],
        styles,
    )

    story += section(
        "How To Run",
        [
            bullet("Install Python 3. Exact version requirement: Not found in repo.", styles),
            bullet("Install inferred packages: `python-telegram-bot` and `reportlab`. Exact dependency file or pinned versions: Not found in repo.", styles),
            bullet("Set `TOKEN`, `SUPREME_ADMIN_ID`, and `ADMINS` in `config.py`.", styles),
            bullet("Keep the `data/` folder and bundled font file in place.", styles),
            bullet("Start the bot with `python bot.py` from the repo root.", styles),
        ],
        styles,
    )

    story += section(
        "Gaps Marked From Repo",
        [
            bullet("README / setup guide: Not found in repo.", styles),
            bullet("Environment variable support for secrets: Not found in repo.", styles),
            bullet("Tests, deployment instructions, and dependency manifest: Not found in repo.", styles),
        ],
        styles,
    )

    return story


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT_FILE),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = build_styles()
    story = build_story(styles)

    frame_width = A4[0] - doc.leftMargin - doc.rightMargin
    frame_height = A4[1] - doc.topMargin - doc.bottomMargin

    wrapped = KeepInFrame(frame_width, frame_height, story, mode="shrink")
    doc.build([wrapped, Spacer(1, 0)])

    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()
