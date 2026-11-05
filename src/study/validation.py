import asyncio
import re
from collections.abc import Sequence

from fastapi import HTTPException

from board.coords import HexCoordinates
from board.deserializers.sip import position_from_sip
from board.ply import Ply
from board.position import Position
from study.models import StudyPlyTreeNode


PATH_RUN = re.compile(r'(\d*)(?:x(\d+))?', re.ASCII)


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def validate_sip(sip: str) -> Position:
    try:
        return position_from_sip(sip)
    except ValueError:
        raise _invalid(f"Invalid SIP: {sip}")


def _child_indices(path: str, max_depth: int) -> tuple[int, ...]:
    """A path is run-length encoded: `x2:1:` is the first child of the first child, then the second child, then the first one.
    Its runs are measured before being expanded, as a short path can stand for a depth that doesn't fit in memory"""
    runs: list[tuple[int, int]] = []
    depth = 0
    for run in path.split(":"):
        matched = PATH_RUN.fullmatch(run)
        if not matched:
            raise _invalid(f"Invalid node path: {path}")
        repetitions = int(matched.group(2) or 1)
        depth += repetitions
        if not repetitions or depth > max_depth:
            raise _invalid(f"Invalid node path: {path}")
        runs.append((int(matched.group(1) or 0), repetitions))
    return tuple(child_index for child_index, repetitions in runs for _ in range(repetitions))


def _validate_ply_tree(starting_sip: str, nodes: Sequence[StudyPlyTreeNode]) -> None:
    # every node's ancestors have to be present, so a path can't be deeper than there are nodes
    nodes_by_indices = {_child_indices(node.path, len(nodes)): node for node in nodes}
    if len(nodes_by_indices) != len(nodes):
        raise _invalid("Duplicate node paths")

    positions: dict[tuple[int, ...], Position] = {(): validate_sip(starting_sip)}
    for indices in sorted(nodes_by_indices):  # a parent sorts before its children, and a sibling before the next ones
        node = nodes_by_indices[indices]
        parent = positions.get(indices[:-1])
        if not parent or (indices[-1] and indices[:-1] + (indices[-1] - 1,) not in positions):
            raise _invalid(f"The parent or the previous sibling of node {node.path} is missing")

        ply = Ply(
            HexCoordinates(node.ply_from_i, node.ply_from_j),
            HexCoordinates(node.ply_to_i, node.ply_to_j),
            node.ply_morph_into
        )
        if not parent.is_ply_possible(ply):
            raise _invalid(f"The ply of node {node.path} is impossible")
        positions[indices] = parent.perform_ply(ply).new_position


async def validate_ply_tree(starting_sip: str, nodes: Sequence[StudyPlyTreeNode]) -> None:
    """Answers 422 unless the nodes make a tree of legal plies growing from the starting position.
    In a thread, as a big tree takes long enough to be felt by every game on the server"""
    await asyncio.to_thread(_validate_ply_tree, starting_sip, nodes)
