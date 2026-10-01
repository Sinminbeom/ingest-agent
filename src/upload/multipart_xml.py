from __future__ import annotations

import xml.etree.ElementTree as ET


class MultipartXml:
    """S3 멀티파트 XML 페이로드 조립·해석.

    boto3 고수준 API를 쓰지 않으므로 SDK가 감춰주던 XML을 직접 다룬다.
    S3 응답의 네임스페이스 유무가 일정하지 않아 로컬 이름으로만 매칭한다.
    """

    S3_XMLNS = "http://s3.amazonaws.com/doc/2006-03-01/"

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @classmethod
    def build_complete(cls, completed_etags: dict[int, str]) -> bytes:
        """CompleteMultipartUpload 요청 바디.

        모든 파트의 번호와 ETag가 빠짐없이, 파트 번호 오름차순으로 들어가야 한다.
        """
        root = ET.Element("CompleteMultipartUpload", xmlns=cls.S3_XMLNS)
        for part_number in sorted(completed_etags):
            part = ET.SubElement(root, "Part")
            ET.SubElement(part, "PartNumber").text = str(part_number)
            ET.SubElement(part, "ETag").text = completed_etags[part_number]
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @classmethod
    def parse_list_parts(cls, xml_body: bytes | str) -> dict[int, str]:
        """ListParts 응답에서 partNumber -> ETag 매핑을 뽑는다."""
        root = ET.fromstring(xml_body)
        etags: dict[int, str] = {}
        for element in root.iter():
            if cls._local_name(element.tag) != "Part":
                continue
            part_number: int | None = None
            etag: str | None = None
            for child in element:
                name = cls._local_name(child.tag)
                if name == "PartNumber":
                    part_number = int(child.text or 0)
                elif name == "ETag":
                    etag = child.text or ""
            if part_number is not None and etag:
                etags[part_number] = etag
        return etags

    @classmethod
    def parse_error_code(cls, xml_body: bytes | str) -> str | None:
        """바디가 S3 <Error>면 Code를 반환, 아니면 None.

        CompleteMultipartUpload는 HTTP 200으로도 <Error>를 내려줄 수 있어
        상태코드만으로 성공 판정을 할 수 없다.
        """
        if not xml_body:
            return None
        try:
            root = ET.fromstring(xml_body)
        except ET.ParseError:
            return None
        if cls._local_name(root.tag) != "Error":
            return None
        for child in root:
            if cls._local_name(child.tag) == "Code":
                return child.text
        return "UnknownError"
