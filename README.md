# Scaricatore Di Porto

A clean and powerful desktop application to download videos and audio from YouTube and other platforms, with integrated transcription powered by Google Gemini (online) and VOSK (offline).

---

## Features

- **Video & Audio Downloads:** Download full videos in your preferred resolution (including 4K, 1440p, 1080p, ultra-wide, and 2:1 aspect ratios) or extract standalone audio tracks.
- **YouTube n-sig & 403 Protection:** Uses the lightweight Deno JavaScript runtime to solve modern YouTube signature challenges and prevent throttling or 403 Forbidden errors.
- **Browser Cookies Support:** Easily pass cookies from your browser (Chrome, Firefox, Brave, Edge, etc.) to download age-restricted or private playlist content.
- **Dual Transcription Engines:**
  - **Google Gemini (Online):** High-accuracy cloud transcription with multi-language support, custom prompts, and model selection (Gemini Flash / Pro).
  - **VOSK (Offline):** Fast, local, and private speech-to-text with zero internet connection required.
- **Encoding, Trimming & Hardware Acceleration:** Convert formats, cut video segments, and take advantage of GPU acceleration (NVIDIA NVENC, AMD AMF, Intel QSV).
- **Modern Dark/Light GUI:** Responsive interface built with CustomTkinter that matches your system theme.
- **Auto Play:** Automatically opens the media file with your default player once processing finishes.

---

## Requirements

- **Python 3.10+** (if running from source)
- **FFmpeg:** Required for merging video/audio streams, trimming, and encoding.
- **Deno (JavaScript Runtime):** Required by `yt-dlp` to solve YouTube security challenges.
  - *Pre-built Release (.zip):* **`deno.exe` is already bundled** alongside the executable — no setup required.
  - *Source Code:* Install via package manager (e.g. `winget install denoland.deno` on Windows, `brew install deno` on macOS) or download `deno.exe` directly into the project root.
- All Python dependencies are listed in `requirements.txt`.

---

## Installation (From Source)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Emanuele192/ScaricatoreDiPorto.git
   cd ScaricatoreDiPorto
   ```

2. **Create and activate a virtual environment:**
   - **Windows:**
     ```bash
     python -m venv .venv
     .\.venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Deno (if not already installed):**
   ```bash
   # Windows (Winget)
   winget install denoland.deno

   # Or download deno.exe directly into the repository folder
   ```

5. **Launch the application:**
   ```bash
   python ScaricatoreDiPorto.py
   ```

*(If you downloaded a pre-built release, simply extract the `.zip` and double-click `ScaricatoreDiPorto.exe` — Deno is already included).*

---

## Configuration

1. **FFmpeg:** The app checks your system `PATH` automatically. If FFmpeg isn't in your system PATH, you can set the path to your FFmpeg `bin` folder directly in the **Settings** tab.
2. **VOSK Models (Offline STT):** Language models download automatically on first use. The transcription will begin as soon as the model is unpacked into the app folder.
3. **Gemini API Key (Online STT):** To use Gemini transcription:
   - Grab a free API key from **[Google AI Studio](https://aistudio.google.com/)**.
   - Paste it in the **Settings** tab and click **Save Settings**.
4. **Browser Cookies (Optional):** Select your default browser in the Settings tab if you need to authenticate for restricted or member-only videos.

---

## Antivirus False Positives

Some antivirus programs might flag the standalone `.exe` as a generic detection. This is a well-known false positive common to unsigned applications built with PyInstaller. The program is completely safe, open-source, and you are always welcome to inspect the code or build it directly from source.

---

## Disclaimer

This software is developed for educational and personal backup purposes. The author is not responsible for any misuse of the tool. Please ensure you comply with the terms of service of the platforms you download from and respect copyright laws.
