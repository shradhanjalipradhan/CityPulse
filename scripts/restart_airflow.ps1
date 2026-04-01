# restart_airflow.ps1 — Restore the CityPulse pipeline after a Docker restart.
# Run from the project root: .\scripts\restart_airflow.ps1

param(
    [switch]$SkipInstall,    # Skip pip install step (faster if already installed)
    [switch]$DryRun          # Print commands without executing
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Get-Item "$PSScriptRoot\..").FullName
$ContainerName = "airflow"

function Run($cmd) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] $cmd" -ForegroundColor DarkGray
    } else {
        Write-Host "> $cmd" -ForegroundColor Cyan
        Invoke-Expression $cmd
    }
}

Write-Host ""
Write-Host "=== CityPulse Airflow Restore ===" -ForegroundColor Green
Write-Host "Project root: $ProjectRoot"
Write-Host ""

# 1 — Check container is running
Write-Host "[1/6] Checking container..." -ForegroundColor Yellow
$state = docker inspect --format '{{.State.Status}}' $ContainerName 2>$null
if ($state -ne "running") {
    Write-Host "Container '$ContainerName' is not running (state: $state)." -ForegroundColor Red
    Write-Host "Start it first with: docker start $ContainerName"
    exit 1
}
Write-Host "      Container $ContainerName is running" -ForegroundColor Green

# 2 — Create project directory inside container
Write-Host "[2/6] Creating project directory in container..." -ForegroundColor Yellow
Run "docker exec --user root $ContainerName mkdir -p /opt/airflow/citypulse/models/saved_models"
Run "docker exec --user root $ContainerName chown -R airflow:root /opt/airflow/citypulse"

# 3 — Copy project files into container
Write-Host "[3/6] Copying project files..." -ForegroundColor Yellow
Run "docker cp `"$ProjectRoot\.`" `"${ContainerName}:/opt/airflow/citypulse/`""
Run "docker cp `"$ProjectRoot\.env`" `"${ContainerName}:/opt/airflow/citypulse/.env`""
Run "docker cp `"$ProjectRoot\dags\sensor_pipeline_dag.py`" `"${ContainerName}:/opt/airflow/dags/`""

# 4 — Install Python dependencies
if (-not $SkipInstall) {
    Write-Host "[4/6] Installing Python dependencies..." -ForegroundColor Yellow
    Run "docker exec $ContainerName pip install --quiet confluent-kafka supabase requests python-dotenv pandas numpy"
} else {
    Write-Host "[4/6] Skipping pip install (--SkipInstall)" -ForegroundColor DarkGray
}

# 5 — Unpause the DAG
Write-Host "[5/6] Unpausing citypulse_sensor_pipeline DAG..." -ForegroundColor Yellow
Run "docker exec $ContainerName airflow dags unpause citypulse_sensor_pipeline"

# 6 — Verify DAG is visible
Write-Host "[6/6] Verifying DAG registration..." -ForegroundColor Yellow
Run "docker exec $ContainerName airflow dags list | grep citypulse"

Write-Host ""
Write-Host "=== Pipeline Restored ===" -ForegroundColor Green
Write-Host "  Airflow UI: http://localhost:8080"
Write-Host "  DAG:        citypulse_sensor_pipeline"
Write-Host "  Schedule:   every 5 minutes"
Write-Host ""
