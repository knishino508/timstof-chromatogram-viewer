# timsTOF Chromatogram Viewer

A fast, interactive chromatogram viewer for Bruker timsTOF data (`.d` folders), built with PyQt6 and pyqtgraph.

## Download (Windows)

A pre-built Windows executable is available — no Python installation required.

👉 **[Download timsTOF_Viewer.zip](https://www.dropbox.com/scl/fi/oxkzn978jr1jjex6nhtgd/timstof_chromatgram_viewer_v1.0.0.zip?rlkey=4s29whsowtbcfffjj4ki0yzkk&st=0ggn05nr&dl=1)**

### Installation

1. Download and extract the zip file
2. **Place the extracted `timsTOF_Viewer` folder directly under `C:\`**
   ```
   C:\timsTOF_Viewer\timsTOF_Viewer.exe   ✅ Recommended
   C:\Users\yourname\Downloads\timsTOF_Viewer\timsTOF_Viewer.exe   ❌ Avoid
   ```
3. Run `timsTOF_Viewer.exe`

> ⚠️ **Important:** Both the executable and your `.d` data files must be placed in paths that contain **ASCII characters only**. Paths with Japanese or other multi-byte characters will cause data loading to fail silently. Placing files directly under `C:\` is the safest option.

---

## Features

- **TIC / BPI** for MS1 and MS2
- **XIC (Extracted Ion Chromatogram)** with m/z and ppm tolerance settings
- **Multi-XIC** from CSV input or DIA-NN output (RT QC mode)
- **Pump pressure** monitoring (Pump A / Pump B)
- **Overlay or stacked** plot display
- **X-axis linked** across all stacked plots for synchronized zooming
- Load a parent folder (auto-discovers all `.d` files) or add a single `.d` file
- Global normalization across all loaded files

## Requirements (for running from source)

- **Python 3.11** (opentimspy does not work with Python 3.12 or later)
- [opentimspy](https://github.com/MatteoLacki/opentimspy)
- PyQt6
- pyqtgraph
- numpy
- pandas

Install dependencies:

```bash
pip install opentimspy PyQt6 pyqtgraph numpy pandas
```

> **Note:** `opentimspy` requires the Bruker TDF SDK (`timsdata.dll` on Windows). This is bundled automatically in the pre-built `.exe`.

## Usage

### Run from source

```bash
python timstof_chromatogram.py
```

### Build standalone executable (Windows)

Edit `build.bat` if needed to match your virtual environment path, then run:

```bash
build.bat
```

The executable will be generated at `dist\timsTOF_Viewer\timsTOF_Viewer.exe`.

> Requires PyInstaller installed in your Python 3.11 virtual environment.

## ⚠️ Known Issues

### Japanese / multi-byte characters in path

`opentimspy` internally uses the Bruker TDF SDK, which does not support paths containing Japanese or other multi-byte characters. If the `.exe` or your `.d` data files are located in such a path, data loading will silently fail.

**Workaround:** Place both the application and data files in a path with ASCII characters only. Directly under `C:\` is strongly recommended.

```
# NG — Japanese characters in path
C:\ユーザー\データ\sample.d
C:\Users\山田太郎\Downloads\timsTOF_Viewer\timsTOF_Viewer.exe

# OK — ASCII only
C:\timsTOF_Viewer\timsTOF_Viewer.exe
C:\Data\sample.d
```

## File Structure

```
timstof_chromatogram/
├── timstof_chromatogram.py   # Main application
├── timsTOF_viewer.spec       # PyInstaller build spec
└── build.bat                 # Windows build script
```

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
