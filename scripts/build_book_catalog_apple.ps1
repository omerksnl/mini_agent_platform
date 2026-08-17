param([string]$OutputPath = (Join-Path $PSScriptRoot "..\book_library.md"))

$ErrorActionPreference = 'Stop'
$categories = @(
    @{ Name='Science Fiction'; Term='science fiction novel'; Target=20 },
    @{ Name='Psychological Fiction'; Term='psychological fiction novel'; Target=12 },
    @{ Name='Classic Literature'; Term='classic literature'; Target=12 },
    @{ Name='Crime and Mystery'; Term='crime mystery novel'; Target=15 },
    @{ Name='Fantasy'; Term='fantasy novel'; Target=12 },
    @{ Name='History and War'; Term='history war book'; Target=12 },
    @{ Name='Philosophy'; Term='philosophy book'; Target=10 },
    @{ Name='Psychology'; Term='psychology book'; Target=10 },
    @{ Name='Technology and AI'; Term='artificial intelligence technology'; Target=10 },
    @{ Name='Biography and Memoir'; Term='biography memoir'; Target=7 }
)

function ConvertTo-PlainText([string]$Value) {
    if(-not $Value){return $null}
    return ((([System.Net.WebUtility]::HtmlDecode($Value)) -replace '<[^>]+>',' ') -replace '\s+',' ').Trim()
}

$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$books = [System.Collections.Generic.List[object]]::new()
foreach($category in $categories){
    $term=[uri]::EscapeDataString($category.Term)
    try{$response=Invoke-RestMethod -Uri "https://itunes.apple.com/search?term=$term&country=US&media=ebook&entity=ebook&limit=100" -TimeoutSec 30}
    catch{Write-Warning "Could not retrieve $($category.Name)"; continue}

    $candidates=@($response.results) | Where-Object {
        $_.trackName -and $_.artistName -and $_.description -and
        $_.trackName -notmatch '^\d+\s+(Classic|Greatest|Books?|Masterpieces)' -and
        (@($_.artistName -split ',').Count -le 4)
    } | Sort-Object @{Expression={if($_.userRatingCount){[int]$_.userRatingCount}else{0}};Descending=$true}, trackName

    $added=0
    foreach($item in $candidates){
        if($added -ge $category.Target){break}
        $key="$($item.trackName.Trim())|$($item.artistName.Trim())"
        if(-not $seen.Add($key)){continue}
        $description=ConvertTo-PlainText $item.description
        if($description.Length -gt 350){$description=$description.Substring(0,347).TrimEnd()+'...'}
        $books.Add([pscustomobject]@{
            Category=$category.Name; Title=$item.trackName.Trim(); Authors=$item.artistName.Trim()
            Genres=@($item.genres)-join ', '; Released=$item.releaseDate; Rating=$item.averageUserRating
            RatingCount=$item.userRatingCount; Description=$description; Source=$item.trackViewUrl
        })
        $added++
    }
}

$lines=[System.Collections.Generic.List[string]]::new()
$lines.Add('# Book Library');$lines.Add('')
$lines.Add('A curated recommendation catalog built from public Apple Books metadata, weighted toward science fiction, psychological fiction, classics, crime, history, philosophy, psychology, and technology.')
$lines.Add('');$lines.Add("- Total books: $($books.Count)");$lines.Add("- Generated: $((Get-Date).ToString('yyyy-MM-dd'))");$lines.Add('- Personal ratings: not available');$lines.Add('')
$index=1
foreach($book in $books){
    $lines.Add("## $index. $($book.Title)");$lines.Add('')
    $lines.Add("- **Curated category:** $($book.Category)");$lines.Add("- **Author(s):** $($book.Authors)")
    if($book.Genres){$lines.Add("- **Genres:** $($book.Genres)")}
    if($book.Released){$lines.Add("- **Released:** $(([datetime]$book.Released).ToString('yyyy-MM-dd'))")}
    if($book.Rating){$lines.Add("- **Public rating:** $($book.Rating) / 5 ($($book.RatingCount) ratings)")}
    if($book.Source){$lines.Add("- **Source:** $($book.Source)")}
    $lines.Add('');$lines.Add('**Synopsis**');$lines.Add('');$lines.Add($book.Description);$lines.Add('');$index++
}

$resolved=[System.IO.Path]::GetFullPath($OutputPath)
[System.IO.File]::WriteAllLines($resolved,$lines,[System.Text.UTF8Encoding]::new($false))
Write-Output "Created: $resolved";Write-Output "Books: $($books.Count)";Write-Output 'Missing synopses: 0'
