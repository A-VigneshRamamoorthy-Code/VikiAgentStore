<#
VikiVPN reconciler -- the Azure-side backstop that runs outside the VPN VMs.

An Azure Automation runbook (hourly schedule, inside the free 500 job-minutes a
month) authenticated by the Automation account's managed identity. It reads the
deployment from config/regions.json in the VikiVPN storage account, then for each
VPN VM:

  * PowerState/stopped (OS shut down but still allocated, so still billed) -> deallocate
  * running/starting with no live lease for LeaseTTL + Grace seconds, and not
    started in the last StartGrace seconds -> deallocate

Clients write their lease before starting a VM, so a running VM with no lease
is always a leak (crashed app, hung guest, dead in-VM agent).
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

$regions = (Invoke-WebRequest -UseBasicParsing -Uri "$base/config/regions.json" -Headers $blob).Content |
    ConvertFrom-Json
foreach ($r in $regions.regions) {
  try {
    $view = Invoke-RestMethod -Uri "https://management.azure.com$($r.vmId)/instanceView?api-version=$api" -Headers $arm
    $power = ($view.statuses | Where-Object { $_.code -like 'PowerState/*' } | Select-Object -First 1).code -replace '^PowerState/', ''
    $times = @($view.statuses | Where-Object { $_.time } | ForEach-Object { [datetime]$_.time })
    $since = if ($times.Count) { ((Get-Date).ToUniversalTime() - ($times | Sort-Object -Descending)[0].ToUniversalTime()).TotalSeconds } else { $null }

    $list = Invoke-WebRequest -UseBasicParsing -Headers $blob `
        -Uri "$base/leases?restype=container&comp=list&prefix=$($r.code)/"
    $now = [datetime]::Parse($list.Headers['Date']).ToUniversalTime()
    $ages = @(([xml]$list.Content).EnumerationResults.Blobs.Blob | Where-Object { $_ } |
        ForEach-Object { ($now - [datetime]::Parse($_.Properties.'Last-Modified').ToUniversalTime()).TotalSeconds })
    $age = if ($ages.Count) { ($ages | Measure-Object -Minimum).Minimum } else { $null }

    $action = 'none'
    if ($power -eq 'stopped') { $action = 'deallocate (stopped but allocated)' }
    elseif ($power -in 'running', 'starting') {
        $leaseless = ($null -eq $age) -or ($age -gt $LeaseTTL + $Grace)
        if ($leaseless -and (($null -eq $since) -or ($since -gt $StartGrace))) { $action = 'deallocate (no live lease)' }
    }
    if ($action -ne 'none') {
        Invoke-WebRequest -UseBasicParsing -Method Post -Headers $arm -Body '' `
            -Uri "https://management.azure.com$($r.vmId)/deallocate?api-version=$api" | Out-Null
    }
    Write-Output ("{0}: power={1} leaseAge={2} sinceChange={3} action={4}" -f $r.code, $power, $age, $since, $action)
  } catch {
    Write-Output ("{0}: error {1}" -f $r.code, $_.Exception.Message)
  }
}
