# Leap VPN direct home exit for Windows 10/11.
#
# Turns this PC into a WireGuard server that your Mac connects to directly, so the
# Mac's traffic leaves through this PC's home internet connection. No cloud relay.
#
# It runs sing-box (userspace WireGuard, no driver) as a per-user scheduled task, so
# the only administrator step is one firewall rule (a single UAC prompt).
#
# Usage (normal PowerShell on the PC; the Leap VPN app gives you this line):
#   $env:LEAP_MAC='<mac public key>'; $env:LEAP_NAME='Home PC'; irm <url> | iex
# Or saved to a file:
#   powershell -ExecutionPolicy Bypass -File Install-LeapDirect.ps1 -MacKey <key> -Name 'Home PC'
# Optional: LEAP_PORT / -Port (UDP, default 51820). Remove: LEAP_UNINSTALL=1 / -Uninstall.
# Running it again with another Mac key adds that Mac; the PC keeps its own key.
#
# Rules this file follows on purpose:
#  - ASCII only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
#  - Constrained-Language-safe main path (no .NET static calls or Add-Type).
#  - Everything inside a function and `return`, never `exit`: it is run with
#    `irm ... | iex`, where `exit` would close the user's PowerShell window.

param(
    [string]$MacKey = $env:LEAP_MAC,
    [string]$Name = $env:LEAP_NAME,
    [string]$Port = $env:LEAP_PORT,
    [switch]$Uninstall
)

function ConvertTo-LeapUrl([string]$Text) {
    $Out = ''
    foreach ($Ch in $Text.ToCharArray()) {
        $C = [int]$Ch
        if (($C -ge 48 -and $C -le 57) -or ($C -ge 65 -and $C -le 90) -or ($C -ge 97 -and $C -le 122) -or
            $C -eq 45 -or $C -eq 46 -or $C -eq 95 -or $C -eq 126) { $Out += $Ch }
        elseif ($C -lt 128) { $Out += '%' + ('{0:X2}' -f $C) }
    }
    return $Out
}

