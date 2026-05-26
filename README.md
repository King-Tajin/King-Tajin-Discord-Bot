# Tajin Helper

[Discord Server](https://discord.gg/sU2XRxK8EB) | [Website](https://king-tajin.dev)

Tajin Helper is a Discord bot with public-facing Vagudle commands and private tooling for managing mod platform stats, a website feedback pipeline, and other support features.

---

## Vagudle Challenge

`/vagudle_challenge` lets anyone send a custom [Vagudle](https://vagudle.king-tajin.dev) puzzle to a friend. Just pick a secret word, a difficulty tier, and a guess limit, and the bot generates a shareable link that loads that exact challenge in-game.

* **Word:** 4–7 letters, validated against the chosen dictionary.
* **Dictionary:** Normal (common words), Hard (uncommon words), or Extreme (full Scrabble dictionary).
* **Guesses:** 9 or 11 attempts.
* **Works anywhere:** usable in servers, DMs, and private channels.

The word is encoded into the URL so the recipient can't spoil themselves by reading it.

---

## Vagudle Duel

`/vagudle_duel` challenges another player to a head-to-head Vagudle duel. The bot randomly picks the secret word and both players get separate private links encoding the same word and compete to solve it.

* **Difficulty:** Normal (11 guesses, common words) or Hard (9 guesses, uncommon words).
* **Word length:** 4–7 letters.
* **Works anywhere:** usable in servers, DMs, and private channels. In a 1-on-1 DM the opponent is detected automatically; in a server the first person to click Accept becomes the opponent.
* **Links are private:** each player's link is sent as an ephemeral message only they can see.
* **Winner determination:** fewer guesses wins; ties go to faster completion time; identical time is a draw (both win).
* **Results:** when both players finish, the bot DMs each player the outcome including the word, their guesses, their time, and their opponent's result.
* **Leaderboard:** completed duels are recorded in Cloudflare D1 and reflected on the leaderboard.

Duel links expire after 24 hours. Results do not affect normal game stats.

---

## Vagudle Leaderboard

`/vagudle_leaderboard` displays the duel leaderboard with pagination and toggles for sort mode and difficulty.

* **Columns:** rank, player, matches played, wins, win rate, and unique wins.
* **Sort:** toggle between ranking by unique wins (default) or total wins. Ties are broken by win rate.
* **Difficulty:** toggle between Normal and Hard mode leaderboards.
* **Pages:** 25 players per page with ◀ ▶ navigation.
* **Lookup:** optional `user` argument to look up any player's rank and stats directly.
* **Works anywhere:** usable in servers, DMs, and private channels.

Duel stat summaries are also posted to the stats channel every Monday and Friday at 14:45 UTC when new duels have been played since the last post.

---

## Other Features

**Mod stat tracking** — Polls CurseForge and Modrinth every six hours and posts to a stats channel only when downloads, project count, or followers have changed. CurseForge follower counts are scraped via Playwright since they aren't in the API.

**Feedback pipeline** — Reads entries submitted via king-tajin.dev/feedback from Cloudflare KV, checks every two hours for new submissions, and pings the support role. Slash commands cover viewing, filtering, tagging, and marking entries complete.

**DM handling** — Vagudle keyword mentions get a game info embed. Support-related keywords redirect to support@king-tajin.dev and the feedback form. Other DMs get a content-matched response (text, emoji, or GIF).

---

## Built With

* Python · discord.py · aiohttp · Playwright
* Cloudflare KV · Cloudflare D1 · Cloudflare Tunnel

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