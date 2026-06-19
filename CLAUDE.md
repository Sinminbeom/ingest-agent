# CLAUDE.md

## 버전 관리

세션 종료 시 커밋 전에 반드시 아래 순서로 진행한다.

1. `pyproject.toml`의 version 필드 업 (SemVer 기준)
2. `uv lock` 실행
3. `pyproject.toml`, `uv.lock` 함께 커밋

## 릴리스 (태그 배포)

PR 머지 후 고객사 배포가 필요하면 아래 순서로 진행한다.

1. `main`을 최신화한다 (`git checkout main && git pull`).
2. `pyproject.toml`의 version과 **일치하는** 태그를 생성·push한다
   (`git tag v<version> && git push origin v<version>`).
3. 태그 push가 `release` 워크플로를 트리거한다 — 인스톨러 빌드 → GitHub Release
   게시 → 고객사 updater가 polling하여 자동 설치.

주의:

- 태그(`vX.Y.Z`)는 `pyproject.toml`의 version과 반드시 일치해야 한다. 불일치 시
  CI(`Verify tag matches pyproject version`)가 릴리스를 차단한다.
- 태그 push는 고객사 자동 업데이트를 유발하는 **되돌리기 어려운 작업**이다. 배포
  의도가 확실할 때만 수행하고, 사람의 확인을 받는다.
