#!/usr/bin/env python3
"""Keep the server on the DNS that reaches GitHub most reliably (the server has no direct foreign internet access).

Runs as a service (``run``), checks GitHub every few seconds and remembers how each DNS pair did:

* every tick the pair in use is probed, plus one other pair in turn (so each is re-checked about every 20 seconds);
* a probe asks that pair for github.com, then opens a TLS connection to the answer and checks GitHub's certificate. It
  never sends an HTTP request, so GitHub is not hammered and a DNS that answers with a block page or a wrong address fails;
* the best pair over the last 20 probes (success rate, then speed) is used. The pair in use is kept unless it failed twice in
  a row, or another pair is clearly steadier (20 points higher success rate): no flapping between two good ones;
* when nothing works for a minute the network's own DNS is restored.

Other commands:  ``status``  scores and the pair in use;  ``ensure``  one-shot check before a deploy: if a real
``git`` request to GitHub fails it walks the pairs best first until one works (``--switch`` skips the one in use).

Needs systemd-resolved (Ubuntu default) and root; standard library only. Installed by deploy/install_dns_watch.sh.
"""
import http.client
import itertools
import json
import os
import re
import signal
import socket
import ssl
import struct
import subprocess
import sys
import time
from collections import deque
from statistics import median

SERVERS = [                                    # name -> the two DNS servers of one provider
    ('Electro', ['78.157.42.100', '78.157.42.101']),
    ('403.online', ['10.202.10.202', '10.202.10.102']),
    ('Radar Game', ['10.202.10.10', '10.202.10.11']),
    ('Shecan', ['178.22.122.100', '185.51.200.2']),
    ('Begzar', ['185.55.226.26', '185.55.225.25']),
    ('Shatel', ['85.15.1.14', '85.15.1.15']),
]
HOST = 'github.com'
GIT_PATH = '/imerfs/milkid.git/info/refs?service=git-upload-pack'     # what `git pull` asks first
INTERVAL = 3.0
WINDOW = 20
MIN_SAMPLES = 3
SWITCH_MARGIN = 0.2
DNS_TIMEOUT = 1.2
TLS_TIMEOUT = 2.5
HTTP_TIMEOUT = 8
DOWN_AFTER = 60                                # seconds with no working pair before the network's own DNS is restored
STATE_FILE = os.environ.get('DNS_WATCH_STATE', '/run/dns-github-watch.json')


# ---------- DNS over UDP, by hand (no dig needed) ----------

def build_query(name, qid=None):
    qid = int.from_bytes(os.urandom(2), 'big') if qid is None else qid
    header = struct.pack('>HHHHHH', qid, 0x0100, 1, 0, 0, 0)
    question = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\x00' + struct.pack('>HH', 1, 1)
    return qid, header + question


def parse_a_records(data, qid):
    """The IPv4 addresses in a DNS answer; empty for anything that is not a clean answer to ``qid``."""
    try:
        if len(data) < 12:
            return []
        rid, flags, questions, answers = struct.unpack('>HHHH', data[:8])
        if rid != qid or flags & 0x000F:                    # an error code
            return []

        def skip_name(pos):
            while True:
                length = data[pos]
                if length == 0:
                    return pos + 1
                if length & 0xC0 == 0xC0:
                    return pos + 2
                pos += 1 + length

        pos = 12
        for _ in range(questions):
            pos = skip_name(pos) + 4
        found = []
        for _ in range(answers):
            pos = skip_name(pos)
            rtype, _rclass, _ttl, length = struct.unpack('>HHIH', data[pos:pos + 10])
            pos += 10
            if rtype == 1 and length == 4:
                found.append('.'.join(str(b) for b in data[pos:pos + 4]))
            pos += length
        return found
    except (IndexError, struct.error):
        return []


def resolve(server, name=HOST, timeout=DNS_TIMEOUT):
    qid, packet = build_query(name)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(1500)
    return parse_a_records(data, qid)


def handshake(ip, timeout=TLS_TIMEOUT):
    """A TLS handshake with ``ip`` as github.com: the certificate must be GitHub's."""
    context = ssl.create_default_context()
    with socket.create_connection((ip, 443), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=HOST):
            return True


def probe(pair):
    """(ok, milliseconds): ask the pair for github.com and shake hands with the answer."""
    start = time.monotonic()
    for server in pair:
        try:
            ips = resolve(server)
            if ips and handshake(ips[0]):
                return True, (time.monotonic() - start) * 1000
        except (OSError, ssl.SSLError, ValueError):
            continue
    return False, (time.monotonic() - start) * 1000


# ---------- who is steadier ----------

def score(samples):
    if not samples:
        return None
    up = [ms for ok, ms in samples if ok]
    return {'n': len(samples), 'rate': len(up) / len(samples), 'ms': median(up) if up else None, 'last_ok': samples[-1][0]}


def choose(stats, current):
    """The pair to use now. ``stats``: name -> samples [(ok, ms)] (newest last). Stays on ``current`` unless it is down or beaten."""
    scores = {name: score(list(samples)) for name, samples in stats.items()}
    usable = {name: sc for name, sc in scores.items() if sc and sc['n'] >= MIN_SAMPLES and sc['last_ok'] and sc['rate'] > 0}
    if not usable:
        return current
    best = max(usable, key=lambda name: (usable[name]['rate'], -(usable[name]['ms'] or 1e9)))
    if current not in stats or not stats[current]:
        return best
    recent = list(stats[current])[-2:]
    if not any(ok for ok, _ in recent):                     # two failures in a row: leave it
        return best
    if current in usable and usable[best]['rate'] >= usable[current]['rate'] + SWITCH_MARGIN:
        return best
    return current


