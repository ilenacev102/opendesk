# Heartbeat agent (Windows): collect inventory and POST it to ServiceDesk.
# Config via environment only - no secrets in this file:
#   SERVICEDESK_URL    base URL, e.g. http://192.168.1.10:5000
#   SERVICEDESK_TOKEN  API Bearer token (magacioner scope)
#   SERVICEDESK_DRY_RUN=1 prints JSON without POSTing (testing)
#   HOSTNAME_OVERRIDE / SERIAL_OVERRIDE for testing
$ErrorActionPreference = "Stop"

$Endpoint = "/api/v1/discovery/heartbeat"

$BaseUrl = $env:SERVICEDESK_URL
$Token = $env:SERVICEDESK_TOKEN
if ([string]::IsNullOrWhiteSpace($BaseUrl) -or [string]::IsNullOrWhiteSpace($Token)) {
  Write-Error "heartbeat: SERVICEDESK_URL and SERVICEDESK_TOKEN must be set"
  exit 1
}

$HostnameVal = $env:HOSTNAME_OVERRIDE
if ([string]::IsNullOrWhiteSpace($HostnameVal)) { $HostnameVal = $env:COMPUTERNAME }
$SerialVal = $env:SERIAL_OVERRIDE
$ManufacturerVal = ""
$ModelVal = ""
$OsVal = ""
try {
  $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
  if ([string]::IsNullOrWhiteSpace($ManufacturerVal)) { $ManufacturerVal = $cs.Manufacturer }
  if ([string]::IsNullOrWhiteSpace($ModelVal)) { $ModelVal = $cs.Model }
  $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop
  if ([string]::IsNullOrWhiteSpace($SerialVal)) { $SerialVal = $bios.SerialNumber }
  $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
  $OsVal = $os.Caption
} catch {
  Write-Warning "heartbeat: WMI read failed: $($_.Exception.Message)"
}

$Payload = @{
  hostname     = ($HostnameVal | Out-String).Trim()
  serial       = ($SerialVal | Out-String).Trim()
  manufacturer = ($ManufacturerVal | Out-String).Trim()
  model        = ($ModelVal | Out-String).Trim()
  os           = ($OsVal | Out-String).Trim()
} | ConvertTo-Json -Compress

if ($env:SERVICEDESK_DRY_RUN -eq "1") {
  Write-Output $Payload
  exit 0
}

try {
  $Resp = Invoke-RestMethod -Method Post -Uri ($BaseUrl + $Endpoint) `
    -ContentType "application/json" `
    -Headers @{ Authorization = "Bearer $env:SERVICEDESK_TOKEN" } `
    -Body $Payload -TimeoutSec 20
  Write-Output ($Resp | ConvertTo-Json -Compress -Depth 4)
  exit 0
} catch {
  $Status = $null
  try { $Status = [int]$_.Exception.Response.StatusCode } catch { }
  if ($Status -eq 429) { Write-Error "heartbeat: rate limited, retry later" }
  else { Write-Error "heartbeat: post failed: $($_.Exception.Message)" }
  exit 2
}
