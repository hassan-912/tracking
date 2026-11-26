"""Read the text in a screenshot with Windows' own text recognition (Windows.Media.Ocr).

Used for TLS, where the program may not read the web page itself (Cloudflare refuses
browsers a program controls), so it reads the picture of the window instead.
Nothing is installed: it runs a short script in Windows PowerShell 5.1, which has
access to the Windows Runtime OCR engine on every Windows 10 / 11 PC.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
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
foreach ($line in $result.Lines) {
    $w = $line.Words
    $x = ($w | ForEach-Object { $_.BoundingRect.X } | Measure-Object -Minimum).Minimum
    $y = ($w | ForEach-Object { $_.BoundingRect.Y } | Measure-Object -Minimum).Minimum
    $r = ($w | ForEach-Object { $_.BoundingRect.X + $_.BoundingRect.Width } | Measure-Object -Maximum).Maximum
    $b = ($w | ForEach-Object { $_.BoundingRect.Y + $_.BoundingRect.Height } | Measure-Object -Maximum).Maximum
    "{0}`t{1}`t{2}`t{3}`t{4}" -f [int]$x, [int]$y, [int]$r, [int]$b, $line.Text
}
$stream.Dispose()
"""


@dataclass(frozen=True)
class Line:
    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def centre(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


def read_text(png: bytes) -> list[str]:
    """Lines of text in the picture ([] if Windows couldn't read it)."""
    return [line.text for line in read_lines(png)]


def read_lines(png: bytes) -> list[Line]:
    """Lines of text in the picture with where they are (pixels in the picture)."""
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
    lines = []
    for row in done.stdout.decode("utf-8", "replace").splitlines():
        parts = row.split("\t", 4)
        if len(parts) == 5 and parts[4].strip():
            lines.append(Line(" ".join(parts[4].split()), *map(int, parts[:4])))
    return lines
