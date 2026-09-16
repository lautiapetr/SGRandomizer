# SGRand

SGRand is a deterministic, source-level randomizer for Pokémon SoulGold
`v.1.1.4`. This repository contains only the randomizer, its documentation and
synthetic test fixtures. It does not contain or redistribute SoulGold source,
graphics, ROMs, build products or other game assets.

Phase 1 randomizes the main wild-encounter table, the nine starter choices,
scripted static/gift Pokémon, item balls, hidden items and scripted item gifts.
Legendary, Mythical, Ultra Beast and Paradox species remain unchanged. Moves,
abilities, innate abilities and trainer parties have extension interfaces but
are intentionally unchanged.

## Requirements and installation

- Python 3.11 or newer.
- A clean local checkout of SoulGold at the exact tag `v.1.1.4`.
- SoulGold's own toolchain only when building the game.

Install the package and development tools in a virtual environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

## CLI

Preview is read-only and does not create a manifest:

```bash
sgrand preview --source /path/to/soulgold --seed 12345
```

Apply commits every source edit and the manifest as one rollback-capable
transaction:

```bash
sgrand apply --source /path/to/soulgold --seed 12345
```

The default manifest is
`/path/to/soulgold/soulgold-randomizer-manifest.json`. The tool refuses to
replace it unless `--force` is supplied. Restore the SoulGold checkout before
applying a different seed; `--force` replaces only the manifest and is not a
checkout reset.

The module form is equivalent and does not depend on the shell platform:

```bash
python -m sgrand preview --source /path/to/soulgold --seed example
```

## Development and verification

```bash
python -m pytest
ruff check .
ruff format --check .
mypy src/sgrand
```

Run the opt-in read-only integration test against the reference checkout:

```bash
SOULGOLD_SOURCE=.work/soulgold-v1.1.4 python -m pytest -m integration
```

For an end-to-end build, use a disposable checkout so the reference remains
clean:

```bash
git clone --shared .work/soulgold-v1.1.4 /tmp/sgrand-build
sgrand apply --source /tmp/sgrand-build --seed phase-1-build
make -C /tmp/sgrand-build -j2
```

Never commit the checkout, generated manifest, ROM, ELF, map file or build
directory. See [the architecture](docs/architecture.md) and the audited
[SoulGold source map](docs/source-map.md).
