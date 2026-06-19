; Inno Setup 스크립트 — ingest-agent 고객사 머신 인스톨러.
;
; 컴파일(저장소 루트에서, 버전은 CI가 태그로 주입):
;   iscc /DAppVersion=1.2.3 deploy\installer.iss
; 산출물: deploy\Output\ingest-agent-setup-<ver>.exe
;
; 전제: deploy\ingest-agent.spec 빌드 산출물(dist\ingest-agent\)에
;   ingest-agent.exe, updater.exe, ingest-agent-service.exe(WinSW),
;   ingest-agent-service.xml 가 모두 들어있어야 한다 (CI가 준비).
;
; 동작:
;   - {app} 에 실행 파일 배치, {app}\conf 에 설정(최초 1회만, 갱신 시 보존)
;   - WinSW 서비스 등록/시작 (부팅 자동시작 + 크래시 재시작)
;   - updater.exe 를 1시간 주기 작업 스케줄러로 등록
;   - silent 재실행(self-update) 시 서비스 stop -> 교체 -> start

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3B1E2A-7C4D-4E5F-9A1B-INGESTAGENT01}
AppName=Ingest Agent
AppVersion={#AppVersion}
AppPublisher=Ingest Agent
DefaultDirName={autopf}\IngestAgent
DefaultGroupName=Ingest Agent
DisableProgramGroupPage=yes
PrivilegesRequired=admin
; 64비트 앱(win_amd64) → 64비트 설치 모드. {autopf}가 Program Files(64-bit)로 해석됨.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=ingest-agent-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
; SignTool=signtool $f   ; TODO: Authenticode 인증서 확보 후 활성화

[Files]
; PyInstaller onedir 산출물 + WinSW + updater (CI가 dist\ingest-agent 에 모아둠)
Source: "..\dist\ingest-agent\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; 설정 파일: 최초 설치 시에만 배치하고, 업데이트 시 고객 수정본을 보존한다.
Source: "..\conf\*"; DestDir: "{app}\conf"; Flags: onlyifdoesntexist recursesubdirs

[Dirs]
Name: "{app}\logs"

[Code]
const
  SERVICE_NAME = 'ingest-agent';
  TASK_NAME = 'IngestAgentUpdater';

function ServiceExe: String;
begin
  Result := ExpandConstant('{app}\ingest-agent-service.exe');
end;

procedure Run(const Exe, Params: String);
var
  rc: Integer;
begin
  Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, rc);
end;

procedure RunCmd(const Params: String);
begin
  Run(ExpandConstant('{cmd}'), '/C ' + Params);
end;

// 기존 서비스 중지/제거 (업데이트 시 파일 잠금 해제). 없으면 무시.
// sc stop은 비동기라 프로세스가 즉시 죽지 않는다 → exe 파일이 잠긴 채 파일 복사로
// 넘어가면 DeleteFile code 5(액세스 거부)가 난다. 그래서 graceful stop 후
// wrapper(+자식 서버)를 강제 종료하고 핸들 해제를 기다린 뒤 등록을 제거한다.
procedure StopAndRemoveService;
begin
  RunCmd('sc.exe stop ' + SERVICE_NAME);              // graceful stop 시도(비동기)
  RunCmd('taskkill /F /T /IM ingest-agent-service.exe'); // wrapper + 자식 트리 강제 종료
  RunCmd('taskkill /F /IM ingest-agent.exe');            // 혹시 남은 서버 프로세스
  Sleep(3000);                                        // 파일 핸들 해제 대기
  if FileExists(ServiceExe) then
    Run(ServiceExe, 'uninstall');                     // 서비스 등록 제거
end;

procedure WriteVersionFile;
begin
  SaveStringToFile(ExpandConstant('{app}\VERSION'), '{#AppVersion}', False);
end;

// 적용할 APP_ENV(dev|prd) 결정.
//   1) /env=<dev|prd> 인자가 있으면 그 값
//   2) 없으면 기존 {app}\app.env (self-update silent 재실행 시 선택 보존)
//   3) 둘 다 없으면 prd (고객사 배포 기본값. 내부 테스트는 /env=dev 로 명시)
function ResolveAppEnv: String;
var
  envParam: String;
  saved: AnsiString;
  savedStr: String;
begin
  envParam := Lowercase(Trim(ExpandConstant('{param:env|}')));
  if (envParam = 'dev') or (envParam = 'prd') then
  begin
    Result := envParam;
    Exit;
  end;
  if LoadStringFromFile(ExpandConstant('{app}\app.env'), saved) then
  begin
    savedStr := Lowercase(Trim(String(saved)));
    if (savedStr = 'dev') or (savedStr = 'prd') then
    begin
      Result := savedStr;
      Exit;
    end;
  end;
  Result := 'prd';
end;

// 선택한 APP_ENV를 app.env에 저장하고, WinSW xml의 __APP_ENV__ 를 치환한다.
// (xml은 매 설치 시 번들에서 덮어써지므로 placeholder가 복원되어 재치환됨)
procedure ApplyAppEnv;
var
  appEnv: String;
  xmlPath: String;
  xmlRaw: AnsiString;
  xml: String;
begin
  appEnv := ResolveAppEnv;
  SaveStringToFile(ExpandConstant('{app}\app.env'), appEnv, False);
  xmlPath := ExpandConstant('{app}\ingest-agent-service.xml');
  if LoadStringFromFile(xmlPath, xmlRaw) then
  begin
    xml := String(xmlRaw);
    StringChangeEx(xml, '__APP_ENV__', appEnv, True);
    SaveStringToFile(xmlPath, AnsiString(xml), False);
  end;
end;

procedure InstallAndStartService;
begin
  Run(ServiceExe, 'install');
  Run(ServiceExe, 'start');
end;

procedure RegisterUpdaterTask;
begin
  RunCmd('schtasks /Create /TN "' + TASK_NAME + '" /TR "\"' +
    ExpandConstant('{app}\updater.exe') + '\"" /SC HOURLY /RU SYSTEM /RL HIGHEST /F');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopAndRemoveService;  // 파일 복사 전 잠금 해제
  if CurStep = ssPostInstall then
  begin
    WriteVersionFile;
    ApplyAppEnv;  // 서비스 설치 전에 xml의 APP_ENV 치환
    InstallAndStartService;
    RegisterUpdaterTask;
    // 방화벽 인바운드 규칙은 추가하지 않는다. 기본 바인딩이 127.0.0.1(로컬 전용)이라
    // 외부 인바운드가 닿을 소켓이 없다. 외부 호출이 필요하면 INGEST_HOST를 0.0.0.0으로
    // 바꾸고 그 때 운영자가 명시적으로 방화벽 규칙을 추가한다(deploy/README.md 참고).
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RunCmd('sc.exe stop ' + SERVICE_NAME);
    if FileExists(ServiceExe) then
      Run(ServiceExe, 'uninstall');
    RunCmd('schtasks /Delete /TN "' + TASK_NAME + '" /F');
    // 구버전이 추가했을 수 있는 방화벽 규칙을 정리한다(없으면 무시됨).
    RunCmd('netsh advfirewall firewall delete rule name="IngestAgent"');
  end;
end;
