# Yobiru plugin privacy policy

Effective date: October 15, 2026

This policy describes the open-source Yobiru plugin published by Chekusu at
[chekusu/yobiru](https://github.com/chekusu/yobiru). It covers the plugin and its
bundled command-line receiver, not the separate privacy practices of a plugin
marketplace, an AI provider, Tailscale, GitHub, or the Yobiru website.

## What the plugin does with data

Yobiru connects agents on computers that you choose over your Tailscale network.
It has no Chekusu-operated messaging account, message relay, or central file store.
The plugin does not send usage analytics or message contents to Chekusu.

Data is processed on the participating computers to deliver messages, transfer
files, discover peers, wake configured agents, track requests, and diagnose errors:

| Data | Where and why it is processed |
| --- | --- |
| Message text, structured data, sender/recipient identities, timestamps, message IDs and reply relationships | Stored by the participating receivers and sent to the addressed peer. |
| Request text, receipts, progress, final results, deadlines and retry state | Stored in local request ledgers and response queues so delivery and outcomes can be reconciled. |
| Attachments, filenames, sizes, hashes and download grants | Copied to the sender's local outbox; downloaded to the recipient's computer when requested. |
| Tailscale device names and addresses, configured agent names, versions and session metadata | Read or cached locally and disclosed to allowed peers through discovery, routing and status responses. Session metadata can include a configured session ID and display or native name. |
| Receiver policy, agent settings, wake adapters and configuration | Stored locally. A configured adapter may read a webhook URL or credential from an environment variable or local file. |
| Operational logs | Stored by the process or service manager; may include peer addresses, request paths, message IDs, timestamps, status codes and error details. |

The default data directory is `~/.tailmsg`; a user can choose another directory.
Codex integration can also store bridge state and queue information locally.
These files are not uploaded to Chekusu by the plugin.

## Who can receive data

Messages and attachments go to the peers you address. Tailscale provides the
network identity and encrypted network transport; its own infrastructure and
privacy terms apply, including when it relays encrypted traffic. Yobiru's receiver
policy and your Tailscale rules determine which peers may contact the receiver.

If you enable an agent bridge or wake webhook, incoming content and associated
metadata can be passed to that configured agent or endpoint. The AI application
may send it to its model provider under that application's settings and policies.
Installing Yobiru does not change the provider's retention or training settings.
Only configure destinations you intend to receive this information.

Installation and update checks contact the selected plugin host and/or GitHub to
retrieve public package or release information. Those services receive ordinary
network request information. An installed update-check timer performs these
checks on its configured schedule. Yobiru does not include inbox contents or
attachments in its GitHub release checks.

## Retention and deletion

Inbox messages, downloaded attachments, request ledgers, configuration and service
logs remain on the participating computers until their owners remove them or
apply their own retention policy. Acknowledging a message does not erase it.
Deleting only an inbox file may not erase a tracked request: the request ledger
also stores its content and can restore an inbox record.

Attachment download grants expire after 24 hours by default; the sender can
choose another lifetime. The receiver refuses an expired grant. The running
sender service periodically cleans its outbox after the expiry grace period.
This does not delete a recipient's downloaded copy, backups, or copies already
passed to an agent provider.

To stop future processing, disable the receiver, bridge and any update timer,
and uninstall the plugin if desired. To remove local history, first stop the
services using that data directory, then remove the relevant inbox, outbox,
ledger, bridge state and logs. Review any backup you intend to retain. Coordinate
separately with recipients and service providers for their copies. Uninstalling
the plugin alone does not promise deletion of persistent data or services.

## Your choices and questions

You choose the computers, recipients, files, receiver policy and wake adapters.
Network access does not by itself authorize an agent to perform a requested
task. Avoid sending secrets or unrelated private information in messages.

For a question about this policy or the plugin's data handling, open a
[GitHub issue](https://github.com/chekusu/yobiru/issues). Issues are public: do not
post private messages, credentials, webhook URLs, device addresses or logs that
contain them. Ask the maintainer for a private channel before sharing sensitive
details. Chekusu cannot retrieve or delete message history that exists only on
your or your recipients' computers.

Updates to this policy are published in this file with a revised effective date.
The repository history records earlier versions.
