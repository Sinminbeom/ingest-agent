import httpx
import pytest

from upload.multipart_xml import MultipartXml
from upload.presigned_uploader import PresignedUploader
from upload.upload_errors import (
    ChecksumMismatchError,
    PermanentUploadError,
    RetryableUploadError,
)
from upload.upload_state import FileUploadState

PART_SIZE = 10
FILE_BODY = b"0123456789" * 2 + b"abcde"  # 25바이트 → 파트 3개 (10/10/5)


@pytest.fixture
def src_file(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(FILE_BODY)
    return str(path)


def _uploader(handler) -> PresignedUploader:
    return PresignedUploader(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )


@pytest.fixture
def single_state(src_file, make_file_state, make_single_plan) -> FileUploadState:
    return make_file_state(
        plan=make_single_plan(), src_path=src_file, size_bytes=len(FILE_BODY)
    )


@pytest.fixture
def multipart_state(src_file, make_file_state, make_multipart_plan) -> FileUploadState:
    return make_file_state(
        plan=make_multipart_plan(part_count=3, part_size=PART_SIZE),
        src_path=src_file,
        size_bytes=len(FILE_BODY),
    )


def _bad_digest() -> httpx.Response:
    return httpx.Response(400, content="<Error><Code>BadDigest</Code></Error>")


def _complete_ok() -> httpx.Response:
    return httpx.Response(
        200,
        content=f'<CompleteMultipartUploadResult xmlns="{MultipartXml.S3_XMLNS}"/>',
    )


class TestSingleUpload:
    def test_puts_whole_file(self, single_state):
        received = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received["method"] = request.method
            received["content_length"] = request.headers.get("Content-Length")
            received["sha256"] = request.headers.get("x-amz-checksum-sha256")
            received["body"] = request.read()
            return httpx.Response(200, headers={"ETag": '"etag"'})

        _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert received["method"] == "PUT"
        assert received["content_length"] == str(len(FILE_BODY))
        # 서명에 들어간 체크섬 헤더를 계획에 적힌 값 그대로 싣는다.
        assert received["sha256"] == single_state.plan.headers["x-amz-checksum-sha256"]
        assert received["body"] == FILE_BODY

    def test_bad_digest_resends_up_to_limit_then_fails(self, single_state):
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            request.read()
            attempts.append(1)
            return _bad_digest()

        with pytest.raises(ChecksumMismatchError):
            _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert len(attempts) == PresignedUploader.MAX_DIGEST_ATTEMPTS


class TestMultipartUpload:
    def test_uploads_all_parts_and_completes(self, multipart_state):
        part_bodies: dict[int, bytes] = {}
        part_crcs: dict[int, str | None] = {}
        complete_headers: dict[str, str] = {}
        complete_xml: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            if query == "complete":
                complete_headers.update(request.headers)
                complete_xml.append(request.read())
                return _complete_ok()
            part_number = int(query.split("partNumber=")[1])
            part_crcs[part_number] = request.headers.get("x-amz-checksum-crc64nvme")
            part_bodies[part_number] = request.read()
            return httpx.Response(200, headers={"ETag": f'"etag{part_number}"'})

        state = multipart_state
        saves = []
        _uploader(handler).upload_file(state, save_progress=lambda: saves.append(1))

        assert part_bodies == {
            1: FILE_BODY[0:10],
            2: FILE_BODY[10:20],
            3: FILE_BODY[20:25],
        }
        assert state.completed_etags == {1: '"etag1"', 2: '"etag2"', 3: '"etag3"'}
        assert len(saves) == 3
        # 조각마다 그 조각의 CRC 헤더, 완료 요청에는 전체 CRC 헤더를 싣는다.
        assert part_crcs == {
            n: state.plan.part(n).headers["x-amz-checksum-crc64nvme"] for n in (1, 2, 3)
        }
        for name, value in state.plan.complete_headers.items():
            assert complete_headers[name] == value
        assert complete_headers["content-type"] == "application/xml"
        # complete XML에 모든 파트의 번호·ETag가 빠짐없이 들어간다.
        assert MultipartXml.parse_list_parts(complete_xml[0]) == {
            1: '"etag1"',
            2: '"etag2"',
            3: '"etag3"',
        }

    def test_resume_merges_list_parts_and_skips_completed(self, multipart_state):
        uploaded_parts: list[int] = []
        complete_xml: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            if "list" in query:
                body = f"""<ListPartsResult xmlns="{MultipartXml.S3_XMLNS}">
                  <Part><PartNumber>1</PartNumber><ETag>"etag1"</ETag></Part>
                  <Part><PartNumber>2</PartNumber><ETag>"etag2"</ETag></Part>
                </ListPartsResult>"""
                return httpx.Response(200, content=body)
            if "complete" in query:
                complete_xml.append(request.read())
                return _complete_ok()
            part_number = int(query.split("partNumber=")[1])
            uploaded_parts.append(part_number)
            request.read()
            return httpx.Response(200, headers={"ETag": f'"etag{part_number}"'})

        state = multipart_state
        # 파트 1은 로컬 기록 보유, 파트 2는 ETag 응답 유실(기록 없음) 가정.
        state.record_part(1, '"etag1"')

        _uploader(handler).upload_file(state, save_progress=lambda: None, resume=True)

        assert uploaded_parts == [3]
        assert MultipartXml.parse_list_parts(complete_xml[0]) == {
            1: '"etag1"',
            2: '"etag2"',
            3: '"etag3"',
        }

    def test_resume_treats_no_such_upload_as_completed_when_all_parts_recorded(
        self, multipart_state
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            if "list" in request.url.query.decode():
                return httpx.Response(
                    404, content="<Error><Code>NoSuchUpload</Code></Error>"
                )
            raise AssertionError("파트 PUT/complete가 호출되면 안 된다")

        state = multipart_state
        for n in (1, 2, 3):
            state.record_part(n, f'"etag{n}"')

        _uploader(handler).upload_file(state, save_progress=lambda: None, resume=True)

    def test_complete_error_body_with_http_200_is_detected(
        self, multipart_state, monkeypatch
    ):
        monkeypatch.setattr(PresignedUploader, "MAX_ATTEMPTS", 2)
        monkeypatch.setattr(PresignedUploader, "BACKOFF_BASE_SECONDS", 0.0)

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            if "complete" in query:
                return httpx.Response(
                    200, content="<Error><Code>InternalError</Code></Error>"
                )
            part_number = int(query.split("partNumber=")[1])
            request.read()
            return httpx.Response(200, headers={"ETag": f'"etag{part_number}"'})

        with pytest.raises(RetryableUploadError):
            _uploader(handler).upload_file(multipart_state, save_progress=lambda: None)


class TestChecksumMismatch:
    def test_part_bad_digest_is_resent_with_same_expected_value(self, multipart_state):
        part2_crcs: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            request.read()
            if "complete" in query:
                return _complete_ok()
            part_number = int(query.split("partNumber=")[1])
            if part_number == 2:
                part2_crcs.append(request.headers.get("x-amz-checksum-crc64nvme"))
                if len(part2_crcs) == 1:
                    return _bad_digest()
            return httpx.Response(200, headers={"ETag": f'"etag{part_number}"'})

        state = multipart_state
        _uploader(handler).upload_file(state, save_progress=lambda: None)

        expected = state.plan.part(2).headers["x-amz-checksum-crc64nvme"]
        assert part2_crcs == [expected, expected]
        assert state.completed_etags[2] == '"etag2"'

    def test_part_bad_digest_repeated_fails_without_complete(self, multipart_state):
        completes = []
        part1_attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            request.read()
            if "complete" in query:
                completes.append(1)
                return _complete_ok()
            part1_attempts.append(1)
            return _bad_digest()

        with pytest.raises(ChecksumMismatchError):
            _uploader(handler).upload_file(multipart_state, save_progress=lambda: None)

        assert len(part1_attempts) == PresignedUploader.MAX_DIGEST_ATTEMPTS
        assert completes == []

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(400, content="<Error><Code>BadDigest</Code></Error>"),
            httpx.Response(200, content="<Error><Code>BadDigest</Code></Error>"),
        ],
        ids=["http-400", "error-in-http-200"],
    )
    def test_complete_bad_digest_fails_once(self, multipart_state, response):
        # 조각이 모두 통과해도 전체 CRC가 다르면 성공으로 처리하지 않는다.
        completes = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            request.read()
            if "complete" in query:
                completes.append(1)
                return response
            part_number = int(query.split("partNumber=")[1])
            return httpx.Response(200, headers={"ETag": f'"etag{part_number}"'})

        with pytest.raises(ChecksumMismatchError):
            _uploader(handler).upload_file(multipart_state, save_progress=lambda: None)

        assert completes == [1]


