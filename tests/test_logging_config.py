from stripe_integration.logging_config import _scrub_sensitive, configure_logging


def scrub(event_dict: dict) -> dict:
    return _scrub_sensitive(None, None, event_dict)


class TestScrubSensitive:
    def test_redacts_stripe_test_key(self):
        result = scrub({"event": "key=sk_test_abc123xyz"})
        assert "sk_test_abc123xyz" not in result["event"]
        assert "[REDACTED]" in result["event"]

    def test_redacts_stripe_live_key(self):
        result = scrub({"event": "key=sk_live_abc123xyz"})
        assert "sk_live_abc123xyz" not in result["event"]
        assert "[REDACTED]" in result["event"]

    def test_redacts_webhook_secret(self):
        result = scrub({"secret": "whsec_myhooksecret123"})
        assert "whsec_myhooksecret123" not in result["secret"]
        assert "[REDACTED]" in result["secret"]

    def test_redacts_pan_length_digits_13(self):
        result = scrub({"card": "4111111111111"})  # 13 digits
        assert "[REDACTED]" in result["card"]

    def test_redacts_pan_length_digits_16(self):
        result = scrub({"card": "4111111111111111"})  # 16 digits
        assert "[REDACTED]" in result["card"]

    def test_redacts_pan_length_digits_19(self):
        result = scrub({"card": "4111111111111111111"})  # 19 digits
        assert "[REDACTED]" in result["card"]

    def test_short_number_not_redacted(self):
        result = scrub({"amount": "4200"})
        assert result["amount"] == "4200"

    def test_non_string_int_passes_through(self):
        result = scrub({"count": 42})
        assert result["count"] == 42

    def test_non_string_bool_passes_through(self):
        result = scrub({"flag": True})
        assert result["flag"] is True

    def test_non_string_none_passes_through(self):
        result = scrub({"data": None})
        assert result["data"] is None

    def test_safe_string_unchanged(self):
        result = scrub({"event": "user_signed_up", "user_id": "usr_123"})
        assert result["event"] == "user_signed_up"
        assert result["user_id"] == "usr_123"

    def test_multiple_keys_scrubbed_in_single_call(self):
        result = scrub({"k1": "sk_test_aaa", "k2": "whsec_bbb"})
        assert "[REDACTED]" in result["k1"]
        assert "[REDACTED]" in result["k2"]

    def test_returns_event_dict(self):
        d = {"event": "ok"}
        result = scrub(d)
        assert result is d  # mutates and returns same dict


class TestConfigureLogging:
    def test_production_mode_does_not_raise(self):
        configure_logging(debug=False)

    def test_debug_mode_does_not_raise(self):
        configure_logging(debug=True)
