@echo off
:: SpyBLE - Windows Defender Firewall Configuration Helper
:: Run this script as Administrator to allow SpyBLE network communication

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Apaitountai dikaiomata diaxeiristi (Administrator).
    echo [!] Parakalo kante dexi klik sto arxeio kai epilexte 'Ektelesi os diaxeiristis' (Run as administrator).
    pause
    exit /b 1
)

echo [*] Rythmisi Teixous Prostasias (Windows Defender Firewall) gia to SpyBLE...

set "EXE_PATH=%~dp0SpyBLE.exe"
if not exist "%EXE_PATH%" (
    set "EXE_PATH=%~dp0dist\SpyBLE.exe"
)

if exist "%EXE_PATH%" (
    echo [+] Vrethike to ektelesimo: %EXE_PATH%
    netsh advfirewall firewall delete rule name="SpyBLE" >nul 2>&1
    netsh advfirewall firewall delete rule name="SpyBLE Out" >nul 2>&1

    netsh advfirewall firewall add rule name="SpyBLE" dir=in action=allow program="%EXE_PATH%" enable=yes profile=private,public description="Allow inbound traffic for SpyBLE"
    netsh advfirewall firewall add rule name="SpyBLE Out" dir=out action=allow program="%EXE_PATH%" enable=yes profile=private,public description="Allow outbound traffic for SpyBLE"
    
    echo.
    echo [OK] O kanonas teixous prostasias gia to SpyBLE prostethike me epitychia!
) else (
    echo [-] To SpyBLE.exe den vrethike ston trexonta fakelo.
    echo [*] Prosthiki genikou kanona gia ola ta ektelesima tou SpyBLE...
    netsh advfirewall firewall add rule name="SpyBLE Local" dir=in action=allow protocol=TCP localport=any profile=private
    echo [OK] O kanonas prostethike.
)

echo.
echo I diadikasia oloklirothike.
pause
