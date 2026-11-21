# FR #8698 / BOB-52: Priority this-box no-token gate. WinPS 5.1.

function Get-BobPriorityFuelRemaining {
    [CmdletBinding()]
    param(
        [string]$FixturePath,
        [Nullable[int]]$Remaining
    )
    if ($PSBoundParameters.ContainsKey('Remaining') -and $null -ne $Remaining) {
        return [int]$Remaining
    }
    $envRem = [string]$env:BOB_PRIORITY_FUEL_REMAINING
    if ($envRem -ne '' -and $envRem -match '^-?\d+$') {
        return [int]$envRem
    }
    $path = $FixturePath
    if (-not $path) { $path = [string]$env:BOB_PRIORITY_FUEL_FIXTURE }
    if ($path -and (Test-Path -LiteralPath $path)) {
        $doc = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($doc.PSObject.Properties.Name -contains 'remaining') {
            return [int]$doc.remaining
        }
        if ($doc.PSObject.Properties.Name -contains 'priority_remaining') {
            return [int]$doc.priority_remaining
        }
    }
    # Unknown: do not treat as exhausted (match Cursor unknown policy).
    return $null
}

function Test-BobPriorityFuelExhausted {
    [CmdletBinding()]
    param(
        [string]$FixturePath,
        [Nullable[int]]$Remaining
    )
    $rem = Get-BobPriorityFuelRemaining -FixturePath $FixturePath -Remaining $Remaining
    if ($null -eq $rem) { return $false }
    return ($rem -le 0)
}