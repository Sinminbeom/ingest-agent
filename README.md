# ingest-agent

실험실 PC에서 실행되는 데이터 수집 에이전트. 서버로부터 배치 파일 목록을 조회하고, STS 임시 자격증명으로 S3에 직접 업로드한다.

## 개발 환경 설정

```bash
# 패키지 설치
uv sync
```

oncx-core는 `libs/` 디렉토리의 로컬 wheel로 관리된다 (`libs/oncx_core-*.whl`).

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `APP_ENV` | `dev` | 실행 환경 (`dev` / `prd`) |

환경별 설정은 `conf/application.conf`의 `[DEV]` / `[PRD]` 섹션에서 관리한다.

## 프로젝트 실행

```bash
# 서버 실행
uv run uvicorn main:app --reload --app-dir src --port 33000

# 윈도우 더블클릭 실행
deploy\run.bat

# 윈도우 프로세스 kill (fastapi 포트 점유 시)
netstat -ano | findstr :33000
taskkill /F /PID <PID>
```

## API

`POST /api/v1/ingest/batch/{batch_public_id}`

요청 body에 STS 임시 자격증명을 포함해야 한다.

```json
{
  "sts": {
    "access_key": "...",
    "secret_key": "...",
    "session_token": "..."
  }
}
```

## 배포 전 체크

```bash
uv run ruff format .         # 포맷팅
uv run ruff check . --fix    # 린팅 및 자동 수정
uv run pyright               # 타입 체킹
```
