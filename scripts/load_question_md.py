#!/usr/bin/env python3
"""Load a markdown question file into the content.questions table."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Dict

try:
    import psycopg2  # type: ignore
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "The 'psycopg2' package is required. Install it with 'pip install psycopg2-binary'."
    ) from exc

try:
    from markdown_it import MarkdownIt  # type: ignore
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "The 'markdown-it-py' package is required. Install it with 'pip install markdown-it-py'."
    ) from exc

try:
    from bs4 import BeautifulSoup, NavigableString, Tag  # type: ignore
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "The 'beautifulsoup4' package is required. Install it with 'pip install beautifulsoup4'."
    ) from exc

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "The 'python-dotenv' package is required. Install it with 'pip install python-dotenv'."
    ) from exc

SECTION_PARSERS: Dict[str, str] = {
    "题目": "question",
    "答案": "answer",
    "分析": "analysis",
    "详解": "explanation",
    "知识点": "knowledge",
    "属性": "attributes",
}

MARKDOWN_RENDERER = MarkdownIt("commonmark").disable("escape")


def parse_sections(md_path: Path) -> Dict[str, str]:
    """Return markdown sections keyed by their heading."""
    sections: Dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

    for raw_line in md_path.read_text(encoding="utf-8").splitlines():
        match = heading_pattern.match(raw_line.strip())
        if match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
                buffer.clear()
            current_heading = match.group(2).strip()
        else:
            if current_heading is not None:
                buffer.append(raw_line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections


def markdown_to_html(source: str) -> str:
    """Convert markdown text to HTML."""
    text = source.strip()
    return MARKDOWN_RENDERER.render(text).strip() if text else ""


def markdown_to_html_list(source: str) -> list[str]:
    """Convert markdown text to a list of HTML fragments."""
    text = source.strip()
    if not text:
        return []

    html = MARKDOWN_RENDERER.render(text).strip()
    soup = BeautifulSoup(html, "html.parser")
    fragments: list[str] = []

    for node in soup.contents:
        if isinstance(node, NavigableString):
            if node.strip():
                fragments.append(node.strip())
            continue

        if isinstance(node, Tag) and node.name in {"ul", "ol"}:
            for child in node.find_all("li", recursive=False):
                fragments.append(str(child))
        else:
            fragments.append(str(node))

    cleaned = [fragment.strip() for fragment in fragments if fragment.strip()]
    return cleaned or [html]


def markdown_to_text_list(source: str) -> list[str]:
    """Convert markdown text to plain-text fragments without HTML tags."""
    text = source.strip()
    if not text:
        return []

    html = MARKDOWN_RENDERER.render(text).strip()
    soup = BeautifulSoup(html, "html.parser")
    fragments: list[str] = []

    for node in soup.contents:
        if isinstance(node, NavigableString):
            cleaned = node.strip()
            if cleaned:
                fragments.append(cleaned)
            continue

        if isinstance(node, Tag) and node.name in {"ul", "ol"}:
            for child in node.find_all("li", recursive=False):
                child_text = child.get_text(separator=" ", strip=True)
                if child_text:
                    fragments.append(child_text)
        else:
            node_text = node.get_text(separator=" ", strip=True)
            if node_text:
                fragments.append(node_text)

    cleaned_fragments = [fragment for fragment in fragments if fragment]
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

    if cleaned_fragments:
        if len(cleaned_fragments) == 1 and len(raw_lines) > 1:
            return raw_lines
        return cleaned_fragments

    if len(raw_lines) > 1:
        return raw_lines

    fallback = soup.get_text(separator=" ", strip=True)
    return [fallback] if fallback else []


def parse_attributes(raw_text: str) -> Dict[str, str]:
    """Parse key:value pairs from the 属性 section."""
    attributes: Dict[str, str] = {}
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned or ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        attributes[key.strip()] = value.strip()
    return attributes


def build_payload(md_path: Path) -> Dict[str, object]:
    """Transform markdown file contents into database-ready payload."""
    sections = parse_sections(md_path)

    required_headings = {"题目", "答案", "分析", "详解", "知识点", "属性"}
    missing = required_headings - sections.keys()
    if missing:
        raise ValueError(
            f"Markdown file is missing sections: {', '.join(sorted(missing))}")

    attributes = parse_attributes(sections["属性"])
    try:
        question_type = attributes["question_type"]
        accuracy = float(attributes["accuracy"])
    except KeyError as missing_key:
        raise ValueError(f"Missing attribute: {missing_key}") from missing_key
    except ValueError as value_error:
        raise ValueError("Accuracy must be a float.") from value_error

    question_html = markdown_to_html(sections["题目"])
    answer_text_list = markdown_to_text_list(sections["答案"])
    analysis_html_list = markdown_to_html_list(sections["分析"])
    explanation_html_list = markdown_to_html_list(sections["详解"])
    knowledge_text_list = markdown_to_text_list(sections["知识点"])

    if not question_html:
        raise ValueError("Question section cannot be empty.")
    if not answer_text_list:
        raise ValueError("Answer section cannot be empty.")

    question_id = int(md_path.stem)

    return {
        "question_id": question_id,
        "question_type": question_type,
        "accuracy": accuracy,
        "question": question_html,
        "answer": answer_text_list,
        "analysis": analysis_html_list,
        "explanation": explanation_html_list,
        "knowledge": knowledge_text_list,
    }


def insert_question(dsn: str, payload: Dict[str, object]) -> None:
    """Execute an upsert into content.questions."""
    sql = """
        INSERT INTO content.questions (
            question_id,
            question_type,
            accuracy,
            question,
            answer,
            analysis,
            explanation,
            knowledge
        ) VALUES (%(question_id)s, %(question_type)s, %(accuracy)s, %(question)s,
                  %(answer)s, %(analysis)s, %(explanation)s, %(knowledge)s)
        ON CONFLICT (question_id) DO UPDATE
        SET question_type = EXCLUDED.question_type,
            accuracy = EXCLUDED.accuracy,
            question = EXCLUDED.question,
            answer = EXCLUDED.answer,
            analysis = EXCLUDED.analysis,
            explanation = EXCLUDED.explanation,
            knowledge = EXCLUDED.knowledge,
            updated_at = NOW();
    """

    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, payload)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Load a markdown question into PostgreSQL.")
    parser.add_argument(
        "md_path",
        type=Path,
        help="Path to the markdown file (e.g., question/1.md).",
    )
    parser.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL"),
        help=
        "PostgreSQL DSN or connection string. Defaults to env DATABASE_URL.",
    )
    args = parser.parse_args()

    if args.dsn is None:
        parser.error(
            "A PostgreSQL DSN must be provided via --dsn or DATABASE_URL.")

    payload = build_payload(args.md_path)
    insert_question(args.dsn, payload)
    print(
        f"Inserted question {payload['question_id']} into content.questions.")


if __name__ == "__main__":
    main()
