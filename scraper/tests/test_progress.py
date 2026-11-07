from scraper.polite import PROGRESS, report_progress
from scraper.worker import progress_line


def test_progress_line_with_position_and_eta():
    line = progress_line("ubee", 600, 40, {"requests": 120, "done": 117, "total": 468})
    assert line == "[progress] ubee: 10 min, 40 listings sent, 120 requests, 117/468 checked (25 %), ~30 min left"


def test_progress_line_without_total_and_hours():
    assert progress_line("centris", 4000, 900, {"requests": 1100}) == \
        "[progress] centris: 1 h 07, 900 listings sent, 1100 requests"
    assert progress_line("facebook", 30, 0, {}) == "[progress] facebook: 0 min, 0 listings sent"


def test_report_progress_keeps_request_count():
    PROGRESS.pop("t", None)
    PROGRESS["t"] = {"requests": 3}
    report_progress("t", 2, 10)
    assert PROGRESS["t"] == {"requests": 3, "done": 2, "total": 10}
    PROGRESS.pop("t")
