# Codex mobile presentation

Scoped presentation over the existing Codex chat, session, upload, recording, TTS, model and settings handlers. The sunset home, SSH and separately served Claude app are not replaced. The ChatGPT title describes the requested visual treatment; the actual model is shown immediately below it and remains Codex.

Features: history drawer with local title search, new/open/delete chats, text export, response copy/read/share, model selector, grouped settings, device-local light/dark/system appearance and accent, and voice entry using the existing recorder. No ChatGPT account subscription, memory, projects, or Advanced Voice service is simulated. Voice is recorded-message exchange, not a realtime ChatGPT call.

Official visual references inspected 2026-10-29:
- https://help.openai.com/en/articles/8142208-chatgpt-ios-and-android-app-faq
- https://help.openai.com/en/articles/11958281-updating-your-visual-experience-on-chatgpt
- https://chatgpt.com/download/
- https://apps.apple.com/us/app/chatgpt/id6448311069
- https://play.google.com/store/apps/details?id=com.openai.chatgpt

Run `python3 claudex/check-codex-mobile.py` with Playwright and Chromium available. All requests are intercepted; no real CLI commands, messages, account changes or SSH connections are made. Set `CLODEX_STATIC` to test a staged copy of the latest production frontend. Screenshots go to a temporary directory.

Deployment: add codex-mobile.css and codex-mobile.js, then insert their two tags in the CURRENT production index (after existing styles and scripts). Do not overwrite the index from an older checkout: production has newer independent Claude routing. The only production existing-file change is these two added tags; existing cache versions and Claude files are preserved. Roll back by restoring the saved production index; the added unreferenced assets can remain.
