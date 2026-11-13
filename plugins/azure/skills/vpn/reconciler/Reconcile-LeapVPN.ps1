<#
LeapVPN reconciler -- the Azure-side backstop that runs outside the VPN VMs.

An Azure Automation runbook (hourly schedule, inside the free 500 job-minutes a
month) authenticated by the Automation account's managed identity. It reads the
deployment from config/regions.json (plus any tagged VM in the resource groups listed
in config/groups.json, which covers half-built servers) in the LeapVPN storage
account, then for each VPN VM:

  * PowerState/stopped (OS shut down but still allocated, so still billed) -> deallocate
  * running/starting with no live lease for LeaseTTL + Grace seconds, and not
    started in the last StartGrace seconds -> deallocate

Clients write their lease before starting a VM, so a running VM with no lease
is always a leak (crashed app, hung guest, dead in-VM agent).

Every mutation is re-checked under the region lock (leases/_locks/<code>) that the apps
and the VM agents share, so a device joining at the same moment always wins.

It also enforces config/settings.json for deallocated, leaseless servers that do not
relay a home PC (settings.relays, or any exits/<region>/ blob):

  * ephemeral ("Provision once") -> delete the region's whole resource group
  * staticIP false              -> detach and delete the public IP

settings.regions.<code> may override either switch for one location.
#>
param(
    [Parameter(Mandatory = $true)][string]$StorageAccount,
    [int]$LeaseTTL = 180,
    [int]$Grace = 300,
    [int]$StartGrace = 900
)
$ErrorActionPreference = 'Stop'
$api = '2024-07-01'

function Get-MIToken([string]$Resource) {
    $uri = "$($env:IDENTITY_ENDPOINT)?resource=$([uri]::EscapeDataString($Resource))&api-version=2019-08-01"
    (Invoke-RestMethod -Uri $uri -Headers @{ 'X-IDENTITY-HEADER' = $env:IDENTITY_HEADER }).access_token
}

$arm = @{ Authorization = 'Bearer ' + (Get-MIToken 'https://management.azure.com/') }
$blob = @{ Authorization = 'Bearer ' + (Get-MIToken 'https://storage.azure.com/'); 'x-ms-version' = '2021-08-06' }
$base = "https://$StorageAccount.blob.core.windows.net"

$regions = try {
    (Invoke-WebRequest -UseBasicParsing -Uri "$base/config/regions.json" -Headers $blob).Content | ConvertFrom-Json
} catch { [pscustomobject]@{ regions = @() } }  # first setup: no finished server yet
$targets = @($regions.regions | Where-Object { $_ } | ForEach-Object { [pscustomobject]@{ code = $_.code; vmId = $_.vmId } })

# Servers still being built are not in regions.json yet. The app registers their
# resource groups in config/groups.json before creating them, so find any tagged VM there.
try {
    $groups = ((Invoke-WebRequest -UseBasicParsing -Uri "$base/config/groups.json" -Headers $blob).Content |
        ConvertFrom-Json).groups
    $sub = ($regions.regions | Select-Object -First 1).vmId -replace '^(/subscriptions/[^/]+).*', '$1'
    if (-not $sub) { $sub = '/subscriptions/' + (Invoke-RestMethod -Headers $arm `
        -Uri 'https://management.azure.com/subscriptions?api-version=2022-12-01').value[0].subscriptionId }
    foreach ($g in $groups) {
        # A deleted group ("Provision once") loses its role assignment too: 403, like 404, means gone.
        try {
            $vms = Invoke-RestMethod -Headers $arm `
                -Uri "https://management.azure.com$sub/resourceGroups/$g/providers/Microsoft.Compute/virtualMachines?api-version=$api"
        } catch { continue }
        foreach ($vm in $vms.value) {
            $code = $vm.tags.'leapvpn-region'
            if ($code -and -not ($targets | Where-Object { $_.vmId -eq $vm.id })) {
                $targets += [pscustomobject]@{ code = $code; vmId = $vm.id }
            }
        }
    }
} catch { Write-Output ("groups: {0}" -f $_.Exception.Message) }

