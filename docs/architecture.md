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
| `sgrand.move_config` | Versioned move-profile loading and strict schema/range validation. |
| `sgrand.moves` | Separate property, level-up and TM/tutor compatibility passes. |
| `sgrand.ability_config` | Strict versioned profiles, power bands and immutable protection lists. |
| `sgrand.abilities` | Resolves real species-info storage and plans separate normal/innate assignments. |
| `sgrand.rng` | Stable seed parsing and named independent PRNG streams. |
| `sgrand.transaction` | Preflight, staging, atomic per-file replacement and rollback. |
| `sgrand.interfaces` | Protocols for implemented passes and the future trainer pass. |

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
- `move-properties`
- `move-level-up-learnsets`
- `move-tm-tutor-compatibility`
- `species-abilities`
- `species-innates`

Creating, removing or consuming values in one stream cannot shift another
subsystem. Stream names are part of the manifest and should be treated as a
reproducibility API: renaming one is a deliberate output-format change.

## Extension design

`RandomizationPass` requires a named pass to return planned writes and audit
records without mutating its source. `LevelUpLearnsetsPass`,
`MoveCompatibilityPass` and `MovePropertiesPass` describe the implemented move
boundaries. `AbilitiesPass` and `InnatesPass` are implemented as separate
logical passes. Because both fields live in the same species-info records,
their plans are validated and rendered into one write per family header.
`TrainersPass` remains the reserved extension point.

Ability metadata comes from the authoritative `gAbilitiesInfo` designated
initializers; omitted ratings use C's implicit zero. Effective species arrays
come from the documentation projection and are resolved back to literal,
conditional, aliased and shared-macro storage in `species_info`. Evolution and
shared-storage unions are decided before selection. The innate pass receives
the completed normal assignment only to enforce the invariant that an innate
cannot repeat a main ability; its random draws remain on a separate stream.

Form-change predicate abilities and the mandatory species-locked list are
never candidates. Their owners, all owners of the same source initializer and
parameterized macros that cannot be split safely are preserved as complete
normal/innate pairs. See [ability configuration](abilities-config.md).

Move selection uses the canonical metadata snapshot loaded before any writes.
This keeps the learnset stream independent from property RNG consumption.
Property randomization changes only `.power`, `.accuracy`, `.pp`, `.type` and
the physical/special category of ordinary damaging moves. It never changes
`.effect`, priority, targets, flags, animation, zero-power status moves or
variable/fixed-power moves represented by power 0/1.

If two passes propose the same path, they must merge their transformations
before building the transaction; a transaction rejects duplicate targets.
The abilities subsystem already does this for the normal and innate passes,
producing one final write per species-info file. This prevents order-dependent
silent overwrites.

## Compatibility strategy

The source map in `docs/source-map.md` distinguishes canonical inputs,
generated files and phase-1 coverage. Parsers fail closed when required shapes
or sentinel counts change (for example, anything other than nine starter
slots). Support for a new SoulGold tag requires updating that map, adding a
fixture for each changed format and completing a real-checkout preview and
build before changing `SUPPORTED_TAG`.
