# Architecture

## Scope and boundaries

SGRand reads a user-supplied SoulGold checkout and produces deterministic text
edits. SoulGold is an external input, never a vendored dependency. `.work/` is
ignored, tests create only synthetic fixtures, and the package contains no game
data or assets.

The supported compatibility contract is the exact Git tag `v.1.1.4`. A real
Git checkout at any other commit is rejected. A directory without Git metadata
is accepted only after the required layout is validated; this permits isolated
synthetic fixtures and exported source trees.

## Modules

| Module | Responsibility |
| --- | --- |
| `sgrand.cli` | `preview` and `apply` commands; user-facing errors and summaries. |
| `sgrand.engine` | Loads metadata, composes passes, builds the manifest and owns the apply boundary. |
| `sgrand.source` | Layout/tag validation and parsers for species and item metadata. |
| `sgrand.species` | Safe species filtering, evolution graphs, family matching and starters. |
| `sgrand.transforms` | Pure text/JSON transformations for starters, wild data, scripts and items. |
| `sgrand.rng` | Stable seed parsing and named independent PRNG streams. |
| `sgrand.transaction` | Preflight, staging, atomic per-file replacement and rollback. |
| `sgrand.interfaces` | Protocols for future move, ability, innate and trainer passes. |

The dependency direction is CLI → engine → parsers/transforms → immutable
models. Parsers and transforms do not write. This makes preview the natural
result of planning rather than a special dry-run code path.

## Planning and apply

`Randomizer.plan()` performs all parsing, selection, serialization and
validation in memory. It records each changed file with its original bytes,
new bytes and checksums. Errors during this phase cannot modify the checkout.

`Randomizer.run(..., APPLY)` adds the manifest to that plan and delegates the
complete set to `FileTransaction`:

1. Verify every target still equals the bytes observed during planning.
2. Stage every new file and every rollback copy beside its target, flush it and
   call `fsync`.
3. Replace targets one at a time with same-filesystem `os.replace`.
4. If any replacement raises, restore every target already replaced in reverse
   order and remove a newly created manifest.
5. Remove all remaining staging files.

Thus validation, encoding and permission failures occur before commit, while a
caught commit error triggers rollback. No portable filesystem API offers a
single atomic rename across hundreds of files; abrupt power loss or process
termination during the very short commit interval is outside this guarantee.
The manifest contains SHA-256 values so interrupted external recovery can be
audited.

## RNG contract

The user seed is normalized to an integer. Each subsystem derives a separate
128-bit seed using SHA-256 over the root seed and a stable domain name:

- `wild-species`
- `static-gift-species`
- `static-gift-duplicate-resolution`
- `starters`
- `map-items`
- `scripted-items`

Creating, removing or consuming values in one stream cannot shift another
subsystem. Stream names are part of the manifest and should be treated as a
reproducibility API: renaming one is a deliberate output-format change.

## Extension design

`RandomizationPass` requires a named pass to return planned writes and audit
records without mutating its source. `MovesPass`, `AbilitiesPass`,
`InnatesPass` and `TrainersPass` refine that contract as reserved extension
points. Future implementations should receive their own named RNG streams,
validate all referential constraints before returning, and let the engine merge
their writes into the same transaction.

If two passes propose the same path, the future composition layer must merge
their transformations explicitly; a transaction rejects duplicate targets.
This prevents order-dependent silent overwrites.

## Compatibility strategy

The source map in `docs/source-map.md` distinguishes canonical inputs,
generated files and phase-1 coverage. Parsers fail closed when required shapes
or sentinel counts change (for example, anything other than nine starter
slots). Support for a new SoulGold tag requires updating that map, adding a
fixture for each changed format and completing a real-checkout preview and
build before changing `SUPPORTED_TAG`.
