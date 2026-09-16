# Move randomization configuration

The packaged profile is `src/sgrand/configs/moves-v1.json`. It is part of the
Python distribution, has `schema_version: 1`, and is hashed into every preview
or apply report. A custom JSON file can be selected with `--moves-config`.
Unknown fields, missing fields, duplicate constants, inverted ranges, invalid
percentages and unsupported schema versions fail before any checkout write.

## Global lists

- `protected_moves` are never replaced and their properties remain unchanged.
  The ten field/progression moves are mandatory and cannot be removed from this
  list. At runtime the engine also adds every valid `MOVE_*` referenced by map
  or global event scripts.
- `signature_moves` remain on their original owners, are never distributed as
  ordinary candidates, and retain their basic properties by default.
- `excluded_moves` are neither replaced nor selected. The default includes
  mechanically exceptional moves such as Struggle, Sketch, Transform and
  Metronome.

All three lists are disjoint and validated against the selected checkout.

## `learnsets`

`source_files` identifies the canonical inputs used by the v.1.1.4 build. The
default starts with the active `gen_9.h` and then `gen_7.h`, from which
SoulGold produces its legacy-compatible generated header. Shared original
moves receive the same replacement in both inputs; this preserves the
generator's deduplication and its `MAX_LEVEL_UP_MOVES` bound.

- `offensive_percent` is the target chance that a replaceable slot receives a
  damaging move.
- `stab_percent` prefers a move matching one of the owning species' types.
- `category_match_percent` prefers physical moves for higher Attack or special
  moves for higher Special Attack.
- `minimum_accuracy` excludes ordinary candidates below the threshold;
  accuracy zero retains its engine meaning of never missing.
- `progressive_power` is an ordered set of inclusive level/power bands. Filters
  relax only when a constrained pool would otherwise be empty.
- `early_attack_level` guarantees a damaging move at or before that level when
  the learnset has a replaceable early slot. Fully exceptional learnsets such
  as Ditto/Transform are recorded as exemptions.
- `preserve_signature_moves` prevents replacement of existing signature slots.

Levels and array structure remain unchanged.

## `compatibility`

`tm_percent` and `tutor_percent` independently control base compatibility.
`stab_bonus_percent` and `category_match_bonus_percent` are additive and capped
at 100. Decisions operate only on moves currently exposed as TMs or tutors;
non-teachable source data is retained. `preserve_protected_moves` and
`preserve_signature_moves` retain their original membership. Universal and
species-specific overrides in `special_movesets.json` are not rewritten.

## `properties`

`power_variation_percent` varies ordinary damaging moves around their canonical
power, clamped by `minimum_power`, `maximum_power` and `power_step`. Accuracy
and PP use their respective min/max/step fields. `types` is the allowed type
pool. `randomize_type` and `randomize_category` can be disabled independently.

The property pass never changes internal effects. Status categories and zero
power remain status; dynamic/fixed-power moves represented by power 0 or 1 are
left intact. Protected, signature and excluded moves retain all properties.

Each domain consumes its own named RNG stream. Given the same SoulGold tag,
configuration bytes and seed, preview and apply produce the same plan.
