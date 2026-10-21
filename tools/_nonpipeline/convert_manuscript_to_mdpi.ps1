param(
    [string]$MarkdownPath = "docs/PAPER_MANUSCRIPT copy.md",
    [string]$OutputDir = "docs/overleaf_package"
)

$ErrorActionPreference = 'Stop'

function Get-AbsolutePath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path (Get-Location) $Path
}

function Escape-CodeText {
    param([string]$Text)
    $escaped = $Text.Replace('\', '\textbackslash{}')
    $escaped = $escaped.Replace('{', '\{').Replace('}', '\}')
    $escaped = $escaped.Replace('_', '\_').Replace('%', '\%').Replace('&', '\&').Replace('#', '\#')
    return $escaped
}

function Protect-Token {
    param(
        [hashtable]$TokenMap,
        [string]$Value
    )

    $token = "@@TOKEN$($TokenMap.Count)@@"
    $TokenMap[$token] = $Value
    return $token
}

function Convert-InlineMarkdown {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $working = $Text
    $tokenMap = @{}

    $working = [regex]::Replace($working, 'https?://\S+', {
        param($match)
        $url = $match.Value
        $suffix = ''
        while ($url.Length -gt 0 -and @('.', ',', ';', ')') -contains $url[-1].ToString()) {
            $suffix = $url[-1] + $suffix
            $url = $url.Substring(0, $url.Length - 1)
        }
        $token = Protect-Token -TokenMap $tokenMap -Value ("\url{" + $url + "}")
        return $token + $suffix
    })

    $working = [regex]::Replace($working, '`([^`]+)`', {
        param($match)
        $code = Escape-CodeText $match.Groups[1].Value
        return Protect-Token -TokenMap $tokenMap -Value ("\texttt{" + $code + "}")
    })

    $working = [regex]::Replace($working, '\*\*([^*]+)\*\*', {
        param($match)
        $inner = Convert-InlineMarkdown $match.Groups[1].Value
        return Protect-Token -TokenMap $tokenMap -Value ("\textbf{" + $inner + "}")
    })

    $working = [regex]::Replace($working, '(?<!\*)\*([^*]+)\*(?!\*)', {
        param($match)
        $inner = Convert-InlineMarkdown $match.Groups[1].Value
        return Protect-Token -TokenMap $tokenMap -Value ("\textit{" + $inner + "}")
    })

    $segments = [regex]::Split($working, '(\$[^$]+\$)')
    $builder = New-Object System.Text.StringBuilder
    foreach ($segment in $segments) {
        if ($segment -match '^\$[^$]+\$$') {
            [void]$builder.Append($segment)
            continue
        }

        $escaped = $segment.Replace('\', '\textbackslash{}')
        $escaped = $escaped.Replace('&', '\&').Replace('%', '\%').Replace('#', '\#').Replace('_', '\_')
        $escaped = $escaped.Replace('{', '\{').Replace('}', '\}')
        [void]$builder.Append($escaped)
    }

    $result = $builder.ToString()
    foreach ($token in $tokenMap.Keys) {
        $result = $result.Replace($token, $tokenMap[$token])
    }

    return $result
}

function Strip-HeadingPrefix {
    param([string]$Heading)
    $trimmed = $Heading.Trim()
    $trimmed = [regex]::Replace($trimmed, '^\d+(\.\d+)*\.\s*', '')
    $trimmed = [regex]::Replace($trimmed, '^[A-Z](\.\d+)?\.\s*', '')
    $trimmed = [regex]::Replace($trimmed, '^Appendix\s+[A-Z]:\s*', '')
    return $trimmed.Trim()
}

function Convert-TableBlock {
    param(
        [string]$CaptionPrefix,
        [string]$CaptionText,
        [string[]]$TableLines
    )

    $rows = @()
    foreach ($line in $TableLines) {
        if ($line -match '^\|(?:\s*[-:]+\s*\|)+$') {
            continue
        }
        if ($line -match '^\|') {
            $cells = $line.Trim().Trim('|').Split('|') | ForEach-Object { Convert-InlineMarkdown $_.Trim() }
            $rows += ,@($cells)
        }
    }

    $captionBody = $null
    $captionLabel = $null
    if ($CaptionPrefix) {
        $captionBody = Convert-InlineMarkdown $CaptionText
        if ($CaptionPrefix -match 'Table\s+(\d+)') {
            $captionLabel = '\label{tab:' + $matches[1] + '}'
        }
    }

    if ($rows.Count -lt 1) {
        if ($captionBody) {
            return @(
                '\begin{table}[H]',
                '\caption{' + $captionBody + '}' + $captionLabel,
                '\end{table}'
            )
        }
        return @()
    }

    $columnCount = $rows[0].Count
    $columnSpec = ('Y' * $columnCount)
    $output = @()
    $useLongTable = $rows.Count -gt 20
    $longTableColumnSpec = @()
    $widthRatio = [math]::Round((0.92 / $columnCount), 2)
    if ($widthRatio -gt 0.45) {
        $widthRatio = 0.45
    }
    for ($columnIndex = 0; $columnIndex -lt $columnCount; $columnIndex++) {
        $longTableColumnSpec += '>{\RaggedRight\arraybackslash}p{' + $widthRatio.ToString('0.00', [System.Globalization.CultureInfo]::InvariantCulture) + '\textwidth}'
    }

    if ($useLongTable) {
        $output += '\begin{longtable}{' + ($longTableColumnSpec -join '') + '}'
        if ($captionBody) {
            $output += '\caption{' + $captionBody + '}' + $captionLabel + '\\'
        }
        $output += '\small'
    } else {
        $output += '\begin{table}[H]'
        if ($captionBody) {
            $output += '\caption{' + $captionBody + '}' + $captionLabel
        }
        $output += '\small'
        $output += '\begin{tabularx}{\textwidth}{' + $columnSpec + '}'
    }

    $output += '\toprule'
    $output += (($rows[0] -join ' & ') + '\\')
    if ($rows.Count -gt 1) {
        $output += '\midrule'
    }
    for ($rowIndex = 1; $rowIndex -lt $rows.Count; $rowIndex++) {
        $output += (($rows[$rowIndex] -join ' & ') + '\\')
    }
    $output += '\bottomrule'
    if ($useLongTable) {
        $output += '\end{longtable}'
    } else {
        $output += '\end{tabularx}'
        $output += '\end{table}'
    }
    return $output
}

function Emit-FigureBlock {
    param(
        [string]$CaptionPrefix,
        [string]$CaptionText,
        [string]$ImageRelativePath
    )

    $output = @()
    if ($ImageRelativePath -or $CaptionPrefix) {
        $captionBody = Convert-InlineMarkdown $CaptionText
        $captionLabel = ''
        if ($CaptionPrefix -match 'Figure\s+(\d+)') {
            $captionLabel = '\label{fig:' + $matches[1] + '}'
        }
        $output += '\begin{figure}[H]'
        if ($ImageRelativePath) {
            $output += '\centering'
            $output += '\includegraphics[width=0.92\textwidth]{' + $ImageRelativePath.Replace('\', '/') + '}'
        }
        $output += '\caption{' + $captionBody + '}'
        if ($captionLabel) {
            $output += $captionLabel
        }
        $output += '\end{figure}'
    }
    return $output
}

$markdownFullPath = Get-AbsolutePath $MarkdownPath
$outputFullDir = Get-AbsolutePath $OutputDir
$outputTexPath = Join-Path $outputFullDir 'PAPER_MANUSCRIPT_MDPI.tex'
$outputFigureDir = Join-Path $outputFullDir 'figures'
$outputManifestPath = Join-Path $outputFullDir 'OVERLEAF_ASSETS.txt'

New-Item -ItemType Directory -Path $outputFullDir -Force | Out-Null
New-Item -ItemType Directory -Path $outputFigureDir -Force | Out-Null

$lines = Get-Content -Path $markdownFullPath -Encoding UTF8

$title = ($lines[0] -replace '^#\s*', '').Trim()
function Get-MetadataValue {
    param(
        [string[]]$SourceLines,
        [string]$Pattern
    )

    foreach ($sourceLine in $SourceLines) {
        if ($sourceLine -match $Pattern) {
            return $matches[1].Trim()
        }
    }

    return ''
}

$authors = Get-MetadataValue -SourceLines $lines -Pattern '^\*\*Authors:\*\*\s*(.+)$'
$affiliation = Get-MetadataValue -SourceLines $lines -Pattern '^\*\*Affiliation:\*\*\s*(.+)$'
$corresponding = Get-MetadataValue -SourceLines $lines -Pattern '^\*\*Corresponding author:\*\*\s*(.+)$'
$abstract = Get-MetadataValue -SourceLines $lines -Pattern '^\*\*Abstract:\*\*\s*(.+)$'
$keywords = Get-MetadataValue -SourceLines $lines -Pattern '^\*\*Keywords:\*\*\s*(.+)$'

$bodyStart = 0
for ($index = 0; $index -lt $lines.Count; $index++) {
    if ($lines[$index] -match '^##\s+') {
        $bodyStart = $index
        break
    }
}

$bodyLines = $lines[$bodyStart..($lines.Count - 1)]
$output = New-Object System.Collections.Generic.List[string]

$output.Add('% Compile this file with pdfLaTeX inside the MDPI Overleaf template project.')
$output.Add('\documentclass[realestate,article,submit,pdftex,oneauthor]{Definitions/mdpi}')
$output.Add('\firstpage{1}')
$output.Add('\makeatletter')
$output.Add('\setcounter{page}{\@firstpage}')
$output.Add('\makeatother')
$output.Add('\pubvolume{1}')
$output.Add('\issuenum{1}')
$output.Add('\articlenumber{0}')
$output.Add('\pubyear{2026}')
$output.Add('\copyrightyear{2026}')
$output.Add('\datereceived{ }')
$output.Add('\daterevised{ }')
$output.Add('\dateaccepted{ }')
$output.Add('\datepublished{ }')
$output.Add('\usepackage{CJKutf8}')
$output.Add('\usepackage{longtable}')
$output.Add('\newcolumntype{Y}{>{\RaggedRight\arraybackslash}X}')
$output.Add('\appendixtitles{yes}')
$output.Add('')
$output.Add('\Title{' + (Convert-InlineMarkdown $title) + '}')
$output.Add('\Author{' + (Convert-InlineMarkdown $authors) + ' $^{1}$}')
$output.Add('\AuthorNames{' + (Convert-InlineMarkdown $authors) + '}')
$output.Add('\address{$^{1}$ \quad ' + (Convert-InlineMarkdown $affiliation) + '}')
$output.Add('\corres{Correspondence: ' + (Convert-InlineMarkdown $corresponding) + '}')
$output.Add('\abstract{' + (Convert-InlineMarkdown $abstract) + '}')
$output.Add('\keyword{' + (Convert-InlineMarkdown $keywords) + '}')
$output.Add('')
$output.Add('\begin{document}')
$output.Add('\begin{CJK*}{UTF8}{gbsn}')
$output.Add('')

$paragraphBuffer = New-Object System.Collections.Generic.List[string]
$pendingImage = $null
$insideAppendix = $false
$dataAvailabilityEntries = New-Object System.Collections.Generic.List[string]
$referenceEntries = New-Object System.Collections.Generic.List[string]
$collectingDataAvailability = $false
$collectingReferences = $false
$figureManifest = New-Object System.Collections.Generic.List[string]

function Flush-ParagraphBuffer {
    param([System.Collections.Generic.List[string]]$Buffer, [System.Collections.Generic.List[string]]$Sink)
    if ($Buffer.Count -eq 0) {
        return
    }
    $paragraph = ($Buffer.ToArray() -join ' ').Trim()
    if ($paragraph) {
        $Sink.Add((Convert-InlineMarkdown $paragraph))
        $Sink.Add('')
    }
    $Buffer.Clear()
}

$lineIndex = 0
while ($lineIndex -lt $bodyLines.Count) {
    $line = $bodyLines[$lineIndex]
    $trimmed = $line.Trim()

    if ($collectingDataAvailability) {
        if ($trimmed -match '^##\s+') {
            $collectingDataAvailability = $false
        } else {
            if ($trimmed -ne '') {
                $dataAvailabilityEntries.Add($trimmed)
            }
            $lineIndex++
            continue
        }
    }

    if ($collectingReferences) {
        if ($trimmed -match '^##\s+') {
            $collectingReferences = $false
        } else {
            if ($trimmed -ne '') {
                $referenceEntries.Add($trimmed)
            }
            $lineIndex++
            continue
        }
    }

    if ($trimmed -eq '') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $lineIndex++
        continue
    }

    if ($trimmed -match '^!\[[^\]]*\]\(([^)]+)\)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $pendingImage = $matches[1]
        $lineIndex++
        continue
    }

    if ($trimmed -match '^\*\*(Figure\s+[^.]+\.)\*\*\s*(.+)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $captionPrefix = $matches[1].Trim()
        $captionText = $matches[2].Trim()
        $figureRelativePath = $null
        if ($pendingImage) {
            $sourceImagePath = Join-Path (Split-Path -Parent $markdownFullPath) $pendingImage
            $leafName = Split-Path -Leaf $sourceImagePath
            $destImagePath = Join-Path $outputFigureDir $leafName
            Copy-Item -Path $sourceImagePath -Destination $destImagePath -Force
            $figureRelativePath = 'figures/' + $leafName
            $figureManifest.Add($figureRelativePath)
        }
        foreach ($figureLine in (Emit-FigureBlock -CaptionPrefix $captionPrefix -CaptionText $captionText -ImageRelativePath $figureRelativePath)) {
            $output.Add($figureLine)
        }
        $output.Add('')
        $pendingImage = $null
        $lineIndex++
        continue
    }

    if ($trimmed -match '^\*\*(Table\s+[^.]+\.)\*\*\s*(.+)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $captionPrefix = $matches[1].Trim()
        $captionText = $matches[2].Trim()
        $tableBlock = New-Object System.Collections.Generic.List[string]
        $lineIndex++
        while ($lineIndex -lt $bodyLines.Count -and [string]::IsNullOrWhiteSpace($bodyLines[$lineIndex])) {
            $lineIndex++
        }
        while ($lineIndex -lt $bodyLines.Count -and $bodyLines[$lineIndex].Trim().StartsWith('|')) {
            $tableBlock.Add($bodyLines[$lineIndex].Trim())
            $lineIndex++
        }
        foreach ($tableLine in (Convert-TableBlock -CaptionPrefix $captionPrefix -CaptionText $captionText -TableLines $tableBlock.ToArray())) {
            $output.Add($tableLine)
        }
        $output.Add('')
        continue
    }

    if ($trimmed.StartsWith('|')) {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $tableBlock = New-Object System.Collections.Generic.List[string]
        while ($lineIndex -lt $bodyLines.Count -and $bodyLines[$lineIndex].Trim().StartsWith('|')) {
            $tableBlock.Add($bodyLines[$lineIndex].Trim())
            $lineIndex++
        }
        foreach ($tableLine in (Convert-TableBlock -CaptionPrefix $null -CaptionText $null -TableLines $tableBlock.ToArray())) {
            $output.Add($tableLine)
        }
        $output.Add('')
        continue
    }

    if ($trimmed -match '^\$\$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $mathLines = New-Object System.Collections.Generic.List[string]
        if ($trimmed -match '^\$\$(.+)\$\$$') {
            $mathLines.Add($matches[1])
            $lineIndex++
        } else {
            $lineIndex++
            while ($lineIndex -lt $bodyLines.Count -and $bodyLines[$lineIndex].Trim() -ne '$$') {
                $mathLines.Add($bodyLines[$lineIndex])
                $lineIndex++
            }
            $lineIndex++
        }
        $output.Add('\[')
        foreach ($mathLine in $mathLines) {
            $output.Add($mathLine)
        }
        $output.Add('\]')
        $output.Add('')
        continue
    }

    if ($trimmed -match '^##\s+(.+)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $heading = $matches[1]
        if ($heading -eq 'Data Availability Statement') {
            $collectingDataAvailability = $true
            $lineIndex++
            continue
        }
        if ($heading -eq 'References') {
            $collectingReferences = $true
            $lineIndex++
            continue
        }
            if ($heading -like 'Appendix *') {
            if (-not $insideAppendix) {
                    $output.Add('\appendixstart')
                $output.Add('\appendix')
                $output.Add('')
                $insideAppendix = $true
            }
            $output.Add('\section{' + (Convert-InlineMarkdown (Strip-HeadingPrefix $heading)) + '}')
            $output.Add('')
            $lineIndex++
            continue
        }

        $output.Add('\section{' + (Convert-InlineMarkdown (Strip-HeadingPrefix $heading)) + '}')
        $output.Add('')
        $lineIndex++
        continue
    }

    if ($trimmed -match '^###\s+(.+)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $output.Add('\subsection{' + (Convert-InlineMarkdown (Strip-HeadingPrefix $matches[1])) + '}')
        $output.Add('')
        $lineIndex++
        continue
    }

    if ($trimmed -match '^####\s+(.+)$') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $output.Add('\subsubsection{' + (Convert-InlineMarkdown (Strip-HeadingPrefix $matches[1])) + '}')
        $output.Add('')
        $lineIndex++
        continue
    }

    if ($trimmed -match '^\d+\.\s+') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $output.Add('\begin{enumerate}')
        while ($lineIndex -lt $bodyLines.Count) {
            if ([string]::IsNullOrWhiteSpace($bodyLines[$lineIndex])) {
                $lineIndex++
                continue
            }
            if ($bodyLines[$lineIndex].Trim() -match '^\d+\.\s+(.+)$') {
                $itemText = [regex]::Replace($bodyLines[$lineIndex].Trim(), '^\d+\.\s+', '')
                $output.Add('\item ' + (Convert-InlineMarkdown $itemText))
                $lineIndex++
                continue
            }
            break
        }
        $output.Add('\end{enumerate}')
        $output.Add('')
        continue
    }

    if ($trimmed -match '^[-]\s+') {
        Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output
        $output.Add('\begin{itemize}')
        while ($lineIndex -lt $bodyLines.Count) {
            if ([string]::IsNullOrWhiteSpace($bodyLines[$lineIndex])) {
                $lineIndex++
                continue
            }
            if ($bodyLines[$lineIndex].Trim() -match '^[-]\s+(.+)$') {
                $itemText = [regex]::Replace($bodyLines[$lineIndex].Trim(), '^[-]\s+', '')
                $output.Add('\item ' + (Convert-InlineMarkdown $itemText))
                $lineIndex++
                continue
            }
            break
        }
        $output.Add('\end{itemize}')
        $output.Add('')
        continue
    }

    $paragraphBuffer.Add($trimmed)
    $lineIndex++
}

