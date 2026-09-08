from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SECTION_ALIASES = {
    "LISTENING": "LISTENING",
    "LISTEN": "LISTENING",
    "听力": "LISTENING",
    "READING": "READING",
    "READ": "READING",
    "阅读": "READING",
    "WRITING": "WRITING",
    "WRITE": "WRITING",
    "写作": "WRITING",
    "VOCABULARY": "VOCABULARY",
    "词汇": "VOCABULARY",
    "GRAMMAR": "GRAMMAR",
    "语法": "GRAMMAR",
}
QUESTION_RE = re.compile(r"^\s*(\d{1,3})\s*[\.、\):：\-]\s*(.*)$")
OPTION_RE = re.compile(r"(?:^|\s)([A-Fa-f])\s*[\.、\):：]\s*([^\s].*?)(?=\s+[A-Fa-f]\s*[\.、\):：]\s*|$)")
PART_RE = re.compile(r"^\s*(?:part|section|第\s*[一二三四五六七八九十0-9]+\s*部分)\s*([0-9一二三四五六七八九十]*)?\b.*$", re.IGNORECASE)
ANSWER_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[\.、\):：\-]?\s*([A-Fa-f])\b")


class ParsedOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=4)
    text: str = Field(min_length=1)


class ParsedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    prompt: str
    options: list[ParsedOption] = Field(default_factory=list)
    question_type: str = "text_input"
    section: str = "GENERAL"
    part: str = "Part 1"
    page: int = Field(ge=1)
    answer: str | None = None
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    source_page: int = Field(ge=1)
    source_question_number: int = Field(ge=1)


class ParsedPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    questions: list[ParsedQuestion] = Field(default_factory=list)


class ParsedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    parts: list[ParsedPart] = Field(default_factory=list)


class ParsedExam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[ParsedSection] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    page_count: int = 0
    text_characters: int = 0
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class ExtractedPdf(BaseModel):
    pages: list[str]
    text_characters: int


def extract_pdf_text(path: str | Path) -> ExtractedPdf:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is pinned in requirements
        raise ValueError("PDF_LIBRARY_UNAVAILABLE") from exc
    try:
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError("PDF_TEXT_EXTRACTION_FAILED") from exc
    characters = sum(len(page) for page in pages)
    if characters < 20:
        raise ValueError("OCR_REQUIRED")
    return ExtractedPdf(pages=pages, text_characters=characters)


def parse_exam_pages(extracted: ExtractedPdf) -> ParsedExam:
    sections: list[ParsedSection] = []
    current_section = _new_section("GENERAL")
    sections.append(current_section)
    current_part = _new_part(current_section, 1)
    current_question: dict[str, Any] | None = None
    detected_numbers: set[int] = set()
    warnings: list[dict[str, Any]] = []

    def flush_question() -> None:
        nonlocal current_question
        if current_question is None:
            return
        current_question["section"] = current_section.code
        current_question["part"] = current_part.title
        question = _question_from_raw(current_question)
        current_part.questions.append(question)
        current_question = None

    for page_number, page_text in enumerate(extracted.pages, start=1):
        for raw_line in page_text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            section_code = _section_code(line)
            if section_code:
                flush_question()
                current_section = _get_or_add_section(sections, section_code)
                current_part = _new_part(current_section, len(current_section.parts) + 1)
                continue
            if PART_RE.match(line):
                flush_question()
                if not current_part.questions:
                    current_part.title = line[:180]
                else:
                    current_part = _new_part(current_section, len(current_section.parts) + 1, title=line[:180])
                continue
            match = QUESTION_RE.match(line)
            if match:
                flush_question()
                number = int(match.group(1))
                if number in detected_numbers:
                    warnings.append({"code": "DUPLICATE_QUESTION_NUMBER", "question": number, "page": page_number})
                detected_numbers.add(number)
                current_question = {"number": number, "lines": [match.group(2)], "page": page_number}
                continue
            if current_question is not None:
                current_question["lines"].append(line)
    flush_question()
    sections = [section for section in sections if any(part.questions for part in section.parts)]
    if not sections:
        raise ValueError("INVALID_DOCUMENT_STRUCTURE")
    return ParsedExam(
        sections=sections,
        page_count=len(extracted.pages),
        text_characters=extracted.text_characters,
        warnings=warnings,
    )


