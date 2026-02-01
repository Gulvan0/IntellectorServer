from board.deserializers.sip import position_from_sip
from board.piece import PieceKind
from board.serializers.sip import get_sip
from study.datatypes import StudyPublicity
from study.models import Study, StudyTag, StudyVariationNode


def process_study(study_id: int, data: dict) -> Study:
    variant_raw: str | None = data.get("variantStr")
    if not variant_raw:
        raise ValueError(f'Empty study:\n{data}')

    parts = variant_raw.rsplit(";", 1)
    starting_sip = get_sip(position_from_sip(parts[-1]))
    nodes = []
    if len(parts) > 1:
        for raw_node in parts[0].split(";"):
            path, raw_ply = raw_node.split("/")
            nodes.append(StudyVariationNode(
                joined_path=path,
                ply_from_i=raw_ply[0],
                ply_from_j=raw_ply[1],
                ply_to_i=raw_ply[2],
                ply_to_j=raw_ply[3],
                ply_morph_into=PieceKind(raw_ply[4:].lower()) if len(raw_ply) > 4 else None
            ))

    key_sip = data.get("keyPositionSIP")

    return Study(
        name=data.get("name") or "Unnamed",
        description=data.get("description", ""),
        publicity=StudyPublicity.PRIVATE if data.get("publicity") == "Private" else StudyPublicity.PUBLIC,
        starting_sip=starting_sip,
        key_sip=get_sip(position_from_sip(key_sip)) if key_sip else starting_sip,
        id=study_id,
        author_login=data.get("author"),
        tags=[StudyTag(tag=tag) for tag in data.get("tags", [])],
        nodes=nodes
    )
