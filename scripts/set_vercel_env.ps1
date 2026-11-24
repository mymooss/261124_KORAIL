# Vercel 운영 환경변수(SECRET_KEY, DATABASE_URL) 설정.
# - SECRET_KEY 는 .env.production.local 에서 읽는다.
# - DATABASE_URL 은 Supabase DB 비밀번호를 직접 입력받아 transaction pooler(6543) 주소로 만든다.
# 사용: ktx-twin 폴더에서  .\scripts\set_vercel_env.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ref = 'qhhngyqxztldsehihlgp'
$poolerHost = 'aws-0-ap-northeast-2.pooler.supabase.com'

$secret = (Get-Content '.env.production.local' | Where-Object { $_ -like 'SECRET_KEY=*' }) -replace '^SECRET_KEY=', ''
if (-not $secret) { throw '.env.production.local 에 SECRET_KEY 가 없습니다.' }

$sec = Read-Host 'Supabase DB 비밀번호 (프로젝트 만들 때 입력한 값)' -AsSecureString
$pw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
$pwEnc = [Uri]::EscapeDataString($pw)
$url = "postgresql://postgres.${ref}:${pwEnc}@${poolerHost}:6543/postgres?sslmode=require"

# Vercel CLI 는 안내 문구를 stderr 로 출력한다. PowerShell 5.1 에서 이를 오류로 보고 멈추지 않도록
# 외부 명령 구간에서는 Continue 로 바꾸고, 종료 코드로 성공 여부를 판단한다.
$ErrorActionPreference = 'Continue'
cmd /c "npx --yes vercel@latest env rm SECRET_KEY production --yes >nul 2>&1"
cmd /c "npx --yes vercel@latest env rm DATABASE_URL production --yes >nul 2>&1"
$secret | cmd /c "npx --yes vercel@latest env add SECRET_KEY production 2>&1"
if ($LASTEXITCODE -ne 0) { throw 'SECRET_KEY 설정 실패' }
$url | cmd /c "npx --yes vercel@latest env add DATABASE_URL production 2>&1"
if ($LASTEXITCODE -ne 0) { throw 'DATABASE_URL 설정 실패' }
$ErrorActionPreference = 'Stop'

# 로컬에서도 같은 DB 로 붙을 수 있도록 .env.production.local 에 기록 (git 제외 파일)
$lines = Get-Content '.env.production.local' | Where-Object { $_ -notlike 'DATABASE_URL=*' }
$lines + "DATABASE_URL=$url" | Set-Content '.env.production.local' -Encoding ascii
Write-Host '완료: SECRET_KEY, DATABASE_URL 을 Vercel production 에 설정했습니다.'
