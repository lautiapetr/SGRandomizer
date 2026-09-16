"""Evolution-aware species selection."""

from __future__ import annotations

import random
import re
from collections import defaultdict, deque

from .constants import UNSAFE_SPECIES_PARTS
from .models import Species


def safe_species(species: Species) -> bool:
    if species.dex <= 0 or species.bst <= 0 or "mega" in species.categories:
        return False
    for part in UNSAFE_SPECIES_PARTS:
        if part == "_MEGA":
            if re.search(r"_MEGA(?:_|$)", species.constant):
                return False
        elif part in species.constant:
            return False
    return True


def graph_data(species: dict[str, Species]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    children: dict[str, set[str]] = {constant: set() for constant in species}
    parents: dict[str, set[str]] = {constant: set() for constant in species}
    for constant, mon in species.items():
        for target in mon.evolutions:
            if target in species:
                children[constant].add(target)
                parents[target].add(constant)
    return children, parents


def components(
    species: dict[str, Species],
    children: dict[str, set[str]],
    parents: dict[str, set[str]],
) -> list[set[str]]:
    pending = {constant for constant, mon in species.items() if safe_species(mon)}
    result: list[set[str]] = []
    while pending:
        queue = [min(pending)]
        component: set[str] = set()
        while queue:
            current = queue.pop()
            if current not in pending:
                continue
            pending.remove(current)
            component.add(current)
            queue.extend((children[current] | parents[current]) & pending)
        result.append(component)
    return result


def component_depths(
    component: set[str], children: dict[str, set[str]], parents: dict[str, set[str]]
) -> dict[str, int]:
    roots = sorted(node for node in component if not (parents[node] & component)) or [
        min(component)
    ]
    depths = {root: 0 for root in roots}
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for child in sorted(children[node] & component):
            depth = depths[node] + 1
            if child not in depths or depth < depths[child]:
                depths[child] = depth
                queue.append(child)
    for node in component:
        depths.setdefault(node, 0)
    return depths


def family_signature(
    component: set[str], depths: dict[str, int], species: dict[str, Species]
) -> tuple[int, tuple[int, ...]]:
    max_depth = max(depths.values(), default=0)
    medians: list[int] = []
    for depth in range(max_depth + 1):
        values = sorted(species[node].bst for node in component if depths[node] == depth)
        medians.append(values[len(values) // 2])
    return max_depth, tuple(medians)


def build_species_mapping(species: dict[str, Species], rng: random.Random) -> dict[str, str]:
    children, parents = graph_data(species)
    families = components(species, children, parents)
    depth_by_family = {
        id(family): component_depths(family, children, parents) for family in families
    }
    candidate_families = [
        family
        for family in families
        if not any(
            species[node].is_special or "ultra_beast" in species[node].categories for node in family
        )
    ]
    by_depth: dict[int, list[set[str]]] = defaultdict(list)
    for family in candidate_families:
        depths = depth_by_family[id(family)]
        by_depth[max(depths.values(), default=0)].append(family)

    mapping: dict[str, str] = {}
    for source_family in sorted(families, key=min):
        source_depths = depth_by_family[id(source_family)]
        if any(
            species[node].is_special or "ultra_beast" in species[node].categories
            for node in source_family
        ):
            mapping.update({node: node for node in source_family})
            continue

        source_signature = family_signature(source_family, source_depths, species)
        candidates = by_depth.get(source_signature[0]) or candidate_families
        scored: list[tuple[int, str, set[str]]] = []
        for candidate in candidates:
            if candidate is source_family and len(candidates) > 1:
                continue
            candidate_depths = depth_by_family[id(candidate)]
            compatible = True
            for source_node in source_family:
                same_stage = [
                    node
                    for node in candidate
                    if candidate_depths[node] == source_depths[source_node]
                ]
                if children[source_node] & source_family:
                    same_stage = [node for node in same_stage if children[node] & candidate]
                tolerance = max(40, round(species[source_node].bst * 0.12))
                if (
                    not same_stage
                    or min(abs(species[source_node].bst - species[node].bst) for node in same_stage)
                    > tolerance
                ):
                    compatible = False
                    break
            if not compatible:
                continue
            candidate_signature = family_signature(candidate, candidate_depths, species)
            width = min(len(source_signature[1]), len(candidate_signature[1]))
            score = (
                sum(
                    abs(source_signature[1][index] - candidate_signature[1][index])
                    for index in range(width)
                )
                + abs(len(source_family) - len(candidate)) * 25
            )
            scored.append((score, min(candidate), candidate))
        scored.sort(key=lambda row: (row[0], row[1]))
        if not scored:
            mapping.update({node: node for node in source_family})
            continue

        best_score = scored[0][0]
        target_family = rng.choice([row for row in scored if row[0] <= best_score + 45][:24])[2]
        target_depths = depth_by_family[id(target_family)]
        target_roots = [node for node in target_family if not (parents[node] & target_family)]
        for source_node in sorted(source_family, key=lambda node: (source_depths[node], node)):
            source_parents = sorted(parents[source_node] & source_family)
            if source_parents:
                choices = {
                    child
                    for source_parent in source_parents
                    for child in children[mapping[source_parent]] & target_family
                }
                same_stage = sorted(choices)
            else:
                same_stage = sorted(target_roots)
            if not same_stage:
                same_stage = [
                    node
                    for node in target_family
                    if target_depths[node] == source_depths[source_node]
                ]
            if children[source_node] & source_family:
                evolvable = [node for node in same_stage if children[node] & target_family]
                if evolvable:
                    same_stage = evolvable
            if not same_stage:
                same_stage = list(target_family)
            ranked = sorted(
                same_stage,
                key=lambda node: (abs(species[source_node].bst - species[node].bst), node),
            )
            best_delta = abs(species[source_node].bst - species[ranked[0]].bst)
            close = [
                node
                for node in ranked
                if abs(species[source_node].bst - species[node].bst) <= best_delta + 10
            ]
            mapping[source_node] = rng.choice(close)

    for constant in species:
        mapping.setdefault(constant, constant)
    return mapping


def starter_pool(species: dict[str, Species]) -> list[str]:
    children, parents = graph_data(species)
    pool: list[str] = []
    for constant, mon in species.items():
        if not safe_species(mon) or mon.is_special or "ultra_beast" in mon.categories:
            continue
        if parents[constant] or not children[constant]:
            continue
        first = children[constant]
        second = {grandchild for child in first for grandchild in children[child]}
        if not second or any(not children[child] for child in first):
            continue
        if any(children[grandchild] for grandchild in second):
            continue
        pool.append(constant)
    return sorted(pool)


def choose_starters(species: dict[str, Species], rng: random.Random) -> list[str]:
    pool = [constant for constant in starter_pool(species) if 270 <= species[constant].bst <= 360]
    if len(pool) < 9:
        from .errors import RandomizerError

        raise RandomizerError(f"Only {len(pool)} valid three-stage starter candidates were found")
    return rng.sample(pool, 9)
