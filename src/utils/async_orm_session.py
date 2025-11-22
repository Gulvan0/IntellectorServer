from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
    overload,
)

from sqlalchemy import text, util
from sqlalchemy.engine.interfaces import _CoreAnyExecuteParams
from sqlalchemy.engine.result import Result, ScalarResult, TupleResult
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from sqlalchemy.orm._typing import OrmExecuteOptionsParameter
from sqlalchemy.sql.base import Executable as _Executable
from sqlmodel.sql.base import Executable
from sqlmodel.sql.expression import Select, SelectOfScalar
from typing_extensions import deprecated


_TSelectParam = TypeVar("_TSelectParam", bound=Any)


# Mostly copied from SQLModel, but adapted for async use. Source: sqlmodel/orm/session.py
class AsyncSession(_AsyncSession):
    @overload
    async def exec(
        self,
        statement: Select[_TSelectParam],
        *,
        params: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
        execution_options: Mapping[str, Any] = util.EMPTY_DICT,
        bind_arguments: Optional[Dict[str, Any]] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> TupleResult[_TSelectParam]:
        ...

    @overload
    async def exec(
        self,
        statement: SelectOfScalar[_TSelectParam],
        *,
        params: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
        execution_options: Mapping[str, Any] = util.EMPTY_DICT,
        bind_arguments: Optional[Dict[str, Any]] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> ScalarResult[_TSelectParam]:
        ...

    async def exec(
        self,
        statement: Union[
            Select[_TSelectParam],
            SelectOfScalar[_TSelectParam],
            Executable[_TSelectParam],
        ],
        *,
        params: Optional[Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = None,
        execution_options: Mapping[str, Any] = util.EMPTY_DICT,
        bind_arguments: Optional[Dict[str, Any]] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> Union[TupleResult[_TSelectParam], ScalarResult[_TSelectParam]]:
        results = await super().execute(
            statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            _parent_execute_state=_parent_execute_state,
            _add_event=_add_event,
        )
        if isinstance(statement, SelectOfScalar):
            return results.scalars()
        return results  # type: ignore

    async def exec_raw(self, query: str) -> Result:
        connection = await self.connection()
        return await connection.execute(text(query))

    @deprecated("See this method's deprecation message for sync Session")
    async def execute(  # type: ignore
        self,
        statement: _Executable,
        params: Optional[_CoreAnyExecuteParams] = None,
        *,
        execution_options: OrmExecuteOptionsParameter = util.EMPTY_DICT,
        bind_arguments: Optional[Dict[str, Any]] = None,
        _parent_execute_state: Optional[Any] = None,
        _add_event: Optional[Any] = None,
    ) -> Result[Any]:
        return await super().execute(
            statement,
            params=params,
            execution_options=execution_options,
            bind_arguments=bind_arguments,
            _parent_execute_state=_parent_execute_state,
            _add_event=_add_event,
        )
