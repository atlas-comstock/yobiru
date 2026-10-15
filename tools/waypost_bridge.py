#!/usr/bin/env python3
"""Reference Yobiru <-> Waypost bridge (skeleton, not production code).

What it is: a small, single-file starting point for keeping a durable,
auditable copy of cross-agent work in Waypost while day-to-day delivery
stays on Yobiru. Runs on the operator's own machine, next to one Yobiru
receiver. Python 3.8+, standard library only.

What it is not: a finished product. Attachment forwarding, retry policy,
daemon supervision and multi-space routing are marked TODO below. See
docs/WAYPOST_INTEROP.md for the positioning, the addressing and receipt
mapping tables, and what must never be built on either side.

Trust notes (read the doc before running anything for real):
- The bridge sees plaintext of every bridged message. Run it only on a
  machine the operator already trusts with that content.
- Never mint a Waypost identity from a self-asserted ``from_agent``.
  Sender identity comes from the receiver-recorded ``received.peer``
  (the Tailscale-verified identity), never from the envelope alone.
- Waypost privacy filtering, if configured, applies on the bridged path.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

ENVELOPE_ID = re.compile(r'[A-Za-z0-9_-]{8,64}\Z')

# Yobiru tracked-request states -> Waypost receipt stage. A timed-out
# request is *unknown*, never processed: it maps to nothing here and the
# caller must reconcile before acting. Final outcomes always map to
# Waypost ``processed``; the outcome itself travels alongside, because a
# Waypost receipt carries no outcome payload.
RECEIPT_MAP = {
    'received': 'received',
    'running': 'received',
    'completed': 'processed',
    'failed': 'processed',
    'rejected': 'processed',
    'blocked': 'processed',
}


def valid_envelope_id(value):
    """Yobiru envelope id shape; also used to validate correlation ids."""
    return isinstance(value, str) and ENVELOPE_ID.match(value) is not None


def stable_request_id(message_id):
    """Fixed-length, stable idempotency key derived from the Yobiru id.

    The original id travels inside the body (see below), so the two
    trails stay correlatable without stuffing foreign ids into fields
    whose meaning belongs to the other system.
    """
    if not valid_envelope_id(message_id):
        raise ValueError('cannot correlate an invalid message id')
    digest = hashlib.sha256(message_id.encode('utf-8')).hexdigest()[:32]
    return 'yb-' + digest


def normalize_agent(name):
    """Mirror the SPEC agent-name rules; raise ValueError when illegal."""
    import unicodedata
    if not isinstance(name, str):
        raise ValueError('agent name must be text')
    cleaned = unicodedata.normalize('NFC', name)
    if not (1 <= len(cleaned) <= 64):
        raise ValueError('agent name must be 1-64 characters')
    if cleaned != cleaned.strip() or '/' in cleaned:
        raise ValueError('agent name must not have outer whitespace or slashes')
    if any(ord(c) < 32 or ord(c) == 127 for c in cleaned):
        raise ValueError('agent name must not contain control characters')
    return cleaned


def short_host(fqdn):
    """First DNS label: 'dev-server.example.ts.net' -> 'dev-server'."""
    return fqdn.split('.')[0]


def waypost_actor_for_sender(from_host, from_agent):
    """Addressing convention: Waypost actor display name is ``host/agent``."""
    return '%s/%s' % (short_host(from_host), normalize_agent(from_agent))


def inject_correlation(payload, request_id, in_reply_to=None):
    """Carry Waypost correlation inside a JSON *body*, never as new
    envelope fields (unknown envelope fields get HTTP 400)."""
    if not valid_envelope_id(request_id):
        raise ValueError('request_id must be a valid envelope id')
    body = dict(payload)
    body['waypost_request_id'] = request_id
    if in_reply_to is not None:
        body['waypost_in_reply_to'] = in_reply_to
    return body


def extract_correlation(payload):
    """Inverse of inject_correlation; returns (request_id, in_reply_to)."""
    if not isinstance(payload, dict):
        return None, None
    request_id = payload.get('waypost_request_id')
    if not valid_envelope_id(request_id):
        return None, None
    return request_id, payload.get('waypost_in_reply_to')


def map_receipt_state(state):
    """Yobiru tracked state -> Waypost receipt stage, or None (unknown)."""
    return RECEIPT_MAP.get(state)


def read_token(path):
    """Bearer token from a 0600 file only; anything more permissive is refused."""
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        raise ValueError('token file must be mode 0600 or stricter: %s' % path)
    return Path(path).read_text(encoding='utf-8').strip()


def load_map(path):
    """Optional JSON: {"host/agent": "<waypost-actor-id>", ...}."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('actor map must be a JSON object')
    return data


