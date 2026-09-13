# 레이아웃 이행의 Windows 11 실환경 검증 — 5축.
#
# `platform_smoke.py` 는 happy path 만 본다. 이행에서 실제로 위험한 것은 **실패 경로**다 —
# 조상이 프로젝트 밖을 가리킬 때, 전환에 실패했을 때, 전환 뒤 정리가 덜 끝났을 때.
# 그 셋은 실패를 주입해야 드러나므로 여기서 따로 만든다.
#
# POSIX 에서는 symlink 로 같은 축을 회귀에 넣었다. Windows 는 **junction 을 써야 한다** —
# reparse point 는 symlink 와 다른 객체이고, 이 제품이 별도 backend 를 가진 이유가 그것이다.
#
# **이 파일은 UTF-8 BOM 으로 저장한다.** Windows PowerShell 5.1 은 BOM 없는 UTF-8 을 ANSI 로
# 읽어 한글 주석이 토큰을 깨뜨린다 — 파서가 멀쩡한 `}` 를 "예기치 않은 토큰" 이라고 낸다.
# Windows 가 실제로 싣고 있는 셸에서 못 도는 검증 스크립트는 검증 스크립트가 아니다.
#
# 사용:
#   git clone <bundle> D:\dev\SAGE-verify
#   ssh win11 "powershell -NoProfile -ExecutionPolicy Bypass -File D:\dev\SAGE-verify\scripts\ci\windows_migration_verify.ps1 -Repo D:\dev\SAGE-verify -Python D:\dev\venvs\sage312\Scripts\python.exe"

param(
  [Parameter(Mandatory=$true)][string]$Repo,
  [Parameter(Mandatory=$true)][string]$Python,
  [string]$Work = "D:\dev\.migration-verify"
)

chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$script:Pass = 0
$script:Fail = 0

function Report($name, $ok, $detail) {
  if ($ok) { $script:Pass++; Write-Output "   OK   $name" }
  else     { $script:Fail++; Write-Output "   FAIL $name — $detail" }
}

function Fresh($dest) {
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  & $Python -m sage install --host claude --dest $dest 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "install 실패: $dest" }
}

function ToLegacy($dest) {
  # 1.0 이 배치한 모양으로 되돌린다.
  New-Item -ItemType Directory -Force -Path "$dest\scripts\sage_harness" | Out-Null
  Move-Item "$dest\sage_harness\hooks"  "$dest\scripts\sage_harness\hooks"
  Move-Item "$dest\sage_harness\schema" "$dest\schema"
  Move-Item "$dest\sage_harness\verify-changes.sh" "$dest\scripts\verify-changes.sh"
  Remove-Item "$dest\sage_harness"
  @'
project:
  name: "winverify"
  prefix: "winverify"
components:
  - { id: core, paths: ["app/core/**"] }
risk:
  l2_path_globs: ["*core/*.src"]
'@ | Out-File -Encoding utf8 "$dest\sage\project-profile.yaml"
}

function Layout($dest) {
  (& $Python "$Repo\scripts\ci\_win_probe.py" $Repo layout $dest).Trim()
}

New-Item -ItemType Directory -Force -Path $Work | Out-Null

Push-Location $Repo
Write-Output "== windows migration verify =="
Write-Output "   repo:   $Repo"
Write-Output "   python: $Python"
& $Python -c "import platform,sys; print('   host:   {} / {} / {}'.format(platform.platform(), platform.machine(), sys.version.split()[0]))"

# --- 0. backend 가 실제로 WindowsBackend 인가 -------------------------------
# 1~4 의 결과는 이 사실이 없으면 증거가 아니다. POSIX backend 로 돌았다면 같은 통과가
# 아무것도 증명하지 않는다.
$backend = (& $Python "$Repo\scripts\ci\_win_probe.py" $Repo backend $Work).Trim()
Report "backend-is-windows" ($backend -eq "windows|True") "capability=$backend"

# --- 1. junction 조상 --------------------------------------------------------
$d1 = "$Work\a1"; $outside = "$Work\outside"
if (Test-Path $d1) { Remove-Item -Recurse -Force $d1 }
if (Test-Path $outside) { Remove-Item -Recurse -Force $outside }
New-Item -ItemType Directory -Force -Path "$outside\hooks\runtime" | Out-Null
"print('프로젝트 밖')" | Out-File -Encoding utf8 "$outside\hooks\runtime\run_hook.py"
New-Item -ItemType Directory -Force -Path "$d1\scripts" | Out-Null
New-Item -ItemType Junction -Path "$d1\scripts\sage_harness" -Target $outside | Out-Null

