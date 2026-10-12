"""The websocket ?token= must never reach the logs."""
import logging

from app.logging_config import RedactTokenFilter, redact_tokens


def test_redacts_token_query_param():
    assert redact_tokens('/ws/market?token=abc.def-ghi_1') == '/ws/market?token=***'
    assert redact_tokens('/ws/market?x=1&token=abc&y=2') == '/ws/market?x=1&token=***&y=2'


def test_leaves_other_text_alone():
    assert redact_tokens('/api/health') == '/api/health'


def test_filter_scrubs_uvicorn_style_access_record(caplog):
    # uvicorn.access formats: '%s - "%s %s HTTP/%s" %d' with the path as an arg
    rec = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/ws/market?token=SECRETJWT", "1.1", 101), None,
    )
    RedactTokenFilter().filter(rec)
    out = rec.getMessage()
    assert "SECRETJWT" not in out and "token=***" in out
