"""Fail-closed material subset supported by the Minecraft Java 1.21.5 roof engine.

This is deliberately a small architectural-material catalog rather than a
claim to enumerate every block in the game. Add a block here only when its
ID, geometric role, and state properties are understood by the generators.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..core.block import BlockState

TARGET_VERSION = "Minecraft Java 1.21.5"
_DIRECTIONS = frozenset({"north", "east", "south", "west"})
_BOOL = frozenset({"true", "false"})


@dataclass(frozen=True)
class _BlockDefinition:
    shape: str
    properties: Mapping[str, frozenset[str]]


_STAIR_PROPERTIES = MappingProxyType(
    {
        "facing": _DIRECTIONS,
        "half": frozenset({"top", "bottom"}),
        "shape": frozenset({"straight", "inner_left", "inner_right", "outer_left", "outer_right"}),
        "waterlogged": _BOOL,
    }
)
_SLAB_PROPERTIES = MappingProxyType({"type": frozenset({"top", "bottom", "double"}), "waterlogged": _BOOL})
_AXIS_PROPERTIES = MappingProxyType({"axis": frozenset({"x", "y", "z"})})
_PANE_PROPERTIES = MappingProxyType(
    {**{direction: _BOOL for direction in _DIRECTIONS}, "waterlogged": _BOOL}
)
_DOOR_PROPERTIES = MappingProxyType(
    {
        "facing": _DIRECTIONS,
        "half": frozenset({"upper", "lower"}),
        "hinge": frozenset({"left", "right"}),
        "open": _BOOL,
        "powered": _BOOL,
    }
)
_TRAPDOOR_PROPERTIES = MappingProxyType(
    {
        "facing": _DIRECTIONS,
        "half": frozenset({"top", "bottom"}),
        "open": _BOOL,
        "powered": _BOOL,
        "waterlogged": _BOOL,
    }
)
_FENCE_GATE_PROPERTIES = MappingProxyType(
    {"facing": _DIRECTIONS, "in_wall": _BOOL, "open": _BOOL, "powered": _BOOL}
)
_LANTERN_PROPERTIES = MappingProxyType({"hanging": _BOOL, "waterlogged": _BOOL})


def _definitions() -> dict[str, _BlockDefinition]:
    result: dict[str, _BlockDefinition] = {}

    def add(block_id: str, shape: str = "full", properties: Mapping[str, frozenset[str]] = MappingProxyType({})) -> None:
        result[f"minecraft:{block_id}"] = _BlockDefinition(shape, properties)

    def add_many(names: set[str] | frozenset[str], suffix: str, shape: str, properties: Mapping[str, frozenset[str]] = MappingProxyType({})) -> set[str]:
        ids = {f"{name}{suffix}" for name in names}
        for block_id in ids:
            add(block_id, shape, properties)
        return ids

    wood_types = {
        "oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove",
        "cherry", "pale_oak", "crimson", "warped",
    }
    wood_types.update({"bamboo", "bamboo_mosaic"})
    stair_bases = wood_types | {
        "stone", "cobblestone", "mossy_cobblestone", "stone_brick", "mossy_stone_brick",
        "brick", "sandstone", "smooth_sandstone", "red_sandstone", "smooth_red_sandstone",
        "quartz", "smooth_quartz", "purpur", "prismarine_brick", "dark_prismarine",
        "nether_brick", "red_nether_brick", "blackstone", "polished_blackstone",
        "polished_blackstone_brick", "cobbled_deepslate", "polished_deepslate",
        "deepslate_brick", "deepslate_tile", "mud_brick", "cut_copper", "exposed_cut_copper",
        "weathered_cut_copper", "oxidized_cut_copper", "waxed_cut_copper",
        "waxed_exposed_cut_copper", "waxed_weathered_cut_copper", "waxed_oxidized_cut_copper",
        "tuff", "polished_tuff", "tuff_brick",
    }
    slab_bases = stair_bases | {"petrified_oak"}
    stair_ids = add_many(stair_bases, "_stairs", "stair", _STAIR_PROPERTIES)
    slab_ids = add_many(slab_bases, "_slab", "slab", _SLAB_PROPERTIES)

    full_ids = {
        "stone", "granite", "polished_granite", "diorite", "polished_diorite", "andesite",
        "polished_andesite", "deepslate", "cobbled_deepslate", "polished_deepslate", "calcite",
        "tuff", "polished_tuff", "tuff_bricks", "chiseled_tuff", "chiseled_tuff_bricks",
        "stone_bricks", "cracked_stone_bricks", "mossy_stone_bricks", "chiseled_stone_bricks",
        "bricks", "mud_bricks", "sandstone", "cut_sandstone", "chiseled_sandstone",
        "smooth_sandstone", "red_sandstone", "cut_red_sandstone", "chiseled_red_sandstone",
        "smooth_red_sandstone", "quartz_block", "chiseled_quartz_block", "quartz_pillar",
        "smooth_quartz", "prismarine", "prismarine_bricks", "dark_prismarine", "blackstone",
        "polished_blackstone", "polished_blackstone_bricks", "cracked_polished_blackstone_bricks",
        "gilded_blackstone", "nether_bricks", "red_nether_bricks", "end_stone", "end_stone_bricks",
        "purpur_block", "purpur_pillar", "glass", "glowstone", "sea_lantern", "shroomlight",
        "obsidian", "crying_obsidian", "netherrack", "bedrock", "clay", "bookshelf",
        "chiseled_bookshelf", "crafting_table", "furnace", "blast_furnace", "smoker",
        "jack_o_lantern", "pumpkin", "melon", "podzol", "mycelium", "sculk", "sponge",
        "wet_sponge", "snow_block", "ice", "packed_ice", "blue_ice", "basalt", "polished_basalt",
        "smooth_basalt", "amethyst_block", "budding_amethyst", "bone_block", "hay_block",
        "dried_kelp_block", "honey_block", "slime_block", "target", "coal_block", "iron_block",
        "gold_block", "diamond_block", "emerald_block", "lapis_block", "redstone_block",
        "netherite_block", "raw_iron_block", "raw_copper_block", "raw_gold_block", "copper_block",
        "cut_copper", "exposed_copper", "weathered_copper", "oxidized_copper", "waxed_copper_block",
        "waxed_cut_copper", "waxed_exposed_copper", "waxed_weathered_copper", "waxed_oxidized_copper",
        "waxed_exposed_cut_copper", "waxed_weathered_cut_copper", "waxed_oxidized_cut_copper",
        "chiseled_copper", "exposed_chiseled_copper", "weathered_chiseled_copper",
        "oxidized_chiseled_copper", "waxed_chiseled_copper", "waxed_exposed_chiseled_copper",
        "waxed_weathered_chiseled_copper", "waxed_oxidized_chiseled_copper", "bamboo_block",
        "stripped_bamboo_block",
    }
    for block_id in full_ids:
        add(block_id)

    colors = {
        "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
        "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black",
    }
    for color in colors:
        for suffix in ("_wool", "_concrete", "_concrete_powder", "_terracotta", "_glazed_terracotta", "_stained_glass"):
            add(f"{color}{suffix}")
        add(f"{color}_stained_glass_pane", "other", _PANE_PROPERTIES)

    wood_axis_blocks: set[str] = set()
    for kind in wood_types - {"bamboo", "bamboo_mosaic"}:
        add(f"{kind}_planks")
        for suffix in ("_log", "_wood", "_stem", "_hyphae"):
            # Only the matching overworld or nether tree types are registered.
            if suffix in ("_stem", "_hyphae") and kind not in {"crimson", "warped"}:
                continue
            if suffix in ("_log", "_wood") and kind in {"crimson", "warped"}:
                continue
            wood_axis_blocks.add(f"{kind}{suffix}")
            wood_axis_blocks.add(f"stripped_{kind}{suffix}")
    add("bamboo_planks")
    add("bamboo_mosaic")
    for block_id in wood_axis_blocks:
        add(block_id, "full", _AXIS_PROPERTIES)

    for block_id in ("torch", "soul_torch"):
        add(block_id, "other")
    for block_id in ("wall_torch", "soul_wall_torch"):
        add(block_id, "other", MappingProxyType({"facing": _DIRECTIONS}))
    for block_id in ("lantern", "soul_lantern"):
        properties = _LANTERN_PROPERTIES
        add(block_id, "other", properties)
    add("chain", "other", _AXIS_PROPERTIES)
    add("iron_bars", "other", _PANE_PROPERTIES)
    add("glass_pane", "other", _PANE_PROPERTIES)
    add("ladder", "other", MappingProxyType({"facing": _DIRECTIONS, "waterlogged": _BOOL}))

    # Register the common non-full wood forms so a mistaken full_block band is
    # rejected as a shape error rather than accepted as a usable solid cube.
    wood_names = wood_types - {"bamboo_mosaic"}
    add_many(wood_names | {"bamboo"}, "_fence", "other", _PANE_PROPERTIES)
    add_many(wood_names | {"bamboo"}, "_fence_gate", "other", _FENCE_GATE_PROPERTIES)
    add_many(wood_names | {"bamboo"}, "_door", "other", _DOOR_PROPERTIES)
    add_many(wood_names | {"bamboo"}, "_trapdoor", "other", _TRAPDOOR_PROPERTIES)

    # Explicit non-full blocks already used by the fail-closed geometry checks.
    for block_id in (
        "cobweb", "lever", "redstone_wire", "repeater", "comparator", "lightning_rod",
        "end_rod", "candle", "scaffolding", "tripwire", "tripwire_hook", "flower_pot",
        "dead_bush", "short_grass", "tall_grass", "fern", "large_fern", "dandelion",
        "poppy", "blue_orchid", "allium", "azure_bluet", "cornflower", "oxeye_daisy",
        "lily_of_the_valley", "torchflower", "wither_rose", "open_eyeblossom", "closed_eyeblossom",
        "large_amethyst_bud", "medium_amethyst_bud", "small_amethyst_bud", "amethyst_cluster",
        "oak_sapling", "spruce_sapling", "birch_sapling", "jungle_sapling", "acacia_sapling",
        "dark_oak_sapling", "mangrove_propagule", "cherry_sapling",
    ):
        add(block_id, "other")

    # Verify the registry construction itself stays unambiguous.
    if not stair_ids or not slab_ids:
        raise RuntimeError("Minecraft roof material catalog is incomplete")
    return result


_BLOCKS = _definitions()


def validate_roof_material_state(state: BlockState) -> None:
    """Reject IDs and properties outside the versioned roof-material catalog."""

    definition = _BLOCKS.get(state.block_id)
    if definition is None:
        raise ValueError(f"{state.to_string()} is not registered for {TARGET_VERSION} roof materials")
    for key, value in state.properties:
        allowed = definition.properties.get(key)
        if allowed is None or value not in allowed:
            raise ValueError(f"{state.to_string()} is not registered for {TARGET_VERSION} roof materials")


def roof_material_shape(state: BlockState) -> str:
    """Return the registered shape class for a validated material state."""

    validate_roof_material_state(state)
    definition = _BLOCKS[state.block_id]
    if definition.shape == "slab" and dict(state.properties).get("type") == "double":
        return "full"
    return definition.shape
