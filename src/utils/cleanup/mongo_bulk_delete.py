import logging
from typing import Any, Iterable, Iterator, List

from bson import Binary
from pymongo.collection import Collection

logger = logging.getLogger('django')

DELETE_CHUNK_SIZE = 2000


def _normalize_id(value: Any) -> Any:
    if isinstance(value, Binary):
        return bytes(value)
    return value


def delete_many_in_chunks(
    collection: Collection,
    id_values: Iterable[Any],
    *,
    id_field: str = 'id',
    chunk_size: int = DELETE_CHUNK_SIZE,
    dry_run: bool = True,
) -> int:
    ids: List[Any] = list(id_values)
    if not ids:
        return 0

    deleted = 0
    chunk_size = max(1, int(chunk_size or DELETE_CHUNK_SIZE))
    for offset in range(0, len(ids), chunk_size):
        chunk = ids[offset:offset + chunk_size]
        if dry_run:
            deleted += len(chunk)
            continue
        result = collection.delete_many({id_field: {'$in': chunk}})
        deleted += int(result.deleted_count)

    return deleted


def aggregation_orphan_ids(
    collection: Collection,
    *,
    parent_collection: str,
    foreign_key_field: str,
    parent_key_field: str = 'id',
    extra_match: dict | None = None,
) -> Iterator[Any]:
    pipeline: list[dict] = [
        {
            '$lookup': {
                'from': parent_collection,
                'localField': foreign_key_field,
                'foreignField': parent_key_field,
                'as': '_parent_row',
            },
        },
        {'$match': {'_parent_row': {'$eq': []}}},
        {'$project': {'id': 1}},
    ]
    if extra_match:
        pipeline.insert(0, {'$match': extra_match})

    for document in collection.aggregate(pipeline, allowDiskUse=True):
        document_id = document.get('id')
        if document_id is not None:
            yield _normalize_id(document_id)
