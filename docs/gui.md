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

1. Select an existing clean SoulGold `v.1.1.4` checkout, or choose **Download
   v.1.1.4**. Downloading performs a shallow, single-tag clone from
   `https://github.com/Eemeliri/soulgold.git` into the chosen empty directory;
   it never copies that checkout into the SGRand repository or executable.
2. Select an output directory. The named ROM copy and technical report are
   written there, never into this repository. SoulGold's own `make` still
   creates its normal `Soulgold.gba` build product inside the selected checkout.
3. Select a preset and enter a text or numeric seed. **Random** creates a
   cryptographically generated 128-bit hexadecimal seed.
4. Edit the versioned JSON in the Moves, Abilities/Innates and Trainers tabs if
   needed. Any edit changes the preset label to `Custom`. Import and export use
   one schema-versioned JSON document containing all three engine documents.
5. Run **Preview**. It validates and plans all edits in memory without writing.
6. Run **Randomize**. The existing transaction preflights, stages and commits
   all source changes and its manifest, rolling back committed files if a
   replacement fails.
7. Run **Build**. Build output streams into the Logs tab, the progress bar
   advances through generation, compilation and linking, and **Cancel** stops
   the build process tree. A cancelled build can leave ordinary generated
   objects in the selected SoulGold checkout; it cannot leave a half-applied
   randomization transaction.

The named output is `SGRand-<preset>-<seed>.gba`; the technical report is
`SGRand-<preset>-<seed>-report.json`. Unsafe filename characters are replaced.
Existing named ROM outputs are not overwritten.

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

**Diagnose** checks the selected checkout and the platform-specific commands;
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
