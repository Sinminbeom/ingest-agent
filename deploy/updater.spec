# PyInstaller spec — self-update updater를 onefile로 번들한다.
#
# 빌드(저장소 루트에서):
#   uv run pyinstaller --distpath dist/_updater deploy/updater.spec
# 산출물: dist/_updater/updater.exe  (CI가 dist/ingest-agent/로 복사)
#
# updater.py는 oncx-core AppLogger(로깅)와 표준 라이브러리만 사용한다.
# oncx_core는 동적 import를 대비해 명시적으로 수집한다.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("oncx_core")

a = Analysis(
    ["updater.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff", "pyright"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# COLLECT 없이 EXE에 binaries/datas를 포함 → onefile
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="updater",
    console=True,
    disable_windowed_traceback=False,
)
