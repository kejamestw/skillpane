# Third-party notices

## oh-my-skills

- Source: https://github.com/AIjunja/oh-my-skills
- Reviewed upstream commit: `6ad9eb7d1106c223277a369d2cdba8649fbfde5d`
- Copyright (c) 2026 oh-my-skills Maintainers
- License: MIT; full unchanged notice in `third_party/oh-my-skills.LICENSE`.

The initial frontmatter parser in `skillpane/catalog.py` was adapted from upstream `skill_ledger/scanner.py`. It has since been replaced by the independent, conservative field reader in `skillpane/metadata.py`; the upstream notice remains preserved. Local skill inventory concepts informed this implementation. Upstream's GUI server, create/edit/archive manager and frontend are not used by Skillpane.

The upstream project is not responsible for this derivative's functionality or maintenance. No affiliation with or endorsement by Apple, OpenAI or Anthropic is implied. Skillpane includes no Apple proprietary fonts, symbols or artwork; it uses the operating system font stack and original SVG icons.

### Scanner boundary review (0.3.2)

[Upstream PR #1](https://github.com/AIjunja/oh-my-skills/pull/1), reviewed at head `a478ed8e089a79c6594744f83f8eaa78fab09c83` (yulmi0630), identified inflated inventory from vendored nested skills and proposed stopping at skill folders. Skillpane independently reproduced the issue and implemented a boundary-aware traversal with pre-entry canonical-path checks, branch cycle detection, preserved aliases and separate synthetic regressions. The PR branch was not installed or executed; the existing upstream MIT notice remains preserved.
