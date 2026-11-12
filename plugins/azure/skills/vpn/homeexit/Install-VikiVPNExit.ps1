# VikiVPN home exit installer for Windows.
#
# Turns this PC into a VikiVPN server: your VPN devices can pick it in the app and
# their traffic leaves through this PC's home internet connection, which streaming
# services accept (they block datacenter IPs such as Azure's).
#
# The PC dials OUT to the VikiVPN relay over SSH (a reverse SOCKS forward), so no
# router or firewall changes are needed and nothing listens on this PC. It uses only
# the OpenSSH client that ships with Windows and a per-user scheduled task, so it
# needs no administrator rights and shows no prompts. While the relay VM is
# deallocated (no device connected) the task just retries quietly.
#
# You normally never handle this file: the VikiVPN app's "Add home PC" gives you a
# one-line command to paste into PowerShell on the PC (or a .cmd wrapper). Either
# way the app has prepended your invite as $VikiInvite. By hand:
#   $env:VIKIVPN_INVITE = '<invite json>'; .\Install-VikiVPNExit.ps1
#   $env:VIKIVPN_INVITE = 'uninstall';     .\Install-VikiVPNExit.ps1
#
# The invite carries the relay address, its SSH host key, the reserved port and a
# write-only URL (valid 48 h) for this exit's registration. The SSH private key is
# generated here and never leaves this PC.
#
# Rules this file follows on purpose:
#  - ASCII only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
#  - Constrained-Language-safe (no .NET static calls): Smart App Control / WDAC can
#    force PowerShell into ConstrainedLanguage mode.
#  - Everything inside a function and `return`, never `exit`: it is run with
#    `irm ... | iex`, where `exit` would close the user's PowerShell window.

