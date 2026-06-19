"""분리된 self-update updater.

별도 프로세스(작업 스케줄러로 주기 실행)로 동작한다. 실행 중인 서비스 exe는
자기 자신을 교체할 수 없으므로, updater가 새 인스톨러를 받아 silent로 실행하면
인스톨러가 서비스 stop -> 파일 교체 -> 서비스 start를 수행한다.

배포 채널은 비공개 S3 버킷을 CloudFront(OAC)로 공개 HTTPS 서빙한다. updater는
환경(app.env: dev/prd)에 해당하는 CloudFront base URL에서 latest.json을 받아
버전을 비교하고, 새 버전이면 인스톨러를 받아 sha256 검증 후 설치한다.
base URL은 conf/application.conf의 [DEV]/[PRD] UPDATE_BASE_URL에서 읽는다.
다운로드는 무인증 공개 HTTPS이므로 머신에 자격증명을 두지 않는다.

HTTP는 표준 라이브러리(urllib)만 사용한다. 로깅은 oncx-core의 AppLogger를
재사용해 {설치폴더}/logs/updater.log 에 기록한다(콘솔 출력도 유지).
"""

import configparser
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

from oncx_core.logger.app_logger import AppLogger


def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


_LOGGER: AppLogger | None = None
LOGGER_NAME = "updater"
LOGGING_CONF = "updater_logging.conf"  # {설치폴더}/conf/ 기준


def _setup_logging() -> AppLogger | None:
    """oncx-core AppLogger로 conf/updater_logging.conf 기반 로거를 구성한다.

    logging.conf가 ./logs/* 를 CWD 기준 상대경로로 읽으므로, 앱(run_server)과
    동일하게 작업 디렉터리를 설치 폴더로 고정한 뒤 로거를 초기화한다.
    설정 실패(파일 누락 등) 시 None을 반환해 print로 폴백한다.
    """
    try:
        os.chdir(_install_dir())  # ./conf, ./logs 상대경로 기준점
        os.makedirs("logs", exist_ok=True)
        AppLogger.set_config(os.path.join("conf", LOGGING_CONF), LOGGER_NAME)
        return AppLogger.instance()
    except Exception as exc:
        print(f"[updater] 로깅 초기화 실패, print로 폴백: {exc}", flush=True)
        return None


def _log(msg: str) -> None:
    if _LOGGER is not None:
        _LOGGER.info(msg)
    else:
        print(f"[updater] {msg}", flush=True)


def _read_app_env(install_dir: str) -> str:
    """설치 시 선택된 환경(dev/prd). 기본 prd."""
    path = os.path.join(install_dir, "app.env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            value = f.read().strip().lower()
            if value in ("dev", "prd"):
                return value
    return "prd"


def _base_url(install_dir: str) -> str:
    """현재 환경의 CloudFront base URL (conf/application.conf의 UPDATE_BASE_URL)."""
    section = "PRD" if _read_app_env(install_dir) == "prd" else "DEV"
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(os.path.join(install_dir, "conf", "application.conf"), encoding="utf-8")
    base = cfg.get(section, "UPDATE_BASE_URL", fallback="").strip()
    if not base:
        raise RuntimeError(f"UPDATE_BASE_URL이 conf [{section}]에 없습니다.")
    return base.rstrip("/")


def _http_get(url: str) -> bytes:
    """무인증 공개 HTTPS GET (CloudFront)."""
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (https only)
        return resp.read()


def _read_installed_version(install_dir: str) -> str:
    version_file = os.path.join(install_dir, "VERSION")
    if os.path.isfile(version_file):
        with open(version_file, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    install_dir = _install_dir()
    base = _base_url(install_dir)

    meta = json.loads(_http_get(f"{base}/latest.json"))
    latest = str(meta.get("version", "")).strip()
    installed = _read_installed_version(install_dir)
    _log(f"channel={base} installed={installed or '(none)'} latest={latest}")

    if not latest:
        _log("latest.json에 version이 없습니다. 종료.")
        return 1
    if latest == installed:
        _log("최신 버전입니다. 종료.")
        return 0

    file_name = str(meta.get("file", "")).strip()
    expected_sha = str(meta.get("sha256", "")).strip().lower()
    if not file_name:
        _log("latest.json에 file이 없습니다. 종료.")
        return 1

    download_dir = os.path.join(install_dir, "update")
    os.makedirs(download_dir, exist_ok=True)
    installer_path = os.path.join(download_dir, file_name)

    _log(f"다운로드: {file_name}")
    data = _http_get(f"{base}/{urllib.parse.quote(file_name)}")
    with open(installer_path, "wb") as f:
        f.write(data)

    # latest.json의 sha256으로 무결성 검증 (있으면).
    if expected_sha:
        actual = _sha256(installer_path)
        if actual.lower() != expected_sha:
            _log(f"체크섬 불일치 — 중단. expected={expected_sha} actual={actual}")
            os.remove(installer_path)
            return 1
        _log("체크섬 검증 통과.")
    else:
        _log("latest.json에 sha256 없음 — 검증 생략.")

    # silent 설치. 인스톨러가 서비스 stop -> 교체 -> start 를 수행한다.
    # updater는 인스톨러를 띄우고 바로 종료한다(자기/서비스 파일 교체와 충돌 방지).
    _log(f"인스톨러 실행: {latest}")
    subprocess.Popen(
        [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        close_fds=True,
    )
    return 0


if __name__ == "__main__":
    _LOGGER = _setup_logging()
    try:
        sys.exit(main())
    except Exception as exc:  # 스케줄러 환경 — traceback째 로그로 남기고 비정상 종료
        if _LOGGER is not None:
            _LOGGER.exception("오류로 종료", exc)
        else:
            print(f"[updater] 오류로 종료: {exc}", flush=True)
        sys.exit(1)
