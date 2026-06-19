"""PyInstaller 진입점.

`uvicorn main:app` 대신 uvicorn을 프로그래매틱하게 띄운다. PyInstaller onedir로
번들될 때 콘솔/서비스 양쪽에서 동일하게 동작하도록 만든다.

main.py가 `./conf/application.conf` 등 CWD 기준 상대경로로 설정을 읽으므로,
서버 시작 전에 작업 디렉터리를 "exe가 있는 설치 폴더"로 고정한다. WinSW에서도
workingdirectory를 같은 위치로 지정한다.
"""

import os
import sys


def _install_dir() -> str:
    """conf/ 가 위치한 설치 루트.

    - frozen(PyInstaller): exe가 있는 디렉터리
    - dev: 저장소 루트 (deploy/ 의 상위)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# dev 실행 시 src-layout 모듈(main, api, app ...)을 import 가능하게 한다.
# frozen 빌드에서는 spec의 pathex로 이미 수집되어 있다.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(_install_dir(), "src"))


def main() -> None:
    import uvicorn

    os.chdir(_install_dir())  # main.py의 ./conf/... 상대경로 기준점

    # logging.conf의 TimedRotatingFileHandler가 ./logs/ingest-agent.log 를 연다.
    # 인스톨러가 logs/ 를 만들지만, 누락 시에도 기동되도록 방어적으로 보장한다.
    os.makedirs("logs", exist_ok=True)

    host = os.environ.get("INGEST_HOST", "127.0.0.1")
    port = int(os.environ.get("INGEST_PORT", "33000"))

    # import string("main:app") 대신 app 객체를 직접 전달한다.
    # (reload/multi-worker 미사용 → frozen 환경에서 import string 재진입 문제 회피)
    from main import app

    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()
