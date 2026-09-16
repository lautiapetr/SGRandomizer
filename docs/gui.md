# Desktop GUI

The PySide6 application is a cross-platform front end over the same tested
`Randomizer.plan()` and transactional `Randomizer.run(..., APPLY)` APIs used by
the CLI. Start it from a development checkout with:

```bash
python -m sgrand.gui
# or, after installation
sgrand-gui
```

## Workflow

1. Select an existing clean SoulGold `v.1.1.4` checkout, or choose **Descargar
   proyecto**. Downloading performs a shallow, single-tag clone from
   `https://github.com/Eemeliri/soulgold.git` into the chosen empty directory;
   it never copies that checkout into the SGRand repository or executable.
2. Select an output directory. The named ROM copy and technical report are
   written there, never into this repository. SoulGold's own `make` still
   creates its normal `Soulgold.gba` build product inside the selected checkout.
3. Select a preset and enter a text or numeric seed. **Random** creates a
   cryptographically generated 128-bit hexadecimal seed.
4. Adjust the guided controls in Moves, Abilities/Innates and Trainers. Every
   engine option is represented by a labelled native control; percentages show
   their unit and controls which do not apply to the selected mode are disabled.
   Any edit changes the preset label to `Custom`.
5. Run **Ver cambios**. It validates and plans all edits in memory without writing.
6. Run **Randomize**. The existing transaction preflights, stages and commits
   all source changes and its manifest, rolling back committed files if a
   replacement fails.
7. Run **Compilar juego**. Build output streams into the **Actividad** tab, the progress bar
   advances through generation, compilation and linking, and **Cancel** stops
   the build process tree. A cancelled build can leave ordinary generated
   objects in the selected SoulGold checkout; it cannot leave a half-applied
   randomization transaction.

Preview, randomization, diagnostics, download and compilation run in background
workers. Their logs and results are transferred through a thread-safe event
queue and are rendered only by the main Qt thread, keeping the interface
responsive even during large reports and full build logs.

If the application closes after a successful randomization, restart it with the
same checkout, output directory and seed and choose **Compilar juego**. The GUI validates
and recovers the technical report (or the applied manifest as a fallback), so a
completed transaction does not need to be repeated. A mismatched seed or an
invalid/non-applied report is rejected.

The named output is `SGRand-<preset>-<seed>.gba`; the technical report is
`SGRand-<preset>-<seed>-report.json`. Unsafe filename characters are replaced.
Existing named ROM outputs are not overwritten.

## Tutorial and configuration editors

Choose **Abrir tutorial**, **Ayuda → Tutorial de uso**, or press **F1** at any time.
The six-step walkthrough explains the source-checkout model, clean-checkout
requirement, presets, deterministic seeds, spoiler-free mode, preview,
transactional apply, diagnostics and compilation. It never changes settings or
starts an operation.

Every configurable label, field, checkbox, list, action button and tab has
contextual help: leave the mouse pointer over it to see what it changes and how
lower, higher or disabled values affect a playthrough. The same descriptions
are exposed to keyboard status tips and accessibility tools. Terms such as STAB
and BST are expanded in the interface, while source constants (`MOVE_`,
`ABILITY_`, `SPECIES_`, `ITEM_` and `TYPE_`) are explained where they are still
required for advanced exclusion lists.

The dark red-and-gold interface uses original SGRand SVG artwork for its application,
subsystem and workflow icons. These assets are packaged with the randomizer and
are not extracted or copied from SoulGold. Main navigation uses player-facing
names such as **MT y tutores**, **Jefes**, **Vista previa** and **Actividad**, while
the exact source terminology remains available in tooltips and advanced mode.

The editors intentionally separate concerns:

- **Movimientos** has pages for protection/exclusion lists, level-up learnsets and
  progressive power bands, TM/tutor compatibility, and basic properties. Move
  effects are not exposed because the engine deliberately preserves them.
- **Habilidades** has distinct pages and RNG policies for normal
  abilities and innates, plus the custom blacklist, special-ability list and
  mandatory form/species protections. The active engine profile is explicit.
- **Entrenadores** has independent pages for ordinary trainers, leaders, the rival
  and bosses, followed by global species/move/item lists and boss classes.

List fields contain one source constant per line. Progressive power bands can
be added and removed in their table. Invalid ranges, duplicates, missing
mandatory protections or unknown schema keys are rejected by the same strict
validators used by the engine.

**Advanced JSON** opens the complete versioned document for just that section.
Accepting the dialog validates it first and then synchronizes all visual
controls. This is the lossless route for hand-authored configurations; the main
interface does not require JSON knowledge. Import and export still use one
schema-versioned aggregate document containing all three engine documents.

## Presets

- **Vanilla+** keeps move data, abilities, innates and trainer parties vanilla
  while retaining the engine's established encounter, starter, static/gift and
  item randomization.
- **Balanced** uses bounded, evolution-aware defaults for every implemented
  subsystem.
- **Chaos** selects the Chaos ability/trainer profiles and broadens move power,
  accuracy and compatibility variation.
- **Custom** is selected automatically after an editor change and preserves the
  complete edited configuration during JSON export.

All presets retain mandatory progression moves, form protections and the other
hard invariants documented in the subsystem configuration guides.

## Spoiler-free mode

When enabled, preview, the returned report and the transactional manifest omit
starter results and detailed species/item mappings. Counts, configuration
hashes, validation results and before/after file hashes remain available for
diagnostics. The randomized checkout and compiled game naturally still contain
the selected results.

## Build adapters and diagnostics

**Comprobar** checks the selected checkout and the platform-specific commands;
it reports remediation text but never installs software or changes system
configuration.

### Linux native

The adapter runs `make -j<N>` directly. It checks `git`, `make`, `python3`,
`arm-none-eabi-gcc`, `pkg-config` and libpng. On Debian/Ubuntu, SoulGold
documents `build-essential`, `binutils-arm-none-eabi`, `gcc-arm-none-eabi`,
`libnewlib-arm-none-eabi`, `git`, `libpng-dev` and `python3`.

### Windows with WSL2

The Windows adapter invokes `make -j<N>` through `wsl.exe --cd <checkout>` and
checks the toolchain inside the default WSL distribution. WSL2 and Ubuntu must already be
configured; SGRand does not request administrator access or install packages.
During a build it records a temporary Linux process-group ID so cancellation
targets only that build rather than stopping the user's WSL distribution.
For performance, keep the checkout in the WSL2 filesystem and select it through
Explorer's `\\wsl.localhost\<distribution>\...` path. The official SoulGold
WSL instructions list the Ubuntu packages used by the diagnostic.

### macOS native

The adapter runs native `make`, supplying `/opt/devkitpro` defaults for
`DEVKITPRO` and `DEVKITARM` when they are absent. SoulGold's documented setup
requires Xcode Command Line Tools, libpng, pkg-config and devkitPro's `gba-dev`
plus `devkitarm-rules`. Homebrew can provide libpng and pkg-config; devkitPro is
installed with its macOS pacman package.

## Desktop artifacts and signing

`.github/workflows/release-gui.yml` tests the package, then builds Windows x64,
Linux x86_64 AppImage, macOS Intel and macOS Apple Silicon artifacts. The
workflow never checks out SoulGold and rejects `.gba`, `.elf` and `.map` files
inside packages.

Current CI artifacts are unsigned. Windows SmartScreen can warn that the
publisher is unknown until releases are Authenticode-signed. macOS bundles are
not Developer ID signed or notarized, so Gatekeeper can quarantine them. See
[`packaging/README.md`](../packaging/README.md) for the required production
signing and notarization steps.
