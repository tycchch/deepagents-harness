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


def test_persist_reload(tmp_path) -> None:
    path = tmp_path / "threads.json"
    first = ThreadStore(path)
    info = first.start("E:/repo")
    second = ThreadStore(path)
    assert normalize_workspace(second.get(info.thread_id).workspace) == normalize_workspace("E:/repo")
