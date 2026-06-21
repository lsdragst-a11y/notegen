param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("fonts", "tokens", "buttons", "surfaces")]
  [string[]]$Part
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

function Get-HeadFile([string]$Path) {
  $lines = git show "HEAD:$Path"
  if ($LASTEXITCODE -ne 0) { throw "Cannot read HEAD:$Path" }
  return ([string]::Join("`n", $lines) + "`n")
}

function Get-MarkedBlock([string]$Path, [string]$Name) {
  $source = Get-Content -Raw -Encoding UTF8 $Path
  $startMarker = "/* === $Name`: START === */"
  $endMarker = "/* === $Name`: END === */"
  $start = $source.IndexOf($startMarker)
  $end = $source.IndexOf($endMarker)
  if ($start -lt 0 -or $end -lt $start) { throw "Missing marked block: $Name" }
  $end += $endMarker.Length
  return $source.Substring($start, $end - $start)
}

function Stage-Content([string]$Path, [string]$Content) {
  $temp = New-TemporaryFile
  try {
    [System.IO.File]::WriteAllText($temp.FullName, $Content, $utf8NoBom)
    $blob = git hash-object -w -- $temp.FullName
    if ($LASTEXITCODE -ne 0) { throw "Cannot create blob for $Path" }
    git update-index --add --cacheinfo 100644 $blob $Path
    if ($LASTEXITCODE -ne 0) { throw "Cannot stage $Path" }
  } finally {
    Remove-Item -LiteralPath $temp.FullName -Force
  }
}

if ($Part -contains "fonts") {
  $layout = Get-HeadFile "web/app/layout.tsx"
  $layout = $layout.Replace(
    'import type { Metadata } from "next";',
    "import type { Metadata } from `"next`";`nimport { DM_Sans, DM_Serif_Display } from `"next/font/google`";"
  )
  $fontDeclarations = @'
const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
});

const dmSerifDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-dm-serif-display",
});
'@
  $layout = $layout.Replace("export const metadata: Metadata = {", "$fontDeclarations`n`nexport const metadata: Metadata = {")
  $layout = $layout.Replace(
    '<html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>',
    '<html lang="zh-CN" className={`h-full antialiased ${dmSans.variable} ${dmSerifDisplay.variable}`} suppressHydrationWarning>'
  )
  Stage-Content "web/app/layout.tsx" $layout
}

$cssParts = @(
  @{ Key = "tokens"; Name = "Warm Fold foundation tokens" },
  @{ Key = "buttons"; Name = "Warm Fold button primitives" },
  @{ Key = "surfaces"; Name = "Warm Fold surface primitives" }
)

if ($Part | Where-Object { $_ -in $cssParts.Key }) {
  $stagedCss = (Get-HeadFile "web/app/globals.css").TrimEnd()
  foreach ($cssPart in $cssParts) {
    if ($Part -contains $cssPart.Key) {
      $block = Get-MarkedBlock "web/app/globals.css" $cssPart.Name
      $stagedCss += "`n`n" + $block
    }
  }
  Stage-Content "web/app/globals.css" ($stagedCss + "`n")
}
