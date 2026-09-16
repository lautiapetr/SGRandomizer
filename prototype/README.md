# SoulGold Semi-Randomizer

Randomizes a clean local checkout of Pokemon SoulGold `v.1.1.4` while
preserving the game's trainers, story progression, species data, and special
Pokemon encounters.

## Rules implemented

- Wild Pokemon: random, similar strength, follow evolutions.
- Trainers: unchanged.
- Starters: nine distinct random base Pokemon whose evolutionary family has
  three stages; similar strength.
- Static and gift Pokemon: random, similar strength, follow evolutions.
- Legendary, Mythical, Ultra Beast, and Paradox Pokemon: unchanged.
- Abilities, movesets, types, stats, and evolution methods: unchanged.
- Field, hidden, and scripted gift items: random.
- The ten early-game Poké Balls from Professor Elm's lab: unchanged.
- Key items, story items, HMs, and other important items: unchanged.

The tool modifies source data, not a compiled ROM. It does not distribute the
SoulGold source, a Pokemon Emerald ROM, or a compiled SoulGold ROM.

## Requirements

- Python 3.10 or newer.
- A clean checkout of `https://github.com/Eemeliri/soulgold` at tag
  `v.1.1.4`.

No third-party Python packages are required.

On Ubuntu/Zorin OS, install the build dependencies with:

```bash
sudo apt update
sudo apt install build-essential binutils-arm-none-eabi gcc-arm-none-eabi \
    libnewlib-arm-none-eabi git libpng-dev python3 pkg-config
```

## Usage

Preview a seed without changing files:

```bash
python3 tools/soulgold_randomizer/randomize.py --source . --seed 12345
```

Apply it to the checkout:

```bash
python3 tools/soulgold_randomizer/randomize.py --source . --seed 12345 --apply
```

The report is written to `soulgold-randomizer-manifest.json`. It contains the
seed, starter choices, species mappings, every changed encounter, and every
changed item.

To use another seed, restore the checkout first and then run the tool again:

```bash
git restore src/data/wild_encounters.json src/ui_birch_case.c data/maps data/scripts
rm soulgold-randomizer-manifest.json
```

The randomizer refuses to apply over an existing manifest unless
`--force` is supplied.

## Build

After applying a seed, build SoulGold normally:

```bash
make -j"$(nproc)"
```

The resulting source build is `Soulgold.gba`. Keep it private and follow
the SoulGold project instructions for creating a patch from a legally obtained
compatible base ROM.

## Compatibility notes

- Developed and compile-tested against SoulGold source tag `v.1.1.4`.
- The official website's cheat-code item IDs (documented for `v1.0.4.5`) are
  used only as an additional allowlist for ordinary item IDs; the actual item
  classification comes from the `v.1.1.4` source.
- The public repository does not currently contain a license file, so this
  README calls it public/source-available source rather than assuming a
  particular open-source license.
