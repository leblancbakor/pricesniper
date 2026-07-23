# 0004: Alert via Discord's REST API, not a gateway bot

- **Status:** accepted
- **Date:** 2026-07-23

## Context
v0.3 needs to post deals to Discord. The usual way to "make a Discord bot" is a
framework like discord.py that opens a persistent gateway (WebSocket) connection
and listens for events. But PriceSniper is a batch job: it wakes up, scans a
feed, sends any new deals, and exits. It never needs to receive messages or
react to events.

## Decision
Post each deal by calling Discord's REST endpoint
`POST /channels/{id}/messages` directly, authenticated with the bot token, using
the `httpx` client we already depend on. No gateway connection, no discord.py.
The alerter sits behind an `Alerter` interface with a `ConsoleAlerter` default,
so Discord is one backend among potentially several (Telegram later).

## Consequences
**Easier**
- No new dependency; `httpx` is already in the project.
- No long-lived connection to manage in what is fundamentally a run-and-exit
  tool. Simpler to reason about and to schedule (cron, Task Scheduler).
- The embed builder is a pure function, so it is unit-testable without a network.

**Harder / accepted trade-offs**
- No inbound interactivity: the bot cannot respond to commands or reactions. Not
  needed now; if it ever is, a gateway client can be added as a separate concern.
- We handle Discord's rate-limit (HTTP 429) ourselves, though minimally.

## Alternatives considered
- **discord.py (gateway bot).** The right tool if we needed slash commands or
  event handling, but heavyweight for one-way posting from a batch job.
- **A channel webhook URL.** Even simpler than a bot, but the person already set
  up a bot and token, and a bot token keeps the door open for richer bot
  features later without re-plumbing.
