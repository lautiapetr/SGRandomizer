"""Compatibility and safety policy for the supported source revision."""

SUPPORTED_TAG = "v.1.1.4"
DEFAULT_MANIFEST = "soulgold-randomizer-manifest.json"
SPECIAL_CATEGORIES = frozenset({"legendary", "mythical", "paradox"})

OFFICIAL_CHEAT_ITEM_ID_RANGES = (
    (1, 291),
    (339, 356),
    (392, 412),
    (418, 704),
    (760, 773),
    (794, 816),
    (891, 925),
)

STORY_ITEM_DENYLIST = frozenset(
    {
        "ITEM_AURORA_TICKET",
        "ITEM_BASEMENT_KEY",
        "ITEM_BECKONING_BELL",
        "ITEM_BICYCLE",
        "ITEM_CARD_KEY",
        "ITEM_CLEAR_BELL",
        "ITEM_COIN_CASE",
        "ITEM_DARK_CRYSTAL",
        "ITEM_DEVON_GOODS",
        "ITEM_DEVON_SCOPE",
        "ITEM_DOWSING_MACHINE",
        "ITEM_EON_TICKET",
        "ITEM_EXP_SHARE",
        "ITEM_GS_BALL",
        "ITEM_JADE_ORB",
        "ITEM_LETTER",
        "ITEM_LIBERTY_PASS",
        "ITEM_LIFT_KEY",
        "ITEM_LOST_ITEM",
        "ITEM_MACH_BIKE",
        "ITEM_MACHINE_PART",
        "ITEM_MAGMA_EMBLEM",
        "ITEM_MEGA_RING",
        "ITEM_METEORITE",
        "ITEM_MYSTERY_EGG",
        "ITEM_OAKS_PARCEL",
        "ITEM_OLD_SEA_MAP",
        "ITEM_PASS",
        "ITEM_POKE_FLUTE",
        "ITEM_POWDER_JAR",
        "ITEM_RAINBOW_PASS",
        "ITEM_RAINBOW_WING",
        "ITEM_RED_ORB",
        "ITEM_ROOM_1_KEY",
        "ITEM_ROOM_2_KEY",
        "ITEM_ROOM_4_KEY",
        "ITEM_ROOM_6_KEY",
        "ITEM_SCANNER",
        "ITEM_SCOPE_LENS_STORY",
        "ITEM_SECRET_KEY",
        "ITEM_SECRET_POTION",
        "ITEM_SILPH_SCOPE",
        "ITEM_SILVER_WING",
        "ITEM_SS_TICKET",
        "ITEM_STORAGE_KEY",
        "ITEM_SQUIRTBOTTLE",
        "ITEM_TEACHY_TV",
        "ITEM_TOWN_MAP",
        "ITEM_TRI_PASS",
        "ITEM_VS_SEEKER",
        "ITEM_WAILMER_PAIL",
    }
)

PROTECTED_SCRIPTED_ITEM_GIFTS = frozenset(
    {
        ("data/maps/NewBarkTown_Lab/scripts.pory", "giveitem", "ITEM_POKE_BALL", 10),
        ("data/maps/NewBarkTown_Lab/scripts.inc", "giveitem", "ITEM_POKE_BALL", 10),
    }
)

UNSAFE_SPECIES_PARTS = (
    "_MEGA",
    "_GMAX",
    "_PRIMAL",
    "_TOTEM",
    "_ETERNAMAX",
    "_BLADE",
    "_BUSTED",
    "_SCHOOL",
    "_NOICE_FACE",
    "_HANGRY",
    "_CROWNED",
    "_RAPID_STRIKE_GMAX",
    "_SINGLE_STRIKE_GMAX",
)