$layout = Layout $d1
& $Python -m sage upgrade --apply --root $d1 2>&1 | Out-Null
$survived = Test-Path "$outside\hooks\runtime\run_hook.py"
Report "junction-ancestor-refused" (($layout -ne "consumer-legacy") -and $survived) `
       "layout=$layout, 밖 파일 생존=$survived"

# --- 2. sentinel 삭제 실패 ---------------------------------------------------
# 전환 자체가 실패하면 **다른 구 자산을 하나도 지우지 않아야** 한다. 계속 지우면 구 트리가
# 아직 정본인 채로 반쪽이 되고, 그 위에서 게이트가 돈다.
$d2 = "$Work\a2"
Fresh $d2; ToLegacy $d2
$sentinel = "$d2\scripts\sage_harness\hooks\runtime\run_hook.py"
$before = (Get-ChildItem "$d2\scripts\sage_harness" -Recurse -File).Count
$handle = [System.IO.File]::Open($sentinel, 'Open', 'Read', 'None')   # 삭제 불가로 잠근다
try {
  & $Python -m sage upgrade --apply --root $d2 2>&1 | Out-Null
  $code = $LASTEXITCODE
} finally { $handle.Close() }
$after = (Get-ChildItem "$d2\scripts\sage_harness" -Recurse -File).Count
# **공존이 남는 것은 설계된 동작이다.** 전환에 실패했으므로 되돌리지 않고 그대로 둔다 —
# 되돌리면 검증까지 끝난 신 트리를 버리게 된다. 중요한 것은 **어느 코드가 게이트인가** 이고,
# 그 답은 아직 구 트리여야 한다.
$core = (& $Python "$Repo\scripts\ci\_win_probe.py" $Repo core $d2).Trim()
$gateIsLegacy = $core -like "*scripts\sage_harness\hooks"
Report "sentinel-failure-removes-nothing" (($code -ne 0) -and ($before -eq $after) -and $gateIsLegacy) `
       "exit=$code, before=$before after=$after, gate=$core"

# --- 3. 정상 이행 ------------------------------------------------------------
$d3 = "$Work\a3"
Fresh $d3; ToLegacy $d3
"echo mine" | Out-File -Encoding utf8 "$d3\scripts\keep-me.sh"
& $Python -m sage upgrade --apply --root $d3 2>&1 | Out-Null
$code3 = $LASTEXITCODE
$ok3 = ($code3 -eq 0) `
  -and (Test-Path "$d3\sage_harness\hooks\runtime\run_hook.py") `
  -and (-not (Test-Path "$d3\scripts\sage_harness\hooks\runtime\run_hook.py")) `
  -and ((Get-Content "$d3\scripts\keep-me.sh" -Raw).Trim() -eq "echo mine") `
  -and ((Layout $d3) -eq "consumer")
Report "happy-path" $ok3 "exit=$code3, layout=$(Layout $d3)"

# --- 4. sentinel 제거 후 일반 파일 제거 실패 ---------------------------------
# 전환은 끝났으므로 **되돌리지 않는다.** 신 경로는 활성이고, 못 지운 파일은 보고되며,
# 다음 실행이 정리를 마친다.
$d4 = "$Work\a4"
Fresh $d4; ToLegacy $d4
$victim = "$d4\scripts\sage_harness\hooks\runtime\hook_runtime.py"
$lock = [System.IO.File]::Open($victim, 'Open', 'Read', 'None')
try {
  & $Python -m sage upgrade --apply --root $d4 2>&1 | Out-Null
} finally { $lock.Close() }
$activated = (Test-Path "$d4\sage_harness\hooks\runtime\run_hook.py") `
             -and (-not (Test-Path "$d4\scripts\sage_harness\hooks\runtime\run_hook.py"))
& $Python -m sage upgrade --apply --root $d4 2>&1 | Out-Null
$cleaned = -not (Test-Path $victim)
Report "leftover-converges-on-rerun" ($activated -and $cleaned) `
       "활성화=$activated, 재실행 후 정리=$cleaned"

# --- 5. 신 namespace 선점 ----------------------------------------------------
$d5 = "$Work\a5"
Fresh $d5; ToLegacy $d5
New-Item -ItemType Directory -Force -Path "$d5\sage_harness" | Out-Null
"echo USER-OWNED" | Out-File -Encoding utf8 "$d5\sage_harness\verify-changes.sh"
& $Python -m sage upgrade --apply --root $d5 2>&1 | Out-Null
$code5 = $LASTEXITCODE
$kept = (Get-Content "$d5\sage_harness\verify-changes.sh" -Raw).Trim() -eq "echo USER-OWNED"
Report "namespace-squat-blocked" (($code5 -ne 0) -and $kept) "exit=$code5, 사용자 파일 보존=$kept"

Pop-Location
Write-Output ""
Write-Output "통과 $script:Pass / 실패 $script:Fail"
if ($script:Fail -gt 0) { exit 1 }
exit 0
