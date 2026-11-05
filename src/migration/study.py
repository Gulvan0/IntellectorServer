from board.deserializers.sip import position_from_sip
from board.serializers.sip import get_sip
from migration.study_repair import build_tree, flatten_tree, merge_duplicate_siblings, repair_tree
from study.datatypes import StudyPublicity
from study.models import Study, StudyTag, StudyPlyTreeNode


def format_new_path_part(branch: str, repetition_cnt: int) -> str:
    part = "" if branch == "0" else branch
    if repetition_cnt > 1:
        part += f"x{repetition_cnt}"
    return part


def convert_path(old_path: str) -> str:
    new_path = ""
    current_branch = None
    current_repetition_cnt = 0

    for part in old_path.split(":"):
        if not current_branch:
            current_branch = part

        if current_branch == part:
            current_repetition_cnt += 1
        else:
            new_path += format_new_path_part(current_branch, current_repetition_cnt) + ":"
            current_repetition_cnt = 1
            current_branch = part

    if current_branch:
        new_path += format_new_path_part(current_branch, current_repetition_cnt)
    return new_path


def process_study(study_id: int, data: dict) -> Study:
    variant_raw: str | None = data.get("variantStr")
    if not variant_raw:
        raise ValueError(f'Empty study:\n{data}')

    parts = variant_raw.rsplit(";", 1)
    starting_sip = get_sip(position_from_sip(parts[-1]))
    nodes = []
    if len(parts) > 1:
        tree = build_tree([(path, raw_ply) for path, raw_ply in (raw_node.split("/") for raw_node in parts[0].split(";"))])
        merged_cnt = merge_duplicate_siblings(tree)
        if merged_cnt:
            print(f'Study {study_id}: merged {merged_cnt} duplicate plies')
        for change in repair_tree(tree, position_from_sip(starting_sip)):
            print(f'Study {study_id}: {change}')
        for path, ply in flatten_tree(tree):
            nodes.append(StudyPlyTreeNode(
                path=convert_path(path),
                ply_from_i=ply.departure.i,
                ply_from_j=ply.departure.j,
                ply_to_i=ply.destination.i,
                ply_to_j=ply.destination.j,
                ply_morph_into=ply.morph_into
            ))

    key_sip = data.get("keyPositionSIP")

    return Study(
        name=data.get("name") or "Unnamed",
        description=data.get("description", ""),
        publicity=StudyPublicity.PRIVATE if data.get("publicity") == "Private" else StudyPublicity.PUBLIC,
        starting_sip=starting_sip,
        key_sip=get_sip(position_from_sip(key_sip)) if key_sip else starting_sip,
        id=study_id,
        author_login=(data.get("author") or "").lower() or None,
        tags=[StudyTag(tag=tag) for tag in data.get("tags", [])],
        nodes=nodes
    )
