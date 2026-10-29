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


## Hands-free voice

`codex-live.js/css` intercept the wave control before the old voice sheet. Speech detection ends a turn after 500 ms of silence, posts audio to the existing authenticated STT endpoint, sends the transcript to the current Codex conversation, awaits that task's audio and plays it with a gesture-unlocked AudioContext. Listening restarts after playback. This is turn-based hands-free voice, not OpenAI's native realtime service; model/tool time remains part of latency. The microphone is off during playback; tapping the orb interrupts audio. No backend changes or service restart are needed.

End, page hiding and permission errors release microphone tracks and playback; stale permission/decode results are discarded. An already accepted Codex task continues to completion in chat when a call ends, with its later automatic audio suppressed. Existing drafts/attachments and running jobs must be resolved before opening the call. Max recorded turn is 25 seconds, reply wait limit five minutes, and failures expose Retry rather than silently looping.

Run `python3 claudex/check-codex-live.py` for two automatic media turns, cleanup, denied/late microphone permission and STT error handling. Media and HTTP are mocked; real-device permission/playback still needs confirmation. Backend STT and TTS were separately checked with a benign synthetic Persian sample.


## Typography and session actions

Native platform Latin typography with locally hosted Noto Sans Arabic 400/500/600 fallback (OFL license alongside fonts); larger, consistent labels and readable response text even with automatic voice replies enabled. Chat list rows expose a three-dot menu and a press-and-hold/context-menu action. Deleting opens a named confirmation screen and calls the existing two-step session API only after confirmation. Cancel keeps the session; deleting a different session keeps the current conversation and draft. A running session cannot be deleted from this menu. Codex source session files are retained by the existing backend.

Voice endpoint polling is 250 ms; end-of-speech silence is 500 ms (previously 450 ms / 1000 ms). This removes 350 ms of mandatory silence plus some polling delay; it does not shorten model or TTS processing time.

Visual references re-opened: official ChatGPT download page and https://help.openai.com/en/articles/8809935-deleting-and-archiving-chats-in-chatgpt. Native app pixel parity is not claimed. Google Fonts Noto Sans Arabic is a fallback, not a claim about OpenAI's proprietary typeface.

Speech recording requests 24 kbit/s audio, falling back to the previous recorder options when unsupported. This reduces upload bandwidth on browsers that honor the requested rate; real-device bitrate and latency still need measurement. Silence is now 500 ms (150 ms shorter than the previous 650 ms). Polling remains 250 ms. The voice test also checks the low-bitrate request and unsupported-option fallback.
