import json
import logging
from unittest import mock

from django.db import OperationalError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from django_project import observability


class Healthz(TestCase):
    def test_reports_ok_without_logging_in(self):
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok'})

    def test_answers_503_when_the_database_is_down(self):
        with mock.patch('main.health.connection.cursor', side_effect=OperationalError('down')):
            response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'error', 'database': 'unreachable'})

    def test_is_never_cached_and_leaks_no_details(self):
        response = self.client.get(reverse('healthz'))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn('version', response.json())


class JsonLogs(SimpleTestCase):
    def record(self, **kw):
        return logging.LogRecord('main.requests', kw.get('level', logging.WARNING), __file__, 1,
                                 kw.get('msg', 'نمونه %s'), kw.get('args', ('پیام',)), kw.get('exc_info'))

    def test_one_json_object_per_line_with_the_fields_a_log_tool_needs(self):
        line = observability.JsonFormatter().format(self.record())
        data = json.loads(line)
        self.assertEqual((data['level'], data['logger'], data['message']), ('WARNING', 'main.requests', 'نمونه پیام'))
        self.assertIn('time', data)
        self.assertNotIn('\n', line)

    def test_exceptions_are_included(self):
        with self.assertRaises(ValueError) as caught:
            raise ValueError('boom')
        error = caught.exception
        exc_info = (type(error), error, error.__traceback__)
        line = observability.JsonFormatter().format(self.record(level=logging.ERROR, exc_info=exc_info))
        self.assertIn('ValueError: boom', json.loads(line)['exception'])


class SentrySetup(SimpleTestCase):
    def test_does_nothing_without_a_dsn(self):
        with mock.patch('sentry_sdk.init') as init:
            self.assertFalse(observability.init_sentry(''))
        init.assert_not_called()

    def test_starts_without_personal_data_when_a_dsn_is_set(self):
        with mock.patch('sentry_sdk.init') as init:
            self.assertTrue(observability.init_sentry('https://key@example.invalid/1'))
        kwargs = init.call_args.kwargs
        self.assertFalse(kwargs['send_default_pii'])
        self.assertEqual(kwargs['traces_sample_rate'], 0)
