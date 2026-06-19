"""런타임 agent 버전 출처.

버전의 단일 authoring source는 `pyproject.toml`의 `[project].version` 이다.
다만 배포본(PyInstaller 번들)에는 `pyproject.toml`이 포함되지 않으므로, 인스톨러가
설치 시 기록하는 `VERSION` 파일(updater가 읽는 것과 동일)에서 버전을 읽는다.

탐색 순서 (모두 CWD 기준 — run_server가 CWD를 설치 폴더로 고정한다):

1. ``./VERSION`` — 배포 환경. 인스톨러가 git 태그(``vX.Y.Z``)를 그대로 기록하므로
   앞의 ``v`` 를 떼어 SemVer로 정규화한다. (파일 자체는 updater의 태그 비교를 위해
   ``vX.Y.Z`` 형식을 유지하므로 여기서만 정규화한다.)
2. ``./pyproject.toml`` — 개발 환경(설치 안 한 상태, VERSION 부재).
3. 둘 다 없으면 ``UNKNOWN_VERSION``.
"""

import tomllib

UNKNOWN_VERSION = "0.0.0+unknown"


def _normalize(raw: str) -> str:
    """``vX.Y.Z`` → ``X.Y.Z``. 앞의 ``v`` 접두사만 제거한다."""
    raw = raw.strip()
    return raw[1:] if raw[:1] == "v" else raw


def resolve_version() -> str:
    """현재 실행 중인 agent 버전을 반환한다. 위 탐색 순서를 따른다."""
    try:
        with open("./VERSION", encoding="utf-8") as f:
            version = _normalize(f.read())
            if version:
                return version
    except OSError:
        pass

    try:
        with open("./pyproject.toml", "rb") as f:
            version = str(tomllib.load(f)["project"]["version"]).strip()
            if version:
                return version
    except (OSError, KeyError):
        pass

    return UNKNOWN_VERSION
