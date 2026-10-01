import pytest

from upload.upload_state_store import UploadStateStore


@pytest.fixture
def new_state(make_batch_state, make_file_state):
    return lambda batch_public_id: make_batch_state(
        [make_file_state()], batch_public_id=batch_public_id
    )


class TestUploadStateStore:
    def test_save_and_load_round_trip(self, tmp_path, new_state):
        store = UploadStateStore(str(tmp_path))
        state = new_state("b-1")

        store.save(state)

        assert store.load("b-1") == state

    def test_load_missing_returns_none(self, tmp_path):
        store = UploadStateStore(str(tmp_path))

        assert store.load("nope") is None

    def test_delete_removes_state(self, tmp_path, new_state):
        store = UploadStateStore(str(tmp_path))
        store.save(new_state("b-1"))

        store.delete("b-1")

        assert store.load("b-1") is None
        store.delete("b-1")  # 없는 파일 삭제는 no-op

    def test_load_all_skips_broken_file(self, tmp_path, new_state):
        store = UploadStateStore(str(tmp_path))
        store.save(new_state("b-1"))
        store.save(new_state("b-2"))
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

        states = store.load_all()

        assert [s.batch_public_id for s in states] == ["b-1", "b-2"]

    def test_save_overwrites_atomically(self, tmp_path, new_state):
        store = UploadStateStore(str(tmp_path))
        state = new_state("b-1")
        store.save(state)
        state.files[0].record_part(1, '"etag1"')

        store.save(state)

        loaded = store.load("b-1")
        assert loaded is not None
        assert loaded.files[0].completed_etags == {1: '"etag1"'}
        assert not (tmp_path / "b-1.json.tmp").exists()
