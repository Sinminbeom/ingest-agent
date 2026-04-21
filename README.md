# ingest-agent

실험 데이터 배치 파일을 AWS S3로 업로드하고 후속 워크플로우를 트리거하는 FastAPI 기반 마이크로서비스.

## 개요

- 배치 단위 파일 업로드 관리 및 상태 추적
- 멀티스레드 Job Queue로 파일 병렬 처리
- 메타데이터 스키마 검증 및 `metadata.json` 생성
- PostgreSQL로 배치/파일 상태 관리
- AWS Step Functions로 다운스트림 워크플로우 실행

## 기술 스택

| 항목 | 내용 |
|------|------|
| Framework | FastAPI + Uvicorn |
| Database | PostgreSQL (psycopg) |
| Storage | AWS S3 |
| Auth | AWS Cognito (JWT RS256) |
| AWS | boto3 (Secrets Manager, Step Functions) |
| 패키지 관리 | uv |

## 프로젝트 구조

```
ingest-agent/
├── src/
│   ├── main.py
│   ├── api/v1/endpoints/    # FastAPI 라우터
│   ├── agent/               # IngestAgent, Job 처리 파이프라인
│   ├── container/           # 요청/샘플 상태 컨테이너
│   ├── job/                 # UploadJob, RequestJob, CompleteJob
│   └── ...
├── tests/
├── conf/
│   └── application.conf     # 환경별 설정
├── libs/
│   └── python_library-2.2.7-py3-none-any.whl
└── pyproject.toml
```

## API

| Method | Path | 설명 |
|--------|------|------|
| POST | `/ingest-agent/v1/ingest/batch/{batch_public_id}` | 배치 인제스트 요청 (HTTP 202 반환) |
| GET | `/ingest-agent/health` | 헬스 체크 |

## 설정

`conf/application.conf`에서 환경별 설정 관리. `APP_ENV` 환경변수로 `DEV` / `PRD` 구분.

```ini
[COMMON]
PROJECT_NAME = ingest-agent
PROJECT_VERSION = 0.1.0
THREAD_COUNT = 3
META_SCHEMA_URL = <메타데이터 스키마 URL>
REGION_NAME = ap-northeast-2
S3_BASE_PATH = ingest-agent

[ACQUISITION]
SOFTWARE_NAME = <소프트웨어명>
SOFTWARE_VERSION = <버전>
MODE_CODE = <모드코드>
MODE_URL = <모드 URL>

[DEV]
COGNITO_USER_POOL_ID = <Cognito User Pool ID>
AWS_DB_SECRET_ID = <DB Secret ARN>
DB_SSM_TUNNEL_PORT = <포트>
S3_BUCKET = <S3 버킷명>
STATE_MACHINE_ARN = <Step Functions ARN>

[PRD]
COGNITO_USER_POOL_ID = <Cognito User Pool ID>
AWS_DB_SECRET_ID = <DB Secret ARN>
DB_SSM_TUNNEL_PORT = <포트>
S3_BUCKET = <S3 버킷명>
STATE_MACHINE_ARN = <Step Functions ARN>
```

## 개발 환경 설정

```bash
# 의존성 설치
uv sync

# 코드 품질 검사
uv run ruff format .
uv run ruff check . --fix
uv run pyright

# 테스트
uv run pytest
```

## 실행

```bash
# 개발 서버 (hot reload)
uvicorn src.main:app --reload

# 프로세스 종료 (Windows - 포트가 안 풀릴 때)
netstat -ano | findstr :8000
taskkill /F /PID <PID>
```

## 배포 전 체크리스트

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```
