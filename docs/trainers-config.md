# Trainer configuration

Trainer randomization reads and writes the canonical competitive-syntax file
`src/data/trainers.party`. Policy lives in the embedded, versioned
`trainers-v1.json`. Custom files use the same strict schema: missing or unknown
keys, invalid ranges, unsupported versions and unknown species, move or item
constants fail before planning any write.

Select either built-in profile:

```bash
sgrand preview --source /path/to/soulgold --seed example \
  --trainer-profile Balanced

sgrand preview --source /path/to/soulgold --seed example \
  --trainer-profile Chaos
```

Supply a complete custom configuration with:

```bash
sgrand preview --source /path/to/soulgold --seed example \
  --trainers-config /path/to/trainers-v1-custom.json \
  --trainer-profile Balanced
```

The manifest records the configuration schema, profile, SHA-256, source and
blacklists. Trainer species, level/team-size decisions, themes, moves and
items consume distinct RNG streams.

## Categories and profiles

Every profile defines independent rules for `trainers`, `leaders`, `rival`
and `bosses`. Classification is ordered: the Rival class and every
`TRAINER_RIVAL*` ID are rivals; the Leader class is a leader; configured
`boss_classes` and IDs containing `BOSS` are bosses; everything else is a
regular trainer. The default boss classes include Elite Four, Champion and
the named villain-leader classes.

`Balanced` retains vanilla levels and party sizes. It uses bounded BST
replacement, gives leaders and bosses a type based on their original team,
uses a smaller chance of themes and held items for ordinary trainers, keeps
legendaries out of ordinary/leader/rival pools and permits them at a low rate
for bosses.

`Chaos` permits the full BST range, scales levels upward, varies ordinary,
leader and rival party sizes, gives bosses six Pokémon, increases themes and
held items, and permits configurable legendary rates in every category. Hard
safety and legality checks still apply.

Each category accepts:

- `enabled`: randomize this category.
- `maximum_bst_delta`: maximum absolute BST difference. If a source-only form
  has no safe candidate in the band, it is preserved rather than weakened by
  an out-of-band replacement.
- `level_mode`: `vanilla`, `scaled` or `fixed`. Scaled levels use
  `level_percent` and `level_offset`; fixed levels use `fixed_level`. All are
  clamped to `minimum_level`–`maximum_level`.
- `team_size_mode`: `vanilla`, `fixed` or `range`, using the corresponding
  fixed/minimum/maximum fields and the engine limit of one through six.
- `theme_mode`: `none`, `vanilla` (the most represented original type), or
  `random`; `theme_percent` controls whether it applies.
- `moves_mode`: `legal` rewrites authored slots from the target's legal pool;
  `preserve` keeps an authored species/moves combination together. A forced
  rival-starter replacement is always legalized.
- `held_items_mode`: `preserve`, `random` or `none`, with
  `held_item_percent` for random assignment.
- `allow_legendaries` and `legendary_percent`: inclusion and selection rate
  for Legendary, Mythical, Paradox and Ultra Beast candidates.
- `allow_duplicates`: whether one team may repeat a species.
- `double_synergy`: enforce a shared type when possible, prefer a legal
  support move on the lead and avoid duplicate held items when the pool allows.

Top-level blacklists independently remove species, moves and items. An empty
`held_item_allowlist` derives the pool from valid items already equipped in
the canonical party file; a non-empty list replaces that pool.

## Structural and gameplay protections

1. The parser preserves each trainer section and its competitive layout.
   Names, class, portrait, gender, music, AI, difficulty, IVs, EVs, nature,
   gender, nickname, ball and transformation fields remain untouched unless a
   configured rule owns that field.
2. Normal and Hard definitions with the same trainer ID remain separate and
   keep their original `Difficulty` metadata.
3. Explicit moves are selected only from the target species entry in
   `all_learnables.json`. Empty authored movesets remain empty so SoulGold's
   built-in level-aware legal generator continues to fill them. Source-only
   forms absent from that JSON are preserved with their authored moves.
4. Existing explicit Ability lines are changed to an ability from the final
   randomized normal-ability assignment. Entries without an Ability line keep
   trainerproc's normal default behavior.
5. Held items come only from constants defined by the checkout and accepted by
   the validated pool. Story/key items cannot enter the derived pool because
   it is based on items already used competitively.
6. The Silver branches remain coherent with the randomized starter choices:
   Chikorita, Cyndaquil and Totodile branch labels map to the first randomized
   choice-0, choice-1 and choice-2 lines, respectively, and encounters 1,
   2–3 and 4–7 use their base, middle and final stages. Resized teams retain
   exactly one such starter slot. SoulGold stores only
   three branch variables for nine visible choices, so all three UI choices
   sharing a choice number intentionally share the same rival line.
7. A species blacklist, move blacklist or item blacklist is absolute. Invalid
   references fail before a transaction is constructed.
8. After rendering, the section count is revalidated. `trainerproc` and the
   full game build provide the final syntax and C-level verification.

The real v1.1.4 projection resolves 1,947 party entries. The single literal
Cherrim entry is not exposed by `romhack-docs.json`; it is preserved verbatim
instead of guessing a form.

Validate a disposable result with the same generator and build used by the
game:

```bash
git clone --shared .work/soulgold-v1.1.4 /tmp/sgrand-trainer-build
sgrand apply --source /tmp/sgrand-trainer-build --seed trainer-check \
  --trainer-profile Balanced
make -C /tmp/sgrand-trainer-build src/data/trainers.h
make -C /tmp/sgrand-trainer-build -j2
```

Repeat with `--trainer-profile Chaos` to exercise configurable team resizing
and level scaling.
