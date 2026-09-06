from server.session import ThreadStore


def test_list_resume_archive(tmp_path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    info = store.start("E:/repo")
    assert store.get(info.thread_id) is not None
    assert store.list()[0].thread_id == info.thread_id
    assert store.resume(info.thread_id).workspace == "E:/repo"

    store.archive(info.thread_id)
    assert store.list() == []
    assert store.resume(info.thread_id) is None


def test_persist_reload(tmp_path) -> None:
    path = tmp_path / "threads.json"
    first = ThreadStore(path)
    info = first.start("E:/repo")
    second = ThreadStore(path)
    assert second.get(info.thread_id).workspace == "E:/repo"
