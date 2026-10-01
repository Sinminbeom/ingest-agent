import xml.etree.ElementTree as ET

from upload.multipart_xml import MultipartXml


def _child_text(element: ET.Element, tag: str) -> str:
    text = element.findtext(f"{{{MultipartXml.S3_XMLNS}}}{tag}")
    assert text is not None, f"{tag} missing"
    return text


class TestBuildComplete:
    def test_contains_all_parts_in_ascending_order(self):
        xml_body = MultipartXml.build_complete(
            {3: '"etag3"', 1: '"etag1"', 2: '"etag2"'}
        )

        root = ET.fromstring(xml_body)
        assert root.tag.endswith("CompleteMultipartUpload")
        parts = list(root)
        numbers = [int(_child_text(p, "PartNumber")) for p in parts]
        etags = [_child_text(p, "ETag") for p in parts]
        assert numbers == [1, 2, 3]
        assert etags == ['"etag1"', '"etag2"', '"etag3"']


class TestParseListParts:
    def test_parses_namespaced_response(self):
        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListPartsResult xmlns="{MultipartXml.S3_XMLNS}">
  <UploadId>upload-1</UploadId>
  <Part><PartNumber>1</PartNumber><ETag>"etag1"</ETag><Size>100</Size></Part>
  <Part><PartNumber>3</PartNumber><ETag>"etag3"</ETag><Size>100</Size></Part>
</ListPartsResult>"""

        assert MultipartXml.parse_list_parts(xml_body) == {1: '"etag1"', 3: '"etag3"'}

    def test_no_parts_returns_empty(self):
        xml_body = f'<ListPartsResult xmlns="{MultipartXml.S3_XMLNS}"><UploadId>u</UploadId></ListPartsResult>'

        assert MultipartXml.parse_list_parts(xml_body) == {}


class TestParseErrorCode:
    def test_error_document_returns_code(self):
        xml_body = "<Error><Code>NoSuchUpload</Code><Message>gone</Message></Error>"

        assert MultipartXml.parse_error_code(xml_body) == "NoSuchUpload"

    def test_success_document_returns_none(self):
        xml_body = f'<CompleteMultipartUploadResult xmlns="{MultipartXml.S3_XMLNS}"><Key>k</Key></CompleteMultipartUploadResult>'

        assert MultipartXml.parse_error_code(xml_body) is None

    def test_empty_or_invalid_body_returns_none(self):
        assert MultipartXml.parse_error_code(b"") is None
        assert MultipartXml.parse_error_code("not xml at all") is None
