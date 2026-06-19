# PyInstaller spec — ingest-agent 서버를 onedir로 번들한다.
#
# 빌드(저장소 루트에서):
#   uv run pyinstaller deploy/ingest-agent.spec
# 산출물: dist/ingest-agent/  (ingest-agent.exe + 의존성)
#
# conf/ 는 환경별로 수정되어야 하므로 번들에 넣지 않고 인스톨러(Inno)가 외부
# 파일로 배치한다. updater.exe 는 CI에서 별도 빌드해 같은 폴더로 복사한다.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# src-layout 모듈을 import string 없이 따라가도록 명시한다.
_src_packages = [
    "api",
    "app",
    "aws",
    "config",
    "domain",
    "exceptions",
    "job",
    "job_container",
    "meta",
    "response",
    "schemas",
    "security",
    "utils",
]

hiddenimports = ["main"]
for _pkg in _src_packages:
    hiddenimports += collect_submodules(_pkg)
hiddenimports += collect_submodules("oncx_core")

# uvicorn은 프로토콜/루프 구현을 런타임에 동적 import 한다.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

# boto3/botocore는 endpoints.json 등 데이터 파일을 런타임에 읽는다.
datas = collect_data_files("botocore") + collect_data_files("boto3")

a = Analysis(
    ["run_server.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff", "pyright"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ingest-agent",
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ingest-agent",
)
