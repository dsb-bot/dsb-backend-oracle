from datetime import date

import pytest

from dsb_bot.models import PlanSource
from dsb_bot.parser import PlanParseError, parse_student_document, parse_teacher_document


STUDENT_HTML = b"""<!doctype html><html><head><meta charset="windows-1252"></head><body>
<table class="mon_head"><tr><td>Untis</td></tr></table>
<div class="mon_title">6.11.2026 Freitag, Woche B</div>
<table class="info"><tr><td>Info</td></tr></table>
<table class="mon_list"><tr><th>Klasse(n)</th><th>Stunde</th><th>Vertreter</th>
<th>(Lehrer)</th><th>Fach</th><th>Raum</th><th>(Fach)</th><th>Art</th><th>Text</th></tr>
<tr><td>05a</td><td>1</td><td>ABC</td><td>DEF</td><td>D</td><td>101</td><td>D</td>
<td>Vertretung</td><td></td></tr></table></body></html>"""


TEACHER_SECTION = """<table class="mon_head"><tr><td>Untis</td></tr></table>
<center><div class="mon_title">{title}</div>
<table class="info"><tr class="info"><td>Nachrichten zum Tag</td><td>Keine</td></tr></table>
<table class="mon_list">
<tr class="list"><th>Vertreter</th><th>Stunde</th><th>Klasse(n)</th><th>Fach</th>
<th>Raum</th><th>(Lehrer)</th><th>Vertr. von</th><th>Art</th><th>Text</th></tr>
<tr class="list odd"><td>ABC</td><td>1</td><td>05a</td><td>D</td><td>101</td>
<td>DEF</td><td></td><td>{activity}</td><td>Test</td></tr>
</table></center>"""


@pytest.fixture
def teacher_html():
    return (
        "<html><body>"
        + TEACHER_SECTION.format(title="9.11.2026 Montag, Woche A", activity="Vertretung")
        + TEACHER_SECTION.format(title="10.11.2026 Dienstag, Woche A", activity="Freisetzung")
        + TEACHER_SECTION.format(title="11.11.2026 Mittwoch, Woche A", activity="Pausenaufsicht")
        + TEACHER_SECTION.format(title="12.11.2026 Donnerstag, Woche A", activity="Entfall")
        + TEACHER_SECTION.format(title="13.11.2026 Freitag, Woche A", activity="Vertretung")
        + "</body></html>"
    ).encode("utf-8")


def test_student_document_is_kept_byte_for_byte():
    candidate = parse_student_document(STUDENT_HTML, "text/html; charset=windows-1252")

    assert candidate.date == date(2026, 11, 6)
    assert candidate.source is PlanSource.STUDENT
    assert candidate.html_content == STUDENT_HTML


def test_teacher_sections_are_independent_and_cutoff_is_calendar_based(teacher_html):
    plans = parse_teacher_document(
        teacher_html,
        template="<html><head><meta charset='utf-8'></head><body>",
        earliest_date=date(2026, 11, 11),
    )

    assert [plan.date for plan in plans] == [
        date(2026, 11, 11),
        date(2026, 11, 12),
        date(2026, 11, 13),
    ]
    assert all(plan.source is PlanSource.TEACHER_CONVERTED for plan in plans)
    converted = [plan.html_content.decode("utf-8") for plan in plans]
    assert all("Klasse(n)" in html for html in converted)
    assert all("Pausenaufsicht" not in html and "Freisetzung" not in html for html in converted)
    assert "---" in converted[1]
    assert "Entfall" in converted[1]
    assert "Vertretung" in converted[2]


def test_teacher_document_without_dated_table_is_an_error():
    with pytest.raises(PlanParseError):
        parse_teacher_document(
            b"<html><body><table class='mon_list'></table></body></html>",
            template="<html><body>",
            earliest_date=date(2026, 11, 11),
        )


def test_windows_1252_teacher_content_is_rendered_as_utf8():
    section = TEACHER_SECTION.format(
        title="11.11.2026 Mittwoch, Woche A",
        activity="Unterricht ge\u00e4ndert",
    )
    body = f"<html><body>{section}</body></html>".encode("cp1252")

    plans = parse_teacher_document(
        body,
        earliest_date=date(2026, 11, 11),
        content_type="text/html; charset=windows-1252",
    )

    assert len(plans) == 1
    assert b"Unterricht ge\xc3\xa4ndert" in plans[0].html_content