function Install-VikiVPNExit {
    $ErrorActionPreference = 'Stop'
    $TaskPrefix = 'VikiVPN Home Exit '
    $Root = Join-Path $env:LOCALAPPDATA 'VikiVPN'
    $Raw = if ($script:VikiInvite) { $script:VikiInvite } elseif ($global:VikiInvite) { $global:VikiInvite } else { $env:VIKIVPN_INVITE }

    if ($Raw -eq 'uninstall') {
        Get-ScheduledTask -TaskName "$TaskPrefix*" -ErrorAction SilentlyContinue |
            Unregister-ScheduledTask -Confirm:$false
        Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*vikiexit@*' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Remove-Item -Recurse -Force $Root -ErrorAction SilentlyContinue
        Write-Host 'VikiVPN home exit removed from this PC. Remove it from the server list in the app too.'
        return
    }
    if (-not $Raw) { Write-Host 'No invite. In the VikiVPN app: server list > Add home PC.' -ForegroundColor Red; return }

    try { $Invite = $Raw | ConvertFrom-Json } catch { $Invite = $null }
    if (-not $Invite -or $Invite.v -ne 1 -or $Invite.id -notmatch '^[a-z0-9-]{1,40}$' -or
        $Invite.relay -notmatch '^[0-9.]+$' -or $Invite.hostKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+$' -or
        [int]$Invite.port -lt 10801 -or [int]$Invite.port -gt 10899 -or $Invite.put -notmatch '^https://') {
        Write-Host 'This invite is not valid. Create a new one in the app.' -ForegroundColor Red; return
    }
    if (([datetime]$Invite.expires).ToUniversalTime() -lt (Get-Date).ToUniversalTime()) {
        Write-Host 'This invite has expired (they last 48 hours). Create a new one in the app.' -ForegroundColor Red; return
    }
    # Windows PowerShell 5.1 may default to TLS 1.0; blocked in ConstrainedLanguage, where it is not needed.
    try { [Net.ServicePointManager]::SecurityProtocol = 'Tls12' } catch {}

    Write-Host "Adding this PC to VikiVPN as home exit '$($Invite.id)' (relay: $($Invite.regionName))..."

    $SshDir = Join-Path $env:SystemRoot 'System32\OpenSSH'
    $Ssh = Join-Path $SshDir 'ssh.exe'
    $Keygen = Join-Path $SshDir 'ssh-keygen.exe'
    if (-not (Test-Path $Ssh)) {
        Write-Host 'The Windows OpenSSH client is missing. Turn it on in Settings > System > Optional features >' -ForegroundColor Red
        Write-Host '"OpenSSH Client", then run this again.' -ForegroundColor Red
        return
    }

    $Dir = Join-Path $Root $Invite.id
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $Me = "$env:USERDOMAIN\$env:USERNAME"
    $Key = Join-Path $Dir 'id_ed25519'
    if (-not (Test-Path $Key)) {
        & $Keygen -q -t ed25519 -N '""' -C "vikivpn-exit-$($Invite.id)" -f $Key | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Key)) { Write-Host 'ssh-keygen failed.' -ForegroundColor Red; return }
    }
    icacls $Key /inheritance:r /grant:r "${Me}:F" | Out-Null
    $Pub = ((Get-Content "$Key.pub" -Raw).Trim() -split ' ')[0..1] -join ' '

    # Where this PC appears on the internet, measured before any tunnel exists.
    $Where = $null
    try { $Where = Invoke-RestMethod -Uri 'https://ipinfo.io/json' -TimeoutSec 15 } catch {}
    $Country = if ($Where -and $Where.country -match '^[A-Z]{2}$') { $Where.country } else { 'XX' }
    $City = if ($Where -and $Where.city) { ([string]$Where.city) -replace '[^\x20-\x7e]', '' } else { '' }
    $Isp = if ($Where -and $Where.org) { (([string]$Where.org) -replace '^AS\d+\s+', '') -replace '[^\x20-\x7e]', '' } else { '' }
    $Loc = if ($Where -and ([string]$Where.loc) -match '^-?[0-9.]+,-?[0-9.]+$') { [string]$Where.loc } else { '' }
    $Name = if ($City) { "$City Home" } else { "$env:COMPUTERNAME" }
    if ($Name.Length -gt 40) { $Name = $Name.Substring(0, 40) }
    if ($Isp -match 'Microsoft|Amazon|Google|DigitalOcean|OVH|Hetzner|Oracle') {
        Write-Host "WARNING: this PC's internet looks like a datacenter ($Isp)." -ForegroundColor Yellow
        Write-Host 'Streaming services will block it just like the Azure servers.' -ForegroundColor Yellow
    }

    $Exit = [ordered]@{
        id           = $Invite.id
        name         = $Name
        country      = $Country
        city         = $City
        isp          = $Isp
        loc          = $Loc
        region       = $Invite.region
        port         = [int]$Invite.port
        sshPublicKey = $Pub
        host         = ($env:COMPUTERNAME -replace '[^\x20-\x7e]', '')
        createdAt    = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    try {
        Invoke-RestMethod -Method Put -Uri $Invite.put -ContentType 'application/json' `
            -Headers @{ 'x-ms-blob-type' = 'BlockBlob'; 'x-ms-version' = '2022-11-02' } `
            -Body ($Exit | ConvertTo-Json -Compress) | Out-Null
    } catch {
        Write-Host "Could not register with VikiVPN: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'The invite may have expired or been cancelled. Create a new one in the app.' -ForegroundColor Red
        return
    }

    Set-Content -Encoding Ascii -Path (Join-Path $Dir 'known_hosts') -Value "$($Invite.relay) $($Invite.hostKey)"
    Set-Content -Encoding Ascii -Path (Join-Path $Dir 'exit.json') `
        -Value (@{ port = [int]$Invite.port; relay = $Invite.relay } | ConvertTo-Json -Compress)
    $Run = @'
$ErrorActionPreference = 'Continue'
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cfg = Get-Content (Join-Path $Dir 'exit.json') -Raw | ConvertFrom-Json
$Ssh = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
while ($true) {
    $out = & $Ssh -N -T -i "$Dir\id_ed25519" -o "UserKnownHostsFile=$Dir\known_hosts" `
        -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10 `
        -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes `
        -R "127.0.0.1:$($Cfg.port)" "vikiexit@$($Cfg.relay)" 2>&1
    "$(Get-Date -Format s) exit=$LASTEXITCODE $($out | Select-Object -Last 3)" |
        Set-Content -Encoding Ascii (Join-Path $Dir 'last.log')
    Start-Sleep -Seconds 15
}
'@
    Set-Content -Encoding Ascii -Path (Join-Path $Dir 'run.ps1') -Value $Run

    # conhost --headless keeps the background loop from opening a console window.
    $Task = "$TaskPrefix$($Invite.id)"
    $Action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\conhost.exe') `
        -Argument "--headless powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Dir\run.ps1`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Me
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $Task -Action $Action -Trigger $Trigger `
        -Settings $Settings -Principal $Principal -Force | Out-Null
    Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $Task

    Write-Host ''
    Write-Host "Done. '$Name' ($Country, $Isp) is now a VikiVPN server." -ForegroundColor Green
    Write-Host 'It appears in the VikiVPN app server list within a minute.'
    Write-Host 'Keep this PC on, awake and signed in while you use it.'
    Write-Host "Connection log: $Dir\last.log"
}

Install-VikiVPNExit
