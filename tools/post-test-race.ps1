<#
.SYNOPSIS
Feeds a test race with Time Machine results and barcode scans at race-like rates, for
testing the results view (tm-csv-connector #156) without the hardware.

.DESCRIPTION
Posts directly to /_postresult and /_postbib, as tm-reader-client and barcode-scanner-client do.
Finishers arrive in bursts (several a second) and lulls. Scans arrive a few seconds after
their results, in finish order as in the chute. A few finishers are never scanned (each needs
an Ins), and some results carry a keypad bib. Optionally, a finisher is scanned but missed by
the TM, so the operator has to add a result for it.

Create the race first in the Races view, and select it on the results page. Selecting it
rewrites the output CSV for that race, and syncthing copies the CSV to the RDS laptop, so
don't run this while RDS is importing a real race.

.EXAMPLE
.\post-test-race.ps1 -RaceId 12 -WhatIf     # show the schedule without posting
.\post-test-race.ps1 -RaceId 12 -Count 60
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][int]$RaceId,
    [int]$Count = 60,                          # number of finishers
    [string]$BaseUrl = 'http://tm.localhost:8080',
    [int]$MissedScans = 2,                     # finishers never scanned
    [int]$MissedResults = 0,                   # finishers scanned but missed by the TM
    [int]$KeypadPct = 30,                      # results with a bib typed on the TM keypad
    [int]$FirstPos = 1,                        # TM position of the first result; continue a run with the next pos
    [int]$Seed = 0                             # nonzero for a repeatable schedule
)

$rand = if ($Seed) { [System.Random]::new($Seed) } else { [System.Random]::new() }
$bibs = 101..499 | Sort-Object { $rand.Next() } | Select-Object -First ($Count + $MissedResults)
# spread the missed scans and results over the run
$missed = 0..($Count - 1) | Sort-Object { $rand.Next() } | Select-Object -First $MissedScans
$extra = 0..($Count - 1) | Sort-Object { $rand.Next() } | Select-Object -First $MissedResults

# build the schedule: seconds since start for each result and scan
$events = @()
$t = 0.0
$lastscan = 0.0
$extrabib = $Count
$burst = $false
for ($i = 0; $i -lt $Count; $i++) {
    # switch between bursts and lulls now and then
    if ($rand.Next(100) -lt 20) { $burst = -not $burst }
    $t += if ($burst) { 0.3 + $rand.NextDouble() * 0.9 } else { 1.0 + $rand.NextDouble() * 5.0 }

    $pos = $FirstPos + $i
    $bib = $bibs[$i]
    # elapsed race time starts at 20:00, later for a continued run so times keep increasing
    $elapsed = [TimeSpan]::FromSeconds(20 * 60 + ($FirstPos - 1) * 3 + $t)
    $result = [ordered]@{ opcode = 'primary'; raceid = "$RaceId"; pos = $pos; time = $elapsed.ToString('hh\:mm\:ss\.ff') }
    if ($rand.Next(100) -lt $KeypadPct) {
        $result.opcode = 'select'
        $result.bibno = $bib
    }
    $events += [pscustomobject]@{ At = $t; Kind = 'result'; Url = '/_postresult'; Body = $result; Note = "pos $pos bib $bib" }

    # scans come in finish order, at least half a second apart
    if ($missed -notcontains $i) {
        $lastscan = [Math]::Max($t + 2.0 + $rand.NextDouble() * 4.0, $lastscan + 0.5)
        $scan = [ordered]@{ opcode = 'scannedbib'; raceid = "$RaceId"; bibno = "$bib" }
        $events += [pscustomobject]@{ At = $lastscan; Kind = 'scan'; Url = '/_postbib'; Body = $scan; Note = "bib $bib (pos $pos)" }
    } else {
        $events[-1].Note += ', not scanned (needs Ins)'
    }
    if ($extra -contains $i) {
        $lastscan += 0.5
        $stray = $bibs[$extrabib++]
        $scan = [ordered]@{ opcode = 'scannedbib'; raceid = "$RaceId"; bibno = "$stray" }
        $events += [pscustomobject]@{ At = $lastscan; Kind = 'scan'; Url = '/_postbib'; Body = $scan; Note = "bib $stray, missed by TM after pos $pos (needs a result added)" }
    }
}
$events = $events | Sort-Object At

$start = Get-Date
foreach ($e in $events) {
    $wait = $e.At - ((Get-Date) - $start).TotalSeconds
    if ($wait -gt 0 -and -not $WhatIfPreference) { Start-Sleep -Milliseconds ([int]($wait * 1000)) }
    $line = '{0,7:0.0}s {1,-6} {2}' -f $e.At, $e.Kind, $e.Note
    if ($PSCmdlet.ShouldProcess($line, "POST $($e.Url)")) {
        $resp = Invoke-RestMethod -Method Post -Uri "$BaseUrl$($e.Url)" -ContentType 'application/json' -Body ($e.Body | ConvertTo-Json -Compress)
        Write-Host "$line -> $($resp.status)"
    }
}
Write-Host "done: next -FirstPos is $($FirstPos + $Count)"
