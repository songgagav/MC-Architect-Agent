"""Conservative, repeatable semantic suggestions based on explicit block IDs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import LitematicRegion, Position3


@dataclass(frozen=True)
class AnnotationProposal:
    rule_id: str
    component_type: str
    positions: tuple[Position3, ...]
    confidence: float
    explanation: str


_RULES = (
    ("mc.identity.door.v1", "door", lambda block: block.endswith("_door"), 0.75,
     "Minecraft door block identities are a direct visual cue; the grouping remains unreviewed."),
    ("mc.identity.window.v1", "window", lambda block: "glass" in block or block.endswith("_pane"), 0.65,
     "Glass block identities may represent windows or decoration; manual review is required."),
    ("mc.identity.railing.v1", "railing", lambda block: block.endswith("_fence") or block.endswith("_wall") or block == "minecraft:iron_bars", 0.65,
     "Fence, wall, and iron-bar identities may be rails or other details; manual review is required."),
)


def propose_region_annotations(region: LitematicRegion) -> tuple[AnnotationProposal, ...]:
    matches: dict[str, list[Position3]] = defaultdict(list)
    for position, state in region.iter_non_air_blocks():
        for rule_id, _component_type, predicate, _confidence, _explanation in _RULES:
            if predicate(state.name):
                matches[rule_id].append(position)
    proposals: list[AnnotationProposal] = []
    for rule_id, component_type, _predicate, confidence, explanation in _RULES:
        positions = matches.get(rule_id, [])
        if positions:
            proposals.append(
                AnnotationProposal(
                    rule_id=rule_id,
                    component_type=component_type,
                    positions=tuple(sorted(positions, key=lambda p: (p[1], p[2], p[0]))),
                    confidence=confidence,
                    explanation=explanation,
                )
            )
    return tuple(proposals)
