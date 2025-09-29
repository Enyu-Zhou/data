#!/usr/bin/env python3
"""Ingest exam markdown files into PostgreSQL (normalized schema)."""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row

FIELD_PATTERN = re.compile(r"^\*\*(?P<field>[^*]+)\*\*:\s*(?P<value>.*)$")
OPTION_PATTERN = re.compile(r"^[-*]?\s*([A-Z])\.?\s*(.*)$")
QUESTION_HEADER_PATTERN = re.compile(r"^###\s+(?P<number>\d+)")
TITLE_PATTERN = re.compile(r"^(?P<year>\d{4})(?:[\-_/ ]|年)?\s*(?P<name>.+)$")
SPLIT_PATTERN = re.compile(r"[\s,;\u3001\uFF0C\uFF1B\u2014]+")
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((?P<path>[^)]+)\)")
BULLET_PATTERN = re.compile(r"^(?P<indent>\s*)[-*]\s+(?P<text>.+)$")
VALID_QUESTION_TYPES = {"single_choice", "multiple_choice", "fill_blank", "problem_solving"}


@dataclass
class Question:
    number: int
    question_type: str
    difficulty: int
    question_text: str
    options: Dict[str, str] = field(default_factory=dict)
    correct_answer: str = ""
    explanation: Optional[str] = None
    images: List[str] = field(default_factory=list)
    parts: List["ProblemPart"] = field(default_factory=list)


@dataclass
class ProblemPart:
    part_number: str
    text: str
    images: List[str] = field(default_factory=list)


@dataclass
class Exam:
    year: int
    name: str
    provinces: List[str]
    questions: List[Question]
    description: Optional[str] = None


class ParseError(RuntimeError):
    """Raised when the markdown structure is invalid."""


