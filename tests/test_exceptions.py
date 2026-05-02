import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from stripe_integration.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)


# ---------------------------------------------------------------------------
# Exception class unit tests
# ---------------------------------------------------------------------------


class TestAppError:
    def test_default_status_code_is_500(self):
        assert AppError("broke").status_code == 500

    def test_custom_status_code(self):
        assert AppError("bad", 422).status_code == 422

    def test_message_stored(self):
        assert AppError("something").message == "something"

    def test_str_is_message(self):
        assert str(AppError("msg")) == "msg"

    def test_is_exception_subclass(self):
        assert isinstance(AppError("x"), Exception)


class TestNotFoundError:
    def test_default_status_code(self):
        assert NotFoundError().status_code == 404

    def test_default_message(self):
        assert NotFoundError().message == "Resource not found"

    def test_custom_message(self):
        assert NotFoundError("payment missing").message == "payment missing"

    def test_is_app_error(self):
        assert isinstance(NotFoundError(), AppError)


class TestUnauthorizedError:
    def test_default_status_code(self):
        assert UnauthorizedError().status_code == 401

    def test_default_message(self):
        assert UnauthorizedError().message == "Unauthorized"

    def test_custom_message(self):
        assert UnauthorizedError("bad token").message == "bad token"

    def test_is_app_error(self):
        assert isinstance(UnauthorizedError(), AppError)


class TestConflictError:
    def test_default_status_code(self):
        assert ConflictError().status_code == 409

    def test_default_message(self):
        assert ConflictError().message == "Conflict"

    def test_custom_message(self):
        assert ConflictError("duplicate key").message == "duplicate key"

    def test_is_app_error(self):
        assert isinstance(ConflictError(), AppError)


# ---------------------------------------------------------------------------
# Handler integration tests via a minimal test app
# ---------------------------------------------------------------------------


@pytest.fixture
def exc_app():
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/not-found")
    async def raise_not_found():
        raise NotFoundError("the item was not found")

    @app.get("/unauthorized")
    async def raise_unauthorized():
        raise UnauthorizedError()

    @app.get("/conflict")
    async def raise_conflict():
        raise ConflictError("duplicate exists")

    @app.get("/app-error-custom")
    async def raise_custom_app_error():
        raise AppError("custom app error", 422)

    @app.get("/http-exception")
    async def raise_http():
        raise StarletteHTTPException(status_code=403, detail="forbidden")

    @app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("internal boom — must not reach client")

    return app


@pytest.fixture
async def exc_client(exc_app):
    # raise_app_exceptions=False lets ServerErrorMiddleware return the 500 response
    # instead of re-raising (Starlette always re-raises after calling the handler).
    async with AsyncClient(
        transport=ASGITransport(app=exc_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


async def test_not_found_returns_404(exc_client):
    resp = await exc_client.get("/not-found")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "the item was not found"}


async def test_unauthorized_returns_401(exc_client):
    resp = await exc_client.get("/unauthorized")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_conflict_returns_409(exc_client):
    resp = await exc_client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "duplicate exists"}


async def test_app_error_custom_status_code(exc_client):
    resp = await exc_client.get("/app-error-custom")
    assert resp.status_code == 422
    assert resp.json() == {"detail": "custom app error"}


async def test_http_exception_preserves_status_and_detail(exc_client):
    resp = await exc_client.get("/http-exception")
    assert resp.status_code == 403
    assert resp.json() == {"detail": "forbidden"}


async def test_unhandled_exception_returns_generic_500(exc_client):
    resp = await exc_client.get("/unhandled")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


async def test_unhandled_exception_does_not_leak_internal_message(exc_client):
    resp = await exc_client.get("/unhandled")
    assert "internal boom" not in resp.text
    assert "RuntimeError" not in resp.text