# ---------- the system's resolver ----------

def interface():
    out = subprocess.run(['ip', '-o', 'route', 'get', '1.1.1.1'], capture_output=True, text=True, check=False).stdout
    match = re.search(r' dev (\S+)', out)
    return match.group(1) if match else None


def apply(name, pair):
    iface = interface()
    if not iface:
        print('no network interface found', flush=True)
        return False
    subprocess.run(['resolvectl', 'dns', iface, *pair], check=False)
    subprocess.run(['resolvectl', 'default-route', iface, 'yes'], check=False)
    subprocess.run(['resolvectl', 'flush-caches'], check=False)
    print(f'using {name}: {" ".join(pair)}', flush=True)
    return True


def revert():
    iface = interface()
    if iface:
        subprocess.run(['resolvectl', 'revert', iface], check=False)
        subprocess.run(['resolvectl', 'flush-caches'], check=False)
        print("nothing reaches GitHub; back to the network's own DNS", flush=True)


def git_reachable():
    """What git does first: GET info/refs over HTTPS through the system's DNS. True on a 200."""
    try:
        conn = http.client.HTTPSConnection(HOST, timeout=HTTP_TIMEOUT)
        conn.request('GET', GIT_PATH, headers={'User-Agent': 'git/2'})
        ok = conn.getresponse().status == 200
        conn.close()
        return ok
    except (OSError, ssl.SSLError, http.client.HTTPException):
        return False


# ---------- state shared with `status` and `ensure` ----------

def write_state(current, stats):
    payload = {'current': current, 'updated': int(time.time()),
               'scores': {name: score(list(samples)) for name, samples in stats.items()}, 'pid': os.getpid()}
    try:
        with open(STATE_FILE + '.tmp', 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        os.replace(STATE_FILE + '.tmp', STATE_FILE)
    except OSError:
        pass


def read_state():
    try:
        with open(STATE_FILE, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


# ---------- commands ----------

def run():
    pairs = dict(SERVERS)
    stats = {name: deque(maxlen=WINDOW) for name in pairs}
    state = {'reread': False, 'down_since': None, 'reverted': False}
    signal.signal(signal.SIGUSR1, lambda *_: state.update(reread=True))
    for _ in range(MIN_SAMPLES):                                  # a first look at everyone
        for name, pair in SERVERS:
            stats[name].append(probe(pair))
    current = choose(stats, None)
    if current:
        apply(current, pairs[current])
    rotation = itertools.cycle([name for name, _ in SERVERS])
    while True:
        write_state(current, stats)
        time.sleep(INTERVAL)
        if state['reread']:                                       # `ensure` switched the pair by hand
            state['reread'] = False
            chosen = read_state().get('current')
            if chosen in pairs:
                current = chosen
        if current:
            stats[current].append(probe(pairs[current]))
        other = next(name for name in rotation if name != current)
        stats[other].append(probe(pairs[other]))
        new = choose(stats, current)
        if new and new != current:
            print(f'switching from {current} to {new}', flush=True)
            if apply(new, pairs[new]):
                current = new
        working = any(s and s[-1][0] for s in stats.values())
        if working:
            state['down_since'] = None
            if state['reverted'] and current:
                apply(current, pairs[current])
                state['reverted'] = False
        else:
            state['down_since'] = state['down_since'] or time.monotonic()
            if not state['reverted'] and time.monotonic() - state['down_since'] > DOWN_AFTER:
                revert()
                state['reverted'] = True


def status():
    state = read_state()
    if not state:
        print('the service has not written its state yet (is dns-github-watch running?)')
        return 1
    print(f'in use: {state.get("current")}   (updated {int(time.time()) - state.get("updated", 0)} s ago)')
    for name, sc in sorted((state.get('scores') or {}).items(), key=lambda kv: -((kv[1] or {}).get('rate') or 0)):
        if sc:
            ms = f'{sc["ms"]:.0f} ms' if sc['ms'] is not None else '-'
            print(f'  {name:12} success {sc["rate"] * 100:3.0f}%  median {ms:>8}  over {sc["n"]} probes')
    return 0


def ensure(switch=False):
    """Make sure a real git request works now: try the pairs best first until one does."""
    state = read_state()
    pairs = dict(SERVERS)
    in_use = state.get('current')
    if not switch and git_reachable():
        print('GitHub is reachable.')
        return 0
    ranked = sorted(pairs, key=lambda name: -(((state.get('scores') or {}).get(name) or {}).get('rate') or 0))
    for name in ranked:
        if switch and name == in_use:
            continue
        ok, _ = probe(pairs[name])
        if not ok:
            continue
        apply(name, pairs[name])
        if git_reachable():
            print(f'GitHub is reachable through {name}.')
            state['current'] = name
            try:
                with open(STATE_FILE, 'w', encoding='utf-8') as handle:
                    json.dump(state, handle)
                if state.get('pid'):
                    os.kill(state['pid'], signal.SIGUSR1)         # the service keeps the same pair
            except (OSError, ProcessLookupError):
                pass
            return 0
    print('GitHub is not reachable through any listed DNS.')
    return 1


def main(argv):
    command = argv[1] if len(argv) > 1 else 'status'
    if command == 'run':
        run()
        return 0
    if command == 'status':
        return status()
    if command == 'ensure':
        return ensure(switch='--switch' in argv)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
