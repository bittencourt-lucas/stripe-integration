import pytest
from pydantic import ValidationError

from stripe_integration.schemas import ErrorResponse, HealthResponse


class TestHealthResponse:
    def test_creates_with_valid_data(self):
        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
        assert h.version == "0.1.0"

    def test_serializes_to_dict(self):
        assert HealthResponse(status="ok", version="0.1.0").model_dump() == {
            "status": "ok",
            "version": "0.1.0",
        }

    def test_missing_status_raises(self):
        with pytest.raises(ValidationError):
            HealthResponse(version="0.1.0")  # type: ignore[call-arg]

    def test_missing_version_raises(self):
        with pytest.raises(ValidationError):
            HealthResponse(status="ok")  # type: ignore[call-arg]


class TestErrorResponse:
    def test_creates_with_detail(self):
        assert ErrorResponse(detail="something went wrong").detail == "something went wrong"

    def test_serializes_to_dict(self):
        assert ErrorResponse(detail="oops").model_dump() == {"detail": "oops"}

    def test_missing_detail_raises(self):
        with pytest.raises(ValidationError):
            ErrorResponse()  # type: ignore[call-arg]

    def test_empty_string_detail_accepted(self):
        assert ErrorResponse(detail="").detail == ""
