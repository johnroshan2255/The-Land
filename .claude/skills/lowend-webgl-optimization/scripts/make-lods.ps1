<#
  Batch LOD generation with gltfpack (meshoptimizer CLI).

  ./make-lods.ps1 -In public/assets/props -Out public/assets/props/lod -Ratios 0.4,0.12

  For each NAME.glb writes NAME_lod0.glb (compressed only) and NAME_lodN.glb per ratio
  (simplified with -si -sa). -KeepNames keeps named nodes/materials (use for cars, colliders).
  Requires gltfpack on PATH (npm i -g gltfpack) or falls back to npx.
#>
param(
  [Parameter(Mandatory = $true)][string]$In,
  [string]$Out = "",
  [double[]]$Ratios = @(0.4, 0.12),
  [switch]$KeepNames,
  [switch]$KeepTopology # default adds -sa (needed for flat-shaded split-normal meshes); set to preserve topology
)

$gltfpack = (Get-Command gltfpack -ErrorAction SilentlyContinue)
function Invoke-Gltfpack([string[]]$GpArgs) {
  if ($gltfpack) { & gltfpack @GpArgs } else { & npx -y gltfpack @GpArgs }
  if ($LASTEXITCODE -ne 0) { throw "gltfpack failed: $GpArgs" }
}

$files = if (Test-Path $In -PathType Container) {
  Get-ChildItem $In -Filter *.glb | Where-Object { $_.BaseName -notmatch '_(lod\d+|col)$' }
} else { Get-Item $In }

if (-not $Out) { $Out = Join-Path (Split-Path ($files | Select-Object -First 1).FullName) 'lod' }
New-Item -ItemType Directory -Force $Out | Out-Null

$common = @('-cc')
if ($KeepNames) { $common += @('-kn', '-km') }

foreach ($f in $files) {
  $lod0 = Join-Path $Out "$($f.BaseName)_lod0.glb"
  Invoke-Gltfpack (@('-i', $f.FullName, '-o', $lod0) + $common)
  $i = 1
  foreach ($r in $Ratios) {
    $dst = Join-Path $Out "$($f.BaseName)_lod$i.glb"
    $extra = @('-si', "$r")
    if (-not $KeepTopology) { $extra += '-sa' }
    Invoke-Gltfpack (@('-i', $f.FullName, '-o', $dst) + $common + $extra)
    $i++
  }
  $sizes = Get-ChildItem $Out -Filter "$($f.BaseName)_lod*.glb" | ForEach-Object { "{0} {1:N1} KB" -f $_.Name, ($_.Length / 1KB) }
  Write-Output ($sizes -join ' | ')
}