Flush-ParagraphBuffer -Buffer $paragraphBuffer -Sink $output

$dataAvailabilityText = 'Data supporting the reported results are available from the corresponding author upon reasonable request.'
if ($dataAvailabilityEntries.Count -gt 0) {
    $dataAvailabilityText = Convert-InlineMarkdown (($dataAvailabilityEntries.ToArray() -join ' '))
}

$authorContributionText = 'Conceptualization, methodology, software, formal analysis, investigation, data curation, writing---original draft preparation, writing---review and editing, visualization, supervision, and project administration, ' + (Convert-InlineMarkdown $authors) + '. The author has read and agreed to the published version of the manuscript.'

$output.Add('\authorcontributions{' + $authorContributionText + '}')
$output.Add('')
$output.Add('\funding{This research received no external funding.}')
$output.Add('')
$output.Add('\institutionalreview{Not applicable.}')
$output.Add('')
$output.Add('\informedconsent{Not applicable.}')
$output.Add('')
$output.Add('\dataavailability{' + $dataAvailabilityText + '}')
$output.Add('')
$output.Add('\acknowledgments{}')
$output.Add('')
$output.Add('\conflictsofinterest{The author declares no conflicts of interest.}')
$output.Add('')

if ($referenceEntries.Count -gt 0) {
    $output.Add('\reftitle{References}')
    $output.Add('')
    $output.Add('\begin{thebibliography}{999}')
    $output.Add('')
    for ($refIndex = 0; $refIndex -lt $referenceEntries.Count; $refIndex++) {
        $referenceText = Convert-InlineMarkdown $referenceEntries[$refIndex]
        $output.Add('\bibitem{ref' + ($refIndex + 1) + '}')
        $output.Add($referenceText)
        $output.Add('')
    }
    $output.Add('\end{thebibliography}')
    $output.Add('')
}

$output.Add('\end{CJK*}')
$output.Add('\end{document}')

Set-Content -Path $outputTexPath -Value $output -Encoding UTF8
Set-Content -Path $outputManifestPath -Value (($figureManifest | Sort-Object -Unique) -join [Environment]::NewLine) -Encoding UTF8

Write-Output "Generated: $outputTexPath"
Write-Output "Figure manifest: $outputManifestPath"