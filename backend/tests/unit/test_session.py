from server.session import ThreadStore, normalize_workspace


def test_list_resume_archive(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    info = store.start("E:/repo")
    assert store.get(info.thread_id) is not None
    assert store.list()[0].thread_id == info.thread_id
    assert normalize_workspace(store.resume(info.thread_id).workspace) == normalize_workspace("E:/repo")

    store.archive(info.thread_id)
    assert store.list() == []
    assert store.list(include_archived=True)[0].archived is True
    assert store.resume(info.thread_id) is not None
    store.unarchive(info.thread_id)
    assert store.list()[0].thread_id == info.thread_id


def test_latest_for_workspace_is_newest(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    older = store.start(str(tmp_path / "ws"))
    store._items[older.thread_id].updated_at = "2020-01-01T00:00:00+00:00"
    newer = store.start(str(tmp_path / "ws"))
    store.touch(newer.thread_id, title="new")
    store.start(str(tmp_path / "other"))
    found = store.latest_for_workspace(str(tmp_path / "ws"))
    assert found is not None
    assert found.thread_id == newer.thread_id
    assert normalize_workspace(found.workspace) == normalize_workspace(str(tmp_path / "ws"))


def test_rename_beats_auto_title(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    info = store.start("E:/repo")
    store.touch(info.thread_id, title="第一条消息")
    assert store.get(info.thread_id).title == "第一条消息"

    renamed = store.rename(info.thread_id, "  重构计划  ")
    assert renamed.title == "重构计划"
    store.touch(info.thread_id, title="后来的消息")
    assert store.get(info.thread_id).title == "重构计划"
    assert ThreadStore(tmp_path / "threads.json").get(info.thread_id).title == "重构计划"
    assert store.rename("nope", "x") is None


def test_set_workspace_rebinds_thread(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    info = store.start(str(tmp_path / "old"))
    other = tmp_path / "new"
    other.mkdir()
    moved = store.set_workspace(info.thread_id, str(other))
    assert moved is not None
    assert normalize_workspace(moved.workspace) == normalize_workspace(str(other))
    assert store.set_workspace("nope", str(other)) is None


def test_delete_removes_record(tmp_path) -> None:
    path = tmp_path / "threads.json"
    store = ThreadStore(path)
    info = store.start("E:/repo")
    assert store.delete(info.thread_id) is True
    assert store.get(info.thread_id) is None
    assert store.delete(info.thread_id) is False
    assert ThreadStore(path).get(info.thread_id) is None


def test_list_filters_by_source(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    web = store.start("E:/repo", source="desktop")
    cli = store.start("E:/repo", source="cli")
    assert {item.thread_id for item in store.list(source="cli")} == {cli.thread_id}
    assert {item.thread_id for item in store.list(source="desktop")} == {web.thread_id}
    assert {item.thread_id for item in store.list()} == {web.thread_id, cli.thread_id}
    assert store.latest_for_workspace("E:/repo", source="cli").thread_id == cli.thread_id


def test_persist_reload(tmp_path) -> None:
    path = tmp_path / "threads.json"
    first = ThreadStore(path)
    info = first.start("E:/repo")
    second = ThreadStore(path)
    assert normalize_workspace(second.get(info.thread_id).workspace) == normalize_workspace("E:/repo")
