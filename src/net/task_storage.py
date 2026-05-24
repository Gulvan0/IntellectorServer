from asyncio import Task
import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
import traceback
from typing import Any


@dataclass
class ConcurrentTaskStorage:
    on_failure: Callable[[str, str], Coroutine[Any, Any, None]] | None = None
    __tasks: set[Task] = field(default_factory=set)

    def __on_task_done(self, task: Task) -> None:
        self.__tasks.discard(task)

        if task.cancelled():
            return

        exception = task.exception()
        if not exception:
            return

        task_name = task.get_name()
        message = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        print(message)
        with Path('./error_log.txt').open("a") as f:
            f.write(message + '\n\n')

        if self.on_failure:
            db_task = asyncio.create_task(self.on_failure(task_name, message))
            db_task.add_done_callback(
                lambda t: print(t.exception()) if not t.cancelled() and t.exception() else None
            )

    def plan(self, coroutine: Coroutine[Any, Any, Any], name: str | None = None) -> None:
        task = asyncio.create_task(coroutine, name=name or coroutine.__qualname__)
        self.__tasks.add(task)
        task.add_done_callback(self.__on_task_done)
