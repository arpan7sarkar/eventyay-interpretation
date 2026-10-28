# Repository Context: Eventyay Interpretation

## Stack Overview
- **Framework**: Django (v6.1+)
- **Ecosystem**: Eventyay (Pretix core architecture)
- **Language**: Python 3.12+
- **Background Jobs**: Celery
- **Package Manager**: `uv`

## Plugin Architecture
Eventyay loads plugins dynamically via Python entry points defined in `pyproject.toml`:
```toml
[project.entry-points."pretix.plugin"]
interpretation = "interpretation"
```
The plugin hooks into the main application via `signals.py`, intercepting events like navigation rendering or video room initialization.

## Inter-Service Communication (VoxBento)
- **OAuth 2.0 (PKCE)**: The organizer dashboard securely connects to VoxBento.
- **REST API**: We call VoxBento to subscribe to webhooks or fetch metadata.
- **Webhooks**: We receive real-time updates from VoxBento (e.g. interpreter joined, channel active).

## The Big Picture & The 4 Phases of Integration

**Eventyay** handles ticketing, scheduling, and hosting video rooms. 
**VoxBento** handles live audio interpretation, real-time AI transcription, and low-latency audio broadcasting.
This plugin is the "glue" that allows an Eventyay organizer to add live translation to their event, and have Eventyay seamlessly orchestrate VoxBento in the background.

### Phase 1: The Handshake (OAuth 2.0)
Before Eventyay can do anything with VoxBento, the two servers need to trust each other.
* In the Eventyay organizer dashboard, the organizer clicks "Connect to VoxBento" on the "Configure Interpreters" tab. 
* This initiates an OAuth 2.0 PKCE flow. 
* Eventyay redirects the user to VoxBento to log in. VoxBento issues a secure grant, and Eventyay stores a highly secure, encrypted `webhook_secret_key` in the `VoxbentoOAuthGrant` database table.

OAuth attempts store the Eventyay event primary key alongside state and the PKCE
verifier in the server-side session. The callback consumes and validates that
attempt before resolving the event and rechecking organizer permission. Token
exchange sends the resolved event slug as `event` so VoxBento rejects codes issued
for another event before granting ownership. In-flight attempts created before
this event-ID binding was deployed must restart using Connect to VoxBento.

### Phase 2: The Nervous System (Webhooks & Celery)
Eventyay needs to know what is happening inside VoxBento (e.g., *Did an interpreter just go live? Are captions available?*). 
* Eventyay uses a background Celery task to call VoxBento and subscribe to webhooks.
* Whenever an interpreter takes action, VoxBento fires a webhook back to Eventyay. 
* The `views_webhooks.py` intercepts the webhook, cryptographically verifies the `X-VoxBento-Signature` using `hmac.compare_digest` to ensure it isn't spoofed, and updates Eventyay's database.

### Phase 3: Room Configuration
The organizer edits a specific Video Room (like the "Main Stage") from their Eventyay schedule.
* A new "Interpretation" dropdown appears in the room settings.
* The organizer selects VoxBento. This creates a `RoomInterpretation` database record linking that specific Eventyay room to a specific VoxBento booth.

### Phase 4: The Attendee Experience (Frontend Integration)
* When an attendee joins the video room in Eventyay, the backend reads the plugin data and passes the VoxBento connection URLs (WHEP audio URLs and WebSocket caption URLs) to the frontend.
* The Eventyay Vue.js frontend injects a custom `<AudioTranslationDropdown>` component below the native video player.
* When the attendee selects a language, the UI automatically mutes the native video's audio, connects to VoxBento's WebRTC stream to play the interpreter's audio in perfect sync, and overlays the live captions on top of the video.
