# Cross-Platform Setup

The primary engine is cross-platform:

- `ffmpeg` / `ffprobe` for video work,
- Python 3.8+,
- `pillow` and `numpy` from `scripts/requirements.txt`.

---

## Verify first

```bash
python3 --version
ffmpeg -version
ffprobe -version
python3 -c "import PIL, numpy"
```

If imports fail:

```bash
pip install -r scripts/requirements.txt
```

---

## macOS

### Homebrew

```bash
brew install ffmpeg
```

### No Homebrew

Use one of:
- static builds from evermeet.cx,
- static builds from johnvansickle.com,
- MacPorts:

```bash
sudo port install ffmpeg
```

If the binary is not on `PATH`, pass it directly:

```bash
python3 scripts/launch_video.py --config config.json --ffmpeg /path/to/ffmpeg
```

---

## Windows

Options:

```powershell
winget install Gyan.FFmpeg
```

or:

```powershell
choco install ffmpeg
```

or:

```powershell
scoop install ffmpeg
```

Manual option: download a static build from gyan.dev, unzip it, and add the `bin` folder to `PATH`.

If you do not want to edit `PATH`, pass the binary:

```powershell
python scripts/launch_video.py --config config.json --ffmpeg C:\Tools\ffmpeg\bin\ffmpeg.exe
```

Use `python` or `py -3` if `python3` is not the command on your Windows machine.

---

## Linux

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install ffmpeg python3 python3-pip
```

### Fedora

```bash
sudo dnf install ffmpeg python3 python3-pip
```

### Arch

```bash
sudo pacman -S ffmpeg python python-pip
```

### Static build

Use a johnvansickle static build if distro packages are unavailable or too old. Then pass the binary with `--ffmpeg /path/to/ffmpeg`.

---

## Python dependencies

From the skill directory:

```bash
pip install -r scripts/requirements.txt
```

The requirements include:
- `pillow` for graphics frames,
- `numpy` for synthesized music and SFX.

A virtual environment is recommended if system Python is locked down:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
```

Windows activation:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r scripts/requirements.txt
```

---

## Fonts

The skill bundles a font in `fonts/`. The config can override fonts:

```json
{
  "font": "path/to/Regular.ttf",
  "font_bold": "path/to/Bold.ttf"
}
```

If `font` or `font_bold` is `null`, the renderer uses the bundled font or falls back to system fonts. For emoji or non-Latin glyphs, choose a font that supports those glyphs.
