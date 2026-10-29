# Skillpane

A local Agent Skills library with a Traditional Chinese interface. Browse personal skills and tool-managed content, compare responsibilities, and keep recoverable personal notes without editing skill files.

[繁體中文](README.md) · [User guide (Chinese)](docs/USER_GUIDE.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

## Run locally

Use a currently security-supported Python release (3.11 or newer recommended). There are no third-party runtime dependencies or frontend build steps.

```sh
git clone https://github.com/kejamestw/skillpane.git
cd skillpane
python -m skillpane
```

Open `http://127.0.0.1:8766/`. Use `--port` to choose another port. Private repositories require account access; never place a token in a clone URL. On Windows, double-click `Open-Skillpane.cmd`, or run `Start.ps1 -NoBrowser`; use `Stop.ps1` to stop that launcher instance. On macOS/Linux, stop the foreground process with Ctrl+C.

## What it does

- Scans user-level `.agents/skills`, `.codex/skills`, `.claude/skills`, and `.codex/plugins/cache` under the current home directory.
- Deduplicates physical aliases and collapses plugin cache versions. Cached files do not prove that a skill is currently activated.
- Searches names, descriptions, categories, tags, saved notes and personal prompts; offers favorites and organization markers.
- Saves multiple reusable prompts per skill, with multiline editing, copying and backups. Notes remain separate from prompts and panel examples.
- Offers three text sizes and a collapsible sidebar, with browser-local preferences.
- Distinguishes original text, curated translations and user overrides; shows invocation declarations with source evidence.
- Provides stable local identities, previewed imports and restores, and explicit relinking for orphaned notes.
- Compares two skills and their plain-text differences; saves conclusions and flags changed content.
- Keeps source skills read-only. Personal organization data and backups live in the ignored `.data/` directory.

The UI is currently Traditional Chinese only. Project-local skills, usage tracking, skill installation/deletion, automatic merging and remote hosting are not implemented. The app is an early release, not an independent security audit or a guarantee that installed skills are safe.

## Privacy and security

The server binds only to IPv4 loopback and rejects untrusted Host/Origin requests. It does not provide user authentication and is not designed for shared hosts, public networks, reverse proxies or tunnels. Other programs running as your OS user may access it.

Portable backups omit skill bodies and structural local path fields, but include saved notes and other user-entered text. Neither export format anonymizes arbitrary text or guarantees secret removal. Do not upload `.data/`, `.runtime/`, backups or real skill contents. Read [privacy](docs/PRIVACY.md) and [security](SECURITY.md) before sharing material.

Version 0.3 retains data/backup format 2 with an optional personal-prompts field. Data containing prompts requires Skillpane 0.3 or newer. Prompts are stored as text and never executed by the panel.

## Development

```sh
python -B -m unittest discover -s tests -v
node --check web/app.js
node --check web/management.js
node --check web/prompts.js
python scripts/check_publication.py --history --include-untracked
```

Node is only needed for development syntax checks and optional Playwright tests, not to run the app. CI includes Windows/Linux unit, security and copied-bundle CLI lifecycle tests, a redacted Gitleaks history scan, and a separate Linux browser job for Chromium desktop/compact/mobile viewports and Firefox desktop. Each browser test starts a fresh synthetic server; GitHub does not connect to your computer. See [automated testing (Chinese)](docs/TESTING.md) for commands and coverage limits, and [development](docs/DEVELOPMENT.md) for the publication checklist.

The [security testing record (Chinese)](docs/SECURITY_TESTING.md) describes local adversarial checks and their limits. This is internal testing, not an independent penetration test or a guarantee that the software has no vulnerabilities.

## License and attribution

MIT, with preserved upstream attribution. Skillpane began as an independent derivative of [oh-my-skills](https://github.com/AIjunja/oh-my-skills); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSE](LICENSE). It is not affiliated with Apple, OpenAI or Anthropic.
