function Get-BobGitKindValidationError {
    param(
        [string]$Kind
    )
    if (-not $Kind) { return $null }
    if ($Kind -in @('mrb', 'build')) { return $null }
    return "kind must be mrb or build (got '$Kind')"
}

function Get-BobGitPacketKindValidationError {
    param($Packet)
    if (-not $Packet) { return $null }
    if ([string]$Packet.task -ne 'git') { return $null }
    return Get-BobGitKindValidationError -Kind ([string]$Packet.kind)
}