class TestRetryClassification:
    def test_retries_on_5xx_then_succeeds(self, single_state, monkeypatch):
        monkeypatch.setattr(PresignedUploader, "BACKOFF_BASE_SECONDS", 0.0)
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            request.read()
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(500, content="boom")
            return httpx.Response(200, headers={"ETag": '"etag"'})

        _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert len(attempts) == 2

    def test_4xx_is_permanent_without_retry(self, single_state):
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            request.read()
            attempts.append(1)
            return httpx.Response(
                403, content="<Error><Code>AccessDenied</Code></Error>"
            )

        with pytest.raises(PermanentUploadError):
            _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert len(attempts) == 1

    def test_error_message_keeps_s3_code_without_signing_details(self, single_state):
        # 오류 메시지는 로그와 meta.json에 남는다. 서명 계산 내용은 싣지 않는다.
        def handler(request: httpx.Request) -> httpx.Response:
            request.read()
            return httpx.Response(
                403,
                content=(
                    "<Error><Code>SignatureDoesNotMatch</Code>"
                    "<AWSAccessKeyId>AKIAEXAMPLE</AWSAccessKeyId>"
                    "<CanonicalRequest>PUT /k X-Amz-Credential=AKIAEXAMPLE</CanonicalRequest>"
                    "</Error>"
                ),
            )

        with pytest.raises(PermanentUploadError) as exc_info:
            _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert "SignatureDoesNotMatch" in str(exc_info.value)
        assert "AKIAEXAMPLE" not in str(exc_info.value)

    def test_retry_exhaustion_raises_retryable(self, single_state, monkeypatch):
        monkeypatch.setattr(PresignedUploader, "MAX_ATTEMPTS", 3)
        monkeypatch.setattr(PresignedUploader, "BACKOFF_BASE_SECONDS", 0.0)
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            request.read()
            attempts.append(1)
            return httpx.Response(503, content="slow down")

        with pytest.raises(RetryableUploadError):
            _uploader(handler).upload_file(single_state, save_progress=lambda: None)

        assert len(attempts) == 3

    def test_missing_etag_on_part_is_retried(self, multipart_state, monkeypatch):
        monkeypatch.setattr(PresignedUploader, "BACKOFF_BASE_SECONDS", 0.0)
        attempts = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.query.decode()
            request.read()
            if "complete" in query:
                return _complete_ok()
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(200)  # ETag 헤더 누락
            return httpx.Response(200, headers={"ETag": '"etag"'})

        state = multipart_state
        state.record_part(1, '"etag1"')
        state.record_part(2, '"etag2"')

        _uploader(handler).upload_file(state, save_progress=lambda: None)

        assert len(attempts) == 2
        assert state.completed_etags[3] == '"etag"'


class TestPutBytes:
    def test_sends_content_type(self):
        received = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received["content_type"] = request.headers.get("Content-Type")
            received["body"] = request.read()
            return httpx.Response(200)

        _uploader(handler).put_bytes(
            "https://s3.test/meta.json", b'{"a": 1}', "application/json"
        )

        assert received["content_type"] == "application/json"
        assert received["body"] == b'{"a": 1}'