class ExamParser:
    """Parse a markdown exam file into `Exam` and `Question` objects."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def parse(self) -> Exam:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        title: Optional[str] = None
        provinces: List[str] = []
        description: Optional[str] = None
        questions: List[Question] = []

        section: Optional[str] = None
        i = 0
        while i < len(lines):
            raw_line = lines[i]
            line = raw_line.strip()
            if not line:
                i += 1
                continue
            if line.startswith("# "):
                title = line[2:].strip()
                i += 1
                continue
            if line.startswith("## "):
                section = line[3:].strip().lower()
                i += 1
                continue
            if line.startswith("### "):
                question, i = self._parse_question(lines, i)
                questions.append(question)
                continue
            if section == "info":
                field_match = FIELD_PATTERN.match(line)
                if not field_match:
                    i += 1
                    continue
                field = field_match.group("field").strip().lower()
                value = field_match.group("value").strip()
                if field == "province":
                    provinces = self._split_list(value)
                elif field in {"description", "desc"}:
                    description = value
                else:
                    # ignore unknown info fields for now
                    pass
                i += 1
                continue
            i += 1

        if title is None:
            raise ParseError(f"Missing title in {self.path}")
        title_match = TITLE_PATTERN.match(title)
        if not title_match:
            raise ParseError(f"Unable to parse exam title '{title}' in {self.path}")
        year = int(title_match.group("year"))
        name = title_match.group("name").strip()
        if not provinces:
            raise ParseError(f"Missing province info in {self.path}")
        if not questions:
            raise ParseError(f"No questions found in {self.path}")
        return Exam(year=year, name=name, provinces=provinces, questions=questions, description=description)

    def _parse_question(self, lines: Sequence[str], start_idx: int) -> Tuple[Question, int]:
        header_match = QUESTION_HEADER_PATTERN.match(lines[start_idx].strip())
        if not header_match:
            raise ParseError(f"Invalid question header at line {start_idx + 1} in {self.path}")
        number = int(header_match.group("number"))
        question_type: Optional[str] = None
        difficulty: Optional[int] = None
        question_text: Optional[str] = None
        correct_answer: Optional[str] = None
        explanation_parts: List[str] = []
        images: List[str] = []
        options: Dict[str, str] = {}
        current_field: Optional[str] = None
        current_option: Optional[str] = None
        parts: List[ProblemPart] = []
        top_index = 0
        sub_indices: Dict[int, int] = {}
        current_part_index: Optional[int] = None

        i = start_idx + 1
        while i < len(lines):
            raw_line = lines[i]
            stripped = raw_line.strip()
            if stripped.startswith("### ") or stripped.startswith("## "):
                break
            bullet_match: Optional[re.Match[str]] = None
            if question_type == "problem_solving":
                bullet_match = BULLET_PATTERN.match(raw_line)
            if bullet_match:
                indent = len(bullet_match.group("indent"))
                text = bullet_match.group("text").strip()
                if indent == 0:
                    top_index += 1
                    sub_indices[top_index] = 0
                    part_number = str(top_index)
                else:
                    if top_index == 0:
                        top_index = 1
                        sub_indices[top_index] = 0
                    sub_indices[top_index] += 1
                    part_number = f"{top_index}-{sub_indices[top_index]}"
                parts.append(ProblemPart(part_number=part_number, text=text))
                current_field = None
                current_option = None
                current_part_index = len(parts) - 1
                i += 1
                continue
            image_match = IMAGE_PATTERN.search(raw_line)
            if image_match:
                normalized_image = self._normalize_image_path(image_match.group("path"))
                if question_type == "problem_solving" and current_part_index is not None:
                    parts[current_part_index].images.append(normalized_image)
                else:
                    images.append(normalized_image)
                i += 1
                continue
            field_match = FIELD_PATTERN.match(stripped)
            if field_match:
                field = field_match.group("field").strip().lower()
                value = field_match.group("value").strip()
                current_field = field
                current_option = None
                current_part_index = None
                if field == "question_type":
                    question_type = value.lower()
                elif field == "difficulty":
                    try:
                        difficulty = int(value)
                    except ValueError as exc:
                        raise ParseError(
                            f"Invalid difficulty '{value}' for question {number} in {self.path}"
                        ) from exc
                elif field == "question_text":
                    question_text = value
                elif field in {"correct_answer", "answer"}:
                    correct_answer = value
                elif field in {"analysis", "explanation", "solution"}:
                    explanation_parts = [value]
                # other fields are captured in raw_fields but ignored
                i += 1
                continue
            option_match = OPTION_PATTERN.match(stripped)
            if option_match:
                label = option_match.group(1).upper()
                text = option_match.group(2).strip()
                options[label] = text
                current_field = None
                current_option = label
                i += 1
                continue
            if current_option:
                options[current_option] = options[current_option] + "\n" + raw_line.strip()
                i += 1
                continue
            if question_type == "problem_solving" and current_part_index is not None and stripped:
                part = parts[current_part_index]
                part.text = part.text + "\n" + raw_line.strip()
                i += 1
                continue
            if current_field:
                if current_field == "question_text" and question_text is not None:
                    question_text = question_text + "\n" + raw_line.strip()
                elif current_field in {"analysis", "explanation", "solution"}:
                    explanation_parts.append(raw_line.strip())
                i += 1
                continue
            i += 1

        if question_type is None:
            raise ParseError(f"Missing question_type for question {number} in {self.path}")
        if question_type not in VALID_QUESTION_TYPES:
            raise ParseError(f"Unsupported question_type '{question_type}' for question {number} in {self.path}")
        if difficulty is None:
            raise ParseError(f"Missing difficulty for question {number} in {self.path}")
        if question_text is None:
            raise ParseError(f"Missing question_text for question {number} in {self.path}")
        if correct_answer is None:
            raise ParseError(f"Missing correct_answer for question {number} in {self.path}")

        question_text = question_text.rstrip()
        explanation = "\n".join(part for part in explanation_parts if part) or None
        if explanation:
            explanation = explanation.rstrip()
        for part in parts:
            part.text = part.text.rstrip()
        normalized_answers = self._normalize_answer(correct_answer, question_type)
        question = Question(
            number=number,
            question_type=question_type,
            difficulty=difficulty,
            question_text=question_text,
            options=options,
            correct_answer=normalized_answers,
            explanation=explanation,
            images=images,
            parts=parts,
        )
        self._validate_question(question)
        return question, i

    @staticmethod
    def _split_list(value: str) -> List[str]:
        return [part.strip() for part in SPLIT_PATTERN.split(value) if part.strip()]

    @staticmethod
    def _normalize_image_path(path_value: str) -> str:
        path = Path(path_value)
        return path.name if path.name else str(path)

    @staticmethod
    def _normalize_answer(raw: str, question_type: str) -> str:
        value = raw.strip()
        if question_type == "single_choice":
            return value.upper()
        if question_type == "multiple_choice":
            letters = [chunk.strip().upper() for chunk in re.split(r"[\s,;\u3001]+", value) if chunk.strip()]
            if not letters and value:
                letters = list(value.upper())
            return ",".join(letters)
        return value

    def _validate_question(self, question: Question) -> None:
        qtype = question.question_type
        if qtype == "single_choice":
            answer = question.correct_answer.upper()
            if len(answer) != 1 or answer not in question.options:
                raise ParseError(
                    f"Invalid correct_answer '{question.correct_answer}' for single_choice question {question.number} in {self.path}"
                )
        elif qtype == "multiple_choice":
            answers = [part.strip() for part in question.correct_answer.split(",") if part.strip()]
            if not answers:
                raise ParseError(
                    f"Missing correct_answer for multiple_choice question {question.number} in {self.path}"
                )
            unknown = [ans for ans in answers if ans not in question.options]
            if unknown:
                raise ParseError(
                    f"Unknown answer option(s) {unknown} for multiple_choice question {question.number} in {self.path}"
                )
        elif qtype not in {"fill_blank", "problem_solving"}:
            raise ParseError(f"Unsupported question_type '{qtype}' for question {question.number} in {self.path}")


def collect_files(inputs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for entry in inputs:
        matched = False
        if any(char in entry for char in "*?[]"):
            for path_str in glob(entry, recursive=True):
                path = Path(path_str)
                if path.is_file():
                    files.append(path)
            matched = True
        if matched:
            continue
        path = Path(entry)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Input path not found: {entry}")
    deduped: Dict[str, Path] = {str(p.resolve()): p for p in files}
    return sorted(deduped.values(), key=lambda p: str(p))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def write_single_choice(cur: psycopg.Cursor, question_id: int, question: Question) -> None:
    cur.execute(
        """
        INSERT INTO question_single_choice (
            question_id,
            question_text,
            option_a,
            option_b,
            option_c,
            option_d,
            image_filename,
            correct_answer,
            explanation
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            question_id,
            question.question_text,
            question.options.get("A"),
            question.options.get("B"),
            question.options.get("C"),
            question.options.get("D"),
            question.images or None,
            question.correct_answer.upper(),
            question.explanation,
        ),
    )


