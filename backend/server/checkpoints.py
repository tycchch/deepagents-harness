from __future__ import annotations

from langgraph.checkpoint.base import create_checkpoint


async def clone_checkpoint(
    source_saver,
    target_saver,
    *,
    source_thread_id: str,
    source_checkpoint_id: str,
    target_thread_id: str,
) -> str:
    """Clone one completed checkpoint as the root state of another thread."""
    source_config = {
        "configurable": {
            "thread_id": source_thread_id,
            "checkpoint_ns": "",
            "checkpoint_id": source_checkpoint_id,
        }
    }
    checkpoint_tuple = await source_saver.aget_tuple(source_config)
    if checkpoint_tuple is None:
        raise KeyError(source_checkpoint_id)

    step = int(checkpoint_tuple.metadata.get("step", 0))
    checkpoint = create_checkpoint(checkpoint_tuple.checkpoint, None, step)
    metadata = dict(checkpoint_tuple.metadata)
    metadata["forked_from_thread_id"] = source_thread_id
    metadata["forked_from_checkpoint_id"] = source_checkpoint_id
    target_config = {
        "configurable": {
            "thread_id": target_thread_id,
            "checkpoint_ns": "",
        }
    }
    result = await target_saver.aput(
        target_config,
        checkpoint,
        metadata,
        checkpoint["channel_versions"],
    )
    return str(result["configurable"]["checkpoint_id"])
