$ErrorActionPreference = "Continue"

$archiveRoot = "archive/2026-03-09_cleanup"

function Move-IfExists {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$ArchiveSubdir
    )

    if (-not (Test-Path $SourcePath)) {
        Write-Host "SKIP (not found): $SourcePath"
        return
    }

    $destDir = Join-Path $archiveRoot $ArchiveSubdir
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null

    try {
        Move-Item -Path $SourcePath -Destination $destDir -Force -ErrorAction Stop
        if (Test-Path $SourcePath) {
            Write-Warning "PARTIAL move detected for '$SourcePath'. Some files may still be locked."
        }
        else {
            Write-Host "MOVED: $SourcePath -> $destDir"
        }
    }
    catch {
        Write-Warning "FAILED to move '$SourcePath': $($_.Exception.Message)"
        Write-Warning "Close QGIS/file handles and rerun this script."
    }
}

Write-Host "Finalizing cleanup of previously locked paths..."

Move-IfExists -SourcePath "runs/paper_method/tile0816_result" -ArchiveSubdir "runs_paper_method_legacy"
Move-IfExists -SourcePath "runs/paper_method/tile0816_vector" -ArchiveSubdir "runs_paper_method_legacy"
Move-IfExists -SourcePath "runs/labeling" -ArchiveSubdir "runs_legacy"
Move-IfExists -SourcePath "runs/our_method" -ArchiveSubdir "runs_legacy"

Write-Host "Done."
