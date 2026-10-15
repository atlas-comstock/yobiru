# Waypost interop: durable coordination beside Yobiru delivery

**Status:** proposal with a runnable reference. Nothing here changes the
wire protocol, the receiver, or any default path.

[简体中文](WAYPOST_INTEROP.zh-CN.md)

## What Waypost is

[Waypost](https://github.com/mainline-org/waypost) is a durable mailbox
and versioned source-memory service for assistants: one server holds
messages, attachments and library revisions; assistants connect over
HTTP or MCP with scoped credentials and per-client read cursors. It
answers three questions Yobiru deliberately leaves open: what arrived
while a machine was offline, what the full history of a handoff looks
like, and which revision of a shared file everyone is talking about.
Waypost is Apache-2.0; like Yobiru it is skill-driven, so an assistant
with both connections needs no new interface to learn.

## Positioning: transport beside coordination, never inside it

- **Yobiru** stays the edge: direct delivery, wake-ups, per-machine
  policy, no central storage. Nothing in this document adds a store to
  Yobiru's critical path or changes what a receiver accepts.
- **Waypost** is opt-in durability next to it: offline buffering, a
  searchable cross-machine trail, versioned artifacts, and one inbox a
  lead assistant can summarize.
- Either side works fine alone. An operator who never runs the bridge
  below notices no difference at all.

## Routing convention: which channel for what

| Situation | Use |
|---|---|
| Hot peer-to-peer delivery, wake-ups, quiet hours, rate limits | Yobiru |
| Recipient may be offline; sender must not block | Waypost (or bridge it there) |
| Proof of what was handed over, across machines and days | Waypost inbox + receipts |
| A lead assistant summarizing several workers | Waypost inbox as the single collection point |
| Files both sides already hold, fetched peer-to-peer | Yobiru `fetch` |
| Files that must stay citable at a fixed revision | Waypost sealed blobs / memory revisions |

## Addressing: `host/agent` both ways

A Waypost actor that fronts a Yobiru participant uses the display name
`host/agent` with the short Tailscale hostname, e.g. `dev-server/codex`.
Short names are re-resolved on every send from current `tailscale`
status, exactly like Yobiru peer resolution: a unique online match wins,
ambiguous matches are rejected, never pick by list order. After a
rebuild, restore the chosen hostname before expecting bridged mail to
find the same actor.

## Envelope convention: correlate inside JSON bodies

Never add top-level envelope fields: receivers reject unknown fields
with HTTP 400. Correlation travels inside JSON **text** payloads:

```json
{"type": "status", "ok": true,
 "waypost_request_id": "9f2c4e1ab07d33c5",
 "waypost_in_reply_to": "1a2b3c4d5e6f7a8b"}
```

Rules:

- Yobiru `reply_to` chains stay native; a bridged copy additionally
  carries `waypost_in_reply_to` so the Waypost trail links the same way.
- A Waypost `request_id` is stable per logical write and doubles as the
  dedup key on resume. When a Yobiru envelope id is usable as such, the
  reference bridge derives a fixed-shape `yb-<sha256[:32]>` key from it
  and keeps the original id in the body, so both trails stay joinable.
- `yobiru_id` / `yobiru_reply_to` keys inside a Waypost message body
  point back the other way. Either side can be dropped without breaking
  the other system's own semantics.

## Receipt mapping

Yobiru tracked states map onto Waypost receipt stages like this:

| Yobiru state | Waypost stage | Note |
|---|---|---|
| `received` | `received` | stored, nothing more claimed |
| `running` | `received` | started is not processed |
| `completed` / `failed` / `rejected` / `blocked` | `processed` | outcome travels alongside; a Waypost receipt carries no outcome payload |
| `timed_out`, `late` | *(nothing)* | unknown means reconcile first, never auto-process |

A Waypost `processed` receipt therefore means "this consumer durably
recorded its outcome", exactly as in Waypost's own skill contract — it
is not proof the remote task succeeded. Evidence still has to be
checked where success matters.

## Identity and trust: the hard rules

1. **Sender identity is the receiver-recorded `received.peer`**
   (the Tailscale-verified identity), never the envelope's `from` or
   `from_agent` alone. A bridge that mints Waypost identities from
   self-asserted agent names enables spoofing; Yobiru's own privacy
   notice says agent names are routing, not isolation.
2. **The bridge sees plaintext.** Run it only on a machine the operator
   already trusts with that content — in practice the operator's own
   machine or a self-hosted Waypost next to it. Waypost privacy
   filtering, when configured, applies on the bridged path, and the
   bridged trail keeps Waypost's audit.
3. Received content stays a request, never an approval, on both sides.
   The bridge never executes message text, and neither system's wake or
   credential rules change.

## Reference bridge: `tools/waypost_bridge.py`

A ~200-line, stdlib-only starting point (Python 3.8+), with unit tests
in `tests/test_waypost_bridge.py`:

- polls local `inbox/*.json` records (the documented
  `{"envelope", "received"}` shape) and plans one Waypost send each,
  resolving the sender through `received.peer`;
- polls the bridge's own Waypost inbox over HTTP and plans one
  `yobiru send` each;
- `--dry-run` plans without sending anything anywhere;
- refuses illegal agent names before minting anything, refuses
  wide-open token files, keeps a seen-ids ledger.

Explicitly **not** in the skeleton: attachment forwarding (needs
`fetch` plus the Waypost blob prepare/PUT/commit round trip), retry and
backoff policy, supervision, per-space routing, and writing Waypost
receipts back into Yobiru request states. Each is marked `TODO` at the
exact spot. Run it with `--dry-run` first; treat any live run as an
experiment until those are filled in.

## Out of scope, on purpose

- No shared scheduler, no group-room UI, no exactly-once execution —
  both systems already refuse these, and the bridge doesn't add them.
- No Yobiru wake duplication: waking stays entirely Yobiru's job;
  Waypost has no wake to coordinate with.
- No protocol change on either side. If the receipt mapping ever needs
  wire support, it belongs in a short interop appendix to each SPEC,
  not in altered message kinds.

## What would help from the Yobiru side

Almost nothing, which is the point: stable `--json` output (already
true), receiver-recorded sender identity (already in `received.peer`),
and the documented inbox record shape (already in SPEC §5). If those
stay stable, the bridge needs no privileged interface.
