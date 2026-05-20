# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Approach
- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

## Project Overview

**skillup** is a multi-application desktop platform for SKILL code development tools. It provides a unified framework for running multiple applications with a shared UI theme and plugin architecture.

### Key Features

- **Desktop Platform**: Plugin-based architecture for multiple applications
- **Unified Theme System**: Single CSS file controls all apps
- **Multi-App Support**: Apps discovered via `app/*/app.ini` configuration
- **Dual-Mode Operation**: Works as desktop app (Qt WebEngine) or in web browser
- **QWebChannel Integration**: Fast JavaScript ↔ Python communication
- **Multi-language Support**: English and Korean (한글) interface

## Requirements

- Python 3.7+
- PySide2 (Python 3.7-3.10) or PySide6 (Python 3.9+) for Desktop UI

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

**Priority (highest → lowest):** User config file → `SKILLUP_DEFAULT_CONFIG` env var → `skillup_default_config.ini` (auto-detected in parent dir of `skillup/`) → hardcoded defaults.

User configs are stored under `$SKILLUP_CONFIG_HOME/` (defaults to `~/.config/skillup/`). In BaseApp subclasses, always use `self.load_config()` — never call `lib.config.load_config()` directly, or `SKILLUP_DEFAULT_CONFIG` will be silently ignored.

## Built-in Applications

### skillverifier
SKILL code static analyzer - see [app/skillverifier/CLAUDE.md](app/skillverifier/CLAUDE.md) for details.

### sample
Sample application demonstrating the app framework - see [app/sample/CLAUDE.md](app/sample/CLAUDE.md) for details.

## Development Guide

### BaseApp Framework

All apps inherit from `BaseApp` ([lib/baseapp.py](lib/baseapp.py)). Implement `on_run_cli()` for CLI mode and `on_run_desktop_initialize()` for desktop mode. Use `register_handlers()` for JS↔Python communication and `self.state` for thread-safe state management.

For full API reference, see [docs/APP.md](docs/APP.md).

### Creating a New App

Create `app/myapp/` with `app.ini`, a main script (`App` class inheriting `BaseApp`), and `web/` HTML files. The app is automatically discovered on next launch.

For step-by-step guide and examples, see [docs/APP.md](docs/APP.md).

### State Management

`BaseAppState` provides thread-safe state with auto UI notification via `callJS`. Use `self.state.get/set/update()` in background threads. Simple request-response handlers can skip state entirely.

For full API and usage patterns, see [docs/APP.md](docs/APP.md).

### Using Shared Resources

All apps can use shared resources from `desktop/common/`:
```html
<!-- In your app's HTML -->
<link rel="stylesheet" href="/common/style/default.css">
<script src="/common/bootstrap/js/bootstrap.bundle.min.js"></script>
<script src="/common/script/callpython.js"></script>
```

**Note:** The `/common/` URL path maps to the `desktop/common/` directory on disk.

### Theme Development

All apps share the theme in `desktop/common/style/default.css`:
- Modify this file to change the look of all apps
- Uses CSS variables for consistent styling
- Bootstrap-based responsive design

## Architecture Notes

### Key Components

- **[desktop/desktop.py](desktop/desktop.py)**: Desktop manager and app loader
- **[lib/webui.py](lib/webui.py)**: WebUI engine (Qt/HTTP server)
- **[lib/appmgr.py](lib/appmgr.py)**: App loading and CLI routing
- **[desktop/web/](desktop/web/)**: Desktop UI (HTML/CSS/JS)
- **[desktop/common/](desktop/common/)**: Shared resources (Bootstrap, fonts, themes)
- **[app/*/](app/)**: Individual applications

### Desktop Communication Flow

```
JavaScript (Browser)
    ↕ (QWebChannel or REST API)
callpython_handler.handle_action()
    ↕ (shared state object)
App background thread
```

### Subprocess Logging Convention

Apps running as subprocesses communicate via:
- **stdout**: JSON-RPC protocol (structured data)
- **stderr**: Logging and diagnostics

**Log Level Prefixes:**
When printing to stderr, use these prefixes to indicate log level:
- `[error]` - Error messages (exceptions, fatal errors)
- `[warn ]` - Warning messages (interruptions, non-fatal issues)
- No prefix - Info messages (normal progress, status updates)

The desktop process ([desktop/desktop.py](desktop/desktop.py)) automatically parses these prefixes and routes messages to the appropriate log level. The prefix is stripped from the final log output.

**Implementation:**
- Subprocess: Add `[error]` or `[warn ]` prefix to stderr messages
- Desktop: Parses prefixes and calls `log()` with appropriate level

## Mandatory Rules

Each rule below is a brief summary. See [docs/RULE.md](docs/RULE.md) for full details on every item.

### Do Not Use localStorage
Never use `localStorage` / `sessionStorage` / `indexedDB` — causes a 5-second hang in Qt WebEngine. Always use `callPython` → `load_config()` / `save_config()` instead.

### PySide2 Compatibility - CentOS 7 Tooltip Crash
Never add HTML `title` attributes — crashes CentOS 7 PySide2 due to FreeType mismatch. Use CSS-based tooltips or aria-labels instead.

### Dialog Implementation
Modal dialogs in iframe apps must use `parent.desktopModal.open()`. Register Tab trap handlers via `desktopBus` in `app/{appname}/web/desktop_handlers.js`.

### No Native JS Dialogs
Never use `confirm()`, `alert()`, or `prompt()` — they crash Qt WebEngine on RHEL 7 / CentOS 7. Use `parent.showConfirmDialog()` / `parent.showInputDialog()` instead.

### Git Commit Policy
Never commit automatically. Always show `git diff` first and commit only after explicit user approval.

### CSS Compatibility - PySide2 and PySide6

Never use `gap` / `grid-gap` / `row-gap` / `column-gap` — PySide2 does not support them; use `margin` instead.
Always test in PySide2: if it works there, it works in PySide6.

### SQLite Journal Mode

Always use `PRAGMA journal_mode=DELETE` for all SQLite connections. Never use WAL mode — NFS is the primary storage target and WAL requires `.wal`/`.shm` files that are unreliable on NFS.

### Advisor Guidance

Advisor involvement needed: provide concise 150-character instruction.
