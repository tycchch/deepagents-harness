# 架构笔记

这份文档记录 Harness 的**持久化架构**：一个会话在磁盘上被拆成哪几层、各自存什么、
靠什么串起来、以及在什么时机被读写。

---

## 一、五层存储总览

| 存储 | 介质 / 路径 | 谁在管 | 存什么 |
|---|---|---|---|
| `ThreadStore` | `~/.harness/threads.json`（JSON） | Harness 自己写 | 会话的**目录信息** |
| `TurnStore` | `~/.harness/turns.sqlite`（SQLite） | Harness 自己写 | 每轮的**版本锚点** |
| `WorkspaceSnapshotStore` | `~/.harness/workspace_snapshots/{blobs,manifests}/` | Harness 自己写 | 工作区**文件系统快照** |
| checkpointer | `~/.harness/checkpoints.sqlite`（或内存） | LangGraph | **对话记忆本体**（消息历史） |
| store | `~/.harness/store.sqlite`（或内存） | LangGraph / deepagents | agent 的**长期记忆 / 虚拟文件** |

前三个是"**索引层**"，后两个是"**内容层**"。

- 索引层由 `server/` 下的三个文件实现，**始终落盘**。
- 内容层由 `config/persist.py` 装配，**默认是内存实现**（`MemorySaver` / `InMemoryStore`），
  只有把 `persist.checkpointer` / `persist.store` 配成 `sqlite` 才落盘。

一句话概括分工：**索引层负责"去哪找"，内容层负责"存的是啥"。**

---

## 二、各层存什么（字段级）

### ThreadStore —— 会话目录

文件：`~/.harness/threads.json`（见 [server/session.py](../backend/server/session.py)）

每条 `ThreadRecord` 的字段：

| 字段 | 含义 |
|---|---|
| `thread_id` | 会话主键（uuid4），**同时就是 LangGraph 的 `configurable.thread_id`** |
| `workspace` | 绑定的工作目录（`normalize_workspace` 归一化后的绝对路径） |
| `title` | 标题；首条消息自动生成，手动 rename 后 `title_locked=True` 不再被覆盖 |
| `updated_at` | 最后活动时间，列表按它倒序 |
| `archived` | 是否归档 |
| `source` | 来源：`cli` / `desktop` |
| `parent_thread_id` | fork 谱系：父会话 id |
| `forked_from_turn_id` | fork 谱系：从父会话的哪一轮分叉 |
| `root_thread_id` | fork 谱系：整条谱系的根会话 id |

**不含任何对话内容**——只有"有哪些会话、叫什么、在哪个目录、谁从谁分叉出来"。

### TurnStore —— 轮次版本锚点

文件：`~/.harness/turns.sqlite`（见 [server/turns.py](../backend/server/turns.py)）

每条 `TurnRecord` 的字段：

| 字段 | 含义 |
|---|---|
| `turn_id` | 轮次主键（uuid4） |
| `thread_id` | 属于哪个会话 |
| `status` | `running` / `completed` / `error` / `interrupted` |
| `checkpoint_id` | **外键** → checkpointer 里该轮结束时的稳定 checkpoint |
| `workspace_manifest_id` | **外键** → 快照清单 id |
| `started_at` / `completed_at` | 起止时间 |

它自己也不存内容，**只存两个指针**：一个指向"记忆快照"，一个指向"文件快照"。
这两个指针合起来就是 fork 的定位表。

> LangGraph 自己负责 checkpoint 的序列化，`TurnStore` 只记录"哪一个 checkpoint
> 才是这一轮用户可见的稳定终态"。

### WorkspaceSnapshotStore —— 工作区时间机器

目录：`~/.harness/workspace_snapshots/`（见 [server/workspaces.py](../backend/server/workspaces.py)）

两级结构：

```
manifests/{32位hex}.json      ← 一份"文件清单"
    { "workspace": 源路径, "files": { 相对路径: blob_id } }

blobs/{前2位}/{64位sha256}     ← 真正的文件字节
```

- **内容寻址**：blob 按内容 sha256 命名，内容相同的文件天然只存一份（自动去重）。
- 抓取会跳过 `.git` / `.venv` / `node_modules` / `dist` / `__pycache__` 等目录。
- `capture` 写快照并返回 `manifest_id`；`materialize` 按清单把文件复刻到一个新目录。
- 注意：`capture` 返回 `None` 表示"没抓到"（工作区不存在或未配置 root），
  此时该轮会没有 `workspace_manifest_id`，**也就无法作为 fork 点**。

### checkpointer —— 对话记忆本体

- 默认：`MemorySaver`（进程内存）
- 落盘：`~/.harness/checkpoints.sqlite`（`AsyncSqliteSaver`）

每个 `thread_id` 在每一步图执行后存一份完整 state，`messages` 里是
Human / AI / Tool 消息全量。**这是对话历史的唯一真身**，`thread/history` 就是从这里读的。

### store —— 长期记忆 / 虚拟文件

- 默认：`InMemoryStore`
- 落盘：`~/.harness/store.sqlite`

LangGraph 的 `BaseStore`（命名空间 + 键值）。deepagents 用它存放
agent 的长期记忆（`memory=["/memories/AGENTS.md"]`）和虚拟文件系统。

