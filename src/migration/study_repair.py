from dataclasses import dataclass, field

from board.coords import HexCoordinates
from board.piece import PieceKind
from board.ply import Ply
from board.position import Position


# A subtree this small can fit under a wrong node by chance
MIN_REATTACHED_SUBTREE_SIZE = 5


@dataclass(eq=False)  # siblings may be equal in content, yet are different nodes
class PlyTreeNode:
    ply: Ply
    children: list[PlyTreeNode] = field(default_factory=list)

    def size(self) -> int:
        return 1 + sum(child.size() for child in self.children)


def parse_ply(raw_ply: str) -> Ply:
    return Ply(
        HexCoordinates(int(raw_ply[0]), int(raw_ply[1])),
        HexCoordinates(int(raw_ply[2]), int(raw_ply[3])),
        PieceKind(raw_ply[4:].lower()) if len(raw_ply) > 4 else None
    )


def build_tree(raw_nodes: list[tuple[str, str]]) -> list[PlyTreeNode]:
    """The root's children, from (path, ply) pairs of the v1 format, where a path is the child indices joined by `:`.
    As in v1, the indices only order the siblings: a gap between them closes"""
    root_children: list[PlyTreeNode] = []
    nodes_by_indices: dict[tuple[int, ...], PlyTreeNode] = {}
    parsed_nodes = [(tuple(int(index) for index in path.split(":")), raw_ply) for path, raw_ply in raw_nodes]

    for indices, raw_ply in sorted(parsed_nodes, key=lambda parsed_node: (len(parsed_node[0]), parsed_node[0])):
        node = PlyTreeNode(parse_ply(raw_ply))
        nodes_by_indices[indices] = node
        if len(indices) == 1:
            root_children.append(node)
        else:
            nodes_by_indices[indices[:-1]].children.append(node)

    return root_children


def merge_duplicate_siblings(siblings: list[PlyTreeNode]) -> int:
    """v1 could give a node two children with the same ply, which a client can't tell apart. Returns the number of merged nodes"""
    unique: list[PlyTreeNode] = []
    merged_cnt = 0
    for node in siblings:
        twin = next((sibling for sibling in unique if sibling.ply == node.ply), None)
        if twin:
            twin.children += node.children
            merged_cnt += 1
        else:
            unique.append(node)
    siblings[:] = unique
    return merged_cnt + sum(merge_duplicate_siblings(node.children) for node in siblings)


def flatten_tree(root_children: list[PlyTreeNode]) -> list[tuple[str, Ply]]:
    """(path, ply) pairs of the v1 format, parents before their children"""
    flattened: list[tuple[str, Ply]] = []

    def visit(siblings: list[PlyTreeNode], parent_indices: list[int]) -> None:
        for index, node in enumerate(siblings):
            indices = parent_indices + [index]
            flattened.append((":".join(map(str, indices)), node.ply))
            visit(node.children, indices)

    visit(root_children, [])
    return flattened


def _ply_code(ply: Ply) -> str:
    code = f"{ply.departure.i}{ply.departure.j}{ply.destination.i}{ply.destination.j}"
    return code + ply.morph_into.name.capitalize() if ply.morph_into else code


def _fits(node: PlyTreeNode, position: Position) -> bool:
    """Whether the node's ply and all those below it are legal if it grows from the position"""
    if not position.is_ply_possible(node.ply):
        return False
    new_position = position.perform_ply(node.ply).new_position
    return all(_fits(child, new_position) for child in node.children)


def _collect_new_parents(siblings: list[PlyTreeNode], position: Position, misplaced: PlyTreeNode) -> list[PlyTreeNode]:
    """The nodes below the misplaced node's parent, reached by legal plies, that its whole subtree fits under"""
    new_parents: list[PlyTreeNode] = []
    for node in siblings:
        if node is misplaced or not position.is_ply_possible(node.ply):
            continue
        new_position = position.perform_ply(node.ply).new_position
        if _fits(misplaced, new_position):
            new_parents.append(node)
        new_parents += _collect_new_parents(node.children, new_position, misplaced)
    return new_parents


def _attach(parent: PlyTreeNode, node: PlyTreeNode) -> None:
    """A node with the ply of an existing child merges into it, as a client can't tell two children with the same ply apart"""
    twin = next((child for child in parent.children if child.ply == node.ply), None)
    if twin:
        for child in node.children:
            _attach(twin, child)
    else:
        parent.children.append(node)


def repair_tree(root_children: list[PlyTreeNode], starting_position: Position) -> list[str]:
    """Studies saved by v1 may hold illegal plies. Its analysis board ignored a replayed next move while its variation tree
    didn't follow it, so the plies made afterwards landed on a node above the one they were made from. Such a subtree
    moves to where the board really was, if that is certain. Any other subtree starting with an illegal ply is removed.
    Returns the description of every change"""
    changes: list[str] = []

    def repair_children(siblings: list[PlyTreeNode], position: Position, path: list[int]) -> None:
        for index, node in list(enumerate(siblings)):
            node_path = ":".join(map(str, path + [index]))
            if position.is_ply_possible(node.ply):
                repair_children(node.children, position.perform_ply(node.ply).new_position, path + [index])
                continue

            new_parents = _collect_new_parents(siblings, position, node) if node.size() >= MIN_REATTACHED_SUBTREE_SIZE else []
            siblings.remove(node)
            if len(new_parents) == 1:
                _attach(new_parents[0], node)
                changes.append(f"moved {node.size()} plies from {node_path} ({_ply_code(node.ply)}) under the node with the ply {_ply_code(new_parents[0].ply)}")
            else:
                changes.append(f"removed {node.size()} plies from {node_path} ({_ply_code(node.ply)}); {len(new_parents)} possible parents")

    repair_children(root_children, starting_position, [])
    return changes
