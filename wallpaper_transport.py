"""Read the configured user's wallpaper over existing WinRM; install nothing."""
import base64
import ipaddress
import json
import re
import socket

import winrm
from winrm.exceptions import InvalidCredentialsError


class WallpaperError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


# Static, read-only remote command. No credentials/paths are interpolated into PS.
# Use the authenticated user's SID/profile, never the first logged-on account.
READ_WALLPAPER = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $profileKey = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $sid
    $profile = (Get-ItemProperty -LiteralPath $profileKey -Name ProfileImagePath -ErrorAction SilentlyContinue).ProfileImagePath
    if (-not $profile) { $profile = [Environment]::GetFolderPath('UserProfile') }
    $profile = [Environment]::ExpandEnvironmentVariables($profile)
    $desktopKey = 'Registry::HKEY_USERS\' + $sid + '\Control Panel\Desktop'
    $original = (Get-ItemProperty -LiteralPath $desktopKey -Name WallPaper -ErrorAction SilentlyContinue).WallPaper
    $candidates = @()
    if ($profile -match '^[A-Za-z]:\\') {
        $candidates += Join-Path $profile 'AppData\Roaming\Microsoft\Windows\Themes\TranscodedWallpaper'
    }
    if ($original -match '^[A-Za-z]:\\') { $candidates += $original }
    $file = $null
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $item = Get-Item -LiteralPath $candidate
            if ($item.Length -gt 0 -and $item.Length -le 12582912) { $file = $item.FullName; break }
        }
    }
    if (-not $file) { @{status='no_wallpaper'} | ConvertTo-Json -Compress; exit 0 }
    Add-Type -AssemblyName System.Drawing
    $image = $null; $bitmap = $null; $graphics = $null; $memory = $null
    try {
        $image = [Drawing.Image]::FromFile($file)
        if ([long]$image.Width * $image.Height -gt 40000000) { throw 'image_size' }
        $scale = [Math]::Min(640.0 / $image.Width, 360.0 / $image.Height)
        $width = [Math]::Max(1, [int]($image.Width * $scale))
        $height = [Math]::Max(1, [int]($image.Height * $scale))
        $bitmap = New-Object Drawing.Bitmap($width, $height)
        $graphics = [Drawing.Graphics]::FromImage($bitmap)
        $graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.DrawImage($image, 0, 0, $width, $height)
        $memory = New-Object IO.MemoryStream
        $bitmap.Save($memory, [Drawing.Imaging.ImageFormat]::Jpeg)
        if ($memory.Length -gt 524288) { throw 'image_size' }
        @{status='ok'; image=[Convert]::ToBase64String($memory.ToArray())} | ConvertTo-Json -Compress
    } finally {
        if ($graphics) { $graphics.Dispose() }; if ($bitmap) { $bitmap.Dispose() }
        if ($image) { $image.Dispose() }; if ($memory) { $memory.Dispose() }
    }
} catch {
    @{status='unavailable'} | ConvertTo-Json -Compress
}
'''


def normalize_host(value):
    host = str(value or '').strip()
    if host.startswith('[') and ']' in host:
        host = host[1:host.index(']')]
    elif host.count(':') == 1 and host.rsplit(':', 1)[1].isdigit():
        host = host.rsplit(':', 1)[0]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        if not host or len(host) > 253 or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', host):
            raise WallpaperError('invalid_target') from None
        return host


def read_wallpaper(server):
    host = normalize_host(server.get('host'))
    user, password = server.get('username'), server.get('password_plain')
    if not isinstance(user, str) or not user.strip() or not isinstance(password, str) or not password:
        raise WallpaperError('no_credentials')
    port = None
    for candidate in (5986, 5985):
        try:
            with socket.create_connection((host, candidate), timeout=.8):
                port = candidate
                break
        except OSError:
            continue
    if port is None:
        raise WallpaperError('unavailable')
    address = f'[{host}]' if ':' in host else host
    endpoint = f'{"https" if port == 5986 else "http"}://{address}:{port}/wsman'
    session = None
    try:
        session = winrm.Session(endpoint, auth=(user, password), transport='ntlm',
                                proxy=None, server_cert_validation='validate',
                                message_encryption='always', operation_timeout_sec=8, read_timeout_sec=12)
        response = session.run_ps(READ_WALLPAPER)
        if response.status_code != 0 or len(response.std_out) > 800000:
            raise WallpaperError('unavailable')
        data = json.loads(response.std_out.decode('utf-8-sig').strip())
        if data.get('status') != 'ok':
            raise WallpaperError('no_wallpaper' if data.get('status') == 'no_wallpaper' else 'unavailable')
        image = base64.b64decode(data['image'], validate=True)
        if not image or len(image) > 524288:
            raise WallpaperError('invalid_image')
        return image
    except InvalidCredentialsError:
        # One authentication with exactly the registered username; no guessing.
        raise WallpaperError('authentication') from None
    except WallpaperError:
        raise
    except Exception:
        # Never propagate WinRM output, usernames, passwords or authenticated URLs.
        raise WallpaperError('unavailable') from None
    finally:
        if session is not None:
            try:
                transport_session = session.protocol.transport.session
                if transport_session is not None:
                    transport_session.close()
            except Exception:
                pass
