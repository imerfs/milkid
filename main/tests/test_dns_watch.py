"""The server's DNS watch (deploy/dns-github-watch.py): the DNS packet code and which pair it decides to use."""
import importlib.util
import struct
from collections import deque
from pathlib import Path
from unittest import TestCase, mock

SCRIPT = Path(__file__).resolve().parents[2] / 'deploy' / 'dns-github-watch.py'
spec = importlib.util.spec_from_file_location('dns_github_watch', SCRIPT)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def answer(qid, ips, rcode=0, compress=True):
    """A DNS reply to a github.com A query with the given addresses."""
    _, query = watch.build_query('github.com', qid)
    header = struct.pack('>HHHHHH', qid, 0x8180 | rcode, 1, len(ips), 0, 0)
    body = query[12:]
    records = b''
    for ip in ips:
        name = b'\xc0\x0c' if compress else b'\x06github\x03com\x00'
        records += name + struct.pack('>HHIH', 1, 1, 60, 4) + bytes(int(p) for p in ip.split('.'))
    return header + body + records


def samples(*flags):
    return deque(((flag, 100.0) for flag in flags), maxlen=watch.WINDOW)


class Packets(TestCase):
    def test_query_has_the_name_and_asks_for_an_a_record(self):
        qid, packet = watch.build_query('github.com', 0x1234)
        self.assertEqual(qid, 0x1234)
        self.assertEqual(packet[:2], b'\x12\x34')
        self.assertIn(b'\x06github\x03com\x00', packet)
        self.assertEqual(packet[-4:], struct.pack('>HH', 1, 1))

    def test_answers_are_read_with_and_without_name_compression(self):
        for compress in (True, False):
            self.assertEqual(watch.parse_a_records(answer(7, ['140.82.121.4', '1.2.3.4'], compress=compress), 7),
                             ['140.82.121.4', '1.2.3.4'])

    def test_wrong_id_error_code_and_junk_give_nothing(self):
        self.assertEqual(watch.parse_a_records(answer(7, ['1.2.3.4']), 8), [])
        self.assertEqual(watch.parse_a_records(answer(7, [], rcode=3), 7), [])
        self.assertEqual(watch.parse_a_records(b'', 7), [])
        self.assertEqual(watch.parse_a_records(b'\x00' * 40, 7), [])
        self.assertEqual(watch.parse_a_records(answer(7, ['1.2.3.4'])[:20], 7), [])


class Probing(TestCase):
    def test_a_pair_works_when_the_second_server_does_even_if_the_first_is_silent(self):
        def resolve(server, *args, **kwargs):
            if server == 'a':
                raise OSError('timeout')
            return ['140.82.121.4']
        with mock.patch.object(watch, 'resolve', resolve), mock.patch.object(watch, 'handshake', return_value=True):
            self.assertTrue(watch.probe(['a', 'b'])[0])

    def test_a_dns_that_answers_a_wrong_address_fails_the_handshake(self):
        with mock.patch.object(watch, 'resolve', return_value=['10.10.34.35']), \
                mock.patch.object(watch, 'handshake', side_effect=watch.ssl.SSLError('wrong certificate')):
            self.assertFalse(watch.probe(['a', 'b'])[0])

    def test_no_answer_at_all_is_a_failure(self):
        with mock.patch.object(watch, 'resolve', return_value=[]):
            self.assertFalse(watch.probe(['a', 'b'])[0])


class Choosing(TestCase):
    def test_first_choice_is_the_steadiest(self):
        stats = {'x': samples(True, True, True, False), 'y': samples(True, True, True, True), 'z': samples(False, False, False)}
        self.assertEqual(watch.choose(stats, None), 'y')

    def test_stays_on_a_working_pair_unless_another_is_clearly_steadier(self):
        stats = {'x': samples(True, True, True, True, False, True), 'y': samples(True, True, True, True, True, True)}
        self.assertEqual(watch.choose(stats, 'x'), 'x')                  # 83 % against 100 %: not worth a switch
        stats['x'] = samples(True, False, True, False, True, True)       # 66 %: y is 34 points better
        self.assertEqual(watch.choose(stats, 'x'), 'y')

    def test_two_failures_in_a_row_leave_the_pair_at_once(self):
        stats = {'x': samples(True, True, True, True, False, False), 'y': samples(True, True, True)}
        self.assertEqual(watch.choose(stats, 'x'), 'y')

    def test_one_failure_alone_does_not(self):
        stats = {'x': samples(True, True, True, True, False), 'y': samples(True, True, True)}
        self.assertEqual(watch.choose(stats, 'x'), 'x')

    def test_faster_wins_a_tie(self):
        slow = deque(((True, 900.0),) * 5, maxlen=watch.WINDOW)
        fast = deque(((True, 80.0),) * 5, maxlen=watch.WINDOW)
        self.assertEqual(watch.choose({'slow': slow, 'fast': fast}, None), 'fast')

    def test_nothing_usable_keeps_what_there_is(self):
        stats = {'x': samples(False, False, False), 'y': samples(False)}
        self.assertEqual(watch.choose(stats, 'x'), 'x')
        self.assertIsNone(watch.choose(stats, None))

    def test_the_list_has_six_distinct_pairs_with_two_servers_each(self):
        self.assertEqual(len(watch.SERVERS), 6)
        self.assertEqual(len({name for name, _ in watch.SERVERS}), 6)
        self.assertTrue(all(len(pair) == 2 for _, pair in watch.SERVERS))
        self.assertIn(['85.15.1.14', '85.15.1.15'], [pair for _, pair in watch.SERVERS])