$settings = try {
    (Invoke-WebRequest -UseBasicParsing -Uri "$base/config/settings.json" -Headers $blob).Content | ConvertFrom-Json
} catch { $null }  # no file yet: only deallocate
$relays = @($settings.relays | Where-Object { $_ })
try {
    $ex = Invoke-WebRequest -UseBasicParsing -Headers $blob -Uri "$base/exits?restype=container&comp=list"
    $exml = [xml]([Text.Encoding]::UTF8.GetString($ex.RawContentStream.ToArray()).TrimStart([char]0xFEFF))
    foreach ($b in @($exml.EnumerationResults.Blobs.Blob | Where-Object { $_ })) {
        $first = ($b.Name -split '/')[0]
        if ($first -and -not $first.StartsWith('_')) { $relays += $first }
    }
} catch { Write-Output ("exits: {0}" -f $_.Exception.Message) }

function Remove-PublicIP([string]$VmId) {
    $rg = $VmId -replace '/providers/.*$', ''
    $vm = ($VmId -split '/')[-1]
    $nicUri = "https://management.azure.com$rg/providers/Microsoft.Network/networkInterfaces/$vm-nic?api-version=2024-05-01"
    $nic = Invoke-RestMethod -Uri $nicUri -Headers $arm
    $attached = $false
    foreach ($c in $nic.properties.ipConfigurations) {
        if ($c.properties.publicIPAddress) { $c.properties.PSObject.Properties.Remove('publicIPAddress'); $attached = $true }
    }
    if ($attached) {
        Invoke-RestMethod -Method Put -Uri $nicUri -Headers $arm -ContentType 'application/json' `
            -Body ($nic | ConvertTo-Json -Depth 30) | Out-Null
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep 5
            if ((Invoke-RestMethod -Uri $nicUri -Headers $arm).properties.provisioningState -eq 'Succeeded') { break }
        }
    }
    Invoke-WebRequest -UseBasicParsing -Method Delete -Headers $arm `
        -Uri "https://management.azure.com$rg/providers/Microsoft.Network/publicIPAddresses/$vm-ip?api-version=2024-05-01" | Out-Null
}

function Get-State($r) {
    try {
        $view = Invoke-RestMethod -Uri "https://management.azure.com$($r.vmId)/instanceView?api-version=$api" -Headers $arm
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -in 403, 404) { return $null }
        throw
    }
    $power = ($view.statuses | Where-Object { $_.code -like 'PowerState/*' } | Select-Object -First 1).code -replace '^PowerState/', ''
    $times = @($view.statuses | Where-Object { $_.time } | ForEach-Object { [datetime]$_.time })
    $since = if ($times.Count) { ((Get-Date).ToUniversalTime() - ($times | Sort-Object -Descending)[0].ToUniversalTime()).TotalSeconds } else { $null }

    # Includes the server's own _agent heartbeat, refreshed while any tunnel is up.
    $list = Invoke-WebRequest -UseBasicParsing -Headers $blob `
        -Uri "$base/leases?restype=container&comp=list&prefix=$($r.code)/"
    $now = [datetime]::Parse($list.Headers['Date']).ToUniversalTime()
    # Blob listings start with a UTF-8 BOM that .Content mis-decodes; parse the raw bytes.
    $xml = [xml]([Text.Encoding]::UTF8.GetString($list.RawContentStream.ToArray()).TrimStart([char]0xFEFF))
    $ages = @($xml.EnumerationResults.Blobs.Blob | Where-Object { $_ } |
        ForEach-Object { ($now - [datetime]::Parse($_.Properties.'Last-Modified').ToUniversalTime()).TotalSeconds })
    $age = if ($ages.Count) { ($ages | Measure-Object -Minimum).Minimum } else { $null }
    [pscustomobject]@{ power = $power; since = $since; age = $age }
}

function Get-Action($r, $st) {
    $leaseless = ($null -eq $st.age) -or ($st.age -gt $LeaseTTL + $Grace)
    if ($st.power -eq 'stopped') { return 'deallocate' }
    if ($st.power -in 'running', 'starting') {
        if ($leaseless -and (($null -eq $st.since) -or ($st.since -gt $StartGrace))) { return 'deallocate' }
        return 'none'
    }
    if ($st.power -eq 'deallocated' -and $leaseless -and $settings -and ($relays -notcontains $r.code)) {
        # A location's own switches override the fleet defaults.
        $own = if ($settings.regions) { $settings.regions.($r.code) } else { $null }
        $ephemeral = if ($own -and $null -ne $own.ephemeral) { [bool]$own.ephemeral } else { [bool]$settings.ephemeral }
        $staticIP = if ($own -and $null -ne $own.staticIP) { [bool]$own.staticIP } else { [bool]$settings.staticIP }
        if ($ephemeral) { return 'delete' }
        if (-not $staticIP) {
            $rg = $r.vmId -replace '/providers/.*$', ''
            $ip = "https://management.azure.com$rg/providers/Microsoft.Network/publicIPAddresses/$(($r.vmId -split '/')[-1])-ip?api-version=2024-05-01"
            try { Invoke-RestMethod -Uri $ip -Headers $arm | Out-Null; return 'release-ip' } catch { }
        }
    }
    'none'
}

# The region lock every device takes (leases/_locks/<code>): a device holding it is
# building, joining or cleaning up, so the reconciler waits for the next run.
function Lock-Region([string]$Code) {
    $u = "$base/leases/_locks/$Code"
    try {
        Invoke-WebRequest -UseBasicParsing -Method Put -Uri $u -Body '{}' -Headers ($blob + @{
            'x-ms-blob-type' = 'BlockBlob'; 'If-None-Match' = '*' }) | Out-Null
    } catch { if ($_.Exception.Response.StatusCode.value__ -notin 409, 412) { throw } }
    $id = [guid]::NewGuid().ToString()
    try {
        Invoke-WebRequest -UseBasicParsing -Method Put -Uri "$u`?comp=lease" -Headers ($blob + @{
            'x-ms-lease-action' = 'acquire'; 'x-ms-lease-duration' = '60'; 'x-ms-proposed-lease-id' = $id }) | Out-Null
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 409) { return $null }
        throw
    }
    $id
}
function Unlock-Region([string]$Code, [string]$Id) {
    try {
        Invoke-WebRequest -UseBasicParsing -Method Put -Uri "$base/leases/_locks/$Code`?comp=lease" -Headers ($blob + @{
            'x-ms-lease-action' = 'release'; 'x-ms-lease-id' = $Id }) | Out-Null
    } catch { Write-Output ("{0}: unlock {1}" -f $Code, $_.Exception.Message) }
}

