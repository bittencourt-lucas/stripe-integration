import pytest
import stripe
from unittest.mock import MagicMock

from stripe_integration.exceptions import AppError, NotFoundError
from stripe_integration.stripe_client import _map_stripe_error, stripe_call


def _make_error(cls, user_message="error", code=None):
    """Return a MagicMock that passes isinstance checks for the given stripe error class."""
    m = MagicMock()
    m.__class__ = cls
    m.user_message = user_message
    m.code = code
    m.http_status = None
    return m


# ---------------------------------------------------------------------------
# _map_stripe_error unit tests
# ---------------------------------------------------------------------------


class TestMapStripeError:
    def test_card_error_returns_402(self):
        result = _map_stripe_error(_make_error(stripe.CardError, "Your card was declined"))
        assert result.status_code == 402
        assert result.message == "Your card was declined"

    def test_card_error_falls_back_when_no_user_message(self):
        exc = _make_error(stripe.CardError)
        exc.user_message = None
        result = _map_stripe_error(exc)
        assert result.status_code == 402

    def test_invalid_request_returns_400(self):
        result = _map_stripe_error(
            _make_error(stripe.InvalidRequestError, "Invalid amount", code="parameter_invalid_integer")
        )
        assert result.status_code == 400
        assert result.message == "Invalid amount"

    def test_invalid_request_resource_missing_returns_404(self):
        result = _map_stripe_error(
            _make_error(stripe.InvalidRequestError, "No such payment_intent", code="resource_missing")
        )
        assert isinstance(result, NotFoundError)
        assert result.status_code == 404

    def test_rate_limit_error_returns_429(self):
        result = _map_stripe_error(_make_error(stripe.RateLimitError))
        assert result.status_code == 429

    def test_authentication_error_returns_500(self):
        result = _map_stripe_error(_make_error(stripe.AuthenticationError))
        assert result.status_code == 500

    def test_api_connection_error_returns_503(self):
        result = _map_stripe_error(_make_error(stripe.APIConnectionError))
        assert result.status_code == 503

    def test_generic_stripe_error_returns_500(self):
        result = _map_stripe_error(_make_error(stripe.StripeError))
        assert result.status_code == 500

    def test_always_returns_app_error_instance(self):
        for cls in [
            stripe.CardError,
            stripe.InvalidRequestError,
            stripe.RateLimitError,
            stripe.AuthenticationError,
            stripe.APIConnectionError,
            stripe.StripeError,
        ]:
            assert isinstance(_map_stripe_error(_make_error(cls)), AppError)


# ---------------------------------------------------------------------------
# stripe_call unit tests
# ---------------------------------------------------------------------------


class TestStripeCall:
    async def test_returns_result_on_success(self):
        result = await stripe_call(lambda: 42)
        assert result == 42

    async def test_passes_positional_args(self):
        result = await stripe_call(lambda a, b: a + b, 3, 4)
        assert result == 7

    async def test_passes_keyword_args(self):
        result = await stripe_call(lambda a=0, b=0: a * b, a=3, b=4)
        assert result == 12

    async def test_maps_stripe_error_to_app_error(self):
        def raises():
            raise stripe.StripeError("boom")

        with pytest.raises(AppError):
            await stripe_call(raises)

    async def test_non_stripe_exceptions_propagate_unchanged(self):
        def raises():
            raise ValueError("not a stripe error")

        with pytest.raises(ValueError, match="not a stripe error"):
            await stripe_call(raises)

    async def test_stripe_error_status_code_is_mapped(self):
        def raises():
            raise stripe.RateLimitError()

        with pytest.raises(AppError) as exc_info:
            await stripe_call(raises)
        assert exc_info.value.status_code == 429