def write_multiple_choice(cur: psycopg.Cursor, question_id: int, question: Question) -> None:
    answers = [part.strip().upper() for part in question.correct_answer.split(",") if part.strip()]
    cur.execute(
        """
        INSERT INTO question_multiple_choice (
            question_id,
            question_text,
            option_a,
            option_b,
            option_c,
            option_d,
            image_filename,
            correct_answer,
            explanation
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            question_id,
            question.question_text,
            question.options.get("A"),
            question.options.get("B"),
            question.options.get("C"),
            question.options.get("D"),
            question.images or None,
            answers or None,
            question.explanation,
        ),
    )


def write_fill_blank(cur: psycopg.Cursor, question_id: int, question: Question) -> None:
    cur.execute(
        """
        INSERT INTO question_fill_blank (
            question_id,
            question_text,
            image_filename,
            correct_answer,
            explanation
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            question_id,
            question.question_text,
            question.images or None,
            question.correct_answer,
            question.explanation,
        ),
    )


def write_problem_solving(cur: psycopg.Cursor, question_id: int, question: Question) -> None:
    entries: List[Tuple[Optional[str], str, Optional[List[str]], Optional[str], Optional[str]]] = [
        (None, question.question_text, question.images or None, question.correct_answer, question.explanation)
    ]
    for part in question.parts:
        entries.append((part.part_number, part.text, part.images or None, None, None))
    cur.executemany(
        """
        INSERT INTO question_problem_solving_parts (
            question_id,
            part_number,
            question_text,
            image_filename,
            correct_answer,
            explanation
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [(question_id, number, text, images, answer, explanation) for number, text, images, answer, explanation in entries],
    )


def clear_question_subtables(cur: psycopg.Cursor, question_id: int) -> None:
    for table in (
        "question_single_choice",
        "question_multiple_choice",
        "question_fill_blank",
        "question_problem_solving_parts",
    ):
        cur.execute(f"DELETE FROM {table} WHERE question_id = %s", (question_id,))


SUBTYPE_WRITERS = {
    "single_choice": write_single_choice,
    "multiple_choice": write_multiple_choice,
    "fill_blank": write_fill_blank,
    "problem_solving": write_problem_solving,
}


def insert_question(cur: psycopg.Cursor, question: Question) -> int:
    cur.execute(
        "INSERT INTO question (question_type, difficulty) VALUES (%s, %s) RETURNING question_id",
        (question.question_type, question.difficulty),
    )
    question_id = cur.fetchone()[0]
    write_question_payload(cur, question_id, question)
    return question_id


def update_question(cur: psycopg.Cursor, question_id: int, question: Question) -> int:
    cur.execute(
        "UPDATE question SET question_type = %s, difficulty = %s WHERE question_id = %s",
        (question.question_type, question.difficulty, question_id),
    )
    write_question_payload(cur, question_id, question)
    return question_id


def write_question_payload(cur: psycopg.Cursor, question_id: int, question: Question) -> None:
    clear_question_subtables(cur, question_id)
    writer = SUBTYPE_WRITERS.get(question.question_type)
    if writer is None:
        raise ValueError(f"Unsupported question_type '{question.question_type}'")
    writer(cur, question_id, question)


def fetch_exam(conn: psycopg.Connection, year: int, name: str) -> Optional[Dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT exam_id, province, description FROM exam WHERE exam_year = %s AND exam_name = %s",
            (year, name),
        )
        exam_row = cur.fetchone()
    if not exam_row:
        return None
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT question_num, question_id FROM exam_question WHERE exam_id = %s ORDER BY question_num",
            (exam_row["exam_id"],),
        )
        mapping_rows = cur.fetchall()
    exam_row["question_map"] = {row["question_num"]: row["question_id"] for row in mapping_rows}
    return exam_row


def preview_exam(conn: psycopg.Connection, exam: Exam) -> None:
    existing = fetch_exam(conn, exam.year, exam.name)
    question_map = existing["question_map"] if existing else {}
    print("-- Planned operations --")
    for question in exam.questions:
        if question.number in question_map:
            print(f"UPDATE question #{question.number} (question_id {question_map[question.number]})")
        else:
            print(f"INSERT question #{question.number}")
    if existing:
        print(f"UPDATE exam '{exam.name}' ({exam.year}) (exam_id {existing['exam_id']})")
    else:
        print(f"INSERT exam '{exam.name}' ({exam.year})")


def upsert_exam(conn: psycopg.Connection, exam: Exam) -> None:
    existing = fetch_exam(conn, exam.year, exam.name)
    question_map = existing["question_map"] if existing else {}
    exam_id: Optional[int] = existing["exam_id"] if existing else None

    question_refs: List[Tuple[int, int]] = []
    with conn.cursor() as cur:
        for question in exam.questions:
            existing_id = question_map.get(question.number)
            if existing_id is None:
                question_id = insert_question(cur, question)
            else:
                question_id = update_question(cur, existing_id, question)
            question_refs.append((question.number, question_id))

    with conn.cursor() as cur:
        if exam_id is None:
            cur.execute(
                """
                INSERT INTO exam (exam_year, exam_name, province, description)
                VALUES (%s, %s, %s, %s)
                RETURNING exam_id
                """,
                (exam.year, exam.name, exam.provinces, exam.description),
            )
            exam_id = cur.fetchone()[0]
        else:
            cur.execute(
                "UPDATE exam SET province = %s, description = %s WHERE exam_id = %s",
                (exam.provinces, exam.description, exam_id),
            )
        cur.execute("DELETE FROM exam_question WHERE exam_id = %s", (exam_id,))
        cur.executemany(
            "INSERT INTO exam_question (exam_id, question_num, question_id) VALUES (%s, %s, %s)",
            [(exam_id, number, question_id) for number, question_id in question_refs],
        )


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def process_exam_file(conn: psycopg.Connection, path: Path, dry_run: bool = False) -> None:
    parser = ExamParser(path)
    exam = parser.parse()
    print(f"Parsed exam '{exam.name}' ({exam.year}) with {len(exam.questions)} questions from {path}")
    if dry_run:
        preview_exam(conn, exam)
        return
    with conn.transaction():
        upsert_exam(conn, exam)
    print(f"Ingested exam '{exam.name}' ({exam.year})")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest exam markdown files into PostgreSQL")
    parser.add_argument("inputs", nargs="+", help="Markdown files, directories, or glob patterns")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Can also use DATABASE_URL environment variable")
    parser.add_argument("--dry-run", action="store_true", help="Parse files without touching the database")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    dsn = args.dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("Database DSN must be provided via --dsn or DATABASE_URL environment variable")
    files = collect_files(args.inputs)
    if not files:
        parser.error("No markdown files found for provided inputs")

    try:
        with psycopg.connect(dsn) as conn:
            conn.execute("SET search_path TO content, ext")
            for path in files:
                process_exam_file(conn, path, dry_run=args.dry_run)
    except (LookupError, ParseError, ValueError, KeyError, psycopg.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
