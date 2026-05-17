# Tajin Helper

[Discord Server](https://discord.gg/sU2XRxK8EB) | [Website](https://king-tajin.dev)

Tajin Helper is a Discord bot with a public-facing Vagudle challenge command and private tooling for managing mod platform stats, a website feedback pipeline, and other support features.

---

## Vagudle Challenge

`/vagudle_challenge` lets anyone send a custom [Vagudle](https://vagudle.king-tajin.dev) puzzle to a friend — pick a secret word, a difficulty tier, and a guess limit, and the bot generates a shareable link that loads that exact challenge in-game.

* **Word:** 4–7 letters, validated against the chosen dictionary
* **Dictionary:** Normal (common words), Hard (uncommon words), or Extreme (full Scrabble dictionary)
* **Guesses:** 9 or 11 attempts
* **Works anywhere:** usable in servers, DMs, and private channels — no need to add the bot to a server

The word is encoded into the URL so the recipient can't spoil themselves by reading it.

---

## Other Features

**Mod stat tracking** — Polls CurseForge and Modrinth every six hours and posts to a stats channel only when downloads, project count, or followers have changed. CurseForge follower counts are scraped via Playwright since they aren't in the API.

**Feedback pipeline** — Reads entries submitted via king-tajin.dev/feedback from Cloudflare KV, checks every two hours for new submissions, and pings the support role. Slash commands cover viewing, filtering, tagging, and marking entries complete.

**DM handling** — Vagudle keyword mentions get a game info embed. Support-related keywords redirect to support@king-tajin.dev and the feedback form. Other DMs get a content-matched response (text, emoji, or GIF).

---

## Built With

* Python · discord.py · aiohttp · Playwright
* Cloudflare KV · Cloudflare Workers + D1
* Debian

---
## Legal and Compliance

To ensure complete transparency with users and align with Discord's Developer Policy, please review the official policy documents:

* [Privacy Policy](privacy.md) – Information regarding data logging, DM interactions, and data security.
* [Terms of Service](terms.md) – Rules regarding command usage, anti-spam guidelines, and the bot-ban policy.

---

## Contact and Support

For inquiries, bug reporting, or feature requests:
* **Feedback Form:** [Submit Feedback](https://king-tajin.dev/feedback)
* **Discord Server:** Join via invite code sU2XRxK8EB
* **Email:** developer@king-tajin.dev or support@king-tajin.dev