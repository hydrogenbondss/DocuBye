import json
from pathlib import Path

import pytest

from docubye.google_inspect import EXPECTED_CONTACT_STEPS
from docubye.sources.google_report import build_html_report

pytest.importorskip("playwright")

PLANTED_EMAIL = "jane.doe@example.com"
PLANTED_PHONE = "+1 415 555 0132"


def _write_dir(tmp_path, files: dict[str, str]):
    source = tmp_path / "saved"
    source.mkdir()
    for name, content in files.items():
        (source / name).write_text(content, encoding="utf-8")
    return source


def _happy_with_pii():
    return Path("tests/fixtures/google/happy.html").read_text(encoding="utf-8").replace(
        "</main>",
        f'<div aria-label="Google Account: Jane Doe ({PLANTED_EMAIL})" data-ogpc>Jane Doe</div>'
        f'<p>Contact {PLANTED_EMAIL} or {PLANTED_PHONE}</p>'
        '<img src="https://example.com/external-tracker.png"></main>',
    )


def test_report_processes_files_in_name_order(chromium, tmp_path, capsys):
    source = _write_dir(tmp_path, {
        "02-branch.html": _happy_with_pii(),
        "01-start.html": _happy_with_pii(),
    })
    prompts = iter(["save", "save"])
    result = build_html_report(
        source, save_dir=tmp_path / "out", prompt_fn=lambda _message: next(prompts, "")
    )
    assert result.processed_files == ["01-start.html", "02-branch.html"]
    assert len(result.saved_files) == 2
    # Step labels follow file names, in order.
    steps = [c.step for c in result.checks]
    assert steps[:6] == ["01-start"] * 6
    assert steps[6:] == ["02-branch"] * 6
    # Selector checks ran per step: the branch label is found in these pages.
    found = [c for c in result.checks if c.description == f"text:{EXPECTED_CONTACT_STEPS[0]}"]
    assert all(c.status == "found" for c in found)


def test_sanitization_applied_and_summary_shows_counts_not_values(chromium, tmp_path, capsys):
    source = _write_dir(tmp_path, {"01-start.html": _happy_with_pii()})
    result = build_html_report(
        source, save_dir=tmp_path / "out", prompt_fn=lambda _message: "save"
    )
    saved = Path(result.saved_files[0]).read_text(encoding="utf-8")
    assert PLANTED_EMAIL not in saved
    assert PLANTED_PHONE not in saved
    assert "Jane Doe" not in saved

    printed = capsys.readouterr().out
    assert "redacted" in printed and "emails" in printed
    assert PLANTED_EMAIL not in printed
    assert PLANTED_PHONE not in printed


def test_nothing_saved_without_opt_in(chromium, tmp_path):
    source = _write_dir(tmp_path, {"01-start.html": _happy_with_pii()})
    result = build_html_report(
        source, save_dir=tmp_path / "out", prompt_fn=lambda _message: "no"
    )
    assert result.saved_files == []
    assert not (tmp_path / "out").exists()
    assert result.processed_files == ["01-start.html"]


def test_no_network_requests_leave_the_offline_page(chromium, tmp_path):
    source = _write_dir(tmp_path, {"01-start.html": _happy_with_pii()})
    result = build_html_report(
        source, save_dir=tmp_path / "out", prompt_fn=lambda _message: "no"
    )
    # The planted external image attempted a request; the offline guard blocked it.
    assert result.blocked_requests >= 1
    assert any("offline" in note for note in result.notes)
    # The selector checks still ran against the sanitized local copy.
    assert result.checks


def test_report_json_contains_no_page_content(chromium, tmp_path):
    source = _write_dir(tmp_path, {"01-start.html": _happy_with_pii()})
    result = build_html_report(
        source, save_dir=tmp_path / "out", prompt_fn=lambda _message: "no"
    )
    blob = json.dumps(result.report())
    assert PLANTED_EMAIL not in blob
    assert PLANTED_PHONE not in blob
    assert "<html" not in blob
    assert blob.count("01-start.html") >= 1


def test_empty_or_missing_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="Not a directory"):
        build_html_report(tmp_path / "nope", prompt_fn=lambda _m: "")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No .html files"):
        build_html_report(empty, prompt_fn=lambda _m: "")
