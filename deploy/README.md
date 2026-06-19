# 배포 (외부 고객사 머신)

외부 고객사/협력기관의 Windows 머신에 `ingest-agent`를 **단일 인스톨러**로 설치하고,
**Windows 서비스**로 운영하며, **self-update**로 자동 갱신한다. 고객 머신에는
Python/uv를 설치하지 않으며, **자동 업데이트용 자격증명(토큰)도 두지 않는다.**

릴리스 아티팩트는 소스 repo가 아니라 **비공개 S3 버킷**에 올리고, **CloudFront(OAC)**
로 공개 HTTPS 배포한다. 고객 머신은 CloudFront URL에서 평문 HTTPS로만 받으므로
머신에 자격증명이 필요 없다(소스는 S3에 없으므로 노출되지 않는다).

## 구성 요소

| 파일 | 역할 |
|------|------|
| [run_server.py](run_server.py) | PyInstaller 진입점. uvicorn으로 `main:app` 실행 |
| [ingest-agent.spec](ingest-agent.spec) | 서버를 onedir로 번들하는 PyInstaller spec |
| [updater.py](updater.py) | 분리된 updater. CloudFront의 `latest.json` polling → 인스톨러 다운로드 → silent 실행 |
| [winsw/ingest-agent-service.xml](winsw/ingest-agent-service.xml) | WinSW 서비스 정의 (자동시작/재시작) |
| [installer.iss](installer.iss) | Inno Setup. 파일배치 + 서비스등록 + 작업스케줄러 + 방화벽 |
| [../.github/workflows/release.yml](../.github/workflows/release.yml) | 태그 push → 빌드 → 인스톨러 → **S3 업로드 + `latest.json` 갱신** |

## 배포 인프라 (aws-iac에서 관리)

| 환경 | S3 (비공개) | 배포 채널 |
|------|-------------|-----------|
| dev | `s3://oncx-dev-common-assets-bucket/ingest-agent/` | CloudFront(OAC) 공개 HTTPS |
| prd | `s3://oncx-prd-common-assets-bucket/ingest-agent/` | CloudFront(OAC) 공개 HTTPS |

- 버킷은 **비공개**(퍼블릭 액세스 차단) 유지. **CloudFront만 OAC로 `ingest-agent/*` 경로**를 읽어 공개 HTTPS로 서빙한다.
- 버킷·CloudFront(OAC, 경로 한정)·CI 업로드용 OIDC 역할은 **aws-iac**에서 관리한다 (이 repo 아님).
- 객체 구성:
  - `ingest-agent/ingest-agent-setup-<ver>.exe` — 인스톨러
  - `ingest-agent/latest.json` — 최신 버전 메타데이터
- CloudFront 도메인은 인프라 생성 후 [conf/application.conf](../conf/application.conf)의
  `[DEV]`/`[PRD]` `UPDATE_BASE_URL` 에 채운다.

### `latest.json` 포맷

```json
{
  "version": "v0.4.0",
  "file": "ingest-agent-setup-v0.4.0.exe",
  "sha256": "<인스톨러 sha256 hex>"
}
```

## 릴리스 흐름

```
v1.2.3 태그 push
  → Actions(windows): PyInstaller 빌드 → Inno Setup 인스톨러
     → S3(oncx-<env>-common-assets-bucket/ingest-agent/) 업로드 (dev/prd)
     → latest.json 갱신
  → 고객 머신 updater(작업 스케줄러, 1시간 주기):
     CloudFront의 latest.json polling → 설치된 VERSION과 비교
     → 새 버전이면 CloudFront에서 인스톨러 다운로드(공개 HTTPS, 자격증명 없음)
     → sha256 검증 → silent 실행
     → 인스톨러가 서비스 stop → 파일 교체 → 서비스 start
```

배포는 태그를 푸시하면 된다 (태그는 `pyproject.toml` version과 일치해야 함):

```bash
git tag v1.2.3 && git push origin v1.2.3
```

## 고객 머신 최초 설치

