param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [string]$OutputPath = (Join-Path $PSScriptRoot "..\movie_series_library.md")
)

$ErrorActionPreference = "Stop"
$rows = Import-Csv -LiteralPath $CsvPath

$catalog = $rows | ForEach-Object -Parallel {
    $row = $_
    $mediaType = if ($row.'Title Type' -match 'TV|Series|Mini') { 'series' } else { 'movie' }
    $description = $null

    try {
        $uri = "https://v3-cinemeta.strem.io/meta/$mediaType/$($row.Const).json"
        $result = Invoke-RestMethod -Uri $uri -TimeoutSec 20
        $description = $result.meta.description
    }
    catch {
        # A missing external synopsis must not prevent the remaining catalog from being built.
    }

    [pscustomobject]@{
        Position = [int]$row.Position
        Const = $row.Const
        Title = $row.Title
        OriginalTitle = $row.'Original Title'
        TitleType = $row.'Title Type'
        Year = $row.Year
        Genres = $row.Genres
        Runtime = $row.'Runtime (mins)'
        ImdbRating = $row.'IMDb Rating'
        PersonalRating = $row.'Your Rating'
        Directors = $row.Directors
        Url = $row.URL
        Description = $description
    }
} -ThrottleLimit 8 | Sort-Object Position

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# Movie and Series Library')
$lines.Add('')
$lines.Add('Personal IMDb watchlist catalog. Ratings and metadata originate from the supplied IMDb CSV export; synopses are retrieved by IMDb identifier from Cinemeta.')
$lines.Add('')
$lines.Add("- Total titles: $($catalog.Count)")
$lines.Add("- Generated: $((Get-Date).ToString('yyyy-MM-dd'))")
$lines.Add('')

foreach ($item in $catalog) {
    $lines.Add("## $($item.Position). $($item.Title) ($($item.Year))")
    $lines.Add('')
    $lines.Add("- **Type:** $($item.TitleType)")
    $lines.Add("- **Genres:** $($item.Genres)")
    if ($item.Runtime) { $lines.Add("- **Runtime:** $($item.Runtime) minutes") }
    if ($item.Directors) { $lines.Add("- **Director(s):** $($item.Directors)") }
    if ($item.ImdbRating) { $lines.Add("- **IMDb rating:** $($item.ImdbRating) / 10") }
    if ($item.PersonalRating) { $lines.Add("- **Personal rating:** $($item.PersonalRating) / 10") }
    if ($item.OriginalTitle -and $item.OriginalTitle -ne $item.Title) {
        $lines.Add("- **Original title:** $($item.OriginalTitle)")
    }
    $lines.Add("- **IMDb:** $($item.Url)")
    $lines.Add('')
    $lines.Add('**Synopsis**')
    $lines.Add('')
    $lines.Add($(if ($item.Description) { ($item.Description -replace '\s+', ' ').Trim() } else { 'Synopsis unavailable.' }))
    $lines.Add('')
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
[System.IO.File]::WriteAllLines($resolvedOutput, $lines, [System.Text.UTF8Encoding]::new($false))

$withSynopsis = @($catalog | Where-Object Description).Count
Write-Output "Created: $resolvedOutput"
Write-Output "Titles: $($catalog.Count)"
Write-Output "Synopses: $withSynopsis"
Write-Output "Missing synopses: $($catalog.Count - $withSynopsis)"
