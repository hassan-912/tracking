"""Read the text in a screenshot with Windows' own text recognition (Windows.Media.Ocr).

Used for TLS, where the program may not read the web page itself (Cloudflare refuses
browsers a program controls), so it reads the picture of the window instead.
Nothing is installed: it runs a short script in Windows PowerShell 5.1, which has
access to the Windows Runtime OCR engine on every Windows 10 / 11 PC.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

_SCRIPT = r"""
param([string]$Path)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$result.Lines | ForEach-Object { $_.Text }
$stream.Dispose()
"""


def read_text(png: bytes) -> list[str]:
    """Lines of text in the picture ([] if Windows couldn't read it)."""
    with tempfile.TemporaryDirectory(prefix="ocr-") as tmp:
        image, script = Path(tmp) / "shot.png", Path(tmp) / "ocr.ps1"
        image.write_bytes(png)
        script.write_text(_SCRIPT, encoding="utf-8-sig")
        try:
            done = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), str(image)],
                capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return []
    if done.returncode:
        return []
    return [" ".join(l.split()) for l in done.stdout.decode("utf-8", "replace").splitlines()
            if l.strip()]