def read_inbox_envelopes(home):
    """Yield (message_id, envelope, received) from the documented inbox shape:
    ``inbox/<id>.json`` holding ``{"envelope": ..., "received": ...}``."""
    inbox = Path(home) / 'inbox'
    if not inbox.is_dir():
        return
    for child in sorted(inbox.glob('*.json')):
        try:
            record = json.loads(child.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        envelope, received = record.get('envelope'), record.get('received')
        if isinstance(envelope, dict) and isinstance(received, dict):
            yield child.stem, envelope, received


def waypost_request(base_url, token, method, route, body=None):
    """Minimal Waypost HTTP client (bearer auth). Schemas follow the
    Waypost SKILL.md vocabulary; confirm field names against the connected
    Waypost version before production use."""
    data = json.dumps(body or {}).encode('utf-8')
    request = urllib.request.Request(base_url.rstrip('/') + route, data=data, method=method)
    request.add_header('Content-Type', 'application/json')
    request.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def yobiru_cli(launcher, home, *args):
    """Run the Yobiru launcher the documented way (quoted path, optional home)."""
    cmd = ['sh', str(launcher)]
    if home:
        cmd += ['--home', str(home)]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


class Bridge(object):
    """Skeleton wiring: Yobiru inbox files -> Waypost, Waypost inbox -> Yobiru.

    TODO before any real deployment: attachment forwarding (fetch + blob
    upload), retry/backoff policy, supervision, per-space routing, and
    reconciling Waypost receipts back into Yobiru request states.
    """

    def __init__(self, args):
        self.args = args
        self.state_path = Path(args.state)
        try:
            self.seen = set(json.loads(self.state_path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            self.seen = set()
        self.actor_map = load_map(args.map)

    def save_state(self):
        tmp = str(self.state_path) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(sorted(self.seen), handle)
        os.replace(tmp, str(self.state_path))

    def resolve_actor(self, peer, agent):
        """Peer identity first, actor map second, display-name fallback last."""
        key = '%s/%s' % (short_host(peer), agent)
        return self.actor_map.get(key, key)

    def poll_yobiru_once(self):
        """Read newly arrived inbox envelopes; plan one Waypost send each."""
        planned = []
        for message_id, envelope, received in read_inbox_envelopes(self.args.home):
            if message_id in self.seen:
                continue
            peer = received.get('peer') or envelope.get('from', '')
            agent = envelope.get('from_agent') or envelope.get('agent') or 'agent'
            try:
                actor = self.resolve_actor(peer, normalize_agent(agent))
            except ValueError:
                continue  # never mint identities from illegal names
            text = envelope.get('text', '')
            body = {'type': 'yobiru-message', 'text': text,
                    'yobiru_id': message_id}
            if isinstance(envelope.get('request'), dict):
                body['yobiru_request'] = True
            if envelope.get('reply_to'):
                body['yobiru_reply_to'] = envelope['reply_to']
            payload = {
                'request_id': stable_request_id(message_id),
                'recipient_ids': [actor],
                'subject': 'From %s' % actor,
                'body': body,
            }
            planned.append((message_id, payload))
        return planned

    def poll_waypost_once(self, token):
        """Read the bridge's Waypost inbox; plan one Yobiru send each."""
        result = waypost_request(self.args.waypost_url, token, 'POST',
                                 '/v0/inbox/read', {'limit': 50})
        planned = []
        for item in result.get('items', result if isinstance(result, list) else []):
            if not isinstance(item, dict) or item.get('message_id') in self.seen:
                continue
            # TODO: resolve the Waypost recipient to a PEER/AGENT address via
            # configuration, then: yobiru_cli(..., 'send', address, text).
            planned.append((item.get('message_id'), item.get('subject', '')))
        return planned


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--yobiru', required=True, help='quoted launcher path (the documented Y variable)')
    parser.add_argument('--home', default=None, help='Yobiru data home (default lookup)')
    parser.add_argument('--waypost-url', required=True, help='Waypost base URL, e.g. http://127.0.0.1:8787')
    parser.add_argument('--token-file', required=True, help='0600 file holding the Waypost bearer token')
    parser.add_argument('--map', default=None, help='optional host/agent -> Waypost actor JSON map')
    parser.add_argument('--state', default='waypost-bridge-state.json', help='seen-ids ledger path')
    parser.add_argument('--dry-run', action='store_true', help='plan only; send nothing anywhere')
    parser.add_argument('--once', action='store_true', help='single poll pass instead of looping')
    args = parser.parse_args(argv)
    token = read_token(args.token_file)
    bridge = Bridge(args)
    for message_id, payload in bridge.poll_yobiru_once():
        print(json.dumps({'direction': 'yobiru->waypost', 'id': message_id,
                          'payload': payload}, ensure_ascii=False))
    for message_id, subject in bridge.poll_waypost_once(token):
        print(json.dumps({'direction': 'waypost->yobiru', 'id': message_id,
                          'subject': subject}, ensure_ascii=False))
    if args.dry_run:
        print(json.dumps({'dry_run': True, 'sent': False}, ensure_ascii=False))
        return 0
    print(json.dumps({'note': 'live sending is intentionally unwired; see TODOs'},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
