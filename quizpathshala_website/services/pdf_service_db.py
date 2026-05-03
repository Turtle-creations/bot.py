from pathlib import Path
from re import sub

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from config import BASE_DIR, DATA_DIR
from utils.logging_utils import get_logger


logger = get_logger(__name__)


class PdfService:
    def __init__(self):
        self.output_dir = DATA_DIR / "generated_pdfs"
        self.font_name = "QuizPdfFont"
        self._font_registered = False

    def generate_questions_pdf(self, exam_title: str, set_title: str, questions: list[dict]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._register_font()

        file_name = f"{self._slugify(exam_title)}_{self._slugify(set_title)}.pdf"
        file_path = self.output_dir / file_name

        pdf = canvas.Canvas(str(file_path), pagesize=A4)
        width, height = A4
        left_margin = 42
        right_margin = 42
        top_margin = height - 42
        bottom_margin = 42
        text_width = width - left_margin - right_margin
        y = top_margin

        pdf.setFont(self.font_name, 14)
        pdf.drawString(left_margin, y, f"Exam: {exam_title}")
        y -= 22
        pdf.setFont(self.font_name, 12)
        pdf.drawString(left_margin, y, f"Set: {set_title}")
        y -= 28

        for index, question in enumerate(questions, start=1):
            question_lines = simpleSplit(
                f"Q{index}. {question['question_text']}",
                self.font_name,
                11,
                text_width,
            )
            image_height = self._estimate_image_height(question.get("image_path"), text_width)
            option_height = self._estimate_option_block_height(question["options"], text_width)
            answer_lines = simpleSplit(
                f"Answer: {question['correct_option']}",
                self.font_name,
                10,
                text_width,
            )
            required_height = (
                len(question_lines) * 14
                + image_height
                + option_height
                + len(answer_lines) * 13
                + 28
            )
            y = self._ensure_page(pdf, y, required_height, top_margin, bottom_margin)

            pdf.setFont(self.font_name, 11)
            for line in question_lines:
                pdf.drawString(left_margin, y, line)
                y -= 14

            y -= 4
            y = self._draw_image(pdf, question.get("image_path"), left_margin, y, text_width, bottom_margin)

            pdf.setFont(self.font_name, 10)
            for label, option in zip(("A", "B", "C", "D"), question["options"]):
                option_lines = simpleSplit(
                    f"{label}. {option}",
                    self.font_name,
                    10,
                    text_width - 14,
                )
                for line in option_lines:
                    pdf.drawString(left_margin + 14, y, line)
                    y -= 13

            y -= 4
            for line in answer_lines:
                pdf.drawString(left_margin, y, line)
                y -= 13

            y -= 12

        pdf.save()
        return file_path

    def _draw_image(
        self,
        pdf: canvas.Canvas,
        image_path: str | None,
        left_margin: int,
        y: float,
        max_width: float,
        bottom_margin: int,
    ) -> float:
        resolved_path = self._resolve_image_path(image_path)
        if not resolved_path:
            return y

        try:
            reader = ImageReader(str(resolved_path))
            width, height = reader.getSize()
        except Exception:
            return y

        scale = min(max_width / width, 220 / height, 1.0)
        draw_width = width * scale
        draw_height = height * scale
        if y - draw_height < bottom_margin:
            return y

        pdf.drawImage(
            reader,
            left_margin,
            y - draw_height,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        return y - draw_height - 10

    def _estimate_image_height(self, image_path: str | None, max_width: float) -> float:
        resolved_path = self._resolve_image_path(image_path)
        if not resolved_path:
            return 0

        try:
            reader = ImageReader(str(resolved_path))
            width, height = reader.getSize()
        except Exception:
            return 0

        scale = min(max_width / width, 220 / height, 1.0)
        return (height * scale) + 10

    def _estimate_option_block_height(self, options: list[str], text_width: float) -> float:
        total = 0
        for label, option in zip(("A", "B", "C", "D"), options):
            total += len(simpleSplit(f"{label}. {option}", self.font_name, 10, text_width - 14)) * 13
        return total

    def _resolve_image_path(self, image_path: str | None) -> Path | None:
        if not image_path:
            return None

        candidate = Path(image_path)
        if not candidate.is_absolute():
            candidate = BASE_DIR / image_path
        if not candidate.exists():
            return None
        return candidate

    def _register_font(self):
        if self._font_registered:
            return

        preferred_font_path = BASE_DIR / "fonts" / "NotoSansDevanagari-Regular.ttf"
        fallback_font_path = BASE_DIR / "fonts" / "NotoSans-Regular.ttf"

        if preferred_font_path.exists():
            font_path = preferred_font_path
        elif fallback_font_path.exists():
            font_path = fallback_font_path
            logger.warning(
                "Preferred PDF font missing, using fallback font | preferred_font_path=%s fallback_font_path=%s",
                preferred_font_path,
                fallback_font_path,
            )
        else:
            logger.warning(
                "No PDF font file found | preferred_font_path=%s fallback_font_path=%s",
                preferred_font_path,
                fallback_font_path,
            )
            return

        pdfmetrics.registerFont(TTFont(self.font_name, str(font_path)))
        self._font_registered = True

    def _ensure_page(
        self,
        pdf: canvas.Canvas,
        y: float,
        required_height: float,
        top_margin: float,
        bottom_margin: float,
    ) -> float:
        if y - required_height > bottom_margin:
            return y

        pdf.showPage()
        pdf.setFont(self.font_name, 11)
        return top_margin

    def _slugify(self, value: str) -> str:
        cleaned = sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return cleaned or "quiz"


pdf_service = PdfService()
