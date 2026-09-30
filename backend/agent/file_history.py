"""内容寻址的文件历史：agent 改写工作区之前，先把旧内容存进全局 blob。

三个已定的决策（改之前先看这里）：

1. 快照表存在 graph state 的 `file_history` channel 里。它随每个 checkpoint 一起落盘，
   所以 fork 时自动继承，不需要额外搬运，也不会和对话状态不同步。
2. 只跟踪 `/workspace/`。`/skills`、`/memories` 属于 agent 自身的配置，纳入回滚会让
   「回滚会话」的语义变模糊。
3. 记录的是**写入之前**的内容，所以 agent 首次改动之前的原始版本也能回滚。写入前
   文件不存在时记 `blob=None`（回滚动作是删除），这与「文件存在但是空的」不同——后者
   的 blob 是空内容的哈希。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, NotRequired, TypedDict
from uuid import uuid4

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    WriteResult,
)
from langchain.agents import AgentState
from langchain.agents.middleware.types import AgentMiddleware, PrivateStateAttr
from langgraph._internal._constants import CONFIG_KEY_READ, CONFIG_KEY_SEND
from langgraph.config import get_config

from config.schema import HarnessConfig

logger = logging.getLogger(__name__)

FILE_HISTORY_CHANNEL = "file_history"
TRACKED_PREFIX = "/workspace/"
_BLOB_ID_LEN = 16
_HEX_DIGITS = frozenset("0123456789abcdef")

# 读取写入前状态失败（既不是成功也不是「不存在」）时用它，表示这次不该记录。
_UNKNOWN = object()


class FileWriteRecord(TypedDict):
    """一次写入的登记：写入之前那份内容是什么。"""

    seq: int
    """该路径的第几次写入，从 1 开始。"""

    blob: str | None
    """写入前内容的 blob 哈希；`None` 表示写入前该文件不存在（回滚时应删除）。"""

    at: str
    """ISO8601 UTC 时间戳。"""


def _merge_history(
    left: dict[str, list[FileWriteRecord]] | None,
    right: dict[str, list[FileWriteRecord]] | None,
) -> dict[str, list[FileWriteRecord]]:
    """按路径合并。调用方每次都发送该路径的完整列表，所以后者整体覆盖前者。"""
    merged = dict(left or {})
    if right:
        merged.update(right)
    return merged


class FileHistoryState(AgentState):
    """给 graph state 加一个 `file_history` channel。

    `PrivateStateAttr` 让它不出现在公开的输入/输出 schema 里（调用方不需要传它），
    但它仍然随每个 checkpoint 落盘，可以经 `agent.get_state(config).values` 读到。
    """

    file_history: NotRequired[
        Annotated[dict[str, list[FileWriteRecord]], _merge_history, PrivateStateAttr]
    ]
    """每个被跟踪路径的写入登记，按写入顺序排列。"""


class FileHistoryMiddleware(AgentMiddleware):
    """只负责声明 `file_history` channel。

    真正的记录发生在 `FileHistoryBackend` 里——那是所有工具（含子智能体）写文件的
    必经之路，比拦截 write_file/edit_file 工具名更可靠。
    """

    state_schema = FileHistoryState


class BlobStore:
    """内容寻址的 blob 存储，全局唯一、与 thread 无关。

    文件名是 sha256(内容) 的前 16 位，因此同一份内容在任何会话、任何 fork 里都只占
    一份磁盘，fork 时不需要复制任何 blob。
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def put(self, content: bytes) -> str:
        """存一份内容，返回 blob id。内容已存在时不重复写。"""
        blob_id = hashlib.sha256(content).hexdigest()[:_BLOB_ID_LEN]
        target = self.path_for(blob_id)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            # 先写临时文件再 rename：崩溃只会留下 .tmp，不会留下半个 blob。
            tmp = target.with_name(f"{blob_id}.{uuid4().hex}.tmp")
            tmp.write_bytes(content)
            tmp.replace(target)
        return blob_id

    def get(self, blob_id: str) -> bytes | None:
        path = self.path_for(blob_id)
        return path.read_bytes() if path.is_file() else None

    def has(self, blob_id: str) -> bool:
        return self.path_for(blob_id).is_file()

    def path_for(self, blob_id: str) -> Path:
        # blob id 来自上游数据，必须校验，否则可以借它跳出 root。
        if len(blob_id) != _BLOB_ID_LEN or not set(blob_id) <= _HEX_DIGITS:
            raise ValueError(f"bad blob id: {blob_id!r}")
        return self._root / blob_id[:2] / blob_id


