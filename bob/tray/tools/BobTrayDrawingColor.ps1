# FR #7693: a missing colour must not throw "Cannot convert null to type System.Drawing.Color".
# Callers omit -TitleColor. A typed [System.Drawing.Color] parameter binds $null and throws
# before the function body. Resolve here and let the label keep its default.

function Resolve-BobTrayDrawingColor {
    param($Color)
    if ($null -eq $Color) { return $null }
    if ($Color -is [string] -and -not $Color.Trim()) { return $null }
    $c = $Color -as [System.Drawing.Color]
    if ($null -eq $c) { return $null }
    # Empty / transparent is "no override" so the tile default stays.
    if ($c.A -le 0) { return $null }
    return $c
}
