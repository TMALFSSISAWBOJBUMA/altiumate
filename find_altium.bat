@echo off

set "altium="

REM Get Altium Designer path
for /f "tokens=*" %%A in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Altium\Builds"') do (
    for /f "tokens=2*" %%B in ('reg query "%%A" /v ProgramsInstallPath ^| find "ProgramsInstallPath"') do (
        set altium=%%C\X2.exe
        goto end
    )
)
:end

if "%altium%"=="" (
    echo Altium Designer not found
    exit /B 2
)

echo %altium% > %~dp0\.altium_exe
exit /B 0
