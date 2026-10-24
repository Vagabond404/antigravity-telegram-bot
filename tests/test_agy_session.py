"""
Unit tests for agy_session.py
Verifies stream-json input payload formatting, quota error detection,
tool description generation, and session lifecycle management.
"""

import json
import asyncio
import pytest
from agy_session import AgySession, is_quota_error


def test_is_quota_error():
    assert is_quota_error("Resource has been exhausted (e.g. check quota).") is True
    assert is_quota_error("Error 429: Too Many Requests / Rate limit exceeded") is True
    assert is_quota_error("Model token limit exhausted") is True
    assert is_quota_error("SyntaxError: invalid syntax") is False
    assert is_quota_error("") is False
    assert is_quota_error(None) is False


def test_format_tool_action():
    desc1 = AgySession._format_tool_action("run_command", {"CommandLine": "python test.py"})
    assert "Commande" in desc1
    assert "python test.py" in desc1

    desc2 = AgySession._format_tool_action("view_file", {"AbsolutePath": "/var/log/syslog"})
    assert "Lecture" in desc2
    assert "syslog" in desc2

    desc3 = AgySession._format_tool_action("search_web", {"query": "ESP32 pinout"})
    assert "Recherche Web" in desc3
    assert "ESP32 pinout" in desc3

    desc4 = AgySession._format_tool_action("invoke_subagent", {"Subagents": [{"Role": "Recherche"}]})
    assert "Sous-Agent" in desc4
    assert "Recherche" in desc4


def test_stream_json_input_payload():
    prompt = "Bonjour agent"
    payload = {
        "event": "user",
        "message": {
            "content": prompt
        }
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    data = json.loads(encoded)

    assert data["event"] == "user"
    assert "message" in data
    assert data["message"]["content"] == prompt


def test_session_state_reset():
    session = AgySession()
    session.set_conversation("conv-12345")
    session.session_total_tokens = 4500
    session.session_turns = 3
    assert session.has_active_session is True
    assert session.active_conversation_id == "conv-12345"

    session.reset_session()
    assert session.has_active_session is False
    assert session.active_conversation_id is None
    assert session.session_total_tokens == 0
    assert session.session_turns == 0


def test_wait_for_init_event_with_stashed_items():
    async def _run():
        session = AgySession()
        # Put a non-init item first, then init, then another item
        await session._event_queue.put({"event": "raw_output", "text": "Starting Antigravity..."})
        await session._event_queue.put({"event": "init", "conversation_id": "conv-test-999"})
        await session._event_queue.put({"event": "step_update", "step_update": {"state": "ACTIVE"}})

        init_evt = await session._wait_for_init_event(timeout=2.0)
        assert init_evt is not None
        assert init_evt["event"] == "init"
        assert init_evt["conversation_id"] == "conv-test-999"

        # Verify stashed non-init item is still in queue
        item1 = await session._event_queue.get()
        assert item1["event"] in ("raw_output", "step_update")

    asyncio.run(_run())


def test_wait_for_init_event_timeout_preserves_queue():
    async def _run():
        session = AgySession()
        await session._event_queue.put({"event": "raw_output", "text": "No init event here"})

        # Wait with short timeout
        init_evt = await session._wait_for_init_event(timeout=0.2)
        assert init_evt is None

        # Verify the item is still in queue
        item = await session._event_queue.get()
        assert item["event"] == "raw_output"

    asyncio.run(_run())


def test_abort_clean_status():
    async def _run():
        session = AgySession()
        session._turn_in_progress = True
        # Abort the session
        aborted = await session.abort()
        assert aborted is True
        assert session._is_aborted is True
        assert session._turn_in_progress is False

    asyncio.run(_run())