与 checkpointer 的区别：**checkpointer 存"这一个会话怎么走过来的"，
store 存"跨会话的持久资料"。**

---

## 三、关系：靠 id 串联

```
threads.json ── thread_id ──────────────► checkpointer 的 configurable.thread_id
     │                                          ▲
     │  parent_thread_id (文件内自引用)         │ checkpoint_id
     ▼                                          │
turns.sqlite ── turn.thread_id ─────────────────┘   (每个 turn 属于一个 thread)
     │
     │  turn.workspace_manifest_id
     ▼
workspace_snapshots/manifests/{id}.json ── files ──► blobs/{xx}/{sha256}
```

- **`thread_id` 是贯穿所有层的主线**，它同时就是 LangGraph 的 `configurable.thread_id`。
- `turn_id` 只是 `TurnStore` 内部的主键。
- `checkpoint_id` 和 `manifest_id` 是 `TurnStore` 伸向另外两层的外键。
- fork 谱系（`parent_thread_id` / `forked_from_turn_id` / `root_thread_id`）是
  `threads.json` **文件内部的自引用**，不跨文件。

**三个 store 共享 `thread_id` 作为主键，所以在逻辑上仍是一套东西**——
这也是 fork 能成立的前提：三层里都能用同一个 id 找到对应的那一份。

---

## 四、生命周期：什么时候各自发挥作用

| 时刻 | ThreadStore | TurnStore | Snapshot | checkpointer |
|---|---|---|---|---|
| `thread/start` | **写**（新建记录） | — | — | — |
| `thread/list` / `rename` / `archive` / `set_workspace` | **读写**（唯一被碰的 store） | — | — | — |
| `turn/start` | **写** `touch`（刷新时间 + 自动标题） | **写** `start`（记一条 running） | — | agent 开跑，逐步写 |
| 流式输出中 | — | — | — | **持续写**每步 checkpoint |
| `turn/completed` | 读（拿 workspace） | **写** `finish`（回填两个指针） | **写** `capture` 抓快照 | 已写完最终 checkpoint |
| `thread/history` | 读（拿 workspace） | 读（筛出 completed 的 turn_id） | — | **读** `aget_state` |
| `thread/fork` | **写** `fork`（建子记录） | **读** `get`（取两个指针） | **读** `materialize` | **读源 + 写目标** `clone_checkpoint` |
| `thread/delete` | 写 `delete` | 写 `delete_thread` | — | 写 `adelete_thread` |

规律：**`ThreadStore` 在"会话级"操作时出手；`TurnStore` 和 `Snapshot` 只在
"轮次边界"和"fork"时出手。** 平时聊天流式输出时，只有 checkpointer 在动，
另外三个 store 完全不参与。

### fork 的三个动作

`thread/fork` 一次要动三层：

1. **记忆层** —— [server/checkpoints.py](../backend/server/checkpoints.py) 的 `clone_checkpoint`：
   把源线程某个 `checkpoint_id` 的 state 作为子线程的根状态写进目标 checkpointer。
2. **文件层** —— `WorkspaceSnapshotStore.materialize`：把该轮的 `manifest_id`
   复刻到一个全新目录，作为子会话独立的 workspace。
3. **目录层** —— `ThreadStore.fork`：写一条带 `parent_thread_id` /
   `forked_from_turn_id` 的子记录，把三者用新的 `child_id` 绑在一起。

前置条件：源轮次必须是 `completed`，且同时有 `checkpoint_id` 和
`workspace_manifest_id`，否则无法分叉。

---

## 五、两个容易踩的点

### 1. 默认配置下内容层是内存的

[config/schema.py](../backend/config/schema.py) 的 `PersistConfig` 默认
`checkpointer="memory"`、`store="memory"`，即走 `MemorySaver` / `InMemoryStore`：

- **进程一重启，对话历史和长期记忆就没了**；
- 但 `threads.json` / `turns.sqlite` / 快照是写死在
  [server/app.py](../backend/server/app.py) 里的，**始终落盘**。

于是重启后会看到"**会话列表还在，点进去历史空了**"这种不一致。

这也解释了为什么 [server/rpc.py](../backend/server/rpc.py) 要用模块级全局
`_AGENTS` / `_PERSIST` 把 agent（及其内存 checkpointer）钉在进程里——
否则连**页面刷新**都保不住历史。想要真正持久，把配置改成：

```yaml
persist:
  checkpointer: sqlite
  store: sqlite
```

### 2. `threads.json` 是全量重写的

`ThreadStore._save` 每次改动都把**整个 dict** 序列化写盘——简单，但会话多了会变慢。
`turns.sqlite` 则是增量 `INSERT` / `UPDATE` 且有索引，所以设计上是对的：
**元数据量小可以全量，轮次无限增长必须增量。**

---

## 六、为什么分成三个 store 而不是一个

因为它们的**生命周期和访问模式完全不同**：

- 会话元数据是"小而常改" → 一个 JSON 文件正合适；
- 轮次索引是"无限增长 + 要按 thread 查" → 需要 SQL；
- 文件快照是"大 + 要去重 + 要能整份复刻" → 需要内容寻址。

合成一个的话，每次改个标题都要重写一堆文件内容。
