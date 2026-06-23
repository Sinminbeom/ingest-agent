# CLAUDE.md

## 배포 브랜치 전략 (임시 — oncx-claude-plugin 반영 전까지)

> 운영 배포 브랜치 전략. 추후 oncx-claude-plugin(전역 rules/skills)으로 옮긴다.
> 그 전까지 본 문서가 우선한다(프로젝트 CLAUDE.md > 전역 룰).

ingest-agent는 **태그 push가 유일한 배포 트리거**다(브랜치 push로는 배포되지
않는다). 기능을 모아서 한 번에 내보내기 위해 고정 통합 브랜치 `develop`을 둔다.

흐름:

1. 이슈 생성 → feature 브랜치 생성 (`develop` 기준)
2. 구현 + 커밋 + push (배포 트리거 아님 — PR·백업 용도)
3. PR: `feat/#N/...` → **`develop`** (`main` 아님) — `gh pr create --base develop` 필수
4. 리뷰·머지 → develop 갱신 (통합만, 배포 없음)
5. 릴리스 시 PR: `develop` → `main` — 이 PR에 `close #N`을 몰아서 기재
   (default 브랜치가 main이므로 auto-close 동작) → 머지 후 버전 일치 태그 push로
   **고객사 자동 업데이트 1회** (아래 "릴리스" 참조)

- GitHub default 브랜치: `main` (`gh pr create` 기본 base가 main이므로 feature PR은
  반드시 `--base develop`를 명시).

## 버전 관리

버전의 단일 authoring source는 `pyproject.toml`의 `[project].version`이다
(`src/config/version.py`가 런타임에 여기서 읽는다 — 별도 코드 상수 없음).
SemVer 단조 증가를 지키고 **되돌리지 않는다**(과거 태그와 충돌).

배포 브랜치 전략에 따라 **버전 범프는 feature 브랜치가 아니라 릴리스 시점
(`develop` → `main` 직전)에 `develop`에서 1회만** 수행한다(여러 기능이 모일 때
버전 파일 충돌 방지).

릴리스 시점에 `develop`에서 범프할 때 순서:

1. `pyproject.toml`의 version 필드 업 (SemVer 기준)
2. `uv lock` 실행
3. `pyproject.toml`, `uv.lock` 함께 커밋

## 릴리스 (태그 배포)

`develop` → `main` 머지 후 고객사 배포가 필요하면 아래 순서로 진행한다.

1. `main`을 최신화한다 (`git checkout main && git pull`).
2. `pyproject.toml`의 version과 **일치하는** 태그를 생성·push한다
   (`git tag v<version> && git push origin v<version>`).
3. 태그 push가 release 파이프라인을 트리거한다 — 인스톨러 빌드 → S3 업로드(dev/prd)
   + `latest.json` 갱신 → 고객사 updater가 CloudFront polling하여 자동 설치.
   (전체 파이프라인·인프라는 [deploy/README.md](deploy/README.md) 참조.)

주의:

- 태그(`vX.Y.Z`)는 `pyproject.toml`의 version과 반드시 일치해야 한다.
- 태그 push는 고객사 자동 업데이트를 유발하는 **되돌리기 어려운 작업**이다. 배포
  의도가 확실할 때만 수행하고, 사람의 확인을 받는다.