class FileHistoryBackend(BackendProtocol):
    """包装 `/workspace/` 这一条 route：写入前先把旧内容存进 blob 存储。

    只包 route，不包整个 `CompositeBackend`：deepagents 内部对顶层 backend 有多处
    `isinstance(..., CompositeBackend)` 和 `_uses_state_backend` 检查，包顶层会让
    `files` channel 降级成 `AgentState`，直接破坏 StateBackend。

    注意本类收到的是**剥掉前缀后**的路径：`CompositeBackend` 把 `/workspace/a.txt`
    归一成 `/a.txt` 再调 route backend（见 composite.py 的 `_route_for_path`）。所以
    这里不需要再做前缀过滤——挂在这条 route 上就意味着一切都该记；登记进 state 时
    再用 `_virtual()` 还原成完整虚拟路径，方便后续回滚定位。
    """

    def __init__(
        self,
        inner: BackendProtocol,
        blobs: BlobStore,
        *,
        prefix: str = TRACKED_PREFIX,
    ) -> None:
        self._inner = inner
        self._blobs = blobs
        self._prefix = prefix
        self._warned_outside_graph = False

    def __getattr__(self, name: str) -> Any:
        # 只在正常查找失败时触发；_ 开头的是本对象自己的属性，不能在初始化完成前递归。
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    # ------------------------------------------------------------------
    # 写之前备份
    # ------------------------------------------------------------------

    def _virtual(self, backend_path: str) -> str:
        """把 route backend 的路径还原成完整虚拟路径，作为快照表的键。"""
        suffix = backend_path.lstrip("/")
        return f"{self._prefix}{suffix}" if suffix else self._prefix.rstrip("/")

    def _configurable(self) -> dict | None:
        """拿到 CONFIG_KEY_READ/SEND。不在图里跑时返回 None（此时跳过记录）。"""
        try:
            configurable = get_config().get("configurable") or {}
        except RuntimeError:
            return None
        if CONFIG_KEY_READ not in configurable or CONFIG_KEY_SEND not in configurable:
            return None
        return configurable

    def _record(self, backend_path: str, before: bytes | None) -> None:
        """把写入前的内容登记进 state channel。

        记录是辅助能力，失败不应该让文件写入本身失败——所以这里吞掉异常只记日志。
        """
        configurable = self._configurable()
        file_path = self._virtual(backend_path)
        if configurable is None:
            if not self._warned_outside_graph:
                self._warned_outside_graph = True
                logger.warning(
                    "file history: 不在 LangGraph 执行上下文里，跳过记录（%s）", file_path
                )
            return
        try:
            table = configurable[CONFIG_KEY_READ](FILE_HISTORY_CHANNEL, True) or {}
            records = list(table.get(file_path) or [])
            records.append(
                FileWriteRecord(
                    seq=len(records) + 1,
                    blob=self._blobs.put(before) if before is not None else None,
                    at=_now(),
                )
            )
            configurable[CONFIG_KEY_SEND]([(FILE_HISTORY_CHANNEL, {file_path: records})])
        except Exception:
            logger.warning("file history: 记录 %s 失败", file_path, exc_info=True)

    def _download(self, file_path: str) -> bytes | None | object:
        """取当前内容；`None` 表示不存在，`_UNKNOWN` 表示读不出来（跳过记录）。"""
        response = self._inner.download_files([file_path])[0]
        return _content_of(response)

    async def _adownload(self, file_path: str) -> bytes | None | object:
        response = (await self._inner.adownload_files([file_path]))[0]
        return _content_of(response)

    # ------------------------------------------------------------------
    # 拦截写入
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        before = self._download(file_path)
        result = self._inner.write(file_path, content)
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        before = await self._adownload(file_path)
        result = await self._inner.awrite(file_path, content)
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        before = self._download(file_path)
        result = self._inner.edit(file_path, old_string, new_string, replace_all)
        # 编辑失败（比如 old_string 没匹配上）时什么都没写，不该留登记。
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        before = await self._adownload(file_path)
        result = await self._inner.aedit(file_path, old_string, new_string, replace_all)
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result

    def delete(self, file_path: str) -> DeleteResult:
        # 必须显式定义：deepagents 用 `type(backend).delete is not BackendProtocol.delete`
        # 判断 backend 是否支持删除，经 __getattr__ 透传会判定成「不支持」。
        before = self._download(file_path)
        result = self._inner.delete(file_path)
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result

    async def adelete(self, file_path: str) -> DeleteResult:
        before = await self._adownload(file_path)
        result = await self._inner.adelete(file_path)
        if result.error is None and before is not _UNKNOWN:
            self._record(file_path, before)
        return result


def _delegate_to_inner(name: str):
    def method(self: FileHistoryBackend, *args: Any, **kwargs: Any) -> Any:
        return getattr(self._inner, name)(*args, **kwargs)

    method.__name__ = name
    method.__qualname__ = f"FileHistoryBackend.{name}"
    return method


# 透传方法必须显式挂到类上：`read`/`ls`/`grep` 这些定义在 BackendProtocol 里（基类实现
# 是 raise NotImplementedError），正常属性查找会命中基类，`__getattr__` 不会触发，于是
# 读路径会直接抛 NotImplementedError。这里把协议自己的方法除 write/edit/delete 外
# 全部生成成转发方法；`__getattr__` 只兜住 cwd/virtual_mode 这类非协议属性。
_OWN_METHODS = frozenset({"write", "awrite", "edit", "aedit", "delete", "adelete"})
for _name in (n for n in dir(BackendProtocol) if not n.startswith("_")):
    if _name in _OWN_METHODS or not callable(getattr(BackendProtocol, _name, None)):
        continue
    setattr(FileHistoryBackend, _name, _delegate_to_inner(_name))
del _name


def _content_of(response: Any) -> bytes | None | object:
    """把 FileDownloadResponse 归一成「内容 / 不存在 / 读不出来」。"""
    error = getattr(response, "error", None)
    if error is None:
        content = getattr(response, "content", None)
        # error 为空但 content 也是空，说明文件不存在，而不是「内容为空字节」。
        return None if content is None else content
    if error == "file_not_found":
        return None
    return _UNKNOWN


def build_blob_store(cfg: HarnessConfig) -> BlobStore:
    """blob 根目录，跟随 backends.py 的约定放在 memories 的兄弟目录下。"""
    memories = Path(cfg.memories_root or Path.home() / ".harness" / "memories")
    return BlobStore(memories.parent / "file_history")


def build_file_history_middleware() -> FileHistoryMiddleware:
    return FileHistoryMiddleware()


def _now() -> str:
    return datetime.now(UTC).isoformat()
