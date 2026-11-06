import re
import codecs
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from dsb_bot.models import PlanCandidate, PlanSource


class PlanParseError(ValueError):
    pass


DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
STUDENT_HEADERS = [
    "Klasse(n)",
    "Stunde",
    "Vertreter",
    "(Lehrer)",
    "Fach",
    "Raum",
    "(Fach)",
    "Art",
    "Text",
]
ALLOWED_ACTIVITIES = {
    "Vertretung",
    "Entfall",
    "Lehrertausch",
    "Verlegung",
    "Unterricht geändert",
    "Unterricht findet statt",
    "Sondereins.",
    "Betreuung",
    "Vtr. ohne Lehrer",
    "Raum-Vtr.",
    "Tausch",
    "eigenverantwortliches Arbeiten",
    "Teil-Vtr.",
}
TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"


def _title_and_date(node) -> tuple[str, date]:
    title = node.get_text(" ", strip=True)
    match = DATE_PATTERN.search(title)
    if match is None:
        raise PlanParseError(f"Schedule title does not contain a date: {title!r}")
    try:
        parsed_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError as exc:
        raise PlanParseError(f"Schedule title has an invalid date: {title!r}") from exc
    return title, parsed_date


def parse_student_document(
    body: bytes,
    content_type: str,
    retrieved_at: datetime | None = None,
) -> PlanCandidate:
    soup = _parse_html(body, content_type)
    title_node = soup.find("div", class_="mon_title")
    if title_node is None:
        raise PlanParseError("Student schedule has no .mon_title element")
    title, target_date = _title_and_date(title_node)
    if soup.find("table", class_="mon_list") is None:
        raise PlanParseError("Student schedule has no .mon_list table")
    return PlanCandidate(
        date=target_date,
        title=title,
        html_content=body,
        content_type=content_type or "text/html",
        source=PlanSource.STUDENT,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
    )


def parse_teacher_document(
    body: bytes,
    template: str | None = None,
    earliest_date: date | None = None,
    retrieved_at: datetime | None = None,
    content_type: str | None = None,
) -> list[PlanCandidate]:
    soup = _parse_html(body, content_type)
    title_nodes = soup.find_all("div", class_="mon_title")
    plan_tables = soup.find_all("table", class_="mon_list")
    if not title_nodes or len(title_nodes) != len(plan_tables):
        raise PlanParseError(
            "Teacher schedule sections must have one dated title and one plan table each"
        )

    template_header = template or (TEMPLATE_DIRECTORY / "plan_style.html").read_text(
        encoding="utf-8"
    )
    template_header = re.sub(
        r"charset\s*=\s*['\"]?windows-1252['\"]?",
        "charset=utf-8",
        template_header,
        flags=re.IGNORECASE,
    )
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIRECTORY),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    renderer = environment.get_template("converted_plan.html")
    timestamp = retrieved_at or datetime.now(timezone.utc)
    candidates: list[PlanCandidate] = []

    for title_node, source_table in zip(title_nodes, plan_tables, strict=True):
        title, target_date = _title_and_date(title_node)
        if earliest_date is not None and target_date < earliest_date:
            continue
        head_table = title_node.find_previous("table", class_="mon_head")
        if head_table is None:
            raise PlanParseError(f"Teacher section {title!r} has no .mon_head table")
        info_table = None
        for table in title_node.find_all_next("table"):
            if table is source_table:
                break
            if "info" in table.get("class", []):
                info_table = table

        rendered = renderer.render(
            header=template_header,
            head_table=str(head_table),
            title=str(title_node),
            info_table=str(info_table) if info_table is not None else "",
            plan_table=_convert_teacher_table(source_table),
        )
        candidates.append(
            PlanCandidate(
                date=target_date,
                title=title,
                html_content=rendered.encode("utf-8"),
                content_type="text/html; charset=utf-8",
                source=PlanSource.TEACHER_CONVERTED,
                retrieved_at=timestamp,
            )
        )
    return candidates


