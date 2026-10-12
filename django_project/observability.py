"""Logging and error-reporting helpers: JSON log lines for log tools, optional Sentry."""
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to ship to any log tool and to grep."""

    def format(self, record):
        data = {
            'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            data['exception'] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def init_sentry(dsn):
    """Start error reporting when SENTRY_DSN is set. No personal data is sent and tracing is off."""
    if not dsn:
        return False
    import sentry_sdk
    sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0)
    return True
