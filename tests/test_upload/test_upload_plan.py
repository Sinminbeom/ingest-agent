from datetime import datetime, timedelta, timezone

from upload.upload_plan import UploadFilePlan, UploadMode, UploadPlan


def _api_dict(
    expires_at: str = "2099-01-01T00:00:00Z", token: str = "status-token"
) -> dict:
    # 서버는 방식에 없는 필드도 null·빈 값으로 내려준다.
    return {
        "expiresAt": expires_at,
        "metaJsonUrl": "https://s3.test/meta.json?sig",
        "statusToken": token,
        "files": [
            {
                "detailFilePublicId": "df-1",
                "key": "tenant_public_id=t/source=s/batch_public_id=b/small.txt",
                "mode": "SINGLE",
                "checksumAlgorithm": None,
                "url": "https://s3.test/small?sig",
                "headers": {"x-amz-checksum-sha256": "sha"},
                "uploadId": None,
                "partSize": None,
                "parts": [],
                "completeUrl": None,
                "completeHeaders": {},
                "abortUrl": None,
                "listPartsUrl": None,
            },
            {
                "detailFilePublicId": "df-2",
                "key": "tenant_public_id=t/source=s/batch_public_id=b/big.raw",
                "mode": "MULTIPART",
                "checksumAlgorithm": "CRC64NVME",
                "url": None,
                "headers": {},
                "uploadId": "upload-1",
                "partSize": 10,
                "parts": [
                    {
                        "partNumber": 1,
                        "url": "https://s3.test/big?partNumber=1",
                        "headers": {"x-amz-checksum-crc64nvme": "p1"},
                    },
                    {
                        "partNumber": 2,
                        "url": "https://s3.test/big?partNumber=2",
                        "headers": {"x-amz-checksum-crc64nvme": "p2"},
                    },
                ],
                "completeUrl": "https://s3.test/big?complete",
                "completeHeaders": {
                    "x-amz-checksum-crc64nvme": "full",
                    "x-amz-checksum-type": "FULL_OBJECT",
                    "x-amz-mp-object-size": "15",
                },
                "abortUrl": "https://s3.test/big?abort",
                "listPartsUrl": "https://s3.test/big?list",
            },
        ],
    }


class TestUploadPlan:
    def test_from_api_dict_reads_headers(self):
        plan = UploadPlan.from_api_dict(_api_dict())

        single, multipart = plan.files
        assert single.mode == UploadMode.SINGLE
        assert single.headers == {"x-amz-checksum-sha256": "sha"}
        assert single.complete_headers == {}
        assert multipart.mode == UploadMode.MULTIPART
        assert multipart.checksum_algorithm == "CRC64NVME"
        assert multipart.part(2).headers == {"x-amz-checksum-crc64nvme": "p2"}
        assert multipart.complete_headers["x-amz-mp-object-size"] == "15"

    def test_is_expired(self):
        plan = UploadPlan.from_api_dict(_api_dict())

        assert not plan.is_expired()

        now = datetime(2099, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        assert plan.is_expired(now=now)

    def test_is_expired_with_offset_format(self):
        expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        plan = UploadPlan(
            expires_at=expires, meta_json_url="u", status_token="t", files=[]
        )

        assert plan.is_expired()


class TestUploadPlanMerge:
    def test_merge_keeps_all_files_and_earliest_expiry_credentials(self):
        later = UploadPlan.from_api_dict(_api_dict("2099-01-02T00:00:00Z", "late"))
        earlier = UploadPlan.from_api_dict(_api_dict("2099-01-01T00:00:00Z", "early"))

        merged = UploadPlan.merge([later, earlier])

        assert merged.expires_at == "2099-01-01T00:00:00Z"
        assert merged.status_token == "early"
        assert len(merged.files) == 4


class TestUploadFilePlanRoundTrip:
    def test_to_dict_from_dict(self):
        original = UploadPlan.from_api_dict(_api_dict()).files[1]

        restored = UploadFilePlan.from_dict(original.to_dict())

        assert restored == original
