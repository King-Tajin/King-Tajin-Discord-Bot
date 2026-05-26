# Privacy Policy for Tajin Helper

**Last Updated:** May 25, 2026

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

### Temporary Logs
To maintain performance, debug errors, and ensure security, the Bot utilizes temporary logging:
* **Public/Server Channels:** The Bot temporarily caches or logs standard message metadata (such as text, message IDs, and author IDs) to process commands in real time.
* **Direct Messages (DMs):** All interactions, messages, and commands sent directly to Tajin Helper via DM are temporarily logged to assist with automated responses and developer debugging.
* **Retention:** These logs are transient and are automatically cleared or rotated out systematically. They are not used to build long-term user profiles.

---

## 2. Infrastructure & Data Security

* **Network Infrastructure:** The Bot's web traffic and external API connections are securely routed through **Cloudflare** to protect against malicious attacks and maintain uptime.
* **Duel & Leaderboard Data:** Persistent duel results and leaderboard entries are stored in a **Cloudflare D1** database, secured and managed through Cloudflare's infrastructure.
* **Log Storage:** All temporary operational logs are stored securely on a dedicated, private server managed directly by the developer.
* **Data Sharing:** We **never** sell, trade, or share any user data or message content with third-party advertisers or external entities.

---

## 3. Data Deletion & User Rights

You have the right to request deletion of your data at any time.

* **Temporary Logs:** If you want your temporary message logs or interaction data purged immediately, please email us at **developer@king-tajin.dev**.
* **Duel & Leaderboard Data:** If you want your duel results and leaderboard entries permanently deleted from our D1 database, please email us at **developer@king-tajin.dev** with your Discord User ID. This will remove all records associated with your account including match history and leaderboard standings.
* **Processing:** All deletion requests are processed promptly.

---

## 4. Contact and Support

If you have questions about this policy, please reach out via:
* **Email:** developer@king-tajin.dev or support@king-tajin.dev
* **Official Website:** [king-tajin.dev](https://king-tajin.dev)
* **Feedback:** [Feedback Form](https://king-tajin.dev/feedback)