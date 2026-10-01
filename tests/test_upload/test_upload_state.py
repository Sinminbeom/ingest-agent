import pytest

from upload.upload_state import BatchUploadState, FileUploadState, FileUploadStatus


@pytest.fixture
def new_multipart_file(make_file_state, make_multipart_plan):
    return lambda: make_file_state(plan=make_multipart_plan(), size_bytes=25)


class TestFileUploadState:
    def test_pending_parts_excludes_completed(self, new_multipart_file):
        state = new_multipart_file()
        state.record_part(2, '"etag2"')

        assert state.pending_part_numbers() == [1, 3]

    def test_merge_listed_parts_keeps_local_record(self, new_multipart_file):
        state = new_multipart_file()
        state.record_part(1, '"local1"')

        state.merge_listed_parts({1: '"remote1"', 2: '"remote2"'})

        assert state.completed_etags == {1: '"local1"', 2: '"remote2"'}

    def test_reset_for_retry_keeps_completed_parts(self, new_multipart_file):
        state = new_multipart_file()
        state.record_part(1, '"etag1"')
        state.mark_failed("FAIL_UPLOAD_RETRYABLE", "boom", retryable=True)

        state.reset_for_retry()

        assert state.status == FileUploadStatus.PENDING
        assert state.fail_code is None
        assert state.fail_at is None
        assert state.completed_etags == {1: '"etag1"'}

    def test_round_trip_keeps_expected_checksums(self, new_multipart_file):
        # 재개할 때 기대 체크섬과 분할 정보를 다시 계산하지 않고 저장값을 그대로 쓴다.
        state = new_multipart_file()
        state.mark_detected()
        state.record_part(1, '"etag1"')
        state.mark_failed("FAIL_UPLOAD", "boom", retryable=False)

        restored = FileUploadState.from_dict(state.to_dict())

        assert restored == state

    def test_round_trip_keeps_null_identifiers_for_non_sample(self, make_file_state):
        state = make_file_state(file_kind="NON_SAMPLE")

        restored = FileUploadState.from_dict(state.to_dict())

        assert restored.project_public_id is None
        assert restored.sample_public_id is None


class TestBatchUploadState:
    def test_reset_failed_for_retry_excludes_permanent_by_default(
        self, new_multipart_file, make_batch_state
    ):
        retryable = new_multipart_file()
        retryable.mark_failed("FAIL_UPLOAD_RETRYABLE", "net", retryable=True)
        permanent = new_multipart_file()
        permanent.mark_failed("FAIL_UPLOAD", "signature", retryable=False)
        state = make_batch_state([retryable, permanent])

        state.reset_failed_for_retry(include_permanent=False)

        assert retryable.status == FileUploadStatus.PENDING
        assert permanent.status == FileUploadStatus.FAILED

    def test_retrying_a_file_discards_confirmed_meta_json(
        self, new_multipart_file, make_batch_state
    ):
        failed = new_multipart_file()
        failed.mark_failed("FAIL_UPLOAD_RETRYABLE", "net", retryable=True)
        state = make_batch_state([failed])
        state.meta_json = {"batch": {"status": "FAILED"}}

        state.reset_failed_for_retry(include_permanent=False)

        assert state.meta_json is None

    def test_meta_json_is_kept_when_nothing_is_retried(
        self, new_multipart_file, make_batch_state
    ):
        permanent = new_multipart_file()
        permanent.mark_failed("FAIL_UPLOAD", "signature", retryable=False)
        state = make_batch_state([permanent])
        state.meta_json = {"batch": {"status": "FAILED"}}

        state.reset_failed_for_retry(include_permanent=False)

        assert state.meta_json == {"batch": {"status": "FAILED"}}

    def test_reset_failed_for_retry_includes_permanent_on_demand(
        self, new_multipart_file, make_batch_state
    ):
        permanent = new_multipart_file()
        permanent.mark_failed("FAIL_UPLOAD", "signature", retryable=False)
        state = make_batch_state([permanent])

        state.reset_failed_for_retry(include_permanent=True)

        assert permanent.status == FileUploadStatus.PENDING

    def test_round_trip_keeps_confirmed_meta_json(
        self, new_multipart_file, make_batch_state
    ):
        file = new_multipart_file()
        file.record_part(1, '"etag1"')
        state = make_batch_state([file])
        state.mark_requested()
        state.meta_json = {"batch": {"status": "SUCCESS"}, "samples": []}

        restored = BatchUploadState.from_dict(state.to_dict())

        assert restored == state

    def test_mark_requested_keeps_first_timestamp(self, make_batch_state):
        state = make_batch_state([])
        state.mark_requested()
        first = state.requested_at

        state.mark_requested()

        assert state.requested_at == first
