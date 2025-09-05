from collections.abc import AsyncIterator, Sequence
from functools import wraps
import os
import random
import time
from typing import Any, Dict, Optional

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver

from langgraph.types import Command
from psycopg_pool import ConnectionPool

from utils.config import get_config
from utils.logger import get_logger

logger = get_logger("agents.utils")


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


def limit_calls(
    max_calls=10,
    *,
    retries=3,
    backoff_base=0.5,
    backoff_max=8.0,
    jitter_ratio=0.1,
    retry_exceptions=(Exception,),
    retry_if=None,
):
    """
    Decorator that limits the number of calls to a tool function,
    and adds retries with exponential backoff (and jitter).

    The `state` argument must be passed as a keyword argument and is expected
    to be injected (e.g., via a dependency like InjectedState).

    Args:
        max_calls (int): Maximum allowed tool calls.
        retries (int): Number of retries on failure (besides the first attempt).
        backoff_base (float): Initial backoff delay in seconds.
        backoff_max (float): Maximum backoff delay in seconds.
        jitter_ratio (float): Jitter ratio to randomize delay (0-1).
        retry_exceptions (tuple[Exception]): Which exceptions should trigger retries.
        retry_if (callable): Optional filter: (exc, attempt, kwargs) -> bool.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            state = kwargs.get("state")

            if state is None:
                logger.error("'state' must be provided as a keyword argument.")
                raise ValueError("'state' must be provided as a keyword argument.")

            tool_call_id = kwargs.get("tool_call_id")
            if tool_call_id is None:
                logger.error("'tool_call_id' must be provided as a keyword argument.")
                raise ValueError(
                    "'tool_call_id' must be provided as a keyword argument."
                )

            num_calls = state.get("num_calls", [])
            # stop if max_calls exceeded or last_k_elements_equal triggered
            if len(num_calls) > max_calls or last_k_elements_equal(
                num_calls, max_calls // 2
            ):
                logger.debug(
                    "Reached the maximum number of tool calls.",
                    extra={"num_calls": num_calls},
                )
                output = {
                    "details": (
                        "You cannot call any more tools. Please provide a response to the user "
                        "explaining why the request could not be completed."
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

            attempts = 0
            while attempts <= retries:
                try:
                    output = func(*args, **kwargs)
                    # success: exit retry loop
                    break
                except retry_exceptions as e:
                    # check retry filter
                    should_retry = True
                    if callable(retry_if):
                        try:
                            should_retry = bool(retry_if(e, attempts, kwargs))
                        except Exception as filter_err:
                            logger.exception(
                                "retry_if callable raised an error; aborting retries.",
                                extra={
                                    "tool_called": str(func.__name__),
                                    "error": str(filter_err),
                                    "original_error": str(e),
                                },
                            )
                            should_retry = False

                    attempts += 1

                    if not should_retry or attempts > retries:
                        # no more retries
                        logger.exception(
                            "Error in tool call (no more retries).",
                            extra={
                                "tool_called": str(func.__name__),
                                "error": str(e),
                                "attempts": attempts,
                            },
                        )
                        output = {
                            "details": (
                                f"An error occurred in the tool '{func.__name__}'. "
                                f"Error: {str(e)}"
                            ),
                            "events": [],
                        }
                        break

                    # compute backoff with jitter
                    delay = min(backoff_base * (2 ** (attempts - 1)), backoff_max)
                    if jitter_ratio:
                        jitter = delay * jitter_ratio
                        delay = max(0.0, delay + random.uniform(-jitter, jitter))

                    logger.warning(
                        "Tool call failed; retrying with exponential backoff.",
                        extra={
                            "tool_called": str(func.__name__),
                            "error": str(e),
                            "attempt": attempts,
                            "next_delay_seconds": round(delay, 3),
                        },
                    )
                    time.sleep(delay)

                except Exception as e:
                    # non-retryable error
                    logger.exception(
                        "Error in tool call (non-retryable).",
                        extra={"tool_called": str(func.__name__), "error": str(e)},
                    )
                    output = {
                        "details": (
                            f"An error occurred in the tool '{func.__name__}'. Error: {str(e)}"
                        ),
                        "events": [],
                    }
                    break

            return Command(
                update={
                    # NOTE: retries do NOT increment num_calls
                    "num_calls": [str(func.__name__)],
                    "workers_messages": [
                        ToolMessage(output, tool_call_id=tool_call_id)
                    ],
                }
            )

        return wrapper

    return decorator


def create_checkpointer():
    """
    Factory function to create the appropriate checkpointer based on environment.
    In test environment, uses MemorySaver to avoid database connections.
    In production, uses PostgresSaverCustom with connection pool.
    """
    # Check if we're in a test environment
    is_test_env = (
        get_config().TESTING == "true"
        or "pytest" in os.environ.get("PYTEST_CURRENT_TEST", "")
        or os.environ.get("PYTEST") == "true"
    )

    if is_test_env:
        logger.info("Using MemorySaver in test environment.")
        return MemorySaver()
    else:
        DB_URI = os.environ.get("POSTGRES_DB_URI")
        if not DB_URI:
            raise ValueError(
                "POSTGRES_DB_URI environment variable is required for production"
            )

        pool = ConnectionPool(
            conninfo=DB_URI,
            min_size=3,
            max_size=3,
            max_lifetime=900,
            max_waiting=12,
            max_idle=180,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
            },
        )
        # Get a connection from the pool to pass to PostgresSaverCustom
        with pool.connection() as conn:
            checkpointer = PostgresSaverCustom(conn)
            checkpointer.setup()
            logger.info("Using PostgresSaver in production environment.")
            return checkpointer
