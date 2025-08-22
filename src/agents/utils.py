from typing import Any, Dict, Optional
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from collections.abc import AsyncIterator, Sequence
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from functools import wraps


class PostgresSaverCustom(PostgresSaver):
    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Asynchronously fetch a checkpoint tuple using the given configuration.

        Args:
            config (RunnableConfig): Configuration specifying which checkpoint to retrieve.

        Returns:
            Optional[CheckpointTuple]: The requested checkpoint tuple, or None if not found.
        """
        return self.get_tuple(config)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Asynchronously list checkpoints that match the given criteria.

        Args:
            config (Optional[RunnableConfig]): Base configuration for filtering checkpoints.
            filter (Optional[Dict[str, Any]]): Additional filtering criteria for metadata.
            before (Optional[RunnableConfig]): List checkpoints created before this configuration.
            limit (Optional[int]): Maximum number of checkpoints to return.

        Returns:
            AsyncIterator[CheckpointTuple]: Async iterator of matching checkpoint tuples.


        """
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Asynchronously store a checkpoint with its configuration and metadata.

        Args:
            config (RunnableConfig): Configuration for the checkpoint.
            checkpoint (Checkpoint): The checkpoint to store.
            metadata (CheckpointMetadata): Additional metadata for the checkpoint.
            new_versions (ChannelVersions): New channel versions as of this write.

        Returns:
            RunnableConfig: Updated configuration after storing the checkpoint.
        """
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously store intermediate writes linked to a checkpoint.

        Args:
            config (RunnableConfig): Configuration of the related checkpoint.
            writes (List[Tuple[str, Any]]): List of writes to store.
            task_id (str): Identifier for the task creating the writes.
            task_path (str): Path of the task creating the writes.
        """
        return self.put_writes(config, writes, task_id, task_path)


def last_k_elements_equal(lst, k):
    """Check if the last k elements of a list are equal."""
    return len(lst) >= k and all(x == lst[-1] for x in lst[-k:])


def limit_calls(max_calls=10):
    """
    Decorator to limit the number of times a tool function can be called,
    based on the `num_calls` counter inside the `state` dictionary.

    The `state` argument must be passed as a keyword argument and is expected
    to be injected (e.g., via a dependency like InjectedState).

    If the number of calls exceeds `max_calls`, the function is not executed
    and a fallback response is returned.

    Additionally, `num_calls` is incremented automatically after each successful call.

    Args:
        max_calls (int): Maximum number of allowed calls. Default is 10.

    Returns:
        dict: Either the function's original return value, or a fallback response if the limit is exceeded.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            state = kwargs.get("state")

            if state is None:
                raise ValueError("'state' must be provided as a keyword argument.")

            tool_call_id = kwargs.get("tool_call_id")
            if tool_call_id is None:
                raise ValueError(
                    "'tool_call_id' must be provided as a keyword argument."
                )

            num_calls = state.get("num_calls", [])
            # we cannot use more tool if we have already used the max_calls or
            # the last tool calls are the same
            if len(num_calls) > max_calls or last_k_elements_equal(
                num_calls, max_calls // 2
            ):
                output = {
                    "details": (
                        "You cannot call any more tools. Please provide a response to the user "
                        "explaining why the request could not be completed."
                    ),
                    "events": [],
                }
            else:
                try:
                    output = func(*args, **kwargs)
                except Exception as e:
                    output = {
                        "details": (
                            f"An error occurred in the tool '{func.__name__}'. Error: {str(e)}"
                        ),
                        "events": [],
                    }
            return Command(
                update={
                    "num_calls": [str(func.__name__)],
                    "workers_messages": [
                        ToolMessage(output, tool_call_id=tool_call_id)
                    ],
                }
            )

        return wrapper

    return decorator