1. 빌드된 `ingest-agent-setup-<ver>.exe` 를 고객에게 전달한다(이메일 등). 최초 설치는 수동이다.
2. 관리자 권한으로 실행한다. **토큰 인자는 필요 없다**(자동 업데이트는 CloudFront 공개 URL에서 받음).

   ```
   ingest-agent-setup-v1.2.3.exe /env=prd
   ```

### 환경 선택 (`/env`)

서비스가 사용할 환경(`conf/application.conf`의 `[DEV]`/`[PRD]` 섹션)을 설치 시 고른다.

| 인자 | 환경 | 비고 |
|------|------|------|
| (미입력) | **prd** | 고객사 배포 **기본값** |
| `/env=prd` | prd | 운영 |
| `/env=dev` | dev | 내부 테스트 |

- 선택값은 `{설치폴더}\app.env` 에 저장되고 WinSW 서비스의 `APP_ENV` 로 주입된다.
- updater는 이 환경에 해당하는 CloudFront 채널(`UPDATE_BASE_URL`)에서 갱신을 받는다.
- self-update(silent) 재실행 시 `/env` 인자가 없으면 기존 선택을 보존한다.

설치 후 상태:

- 서비스 `ingest-agent` 가 자동 시작 (부팅 시 자동, 크래시 시 재시작), 선택한 `APP_ENV` 로 실행
- 작업 스케줄러 `IngestAgentUpdater` 가 1시간마다 갱신 확인
- 설정은 `{설치폴더}\conf\application.conf` — **업데이트 시 덮어쓰지 않음**(고객 수정본 보존)

### 로그 위치 (장애 추적)

- 서버: `{설치폴더}\logs\` (WinSW 출력 + `ingest-agent.log`)
- 자동 업데이트: `{설치폴더}\logs\updater.log` — updater 실행 내역·실패 사유(네트워크/다운로드/체크섬 등)가 traceback째 기록됨. 고객 머신에서 갱신이 안 될 때 여기부터 확인한다.

## 로컬 빌드 (검증용)

Windows에서:

```bash
uv sync --group build
uv run pyinstaller deploy/ingest-agent.spec
# dist/ingest-agent/ingest-agent.exe 실행 확인
```

> ⚠️ PyInstaller 번들은 동적 import(uvicorn/boto3/pydantic/oncx-core)에 민감하다.
> 최초 빌드 후 반드시 `ingest-agent.exe` 를 실제 실행해 기동·헬스체크
> (`/ingest-agent/health`)까지 확인할 것. 누락 모듈이 있으면 spec의
> `hiddenimports` 에 추가한다.

## 남은 작업 / 주의

- **선행 인프라 (aws-iac)**: ① `ingest-agent/` prefix 쓰기 권한을 가진 CI용 OIDC 역할
  (dev/prd), ② CloudFront(OAC, `ingest-agent/*` 한정) 공개 배포. release.yml의 역할 ARN과
  conf의 `UPDATE_BASE_URL` 은 인프라 생성 후 실제 값으로 교체한다.
- **코드 서명(Authenticode)**: 미적용. 인증서 확보(경영 판단) 후
  [installer.iss](installer.iss) 의 `SignTool` 과 [release.yml](../.github/workflows/release.yml)
  의 signtool 단계를 활성화한다. 미서명 시 고객 머신에서 SmartScreen 경고가 뜬다.
- **방화벽**: 기본 바인딩은 `127.0.0.1:33000`(로컬 전용)이라 인바운드 방화벽 규칙을
  추가하지 않는다. 외부에서 호출해야 하면 WinSW xml의 `INGEST_HOST` 를 `0.0.0.0` 으로
  바꾸고, 그 때 운영자가 직접 방화벽 인바운드 규칙(TCP `INGEST_PORT`)을 추가한다.
  포트는 `INGEST_PORT` 환경변수로 변경할 수 있다(기본 33000).
- **WinSW 버전**: release.yml의 `WINSW_URL` 에서 핀(현재 v2.12.0, .NET Framework 4 필요).
