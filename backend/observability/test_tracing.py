from backend.observability import tracing


def test_off_without_keys_and_everything_is_a_noop():
    assert not tracing.enabled()  # conftest blanks the LANGFUSE_* settings
    with tracing.turn("chat_turn", session_id="s", tags=["t"], input="q") as root:
        with tracing.observe("tool:x", as_type="tool") as span:
            assert span.update(output={"a": 1}) is span
        assert not root and root.trace_id is None
    assert tracing.traceparent() is None
    assert tracing.score("abc", "user_feedback", 1.0) is False
    tracing.flush()


def test_traceparent_round_trip():
    tid, sid = "a" * 32, "b" * 16
    assert tracing.parse_traceparent(f"00-{tid}-{sid}-01") == {
        "trace_id": tid,
        "parent_span_id": sid,
    }


def test_bad_traceparent_is_ignored():
    for value in (None, 42, "", "00-xyz-01", f"00-{'g' * 32}-{'b' * 16}-01"):
        assert tracing.parse_traceparent(value) is None


def test_errors_inside_a_span_still_propagate():
    try:
        with tracing.observe("x"):
            raise ValueError("boom")
    except ValueError as e:
        assert str(e) == "boom"
    else:
        raise AssertionError("swallowed")
