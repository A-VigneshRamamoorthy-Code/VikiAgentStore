<#
VikiVPN reconciler -- the Azure-side backstop that runs outside the VPN VMs.

An Azure Automation runbook (hourly schedule, inside the free 500 job-minutes a
month) authenticated by the Automation account's managed identity. It reads the
deployment from config/regions.json (plus any tagged VM in the resource groups listed
in config/groups.json, which covers half-built servers) in the VikiVPN storage
account, then for each VPN VM:

  * PowerState/stopped (OS shut down but still allocated, so still billed) -> deallocate
  * running/starting with no live lease for LeaseTTL + Grace seconds, and not
    started in the last StartGrace seconds -> deallocate

Clients write their lease before starting a VM, so a running VM with no lease
is always a leak (crashed app, hung guest, dead in-VM agent).

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
            $code = $vm.tags.'vikivpn-region'
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

foreach ($r in $targets) {
  try {
    if (-not $r.vmId) { continue }  # placeholder: region not built
    try {
        $view = Invoke-RestMethod -Uri "https://management.azure.com$($r.vmId)/instanceView?api-version=$api" -Headers $arm
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -in 403, 404) { Write-Output ("{0}: deleted" -f $r.code); continue }
        throw
    }
    $power = ($view.statuses | Where-Object { $_.code -like 'PowerState/*' } | Select-Object -First 1).code -replace '^PowerState/', ''
    $times = @($view.statuses | Where-Object { $_.time } | ForEach-Object { [datetime]$_.time })
    $since = if ($times.Count) { ((Get-Date).ToUniversalTime() - ($times | Sort-Object -Descending)[0].ToUniversalTime()).TotalSeconds } else { $null }

    $list = Invoke-WebRequest -UseBasicParsing -Headers $blob `
        -Uri "$base/leases?restype=container&comp=list&prefix=$($r.code)/"
    $now = [datetime]::Parse($list.Headers['Date']).ToUniversalTime()
    # Blob listings start with a UTF-8 BOM that .Content mis-decodes; parse the raw bytes.
    $xml = [xml]([Text.Encoding]::UTF8.GetString($list.RawContentStream.ToArray()).TrimStart([char]0xFEFF))
    $ages = @($xml.EnumerationResults.Blobs.Blob | Where-Object { $_ } |
        ForEach-Object { ($now - [datetime]::Parse($_.Properties.'Last-Modified').ToUniversalTime()).TotalSeconds })
    $age = if ($ages.Count) { ($ages | Measure-Object -Minimum).Minimum } else { $null }

    $action = 'none'
    if ($power -eq 'stopped') { $action = 'deallocate (stopped but allocated)' }
    elseif ($power -in 'running', 'starting') {
        $leaseless = ($null -eq $age) -or ($age -gt $LeaseTTL + $Grace)
        if ($leaseless -and (($null -eq $since) -or ($since -gt $StartGrace))) { $action = 'deallocate (no live lease)' }
    }
    $leaseless = ($null -eq $age) -or ($age -gt $LeaseTTL + $Grace)
    if ($power -eq 'deallocated' -and $leaseless -and $settings -and ($relays -notcontains $r.code)) {
        $rg = $r.vmId -replace '/providers/.*$', ''
        # A location's own switches override the fleet defaults.
        $own = if ($settings.regions) { $settings.regions.($r.code) } else { $null }
        $ephemeral = if ($own -and $null -ne $own.ephemeral) { [bool]$own.ephemeral } else { [bool]$settings.ephemeral }
        $staticIP = if ($own -and $null -ne $own.staticIP) { [bool]$own.staticIP } else { [bool]$settings.staticIP }
        if ($ephemeral) {
            Invoke-WebRequest -UseBasicParsing -Method Delete -Headers $arm `
                -Uri "https://management.azure.com$rg`?api-version=2021-04-01" | Out-Null
            $action = 'delete resource group (provision once)'
        } elseif (-not $staticIP) {
            $ip = "https://management.azure.com$rg/providers/Microsoft.Network/publicIPAddresses/$(($r.vmId -split '/')[-1])-ip?api-version=2024-05-01"
            $hasIp = $true
            try { Invoke-RestMethod -Uri $ip -Headers $arm | Out-Null } catch { $hasIp = $false }
            if ($hasIp) { Remove-PublicIP $r.vmId; $action = 'release public IP' }
        }
    }
    elseif ($action -ne 'none') {
        Invoke-WebRequest -UseBasicParsing -Method Post -Headers $arm -Body '' `
            -Uri "https://management.azure.com$($r.vmId)/deallocate?api-version=$api" | Out-Null
    }
    Write-Output ("{0}: power={1} leaseAge={2} sinceChange={3} action={4}" -f $r.code, $power, $age, $since, $action)
  } catch {
    Write-Output ("{0}: error {1}" -f $r.code, $_.Exception.Message)
  }
}
