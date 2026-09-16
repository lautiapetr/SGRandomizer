# Ability configuration

Ability randomization is controlled by the embedded, versioned
`abilities-v1.json`. A custom file must use the same exact schema: unknown or
missing keys, unsupported schema versions, invalid ranges, duplicate constants
and references absent from the checkout are rejected before any write.

Select a built-in profile independently of the configuration file:

```bash
sgrand preview --source /path/to/soulgold --seed example \
  --ability-profile Balanced

sgrand preview --source /path/to/soulgold --seed example \
  --ability-profile Chaos
```

Supply an edited copy for custom blacklists or policy values:

```bash
sgrand preview --source /path/to/soulgold --seed example \
  --abilities-config /path/to/abilities-v1-custom.json \
  --ability-profile Balanced
```

The manifest records the schema version, selected profile, configuration
SHA-256 and every protection list. Configuration content is part of the
reproducibility contract.

## Profiles and fields

`Balanced` follows evolution lines for both domains, preserves each species'
vanilla innate count, prevents duplicates, matches the source ability's
`aiRating` within the configured tolerance, limits ratings to 1–8 and excludes
the special-ability list.

`Chaos` makes per-species choices, assigns three innates, permits duplicates,
uses the full -2–10 rating range and permits special abilities. It still
enforces every hard safety rule below.

The `abilities` object in each profile accepts:

- `enabled`: enable the normal/hidden ability pass.
- `follow_evolutions`: give connected evolution stages the same ordered
  non-empty ability sequence.
- `allow_duplicates`: permit the same normal ability in multiple slots.
- `rating_strategy`: `similar` applies `maximum_rating_delta`; `any` ignores
  the source rating after applying the global rating range.
- `minimum_ai_rating` and `maximum_ai_rating`: eligible power band read from
  the real `gAbilitiesInfo` records. Missing `.aiRating` fields have C's
  zero-initialized value.
- `maximum_rating_delta`: maximum distance from the median vanilla rating at
  the corresponding family slot when using `similar`.
- `allow_special_abilities`: include or exclude `special_abilities`.

`innates` has the same fields plus:

- `count_mode`: `vanilla` retains the exact per-species innate count; `fixed`
  uses `fixed_count`.
- `fixed_count`: zero through three innates when `count_mode` is `fixed`.

The top-level `blacklist` is always excluded and is intended for user policy.
`special_abilities` contains functional but unusually strong or disruptive
abilities; profiles decide whether they enter the pool. `ABILITY_NONE` is
always excluded from candidate selection and remains only as an existing empty
normal slot.

## Hard protections

These invariants cannot be disabled by a custom profile:

1. A species can never repeat one of its non-empty normal abilities as an
   innate.
2. Every ability referenced by the source must exist in `src/data/abilities.h`.
3. Abilities used as predicates by `form_change_tables.h` are discovered from
   the checkout, removed from every random pool and preserved on their owning
   species.
4. The mandatory `species_locked_abilities` list cannot remove Forecast,
   Flower Gift, Multitype, Zen Mode, Stance Change, Power Construct, Schooling,
   RKS System, Shields Down, Disguise, Gulp Missile, Ice Face, Hunger Switch,
   Battle Bond, Commander, Zero to Hero, Tera Shift/Tera Shell/Teraform Zero,
   As One or the four Embody Aspect abilities. Those mechanics either check a
   concrete species/form or are incomplete outside their intended family.
5. When one source initializer is shared by several species, protection of one
   owner protects all owners. Parameterized macros whose ability fields cannot
   be safely rewritten as independent arrays are conservatively preserved.
6. Form-protected species retain both their normal and innate arrays, avoiding
   a partial change that could invalidate a transformation.
7. `count_mode: vanilla` is checked again after planning, along with duplicate
   main/innate overlap and referential integrity.

Normal abilities consume only the `species-abilities` RNG stream. Innates
consume only `species-innates`; their sole intentional dependency on the first
pass is the exclusion of the species' resulting normal abilities.
