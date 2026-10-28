"""Independent synthetic catalog for repeatable browser regressions.

Never loads the real home directory or annotation store. Each run keeps its
fixtures under .runtime/ so failures can be inspected without deleting files.
"""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillpane.catalog import Catalog
from skillpane.server import AppServer


class FixtureCatalog(Catalog):
    def snapshot(self):
        return {**super().snapshot(), 'test_fixture': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8779)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1] / '.runtime' / ('browser-fixture-' + uuid4().hex)
    home = base / 'home'

    def write(relative, name, description, extra=''):
        target = home / relative / 'SKILL.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'---\nname: {name}\ndescription: {description}\n{extra}---\n# Synthetic fixture\n'
                          + ('Long fixture content <script>not executable</script>\n' * 180), encoding='utf-8')

    for number in range(150):
        name = f'fixture-{number:03}'
        write(f'.agents/skills/{name}', name, f'Synthetic API helper number {number:03}')
    description = "This skill encodes Emil Kowalski's philosophy on UI polish, component design, animation decisions, and the invisible details that make software feel great."
    write('.agents/skills/emil-design-eng', 'emil-design-eng', description)
    write('.agents/skills/design-helper', 'design-helper', 'A synthetic motion helper')
    write('.agents/skills/manual-only', 'manual-only', 'Synthetic manual API helper', 'disable-model-invocation: true # manual\n')
    write('.codex/plugins/cache/market/plugin/1/skills/fixture-000', 'fixture-000', 'Synthetic plugin API')
    write('.codex/plugins/cache/market/plugin/2/skills/fixture-000', 'fixture-000', 'Synthetic plugin API')
    server = AppServer(port=args.port, home=home, state_dir=base / 'state')
    server.catalog = FixtureCatalog(home)
    server.library.catalog = server.catalog
    server.library.reconcile()
    print(f'Independent synthetic fixture: {server.origin}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
