<#
    run.ps1 -- regenerate the SPICE deck from netlist.py, run ngspice headlessly,
    parse the measured values and assert the design pass criteria of issue #10.

    Exit code 0 = all assertions pass, 1 = at least one assertion failed
    (ngspice does NOT exit nonzero on a .meas miss by itself, so we parse here).

    Usage:   pwsh -File run.ps1        (or)   powershell -File run.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
# use '.' as the decimal separator regardless of the machine's locale
[System.Threading.Thread]::CurrentThread.CurrentCulture =
    [System.Globalization.CultureInfo]::InvariantCulture
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# --- 1. regenerate the deck (single source of truth = ../netlist.py) ----------
Write-Host "== regenerating p48.cir from ../netlist.py ==" -ForegroundColor Cyan
python gen_deck.py
if ($LASTEXITCODE -ne 0) { throw "gen_deck.py failed" }

# --- 2. locate ngspice --------------------------------------------------------
$ng = $null
foreach ($n in 'ngspice_con.exe','ngspice.exe') {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c) { $ng = $c.Source; break }
}
if (-not $ng) {
    foreach ($c in @(
        "$env:LOCALAPPDATA\Programs\ngspice\Spice64\bin\ngspice_con.exe",
        "$HOME\tools\ngspice-46\Spice64\bin\ngspice_con.exe",
        "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\ngspice.exe")) {
        if (Test-Path $c) { $ng = $c; break }
    }
}
if (-not $ng) {
    throw "ngspice not found. Install it (see README.md) and add it to PATH."
}
Write-Host "== ngspice: $ng ==" -ForegroundColor Cyan

# --- 3. run headlessly, capture the full listing to out.log -------------------
& $ng -b p48.cir *>&1 | Tee-Object -FilePath out.log | Out-Null

# --- 4. parse "name = value" pairs (last occurrence wins) ---------------------
$vals = @{}
foreach ($line in Get-Content out.log) {
    $m = [regex]::Match($line, '^\s*([A-Za-z0-9_()]+)\s*=\s*([-+0-9.]+[eE][-+]?[0-9]+|[-+0-9.]+)')
    if ($m.Success) { $vals[$m.Groups[1].Value.ToLower()] = [double]$m.Groups[2].Value }
}
function V($k) {
    if ($vals.ContainsKey($k.ToLower())) { return $vals[$k.ToLower()] }
    return $null
}

# --- 5. assertions ------------------------------------------------------------
$fail = New-Object System.Collections.Generic.List[string]
$pass = 0
function Check($label, $val, $lo, $hi, $unit='') {
    if ($null -eq $val) { $script:fail.Add("MISSING  $label (value not found in out.log)"); return }
    $ok = ($val -ge $lo) -and ($val -le $hi)
    $tag = if ($ok) { 'PASS' } else { 'FAIL' }
    $col = if ($ok) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1,-34} = {2,12:g6} {3}  (expect {4}..{5})" -f $tag,$label,$val,$unit,$lo,$hi) -ForegroundColor $col
    if ($ok) { $script:pass++ } else { $script:fail.Add($label) }
}
function Note($label, $val, $unit='') {
    Write-Host ("  [info] {0,-34} = {1,12:g6} {2}" -f $label,$val,$unit) -ForegroundColor DarkGray
}

Write-Host "`n== 1. OPERATING POINT (rev-E: balanced pins #5, zener off the knee #3) ==" -ForegroundColor Cyan
Check 'V(P2)  hot pin'        (V 'v(p2)')   26.0 29.0 'V'
Check 'V(P3)  cold pin'       (V 'v(p3)')   26.0 29.0 'V'
Check 'I(RF2) pin-2 current'  (V 'irf2')    2.7e-3 3.2e-3 'A'
Check 'I(RF3) pin-3 current'  (V 'irf3')    2.7e-3 3.2e-3 'A'
Check 'V(VPIP) capsule rail'  (V 'v(vpip)') 6.8  7.8  'V'
Check 'I(D1)  zener current'  (V 'izener')  340e-6 470e-6 'A'   # R9->47k doubled the bias
$imb = [math]::Abs((V 'irf3') - (V 'irf2'))
Check 'pin imbalance |I3-I2|' $imb 0.0 0.15e-3 'A'   # rev-E rebalanced (was ~0.35 mA)

Write-Host "`n== 2. OUTPUT IMPEDANCE at pin 2 (rev-E emitter bypass: ~80 ohm, was ~10k #2) ==" -ForegroundColor Cyan
Check 'Zout @ 1 kHz'   (V 'zout_1k')  50 110 'ohm'
Check 'Zout @ 20 kHz'  (V 'zout_20k') 50 110 'ohm'
$zflat = [math]::Abs((V 'zout_20k') - (V 'zout_1k')) / (V 'zout_1k')
Check 'Zout flatness 1k..20k'      $zflat 0.0 0.05 ''
Note 'Zout @ 20 Hz (series-cap reactance)' (V 'zout_20') 'ohm'

Write-Host "`n== 3. AC GAIN capsule -> differential output (rev-E near-unity buffer) ==" -ForegroundColor Cyan
Check 'gain @ 1 kHz (near unity)' (V 'g_1k') -2.0 0.5 'dB'
$mbflat = (V 'g_mid_hi') - (V 'g_mid_lo')
Check 'passband flatness 100Hz-20kHz' $mbflat 0.0 1.0 'dB'
Check 'polarity: real(vdiff)@1k < 0'  (V 'vdre_1k') -1e9 0.0 'V'   # inverting (issue #6)
$lfdroop = (V 'g_1k') - (V 'g_20')
Note 'gain @ 20 Hz'        (V 'g_20')  'dB'
Check 'LF droop 1kHz->20Hz (bypass flattened)' $lfdroop 0.0 1.5 'dB'   # was ~4.3 dB

Write-Host "`n== 4. STARTUP transient (relates to issue #9) ==" -ForegroundColor Cyan
Check 'max Vce(Q1) during startup' (V 'vce_max') 0.0 35.0 'V'
Check 'V(VPIP) settled @ 15 s'     (V 'vpip_15s') 6.0 8.0 'V'
Note 'V(VPIP) @ 0.1 s' (V 'vpip_0p1') 'V'
Note 'V(VPIP) @ 1 s'   (V 'vpip_1s')  'V'
Note 'V(VPIP) @ 2 s'   (V 'vpip_2s')  'V'
Note 't to 90% of final' (V 't_90pct') 's'       # FINDING: ~0.7 s, faster than 5-10 s

Write-Host "`n== 5. POLARITY cross-check (transient blip) ==" -ForegroundColor Cyan
Check 'blip up for down-step (inverting)' (V 'vd_blip') 1e-4 1e9 'V'

Write-Host "`n== 6. NOISE (informational only -- zener avalanche noise NOT modelled) ==" -ForegroundColor Cyan
Note 'output noise total (meaningless abs.)' (V 'onoise_total') 'V'

# --- 6. verdict ---------------------------------------------------------------
Write-Host ""
if ($fail.Count -eq 0) {
    Write-Host "ALL $pass ASSERTIONS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("{0} passed, {1} FAILED:" -f $pass, $fail.Count) -ForegroundColor Red
    $fail | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