def parse_answer_key_text(text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    answers: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    for match in ANSWER_RE.finditer(text):
        number, answer = match.group(1), match.group(2).upper()
        if number in answers:
            warnings.append({"code": "DUPLICATE_ANSWER", "question": int(number)})
        else:
            answers[number] = answer
    if not answers:
        warnings.append({"code": "ANSWER_KEY_PARSE_FAILED"})
    return answers, warnings


def match_answers(exam: ParsedExam, answers: dict[str, str]) -> ParsedExam:
    matched: set[str] = set()
    missing: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for section in exam.sections:
        for part in section.parts:
            for question in part.questions:
                key = str(question.number)
                answer = answers.get(key)
                if answer is None:
                    question.warnings.append("ANSWER_MISSING")
                    question.confidence = min(question.confidence, 0.58)
                    missing.append({"code": "ANSWER_MISSING", "question": question.number})
                    continue
                if question.options and answer not in {option.id.upper() for option in question.options}:
                    question.warnings.append("INVALID_ANSWER_OPTION")
                    question.confidence = min(question.confidence, 0.4)
                    invalid.append({"code": "INVALID_ANSWER_OPTION", "question": question.number, "answer": answer})
                    continue
                question.answer = answer
                matched.add(key)
    for number in sorted(set(answers) - matched, key=lambda value: int(value)):
        exam.warnings.append({"code": "QUESTION_NUMBER_MISMATCH", "question": int(number)})
    exam.warnings.extend(missing)
    exam.warnings.extend(invalid)
    exam.answers = answers
    return exam


def answer_text_from_file(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return "\n".join(extract_pdf_text(path).pages)
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Path(path).read_text(encoding="latin-1")


def _question_from_raw(raw: dict[str, Any]) -> ParsedQuestion:
    lines = [str(item).strip() for item in raw.get("lines", []) if str(item).strip()]
    joined = " ".join(lines)
    options = [ParsedOption(id=match.group(1).upper(), text=match.group(2).strip()) for match in OPTION_RE.finditer(joined)]
    prompt = OPTION_RE.sub(" ", joined).strip() if options else joined
    warnings: list[str] = []
    confidence = 0.92 if prompt and options else 0.7 if prompt else 0.35
    if not prompt:
        warnings.append("PROMPT_MISSING")
    if options and len(options) < 2:
        warnings.append("OPTIONS_INCOMPLETE")
        confidence = min(confidence, 0.55)
    return ParsedQuestion(
        number=int(raw["number"]),
        prompt=prompt or f"Imported question {raw['number']}",
        options=options,
        question_type="multiple_choice" if len(options) >= 2 else "text_input",
        section=str(raw.get("section") or "GENERAL"),
        part=str(raw.get("part") or "Part 1"),
        page=int(raw["page"]),
        confidence=confidence,
        warnings=warnings,
        source_page=int(raw["page"]),
        source_question_number=int(raw["number"]),
    )


def _section_code(line: str) -> str | None:
    normalized = re.sub(r"[^A-Za-z\u4e00-\u9fff]", "", line).upper()
    if len(line) > 80:
        return None
    for alias, code in SECTION_ALIASES.items():
        if alias in normalized:
            return code
    return None


def _new_section(code: str) -> ParsedSection:
    return ParsedSection(code=code, title=code.title())


def _new_part(section: ParsedSection, number: int, title: str | None = None) -> ParsedPart:
    part = ParsedPart(code=f"{section.code}_{number}", title=title or f"Part {number}")
    section.parts.append(part)
    return part


def _get_or_add_section(sections: list[ParsedSection], code: str) -> ParsedSection:
    for section in sections:
        if section.code == code:
            return section
    section = _new_section(code)
    sections.append(section)
    return section
