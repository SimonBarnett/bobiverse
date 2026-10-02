function Get-BobWorkers {
    [CmdletBinding()]
    param()
    $overlay = Read-Overlay
    return @($overlay.workers)
}