function Invoke-LeapAdmin([string]$Command) {
    # Runs one command elevated: directly if we already are, else via a single UAC prompt.
    if ((whoami /groups) -match 'S-1-16-12288') {
        try { Invoke-Expression $Command; return $true } catch { return $false }
    }
    try {
        $P = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -Wait -PassThru `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command $Command"
        return ($P.ExitCode -eq 0)
    } catch { return $false }
}

function Get-LeapUpnp {
    try {
        $U = New-Object -ComObject HNetCfg.NATUPnP
        for ($I = 0; $I -lt 3; $I++) {
            $C = $U.StaticPortMappingCollection
            if ($C) { return $C }
            Start-Sleep -Seconds 1
        }
    } catch {}
    return $null
}

function Install-LeapDirect([string]$MacKey, [string]$Name, [string]$Port, [bool]$Uninstall) {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    $Version = '1.14.4'
    $Hashes = @{
        amd64 = '99185D75D314A07DBBA4A130C8AD986CBEB629A07927975636B341CA61F991DF'
        arm64 = '8CD0A4D0CD8CD480BE5731AC31F17038969A42D12ADD9FEB6E031FD43D85BBAE'
    }
    $TaskName = 'Leap VPN Direct'
    $RuleName = 'Leap VPN Direct'
    $Dir = Join-Path $env:LOCALAPPDATA 'LeapVPN\direct'
    $Exe = Join-Path $Dir 'sing-box.exe'
    $StateFile = Join-Path $Dir 'state.json'
    $Me = "$env:USERDOMAIN\$env:USERNAME"
    $State = $null
    if (Test-Path $StateFile) { try { $State = Get-Content $StateFile -Raw | ConvertFrom-Json } catch {} }

    # Stop whatever is running from a previous install before touching its files.
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Get-Process -Name 'sing-box' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $Exe } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$Dir\run.ps1*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    if ($Uninstall) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        if (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue) {
            if (-not (Invoke-LeapAdmin "Remove-NetFirewallRule -DisplayName '$RuleName'")) {
                Write-Host "Could not remove the firewall rule '$RuleName' (needs administrator)." -ForegroundColor Yellow
            }
        }
        if ($State -and $State.port) {
            $C = Get-LeapUpnp
            if ($C) { try { $C.Remove([int]$State.port, 'UDP') } catch {} }
        }
        Start-Sleep -Seconds 1
        Remove-Item -Recurse -Force $Dir -ErrorAction SilentlyContinue
        Write-Host 'Leap VPN direct exit removed from this PC.'
        return
    }

    $MacKey = ([string]$MacKey).Trim()
    if ($MacKey -notmatch '^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$') {
        Write-Host 'Missing or invalid Mac key. Copy the full command from the Leap VPN app.' -ForegroundColor Red
        return
    }
    $Name = (([string]$Name) -replace '[^\x20-\x7e]', '').Trim()
    if (-not $Name) { $Name = ($env:COMPUTERNAME -replace '[^\x20-\x7e]', '') }
    if ($Name.Length -gt 40) { $Name = $Name.Substring(0, 40) }
    $OldPort = if ($State -and $State.port) { [int]$State.port } else { 0 }
    if ($Port) {
        if ($Port -notmatch '^\d{4,5}$' -or [int]$Port -lt 1024 -or [int]$Port -gt 65535) {
            Write-Host 'LEAP_PORT must be a number between 1024 and 65535.' -ForegroundColor Red; return
        }
        $PortNum = [int]$Port
    } elseif ($OldPort) { $PortNum = $OldPort } else { $PortNum = 51820 }

    # Windows PowerShell 5.1 may default to TLS 1.0; blocked in ConstrainedLanguage, where it is not needed.
    try { [Net.ServicePointManager]::SecurityProtocol = 'Tls12' } catch {}

    Write-Host "Setting up '$Name' as a Leap VPN server..."
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    # Other users may not read the folder: it holds the PC's WireGuard private key.
    icacls $Dir /inheritance:r /grant:r "${Me}:(OI)(CI)F" | Out-Null

    $Arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $Stamp = Join-Path $Dir 'version.txt'
    $Have = if (Test-Path $Stamp) { (Get-Content $Stamp -Raw).Trim() } else { '' }
    if (-not (Test-Path $Exe) -or $Have -ne "$Version-$Arch") {
        $Zip = Join-Path $Dir 'sing-box.zip'
        $Url = "https://github.com/SagerNet/sing-box/releases/download/v$Version/sing-box-$Version-windows-$Arch.zip"
        try { Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Zip } catch {
            Write-Host "Download failed: $($_.Exception.Message)" -ForegroundColor Red; return
        }
        if ((Get-FileHash -Algorithm SHA256 $Zip).Hash -ne $Hashes[$Arch]) {
            Remove-Item -Force $Zip
            Write-Host 'The downloaded sing-box does not match its pinned checksum. Not installing.' -ForegroundColor Red
            return
        }
        $Tmp = Join-Path $Dir 'unpack'
        Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
        Expand-Archive -Path $Zip -DestinationPath $Tmp -Force
        Get-ChildItem -Path (Join-Path $Tmp "sing-box-$Version-windows-$Arch") -File |
            ForEach-Object { Copy-Item -Force $_.FullName (Join-Path $Dir $_.Name) }
        Remove-Item -Recurse -Force $Tmp, $Zip
        Set-Content -Encoding Ascii -Path $Stamp -Value "$Version-$Arch"
    }

    # PC keypair: generated once, kept across re-runs so already-paired Macs keep working.
    if ($State -and $State.privateKey -and $State.publicKey) {
        $Priv = [string]$State.privateKey; $Pub = [string]$State.publicKey
    } else {
        $Kp = (& $Exe generate wg-keypair) -join "`n"
        if ($Kp -notmatch 'PrivateKey:\s*(\S+)') { Write-Host 'Could not generate a WireGuard key.' -ForegroundColor Red; return }
        $Priv = $Matches[1]
        if ($Kp -notmatch 'PublicKey:\s*(\S+)') { Write-Host 'Could not generate a WireGuard key.' -ForegroundColor Red; return }
        $Pub = $Matches[1]
    }
    if ($MacKey -eq $Pub) { Write-Host 'That is this PC''s own key, not the Mac''s.' -ForegroundColor Red; return }

    $Peers = @()
    if ($State -and $State.peers) { $Peers = @($State.peers | Where-Object { $_.key }) }
    $Mine = $Peers | Where-Object { $_.key -eq $MacKey } | Select-Object -First 1
    if ($Mine) {
        $N = [int]$Mine.n
    } else {
        $Used = @($Peers | ForEach-Object { [int]$_.n })
        $N = 2
        while ($Used -contains $N) { $N++ }
        if ($N -gt 254) { Write-Host 'Too many Macs paired with this PC.' -ForegroundColor Red; return }
        $Peers += [pscustomobject][ordered]@{
            n = $N; key = $MacKey; address = "10.77.0.$N"; address6 = "fd77::$N"
            added = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
    }
    $NewState = [ordered]@{ name = $Name; privateKey = $Priv; publicKey = $Pub; port = $PortNum; peers = @($Peers) }
    Set-Content -Encoding Ascii -Path $StateFile -Value ($NewState | ConvertTo-Json -Depth 5)

    $WgPeers = @($Peers | ForEach-Object {
        [ordered]@{ public_key = [string]$_.key; allowed_ips = @("10.77.0.$($_.n)/32", "fd77::$($_.n)/128") }
    })
    $Config = [ordered]@{
        log       = [ordered]@{ level = 'warn'; timestamp = $true; output = 'box.log' }
        endpoints = @([ordered]@{
            type = 'wireguard'; tag = 'wg-in'; system = $false; mtu = 1408
            address = @('10.77.0.1/24', 'fd77::1/64')
            private_key = $Priv; listen_port = $PortNum; peers = $WgPeers
        })
        outbounds = @([ordered]@{ type = 'direct'; tag = 'direct' })
        route     = [ordered]@{
            # Macs reach the internet only, never this PC's home network.
            rules = @([ordered]@{ ip_is_private = $true; action = 'reject' })
            final = 'direct'
        }
    }
    $Cfg = Join-Path $Dir 'config.json'
    Set-Content -Encoding Ascii -Path $Cfg -Value ($Config | ConvertTo-Json -Depth 10)
    $ErrorActionPreference = 'Continue'
    $Check = (& $Exe check -c $Cfg -D $Dir 2>&1 | ForEach-Object { "$_" }) -join ' '
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { Write-Host "Config check failed: $Check" -ForegroundColor Red; return }

    # Firewall before first start, so Windows never asks (and maybe blocks) on its own.
    $RuleOk = $false
    try {
        $R = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($R) {
            $RuleOk = (($R | Get-NetFirewallPortFilter).LocalPort -eq [string]$PortNum) -and
                (($R | Get-NetFirewallApplicationFilter).Program -eq $Exe) -and $R.Enabled -eq 'True'
        }
    } catch {}
    if (-not $RuleOk) {
        $E = $Exe -replace "'", "''"
        $Cmd = "Remove-NetFirewallRule -DisplayName '$RuleName' -ErrorAction SilentlyContinue; " +
            "New-NetFirewallRule -DisplayName '$RuleName' -Direction Inbound -Action Allow -Protocol UDP " +
            "-LocalPort $PortNum -Program '$E' -Profile Any | Out-Null"
        Write-Host 'Allowing Leap VPN through Windows Firewall (approve the prompt)...'
        if (-not (Invoke-LeapAdmin $Cmd)) {
            Write-Host "WARNING: firewall rule not added; Macs may not connect until UDP $PortNum is allowed for $Exe." -ForegroundColor Yellow
        }
    }

    $Run = @'
$ErrorActionPreference = 'Continue'
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
while ($true) {
    $Log = Join-Path $Dir 'box.log'
    if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 1MB) { Remove-Item -Force $Log }
    & (Join-Path $Dir 'sing-box.exe') run -c (Join-Path $Dir 'config.json') -D $Dir 2>&1 | Out-Null
    "$(Get-Date -Format s) sing-box exited with code $LASTEXITCODE" | Add-Content -Encoding Ascii $Log
    Start-Sleep -Seconds 5
}
'@
    Set-Content -Encoding Ascii -Path (Join-Path $Dir 'run.ps1') -Value $Run

    # conhost --headless keeps the background loop from opening a console window.
    $Action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\conhost.exe') `
        -Argument "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dir\run.ps1`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $Me
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Settings $Settings -Principal $Principal -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName

    # Router: ask it to forward the port (UPnP). Many routers have this off.
    $Lan = ''
    try {
        $Rt = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop | Sort-Object { $_.RouteMetric + $_.InterfaceMetric } | Select-Object -First 1
        $Lan = (Get-NetIPAddress -InterfaceIndex $Rt.InterfaceIndex -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notmatch '^169\.254\.' } | Select-Object -First 1).IPAddress
    } catch {}
    $Upnp = Get-LeapUpnp
    $Mapped = $false
    $Wan = ''
    if ($Upnp -and $Lan) {
        try {
            if ($OldPort -and $OldPort -ne $PortNum) { try { $Upnp.Remove($OldPort, 'UDP') } catch {} }
            try { $Upnp.Remove($PortNum, 'UDP') } catch {}
            $M = $Upnp.Add($PortNum, 'UDP', $PortNum, $Lan, $true, 'Leap VPN')
            if ($M) { $Mapped = $true; $Wan = [string]$M.ExternalIPAddress }
        } catch {}
    }

    # Where this PC appears on the internet.
    $Where = $null
    try { $Where = Invoke-RestMethod -Uri 'https://ipinfo.io/json' -TimeoutSec 15 } catch {}
    $Ip = if ($Where -and $Where.ip) { [string]$Where.ip } else { '' }
    if (-not $Ip -or $Ip -match ':') {
        try { $Ip = ([string](Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 15)).Trim() } catch {}
    }
    if ($Ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        Write-Host 'Could not find this PC''s public IPv4 address. Check the internet connection and run again.' -ForegroundColor Red
        return
    }
    $Country = if ($Where -and $Where.country -match '^[A-Z]{2}$') { [string]$Where.country } else { 'XX' }
    $Loc = if ($Where -and ([string]$Where.loc) -match '^-?[0-9.]+,-?[0-9.]+$') { [string]$Where.loc } else { '' }
    $Isp = if ($Where -and $Where.org) { (([string]$Where.org) -replace '^AS\d+\s+', '') -replace '[^\x20-\x7e]', '' } else { '' }

    $Link = 'leapvpn://pair?v=1&n=' + (ConvertTo-LeapUrl $Name) + '&k=' + (ConvertTo-LeapUrl $Pub) +
        "&e=${Ip}:$PortNum&a=10.77.0.$N&a6=fd77::$N&c=$Country&l=" + (ConvertTo-LeapUrl $Loc) +
        '&isp=' + (ConvertTo-LeapUrl $Isp)
    $Copied = $false
    try { Set-Clipboard -Value $Link; $Copied = $true } catch {}

    Write-Host ''
    Write-Host "Done. '$Name' is a Leap VPN server ($Country, $Isp, $Ip port $PortNum UDP)." -ForegroundColor Green
    if ($Mapped) {
        Write-Host "Router port forward added automatically (UPnP)."
        if ($Wan -and $Wan -ne $Ip) {
            Write-Host "WARNING: your router's internet address ($Wan) is not your public IP ($Ip)." -ForegroundColor Yellow
            Write-Host 'Your provider probably shares one IP between customers (CGNAT); direct mode will not work.' -ForegroundColor Yellow
        }
    } else {
        $To = if ($Lan) { $Lan } else { 'this PC' }
        Write-Host "Forward UDP $PortNum on your router to $To (UPnP was not available)." -ForegroundColor Yellow
    }
    if ($Isp -match 'Microsoft|Amazon|Google|DigitalOcean|OVH|Hetzner|Oracle') {
        Write-Host "Note: this internet connection looks like a datacenter ($Isp); streaming services may block it." -ForegroundColor Yellow
    }
    Write-Host 'Keep this PC on, awake and signed in while you use it.'
    if ($Copied) { Write-Host 'Pairing link (copied to the clipboard; paste it into Leap VPN on the Mac):' }
    else { Write-Host 'Pairing link (paste it into Leap VPN on the Mac):' }
    Write-Host $Link
    Write-Output "LEAP-LINK $Link"
}

Install-LeapDirect -MacKey $MacKey -Name $Name -Port $Port -Uninstall ([bool]($Uninstall -or $env:LEAP_UNINSTALL -eq '1'))