def _convert_teacher_table(source_table) -> str:
    rows = source_table.find_all("tr")
    if not rows:
        raise PlanParseError("Teacher .mon_list table has no rows")
    header_cells = rows[0].find_all(["th", "td"], recursive=False)
    headers = [cell.get_text(" ", strip=True) for cell in header_cells]
    expected_headers = [
        "Vertreter",
        "Stunde",
        "Klasse(n)",
        "Fach",
        "Raum",
        "(Lehrer)",
        "Vertr. von",
        "Art",
        "Text",
    ]
    if headers[:9] != expected_headers:
        raise PlanParseError(f"Unexpected teacher table headers: {headers!r}")
    if len(headers) < 9:
        raise PlanParseError("Teacher .mon_list table must contain nine columns")
    output_columns = [
        headers.index("Klasse(n)"),
        headers.index("Stunde"),
        headers.index("Vertreter"),
        headers.index("(Lehrer)"),
        headers.index("Fach"),
        headers.index("Raum"),
        headers.index("Fach"),
        headers.index("Art"),
        headers.index("Text"),
    ]

    data_rows: list[list[str]] = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 9:
            raise PlanParseError("Teacher table contains a row with fewer than nine cells")
        values = [cell.get_text(" ", strip=True) for cell in cells]
        activity = values[headers.index("Art")]
        if activity not in ALLOWED_ACTIVITIES:
            continue
        data_rows.append(values)

    class_index = headers.index("Klasse(n)")
    hour_index = headers.index("Stunde")
    data_rows.sort(key=lambda row: (_class_sort_key(row[class_index]), _hour_sort_key(row[hour_index])))

    output = BeautifulSoup("<table class='mon_list'></table>", "lxml").table
    tbody = BeautifulSoup("", "lxml").new_tag("tbody")
    header_row = BeautifulSoup("", "lxml").new_tag("tr")
    header_row["class"] = ["list"]
    for index, label in enumerate(STUDENT_HEADERS):
        th = BeautifulSoup("", "lxml").new_tag("th", align="center")
        th["class"] = ["list"]
        if index == 0:
            bold = BeautifulSoup("", "lxml").new_tag("b")
            bold.string = label
            th.append(bold)
        else:
            th.string = label
        header_row.append(th)
    tbody.append(header_row)

    for row_number, values in enumerate(data_rows):
        output_row = BeautifulSoup("", "lxml").new_tag("tr")
        output_row["class"] = ["list", "odd" if row_number % 2 == 0 else "even"]
        activity = values[headers.index("Art")]
        for column_number, source_index in enumerate(output_columns):
            cell = BeautifulSoup("", "lxml").new_tag("td", align="center")
            cell["class"] = ["list"]
            text = values[source_index]
            if activity == "Entfall" and column_number in {2, 4, 5}:
                text = "---"
            if column_number == 0:
                bold = BeautifulSoup("", "lxml").new_tag("b")
                bold.string = text
                cell.append(bold)
            else:
                cell.string = text
            output_row.append(cell)
        tbody.append(output_row)

    output.append(tbody)
    return str(output)


def _parse_html(body: bytes, content_type: str | None) -> BeautifulSoup:
    charset_match = re.search(
        r"charset\s*=\s*['\"]?([^;'\"\s]+)", content_type or "", re.IGNORECASE
    )
    encoding = charset_match.group(1) if charset_match else None
    if encoding is not None:
        try:
            codecs.lookup(encoding)
        except LookupError as exc:
            raise PlanParseError(f"Unknown HTML character encoding: {encoding}") from exc
    return BeautifulSoup(body, "lxml", from_encoding=encoding)


def _class_sort_key(value: str) -> tuple[int, str]:
    normalized = value.replace("(", "").replace(")", "").strip()
    match = re.match(r"(\d+)?([a-zA-Z]*)", normalized)
    if match is None or not normalized:
        return (9999, normalized or "zzz")
    number = int(match.group(1)) if match.group(1) else 0
    return (9999 if normalized in {"E1", "E2", "Q1", "Q2", "Q3", "Q4", "AG"} else number, match.group(2) or normalized)


def _hour_sort_key(value: str) -> int:
    match = re.match(r"\s*(\d+)", value)
    return int(match.group(1)) if match else 9999
