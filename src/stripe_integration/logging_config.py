import logging
import re
import sys

import structlog

# Matches Stripe secret keys, webhook secrets, and bare PAN-length digit strings
_SENSITIVE_RE = re.compile(
    r"(sk_(?:test|live)_\w+|whsec_\w+|\b\d{13,19}\b)",
    re.IGNORECASE,
)


def _scrub_sensitive(_logger, _method, event_dict: dict) -> dict:
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = _SENSITIVE_RE.sub("[REDACTED]", value)
    return event_dict


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub_sensitive,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