foreach ($r in $targets) {
  try {
    if (-not $r.vmId) { continue }  # placeholder: region not built
    $st = Get-State $r
    if (-not $st) { Write-Output ("{0}: deleted" -f $r.code); continue }
    $action = Get-Action $r $st
    if ($action -ne 'none') {
        $lock = Lock-Region $r.code
        if (-not $lock) { $action = 'none (region lock held)' }
        else {
            try {
                # Re-read under the lock: a device may have joined since the first look.
                $st = Get-State $r
                $action = if ($st) { Get-Action $r $st } else { 'none (deleted)' }
                $rg = $r.vmId -replace '/providers/.*$', ''
                switch ($action) {
                    'deallocate' {
                        Invoke-WebRequest -UseBasicParsing -Method Post -Headers $arm -Body '' `
                            -Uri "https://management.azure.com$($r.vmId)/deallocate?api-version=$api" | Out-Null
                    }
                    'delete' {
                        Invoke-WebRequest -UseBasicParsing -Method Delete -Headers $arm `
                            -Uri "https://management.azure.com$rg`?api-version=2021-04-01" | Out-Null
                    }
                    'release-ip' { Remove-PublicIP $r.vmId }
                }
            } finally { Unlock-Region $r.code $lock }
        }
    }
    Write-Output ("{0}: power={1} leaseAge={2} sinceChange={3} action={4}" -f $r.code, $st.power, $st.age, $st.since, $action)
  } catch {
    Write-Output ("{0}: error {1}" -f $r.code, $_.Exception.Message)
  }
}
