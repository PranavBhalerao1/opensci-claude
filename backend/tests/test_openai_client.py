"""The OpenAI adapter: Messages-API requests in, Responses-API bodies out, and back (app/openai_client.py)."""

import anthropic

from app import openai_client as oc


def test_tool_loop_transcript_translates_to_responses_input():
    reasoning = oc.ReasoningBlock({"type": "reasoning", "id": "rs_1", "encrypted_content": "x", "summary": []})
    body = oc._body(
        model="gpt-5.5", max_tokens=1000, system="sys",
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "go"}]},
            {"role": "assistant", "content": [reasoning, oc.ToolUseBlock("call_1", "run_python", {"code": "1"})]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "1",
                                          "cache_control": {"type": "ephemeral"}}]},
        ],
        tools=[{"name": "run_python", "description": "d", "input_schema": {"type": "object"}}],
        tool_choice={"type": "any"}, output_config={"effort": "low"}, thinking={"type": "adaptive"},
    )
    assert body["instructions"] == "sys" and body["store"] is False
    assert [i.get("type") or i["role"] for i in body["input"]] == ["user", "reasoning", "function_call", "function_call_output"]
    assert body["input"][3] == {"type": "function_call_output", "call_id": "call_1", "output": "1"}
    assert body["tools"][0]["name"] == "run_python" and body["tool_choice"] == "required"
    assert body["reasoning"]["effort"] == "medium"  # raised to the configured floor
    assert body["max_output_tokens"] == 64_000  # the floor
    assert oc._body(model="m", max_tokens=64_000, messages=[])["max_output_tokens"] == 128_000  # 2×, capped


def test_json_schema_and_response_translation():
    body = oc._body(model="m", max_tokens=10, messages=[{"role": "user", "content": "q"}],
                    output_config={"effort": "high", "format": {"type": "json_schema", "schema": {"type": "object"}}})
    assert body["text"]["format"]["type"] == "json_schema" and body["reasoning"]["effort"] == "high"

    msg = oc._message({"status": "completed", "output": [
        {"type": "reasoning", "id": "rs", "status": "completed"},
        {"type": "message", "content": [{"type": "output_text", "text": "{}"}]},
        {"type": "function_call", "call_id": "c", "name": "t", "arguments": "{\"a\": 1}"},
    ], "usage": {"input_tokens": 100, "output_tokens": 7, "input_tokens_details": {"cached_tokens": 40}}}, "m")
    assert [b.type for b in msg.content] == ["thinking", "text", "tool_use"]
    assert msg.stop_reason == "tool_use" and msg.content[2].input == {"a": 1}
    assert (msg.usage.input_tokens, msg.usage.cache_read_input_tokens, msg.usage.output_tokens) == (60, 40, 7)

    cut = oc._message({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []}, "m")
    assert cut.stop_reason == "max_tokens"


def test_errors_are_the_anthropic_sdk_types_callers_handle():
    assert isinstance(oc._status_error(429, "{}"), anthropic.RateLimitError)
    assert isinstance(oc._status_error(400, '{"error": {"message": "bad"}}'), anthropic.BadRequestError)
    assert isinstance(oc._status_error(502, "x"), anthropic.InternalServerError)


def test_an_account_out_of_credits_is_not_a_retryable_rate_limit():
    body = '{"error": {"message": "You have no credits remaining.", "type": "insufficient_quota", "code": "insufficient_quota"}}'
    err = oc._status_error(429, body)
    assert isinstance(err, anthropic.PermissionDeniedError) and not isinstance(err, anthropic.RateLimitError)
    assert oc._out_of_credits(429, body) and not oc._out_of_credits(429, '{"error": {"code": "rate_limit_exceeded"}}')
