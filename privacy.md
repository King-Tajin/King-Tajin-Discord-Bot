# Privacy Policy for Tajin Helper

**Last Updated:** August 9, 2026

Thank you for using **Tajin Helper**. We take your privacy seriously. This Privacy Policy explains what information is collected, how it is processed, and your rights regarding that data.

By adding or interacting with Tajin Helper, you agree to the practices described in this policy.

---

## 1. Data We Collect & How We Use It

### Persistent Data Storage
* **Core Identifiers:** The Bot may read basic Discord identifiers (such as User IDs, Role IDs, or Server IDs) to process commands and manage access permissions.
* **Vagudle Challenges:** When you use `/vagudle_challenge`, the challenge configuration is encoded directly into the generated URL. No challenge data is stored by the Bot.
* **Vagudle Duels:** When you use `/vagudle_duel`, the following data is persistently stored in a Cloudflare D1 database:
  * Your Discord User ID
  * The duel identifier, word, word length, dictionary type, and guess limit
  * Your game result (win/loss, guesses used, completion time) once you finish playing
  * Leaderboard data derived from completed duels (matches played, matches won, and the Discord User IDs of opponents you have won and lost against)
  
  This data is retained indefinitely to power the duel leaderboard. It is not linked to your username, server membership, or any other personal information beyond your Discord User ID.
* **Vagudle Daily:** When a server admin runs `/vagudle_daily_channel`, the destination channel ID is stored persistently until it's changed. To render and update the live daily progress message, the Bot also keeps a short-lived cache of that day's guesses and results (including Discord User IDs), which is automatically deleted after 2 days, and a rolling record of daily attempts used for reminders and streak calculation, which is automatically deleted after 7 days. Group win streaks are retained indefinitely and reflect the group as a whole rather than any individual, so they are not removed as part of an individual's deletion request.

  Vagudle Daily accounts, usernames, and the public Daily leaderboard (wins, losses, and streaks) are created and managed by Vagudle itself, not by this Bot. That includes how usernames are generated from your Discord display name, how to opt out of appearing on the public leaderboard, and how to request deletion of that data — see [Vagudle's Privacy Policy](https://vagudle.king-tajin.dev/privacy) for details.

### Temporary Logs
To maintain performance, debug errors, and ensure security, the Bot utilizes temporary logging:
* **Public/Server Channels:** The Bot temporarily caches or logs standard message metadata (such as text, message IDs, and author IDs) to process commands in real time.
* **Direct Messages (DMs):** All interactions, messages, and commands sent directly to Tajin Helper via DM are temporarily logged to assist with automated responses and developer debugging.
* **Retention:** These logs are transient and are automatically cleared or rotated out systematically. They are not used to build long-term user profiles.

---

## 2. Infrastructure & Data Security

* **Network Infrastructure:** The Bot's web traffic and external API connections are securely routed through **Cloudflare** to protect against malicious attacks and maintain uptime.
* **Duel & Daily Data:** Persistent duel results, duel leaderboard entries, daily channel settings, daily attempt records, and group streaks are stored in a **Cloudflare D1** database and **Cloudflare KV**, secured and managed through Cloudflare's infrastructure.
* **Log Storage:** All temporary operational logs are stored securely on a dedicated, private server managed directly by the developer.
* **Data Sharing:** We **never** sell, trade, or share any user data or message content with third-party advertisers or external entities.

---

## 3. Data Deletion & User Rights

You have the right to request deletion of your data at any time.

* **Temporary Logs:** If you want your temporary message logs or interaction data purged immediately, please email us at **developer@king-tajin.dev**.
* **Duel & Leaderboard Data:** If you want your duel results and leaderboard entries permanently deleted from our D1 database, please email us at **developer@king-tajin.dev** with your Discord User ID. This will remove all records associated with your account including match history and leaderboard standings.
* **Vagudle Daily Channel Setting:** A server admin can change or clear the configured daily channel by re-running `/vagudle_daily_channel`, or by emailing us with the server ID.
* **Vagudle Daily Account & Leaderboard Data:** Your Daily leaderboard entry, username, and account data are managed by Vagudle, not this Bot — see [Vagudle's Privacy Policy](https://vagudle.king-tajin.dev/privacy) for how to request deletion. Group win streaks are not tied to any single person and are not deleted as part of an individual request.
* **Processing:** All deletion requests are processed promptly.

---

## 4. Contact and Support

If you have questions about this policy, please reach out via:
* **Email:** developer@king-tajin.dev or support@king-tajin.dev
* **Official Website:** [king-tajin.dev](https://king-tajin.dev)
* **Feedback:** [Feedback Form](https://king-tajin.dev/feedback)