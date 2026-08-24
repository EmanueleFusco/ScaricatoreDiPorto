import sys
import os

# --- 1. SETUP DEI PERCORSI PER LA STRUTTURA CON _internal ---
# Se l'app è compilata con PyInstaller, sys.executable punta al file .exe
# Usiamo la cartella dove si trova l'exe per salvare le configurazioni e gli aggiornamenti
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# --- LOGGING DUAL STREAM (Console + File in ambiente di sviluppo) ---
if not getattr(sys, 'frozen', False):
    log_file_path = os.path.join(base_dir, "app_debug.log")
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("=== LOG AVVIO APPLICAZIONE ===\n")
    except Exception:
        pass

    class DualLogger:
        def __init__(self, stream, filepath):
            self.stream = stream
            self.filepath = filepath
        def write(self, message):
            if self.stream:
                try:
                    self.stream.write(message)
                    self.stream.flush()
                except Exception:
                    pass
            try:
                with open(self.filepath, "a", encoding="utf-8") as f:
                    f.write(message)
                    f.flush()
            except Exception:
                pass
        def flush(self):
            if self.stream:
                try:
                    self.stream.flush()
                except Exception:
                    pass

    if sys.stdout:
        sys.stdout = DualLogger(sys.stdout, log_file_path)
    if sys.stderr:
        sys.stderr = DualLogger(sys.stderr, log_file_path)

# --- 2. IL TRUCCO MAGICO ANTI-403 ---
# Inseriamo il file zip scaricato in CIMA ai percorsi di Python. 
# Questo forza il programma a ignorare la versione di yt-dlp dentro _internal.
yt_dlp_update_path = os.path.join(base_dir, "yt_dlp_update.zip")
if os.path.exists(yt_dlp_update_path):
    sys.path.insert(0, yt_dlp_update_path)

import yt_dlp
import customtkinter
import tkinter as tk 
from tkinter import filedialog
from datetime import timedelta
import threading
import subprocess
import re
import shutil
import json
import urllib.request
import zipfile
import wave
import time
import uuid

from vosk import Model, KaldiRecognizer
from google import genai

print("--- DIAGNOSTICA AMBIENTE ---")
print("Python Executable:", sys.executable)
print("Versione yt-dlp in uso:", yt_dlp.version.__version__)
print("Cartella base:", base_dir)
print("--------------------------")

original_path = os.environ.get("PATH", "")
icona_dir = os.path.join(base_dir, "images", "icona64.ico")

# Percorso di default ffmpeg (adatta il percorso se in _internal è posizionato diversamente)
default_ffmpeg_path = os.path.join(base_dir, "ffmpeg-master-latest-win64-gpl-shared", "bin")

# Assicura che base_dir e .venv\Scripts siano nel PATH per trovare deno.exe ed ffmpeg
for extra_p in [base_dir, os.path.join(base_dir, ".venv", "Scripts")]:
    if os.path.exists(extra_p) and extra_p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = extra_p + os.pathsep + os.environ.get("PATH", "")

def get_system_theme():
    if sys.platform == "win32":
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            apps_use_light_theme = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
            winreg.CloseKey(key)
            return "dark" if apps_use_light_theme == 0 else "light"
        except Exception:
            return "light"
    return "dark"

def load_config():
    config_path = os.path.join(base_dir, "config.json")
    default_config = {
        "appearance_mode": "system",
        "custom_ffmpeg_enabled": False,
        "custom_ffmpeg_path": default_ffmpeg_path,
        "gemini_api_key": "",
        "browser_cookies": "None" # Nuova impostazione per i Cookie
    }
    try:
        with open(config_path, "r") as file:
            loaded = json.load(file)
            default_config.update(loaded)
            return default_config
    except (FileNotFoundError, json.JSONDecodeError):
        return default_config

config = load_config()
customtkinter.set_default_color_theme("dark-blue")
customtkinter.set_appearance_mode(config["appearance_mode"] if config["appearance_mode"] != "system" else get_system_theme())

if shutil.which("ffmpeg") is None:
    os.environ["PATH"] += os.pathsep + default_ffmpeg_path

def detect_gpu_vendor_wmi():
    if sys.platform == "win32":
        try:
            import wmi 
            c = wmi.WMI()
            for gpu in c.Win32_VideoController():
                name = gpu.Name.lower()
                if "nvidia" in name: return "nvidia"
                elif "amd" in name or "radeon" in name: return "amd"
                elif "intel" in name: return "intel"
        except Exception: pass
    return "generic"

def get_codec_options():
    vendor = detect_gpu_vendor_wmi()
    codecs = ["x264", "x265"]
    if vendor == "nvidia": codecs += ["Nvidia x264", "Nvidia x265"]
    elif vendor == "amd": codecs += ["AMD x264", "AMD x265"]
    elif vendor == "intel": codecs += ["Intel x264", "Intel x265"]
    return codecs

def get_subprocess_flags():
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    return 0

VOSK_MODELS = {
    "English": {"folder": "vosk-model-small-en-us-0.15", "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"},
    "Italian": {"folder": "vosk-model-small-it-0.22", "url": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip"}
}

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Scaricatore di porto 2.5 - The Ganzest")
        if os.path.exists(icona_dir): self.iconbitmap(icona_dir)
        self.geometry("450x600")
        self.minsize(400, 600)
        self.maxsize(800, 900)
        
        my_font = customtkinter.CTkFont(family="Helvetica", size=13)
        self.setup_context_menu()
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.tabview = customtkinter.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.tabview.add("Download")
        self.tabview.add("Advanced")
        self.tabview.add("Settings")
        
        # --- Scheda DOWNLOAD ---
        self.download_tab = self.tabview.tab("Download")
        self.download_tab.grid_columnconfigure(0, weight=1)
        self.download_tab.grid_columnconfigure(1, weight=1)
        
        self.my_label = customtkinter.CTkLabel(self.download_tab, text="YouTube Downloader", font=("Impact",28))
        self.my_label.grid(row=1, column=0, columnspan=2, pady=10)
        
        self.url_text = customtkinter.StringVar()
        self.url_bar = customtkinter.CTkEntry(self.download_tab, font=my_font, placeholder_text="URL", textvariable=self.url_text)
        self.url_bar.grid(row=2, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        self.bind_context_menu(self.url_bar) 

        self.debounce_job = None
        self.url_text.trace_add("write", self.on_url_change)
        self.url_cache = {} # Info cache per evitare spam 403 API

        self.dir_frame = customtkinter.CTkFrame(self.download_tab, fg_color="transparent")
        self.dir_frame.grid(row=3, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        self.dir_frame.grid_columnconfigure(0, weight=1)
        self.folder = customtkinter.CTkEntry(self.dir_frame, font=my_font, placeholder_text="Default: internal/output")
        self.folder.grid(row=0, column=0, padx=8, sticky="ew")
        self.bind_context_menu(self.folder) 
        
        self.ask_dir = customtkinter.CTkButton(self.dir_frame, text="Browse", command=self.browse_folder, font=my_font)
        self.ask_dir.grid(row=0, column=1, padx=8)
        
        self.combo_frame = customtkinter.CTkFrame(self.download_tab, fg_color="transparent")
        self.combo_frame.grid(row=4, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        self.combo_frame.grid_columnconfigure(0, weight=1)
        self.combo = customtkinter.CTkComboBox(self.combo_frame, font=my_font, values=["Select Resolution"])
        self.combo.grid(row=0, column=0, padx=15, sticky="ew")
        self.audio_var = customtkinter.BooleanVar()
        self.audio_check = customtkinter.CTkSwitch(self.combo_frame, text="Audio Only", font=my_font, variable=self.audio_var)
        self.audio_check.grid(row=0, column=1, padx=10)
        self.audio_var.trace_add('write', self.on_audio_var_change)
        
        self.button_frame = customtkinter.CTkFrame(self.download_tab, fg_color="transparent")
        self.button_frame.grid(row=5, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.clear_button = customtkinter.CTkButton(self.button_frame, text="Clear", command=self.clear_bar, font=my_font)
        self.clear_button.grid(row=0, column=0, padx=10, sticky="ew")
        
        self.download_button = customtkinter.CTkButton(self.download_tab, text="Download", font=my_font, command=self.init_download)
        self.download_button.grid(row=6, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        self.download_button.configure(state='disabled')
        
        self.error_label = customtkinter.CTkLabel(self.download_tab, text="", text_color="red", font=my_font)
        self.error_label.grid(row=7, column=0, columnspan=2, pady=5, padx=20, sticky="w")
        
        self.status_frame = customtkinter.CTkFrame(self.download_tab, fg_color="transparent")
        self.status_frame.grid(row=8, column=0, columnspan=2, pady=5, padx=20, sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_frame.grid_columnconfigure(1, weight=1)
        self.download_label = customtkinter.CTkLabel(self.status_frame, text="", text_color="green", font=my_font)
        self.download_label.grid(row=0, column=0, sticky="w")
        self.speed_label = customtkinter.CTkLabel(self.status_frame, text="", text_color="blue", font=my_font)
        self.speed_label.grid(row=0, column=1, sticky="e")
        
        self.progress_bar = customtkinter.CTkProgressBar(self.download_tab)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=9, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        
        # --- Scheda ADVANCED ---
        self.advanced_tab = self.tabview.tab("Advanced")
        self.advanced_tab.grid_columnconfigure(0, weight=1)
        
        self.encode_switch_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.encode_switch_frame.grid(row=1, column=0, padx=20, pady=(10,5), sticky="ew")
        self.encode = customtkinter.BooleanVar()
        self.encode_button = customtkinter.CTkSwitch(self.encode_switch_frame, text="Encode", font=my_font, variable=self.encode, command=self.on_encode_change)
        self.encode_button.grid(row=0, column=0, sticky="w")
        
        self.codec_options_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.codec_options_frame.grid(row=2, column=0, padx=20, pady=(5,10), sticky="ew")
        self.codec_options_frame.grid_columnconfigure(0, weight=1); self.codec_options_frame.grid_columnconfigure(1, weight=1)
        self.encode_box = customtkinter.CTkComboBox(self.codec_options_frame, font=my_font, values=get_codec_options())
        self.encode_box.grid(row=0, column=0, padx=10, sticky="ew")
        self.encode_audio_box = customtkinter.CTkComboBox(self.codec_options_frame, font=my_font, values=["aac", "mp3", "opus"])
        self.encode_audio_box.grid(row=0, column=1, padx=10, sticky="ew")
        
        self.trim_switch_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.trim_switch_frame.grid(row=3, column=0, padx=20, pady=(10,5), sticky="ew")
        self.trim = customtkinter.BooleanVar()
        self.trim_button = customtkinter.CTkSwitch(self.trim_switch_frame, text="Trim", font=my_font, variable=self.trim, command=self.on_trim_change)
        self.trim_button.grid(row=0, column=0, sticky="w")
        
        self.trim_options_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.trim_options_frame.grid(row=4, column=0, padx=20, pady=(5,10), sticky="ew")
        self.trim_options_frame.grid_columnconfigure(0, weight=1); self.trim_options_frame.grid_columnconfigure(1, weight=1)
        self.trim_start = customtkinter.CTkEntry(self.trim_options_frame, font=my_font, placeholder_text="Start: 00:00:00.000")
        self.trim_start.grid(row=0, column=0, padx=10, sticky="ew")
        self.bind_context_menu(self.trim_start)
        self.trim_end = customtkinter.CTkEntry(self.trim_options_frame, font=my_font, placeholder_text="End: 00:00:00.000")
        self.trim_end.grid(row=0, column=1, padx=10, sticky="ew")
        self.bind_context_menu(self.trim_end)
        
        self.auto_play_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.auto_play_frame.grid(row=5, column=0, padx=20, pady=(10,5), sticky="ew")
        self.play = customtkinter.BooleanVar()
        self.play_check = customtkinter.CTkSwitch(self.auto_play_frame, text="Auto Play", font=my_font, variable=self.play)
        self.play_check.grid(row=0, column=0, sticky="w")
        
        self.transcribe = customtkinter.BooleanVar()
        self.transcribe_switch = customtkinter.CTkSwitch(self.advanced_tab, text="Transcribe", font=my_font, variable=self.transcribe, command=self.on_transcribe_change)
        self.transcribe_switch.grid(row=6, column=0, padx=20, pady=(10,5), sticky="w")
        
        self.transcription_options_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.transcription_options_frame.grid(row=7, column=0, padx=20, pady=(5,0), sticky="ew")
        self.transcription_options_frame.grid_columnconfigure(1, weight=1)
        self.engine_label = customtkinter.CTkLabel(self.transcription_options_frame, text="Engine:", font=my_font)
        self.engine_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.transcription_engine_combo = customtkinter.CTkComboBox(self.transcription_options_frame, font=my_font, values=["VOSK", "Gemini"], command=self.on_engine_change)
        self.transcription_engine_combo.grid(row=0, column=1, sticky="ew")
        
        self.language_label = customtkinter.CTkLabel(self.transcription_options_frame, text="Lang (VOSK):", font=my_font)
        self.language_label.grid(row=1, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        self.transcription_language_combo = customtkinter.CTkComboBox(self.transcription_options_frame, font=my_font, values=list(VOSK_MODELS.keys()))
        self.transcription_language_combo.grid(row=1, column=1, sticky="ew", pady=(10, 0))

        self.gemini_options_frame = customtkinter.CTkFrame(self.advanced_tab, fg_color="transparent")
        self.gemini_options_frame.grid(row=8, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.gemini_options_frame.grid_columnconfigure(1, weight=1)
        
        self.gemini_model_label = customtkinter.CTkLabel(self.gemini_options_frame, text="Gemini Model:", font=my_font)
        self.gemini_model_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(5,0))
        self.gemini_model_combo = customtkinter.CTkComboBox(self.gemini_options_frame, font=my_font, values=["gemini-flash-latest","gemini-flash-lite-latest","gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"])
        self.gemini_model_combo.grid(row=0, column=1, sticky="ew", pady=(5,0))
        self.gemini_lang_label = customtkinter.CTkLabel(self.gemini_options_frame, text="Output Lang:", font=my_font)
        self.gemini_lang_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5,0))
        self.gemini_language_combo = customtkinter.CTkComboBox(self.gemini_options_frame, font=my_font, values=["Original Language", "Italian", "English", "French", "German", "Spanish"])
        self.gemini_language_combo.grid(row=1, column=1, sticky="ew", pady=(5,0))
        self.on_transcribe_change() 

        # --- Scheda SETTINGS ---
        self.settings_tab = self.tabview.tab("Settings")
        self.settings_tab.grid_columnconfigure(0, weight=1)
        self.settings_tab.grid_columnconfigure(1, weight=1)
        
        # --- NOVITÀ: Browser Cookies (Fix 403 aggiuntivo) ---
        self.browser_cookies_label = customtkinter.CTkLabel(self.settings_tab, text="Browser Cookies (Fix 403):", font=my_font)
        self.browser_cookies_label.grid(row=0, column=0, padx=10, pady=(15,5), sticky="w")
        self.browser_cookies_combo = customtkinter.CTkComboBox(self.settings_tab, font=my_font, values=["None", "chrome", "edge", "firefox", "brave", "opera", "safari"])
        self.browser_cookies_combo.set(config.get("browser_cookies", "None"))
        self.browser_cookies_combo.grid(row=0, column=1, padx=10, pady=(15,5), sticky="e")

        self.custom_ffmpeg_enabled = customtkinter.BooleanVar(value=config.get("custom_ffmpeg_enabled", False))
        self.custom_ffmpeg_check = customtkinter.CTkCheckBox(self.settings_tab, text="Custom ffmpeg path", font=my_font, variable=self.custom_ffmpeg_enabled)
        self.custom_ffmpeg_check.grid(row=1, column=0, columnspan=2, padx=10, pady=(15,5), sticky="w")
        self.custom_ffmpeg_entry = customtkinter.CTkEntry(self.settings_tab, font=my_font, width=300)
        self.custom_ffmpeg_entry.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.custom_ffmpeg_entry.insert(0, config.get("custom_ffmpeg_path", default_ffmpeg_path))
        self.bind_context_menu(self.custom_ffmpeg_entry)
        self.custom_ffmpeg_browse = customtkinter.CTkButton(self.settings_tab, text="Browse", font=my_font, command=self.browse_custom_ffmpeg)
        self.custom_ffmpeg_browse.grid(row=2, column=1, padx=10, pady=5, sticky="e")
        
        self.appearance_label = customtkinter.CTkLabel(self.settings_tab, text="Theme:", font=my_font)
        self.appearance_label.grid(row=3, column=0, padx=10, pady=(15,5), sticky="w")
        self.appearance_mode_combo = customtkinter.CTkComboBox(self.settings_tab, font=my_font, values=["System", "Dark", "Light"])
        self.appearance_mode_combo.grid(row=3, column=1, padx=10, pady=(15,5), sticky="e")
        
        self.gemini_api_key_label = customtkinter.CTkLabel(self.settings_tab, text="Gemini API Key:", font=my_font)
        self.gemini_api_key_label.grid(row=4, column=0, columnspan=2, padx=10, pady=(15, 5), sticky="w")
        self.gemini_api_key_entry = customtkinter.CTkEntry(self.settings_tab, font=my_font, show="*")
        self.gemini_api_key_entry.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.gemini_api_key_entry.insert(0, config.get("gemini_api_key", ""))
        self.bind_context_menu(self.gemini_api_key_entry) 

        self.save_settings_button = customtkinter.CTkButton(self.settings_tab, text="Save Settings", font=my_font, command=self.save_settings)
        self.save_settings_button.grid(row=6, column=0, columnspan=2, padx=10, pady=(15, 5))

        # --- NOVITÀ: Pulsante Download Dinamico yt-dlp ---
        self.update_ytdlp_button = customtkinter.CTkButton(
            self.settings_tab, 
            text="Aggiorna yt-dlp (Risolvi Errori Download)", 
            font=customtkinter.CTkFont(family="Helvetica", size=13, weight="bold"), 
            command=self.update_ytdlp, 
            fg_color="#8B0000", hover_color="#600000"
        )
        self.update_ytdlp_button.grid(row=7, column=0, columnspan=2, padx=10, pady=(10, 5))

        self.save_confirm_label = customtkinter.CTkLabel(self.settings_tab, text="", font=my_font, text_color="green")
        self.save_confirm_label.grid(row=8, column=0, columnspan=2, padx=10, pady=5)

    def update_ytdlp(self):
        """Scarica e salva il file zipapp di yt-dlp per by-passare la versione di PyInstaller"""
        def update_task():
            try:
                self.trigger_ui_update(error_text="")
                self.after(0, lambda: self.save_confirm_label.configure(text="Scaricamento aggiornamento... attendi", text_color="orange"))
                
                # Link al pacchetto python ufficiale di yt-dlp
                url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
                zip_path = os.path.join(base_dir, "yt_dlp_update.zip")
                tmp_path = zip_path + ".tmp"
                urllib.request.urlretrieve(url, tmp_path)
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                os.rename(tmp_path, zip_path)
                
                self.after(0, lambda: self.save_confirm_label.configure(text="Aggiornato con successo! RIAVVIA l'app.", text_color="green"))
            except Exception as e:
                self.after(0, lambda: self.save_confirm_label.configure(text=f"Errore di rete: {e}", text_color="red"))
                
        threading.Thread(target=update_task).start()

    # --- MENU CONTESTUALE ---
    def setup_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=False, bg="#2b2b2b", fg="white", activebackground="#1f538d", borderwidth=0)
        self.context_menu.add_command(label="Taglia", command=self.cmd_cut)
        self.context_menu.add_command(label="Copia", command=self.cmd_copy)
        self.context_menu.add_command(label="Incolla", command=self.cmd_paste)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Seleziona Tutto", command=self.cmd_select_all)

    def bind_context_menu(self, widget):
        target = widget._entry if hasattr(widget, '_entry') else widget
        target.bind("<Button-3>", self.show_context_menu)
        if sys.platform == "darwin": target.bind("<Button-2>", self.show_context_menu)

    def show_context_menu(self, event):
        event.widget.focus_set()
        try: self.context_menu.tk_popup(event.x_root, event.y_root)
        finally: self.context_menu.grab_release()

    def cmd_cut(self):
        w = self.focus_get()
        if w: w.event_generate("<<Cut>>")
    def cmd_copy(self):
        w = self.focus_get()
        if w: w.event_generate("<<Copy>>")
    def cmd_paste(self):
        w = self.focus_get()
        if w: w.event_generate("<<Paste>>")
    def cmd_select_all(self):
        w = self.focus_get()
        if w: w.select_range(0, 'end'); w.icursor('end')

    # --- METODI UI ---
    def thread_safe_update(self, left_text=None, right_text=None, progress=None, state=None, error_text=None):
        if left_text is not None: self.download_label.configure(text=left_text)
        if right_text is not None: self.speed_label.configure(text=right_text)
        if progress is not None: self.progress_bar.set(progress)
        if state is not None: self.download_button.configure(state=state)
        if error_text is not None: self.error_label.configure(text=error_text)

    def trigger_ui_update(self, left_text=None, right_text=None, progress=None, state=None, error_text=None):
        self.after(0, self.thread_safe_update, left_text, right_text, progress, state, error_text)

    def browse_folder(self):
        f = filedialog.askdirectory()
        if f: self.folder.delete(0, 'end'); self.folder.insert(0, f)
    
    def browse_custom_ffmpeg(self):
        f = filedialog.askdirectory()
        if f:
            self.custom_ffmpeg_entry.delete(0, 'end')
            self.custom_ffmpeg_entry.insert(0, f)
    
    def get_ffmpeg_exe(self):
        if self.custom_ffmpeg_enabled.get():
            custom_path = self.custom_ffmpeg_entry.get().strip()
            if os.path.isdir(custom_path):
                exe = os.path.join(custom_path, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
                if os.path.isfile(exe): return exe
            return custom_path
        if shutil.which("ffmpeg") is None:
            return os.path.join(default_ffmpeg_path, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        return shutil.which("ffmpeg")

    def update_resolutions_ui(self, video_data):
        if video_data and video_data["resolutions"]:
            self.combo.configure(values=video_data["resolutions"], state="normal")
            self.combo.set(video_data["resolutions"][0])
            self.download_button.configure(state='normal')
            self.error_label.configure(text="")
        else:
            self.error_label.configure(text="Error: Could not load video info (403?).")
            self.combo.configure(values=["Select Resolution"], state="normal")
            self.combo.set("Select Resolution")
            self.download_button.configure(state='disabled')

    def on_url_change(self, *args):
        if self.debounce_job: self.after_cancel(self.debounce_job)
        self.debounce_job = self.after(500, self.init_submit)

    def on_trim_change(self, *args):
        if self.trim.get() and not self.encode.get(): self.encode.set(True)
    def on_encode_change(self, *args):
        if not self.encode.get(): self.trim.set(False)
    def on_audio_var_change(self, *args):
        if self.audio_var.get() and self.url_bar.get() != "":
            self.combo.configure(state='disabled')
            self.download_button.configure(state='normal')
        elif (self.combo.get() == "Select Resolution" or self.url_bar.get() == ""):
            self.combo.configure(state='normal'); self.download_button.configure(state='disabled')
    
    def clear_bar(self):
        self.url_bar.delete(0, 'end'); self.combo.configure(values=["Select Resolution"])
        self.combo.set("Select Resolution"); self.download_button.configure(state='disabled')
        self.trigger_ui_update("", "", 0, 'disabled', ""); self.combo.configure(state='normal')
        self.audio_var.set(False); self.encode.set(False); self.trim.set(False)
        self.url_cache.clear()
    
    def init_submit(self):
        url = self.url_bar.get().strip()
        if not url: return
        self.combo.configure(values=["Loading..."], state="disabled")
        self.combo.set("Loading..."); self.download_button.configure(state='disabled')
        self.error_label.configure(text="")
        
        job_data = {
            'browser_cookies': self.browser_cookies_combo.get()
        }
        threading.Thread(target=submit, args=(url, self, job_data)).start()

    def init_download(self):
        self.error_label.configure(text=""); self.download_label.configure(text="")
        self.speed_label.configure(text=""); self.progress_bar.set(0)
        
        job_data = {
            'url': self.url_bar.get(),
            'resolution': self.combo.get()[:-1] if self.combo.get() != "Select Resolution" else None,
            'percorso': self.folder.get(),
            'encode': self.encode.get(), 'play': self.play.get(),
            'transcribe': self.transcribe.get(), 'engine': self.transcription_engine_combo.get(),
            'lang_vosk': self.transcription_language_combo.get(),
            'api_key': self.gemini_api_key_entry.get(),
            'model_name': self.gemini_model_combo.get(),
            'target_language': self.gemini_language_combo.get(),
            'video_codec_selection': self.encode_box.get(),
            'audio_codec_selection': self.encode_audio_box.get(),
            'trim_start': self.trim_start.get(), 'trim_end': self.trim_end.get(),
            'ffmpeg_used': self.get_ffmpeg_exe(),
            'browser_cookies': self.browser_cookies_combo.get() # Passaggio cookie ai thread
        }

        if self.audio_var.get(): threading.Thread(target=download_audio, args=(self, job_data)).start()
        else: threading.Thread(target=download_completo, args=(self, job_data)).start()

    def on_transcribe_change(self):
        if self.transcribe.get():
            self.transcription_engine_combo.configure(state="normal")
            self.engine_label.configure(state="normal"); self.on_engine_change()
        else:
            self.transcription_engine_combo.configure(state="disabled")
            self.engine_label.configure(state="disabled")
            self.transcription_language_combo.configure(state="disabled")
            self.language_label.configure(state="disabled")

    def on_engine_change(self, choice=None):
        if not self.transcribe.get(): return
        engine = self.transcription_engine_combo.get()
        if engine == "VOSK":
            self.transcription_language_combo.grid(); self.language_label.grid()
            self.gemini_options_frame.grid_remove()
        elif engine == "Gemini":
            self.transcription_language_combo.grid_remove(); self.language_label.grid_remove()
            self.gemini_options_frame.grid()

    def save_settings(self):
        try:
            current_config = load_config()
            current_config["appearance_mode"] = self.appearance_mode_combo.get().lower()
            current_config["custom_ffmpeg_enabled"] = self.custom_ffmpeg_enabled.get()
            current_config["custom_ffmpeg_path"] = self.custom_ffmpeg_entry.get()
            current_config["gemini_api_key"] = self.gemini_api_key_entry.get()
            current_config["browser_cookies"] = self.browser_cookies_combo.get()
            customtkinter.set_appearance_mode(current_config["appearance_mode"])
            with open(os.path.join(base_dir, "config.json"), "w") as file: json.dump(current_config, file, indent=4)
            self.save_confirm_label.configure(text="Settings saved successfully!", text_color="green")
            self.save_confirm_label.after(3000, lambda: self.save_confirm_label.configure(text=""))
        except Exception as e:
            self.save_confirm_label.configure(text="Error saving settings!", text_color="red")

def auto_play(percorso):
    try:
        if sys.platform == "win32": os.startfile(percorso)
        elif sys.platform == "darwin": subprocess.call(['open', percorso])
        else: subprocess.call(['xdg-open', percorso])
    except Exception: pass

def get_base_ydl_opts(job_data=None):
    """Crea le opzioni base incluse quelle dei Cookie ed extractor_args con Deno"""
    deno_exe = os.path.join(base_dir, "deno.exe")
    opts = {
        'js_runtimes': {'deno': {'path': deno_exe} if os.path.exists(deno_exe) else {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'web', 'tv']
            }
        }
    }
    if job_data and job_data.get('browser_cookies') and job_data['browser_cookies'] != "None":
        opts['cookiesfrombrowser'] = (job_data['browser_cookies'],)
    return opts

def extract_clean_resolutions(formats):
    if not formats: return []
    resolutions = {f['height'] for f in formats if f.get('height') and f.get('vcodec') != 'none' and f['height'] >= 144}
    return [f"{r}p" for r in sorted(resolutions, reverse=True)]

def submit(url_string, app_instance, job_data):
    video_data_for_ui = None
    ydl_opts = {
        'quiet': True, 'no_warnings': True, 'simulate': True, 
        'nocheckcertificate': True, 'prefer_insecure': True, 'skip_download': True
    }
    ydl_opts.update(get_base_ydl_opts(job_data))
    
    try:
        if url_string in app_instance.url_cache:
            info_dict = app_instance.url_cache[url_string]
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url_string, download=False)
                app_instance.url_cache[url_string] = info_dict
                
        formats = info_dict.get('formats', None)
        if formats:
            clean_res_list = extract_clean_resolutions(formats)
            if clean_res_list:
                video_data_for_ui = {"resolutions": clean_res_list}
            else:
                resolutions = {f['height'] for f in formats if f.get('height') and f['height'] >= 144}
                video_data_for_ui = {"resolutions": [f"{r}p" for r in sorted(resolutions, reverse=True)]}
    except Exception as e:
        print(f"Errore nel thread di submit: {e}")
    app_instance.after(0, lambda: app_instance.update_resolutions_ui(video_data_for_ui))

def download_completo(app_instance, job_data):
    try:
        ffmpeg_used = job_data['ffmpeg_used']
        url = job_data['url']
        resolution = job_data['resolution']
        percorso = job_data['percorso'] or os.path.join(base_dir, "output")
        if not os.path.exists(percorso):
            os.makedirs(percorso)
        
        ydl_opts_info = {'quiet': True}
        ydl_opts_info.update(get_base_ydl_opts(job_data))
        
        if url in app_instance.url_cache:
            info_dict = app_instance.url_cache[url]
        else:
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                app_instance.url_cache[url] = info_dict

        file_info = {'path': None}
        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                progress = downloaded / total if total else 0
                
                is_audio = d.get('info_dict', {}).get('vcodec') == 'none'
                stream_type = "audio" if is_audio else "video"
                
                left_text = f"Downloading {stream_type}... {int(progress * 100)}%" if total else f"Downloading {stream_type}..."
                speed = d.get('speed')
                right_text = f"Speed: {(speed * 8 / (1024*1024)):.2f} Mbps" if speed else "Speed: -"
                app_instance.trigger_ui_update(left_text, right_text, progress, 'disabled')
            elif d['status'] == 'error':
                app_instance.trigger_ui_update(error_text="Download failed!", state='normal')
            elif d['status'] == 'finished':
                # Risoluzione predittiva per la terminazione di yt-dlp file processing
                if 'info_dict' in d and '_filename' in d['info_dict']:
                    base_n, _ = os.path.splitext(d['info_dict']['_filename'])
                else:
                    base_n, _ = os.path.splitext(d.get('filename', ''))
                file_info['path'] = base_n + ".mp4" if base_n else None
                app_instance.trigger_ui_update("Download completed!", "", 1.0, 'normal')

        # Ottimizzazione outtmpl per prevenire path roots
        nome_pulito = re.sub('[^a-zA-Z0-9_. -]', '-', info_dict.get('title', 'video'))
        res_match = re.search(r'\d+', str(resolution)) if resolution else None
        res_num = res_match.group(0) if res_match else "1080"
        format_selector = f'bestvideo[height={res_num}]+bestaudio/bestvideo[height<={res_num}]+bestaudio/best[height<={res_num}]/best'

        ydl_opts = {
            'outtmpl': f"{percorso}/{nome_pulito}.%(ext)s",
            'format': format_selector,
            'progress_hooks': [progress_hook],
            'ffmpeg_location': ffmpeg_used,
            'merge_output_format': 'mp4' 
        }
        ydl_opts.update(get_base_ydl_opts(job_data))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            error_code = ydl.download([url])
            if error_code: raise Exception("yt-dlp error code")
            
        title = file_info.get('path') or f"{percorso}/{nome_pulito}.mp4"
        total_duration = info_dict.get('duration', 0)

        if job_data['encode']: title = encode_video(title, job_data, app_instance, total_duration)
        if job_data['play']: auto_play(title)

        # --- SEZIONE TRASCRIZIONE ---
        if job_data['transcribe']:
            engine = job_data['engine']
            base, _ = os.path.splitext(title)
            output_txt = base + ".txt"

            if engine == "VOSK":
                app_instance.trigger_ui_update(left_text="Avvio trascrizione VOSK...", progress=0.0, state='disabled')
                transcribe_file(title, ffmpeg_exe=job_data['ffmpeg_used'], lang=job_data['lang_vosk'], app_instance=app_instance, duration=total_duration, output_txt_path=output_txt)
                app_instance.trigger_ui_update(left_text="Elaborazione e Trascrizione VOSK completate!", progress=1.0, state='normal')

            elif engine == "Gemini":
                if not job_data['api_key']:
                    app_instance.trigger_ui_update(left_text="Errore API Gemini.", error_text="Chiave API Gemini mancante.", progress=1.0, state='normal')
                    return

                app_instance.trigger_ui_update(left_text="Avvio trascrizione Gemini...", progress=0.0, state='disabled')
                transcription = transcribe_file_gemini(
                    title, api_key=job_data['api_key'], 
                    model_name=job_data['model_name'], target_language=job_data['target_language'],
                    ffmpeg_exe=job_data['ffmpeg_used'], app_instance=app_instance, duration=total_duration, output_txt_path=output_txt
                )
                if transcription and "Errore" in transcription:
                    app_instance.trigger_ui_update(left_text="Download completato. Trascrizione fallita.", error_text=transcription, progress=1.0, state='normal')
                else:
                    app_instance.trigger_ui_update(left_text="Elaborazione e Trascrizione Gemini completate!", progress=1.0, state='normal')
        else:
            app_instance.trigger_ui_update(left_text="Processo terminato con successo!", progress=1.0, state='normal')

    except Exception as e:
        app_instance.trigger_ui_update("", error_text=f"Errore: {e}", state='normal')

def download_audio(app_instance, job_data):
    try:
        url = job_data['url']
        percorso = job_data['percorso'] or os.path.join(base_dir, "output")
        if not os.path.exists(percorso):
            os.makedirs(percorso)
        file_info = {'path': None}

        def progress_hook(d):
            if d['status'] == 'finished':
                # Evita di acquisire path non ancora post-processate estraendo dal d originale
                pass
            elif d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                progress = downloaded / total if total else 0
                left_text = f"Downloading audio... {int(progress * 100)}%" if total else "Downloading audio..."
                speed = d.get('speed')
                right_text = f"Speed: {(speed * 8 / (1024*1024)):.2f} Mbps" if speed else "Speed: -"
                app_instance.trigger_ui_update(left_text, right_text, progress, 'disabled')
            elif d['status'] == 'error':
                app_instance.trigger_ui_update(error_text="Download failed!", state='normal')

        ydl_opts_info = {'quiet': True}
        ydl_opts_info.update(get_base_ydl_opts(job_data))
        
        if url in app_instance.url_cache:
            info = app_instance.url_cache[url]
        else:
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                app_instance.url_cache[url] = info
                
        clean_title = re.sub('[^a-zA-Z0-9_. -]', '-', info.get('title', 'audio_file'))

        ydl_opts = {
            'outtmpl': f"{percorso}/{clean_title}.%(ext)s",
            'format': 'bestaudio/best',
            'progress_hooks': [progress_hook],
            'ffmpeg_location': job_data['ffmpeg_used'],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
            }]
        }
        ydl_opts.update(get_base_ydl_opts(job_data))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            error_code = ydl.download([url])
            if error_code: raise Exception("yt-dlp error code")
            
        app_instance.trigger_ui_update("Download completed!", "", 1.0, 'normal')
        total_duration = info.get('duration', 0)
        
        # Recupero file certo tramite la simulazione ydl interna (se postprocessors attivi, è opus garantito)
        final_file_path = f"{percorso}/{clean_title}.opus"

        if job_data['encode']: final_file_path = encode_audio(final_file_path, job_data, app_instance, total_duration)
        if job_data['play']: auto_play(final_file_path)

        # --- SEZIONE TRASCRIZIONE ---
        if job_data['transcribe']:
            engine = job_data['engine']
            base, _ = os.path.splitext(final_file_path)
            output_txt = base + ".txt"

            if engine == "VOSK":
                app_instance.trigger_ui_update(left_text="Avvio trascrizione VOSK...", progress=0.0, state='disabled')
                transcribe_file(final_file_path, ffmpeg_exe=job_data['ffmpeg_used'], lang=job_data['lang_vosk'], app_instance=app_instance, duration=total_duration, output_txt_path=output_txt)
                app_instance.trigger_ui_update(left_text="Elaborazione e Trascrizione VOSK completate!", progress=1.0, state='normal')

            elif engine == "Gemini":
                if not job_data['api_key']:
                    app_instance.trigger_ui_update(left_text="Errore API Gemini.", error_text="Chiave API Gemini mancante.", progress=1.0, state='normal')
                    return

                app_instance.trigger_ui_update(left_text="Avvio trascrizione Gemini...", progress=0.0, state='disabled')
                transcription = transcribe_file_gemini(
                    final_file_path, api_key=job_data['api_key'], 
                    model_name=job_data['model_name'], target_language=job_data['target_language'],
                    ffmpeg_exe=job_data['ffmpeg_used'], app_instance=app_instance, duration=total_duration, output_txt_path=output_txt
                )
                if transcription and "Errore" in transcription:
                    app_instance.trigger_ui_update(left_text="Download completato. Trascrizione fallita.", error_text=transcription, progress=1.0, state='normal')
                else:
                    app_instance.trigger_ui_update(left_text="Elaborazione e Trascrizione Gemini completate!", progress=1.0, state='normal')
        else:
            app_instance.trigger_ui_update(left_text="Processo terminato con successo!", progress=1.0, state='normal')
        
    except Exception as e:
        app_instance.trigger_ui_update("", error_text=f"Errore: {e}", state='normal')

def video_format(job_data):
    match job_data['video_codec_selection']:
        case "x264": codec = "libx264"
        case "x265": codec = "libx265"
        case "AMD x264": codec = "h264_amf"
        case "AMD x265": codec = "hevc_amf"
        case "Nvidia x264": codec = "h264_nvenc"
        case "Nvidia x265": codec = "hevc_nvenc"
        case "Intel x264": codec = "h264_qsv"
        case "Intel x265": codec = "hevc_qsv"
        case _: codec = 'copy'
    return codec

def audio_format(job_data):
    match job_data['audio_codec_selection']:
        case "aac": return "aac", "aac"
        case "mp3": return "libmp3lame", "mp3"
        case "opus": return "libopus", "ogg"
        case _: return "copy", "mp3"

def time_to_seconds(t_str):
    try:
        if not t_str: return 0.0
        parts = t_str.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(float(h)) * 3600 + int(float(m)) * 60 + float(s)
        return 0.0
    except:
        return 0.0

def run_ffmpeg_with_progress(command, app_instance, total_duration_sec, text_prefix):
    cmd = command.copy()
    if '-progress' not in cmd:
        cmd.insert(1, '-progress')
        cmd.insert(2, 'pipe:1')
    
    if app_instance:
        app_instance.trigger_ui_update(left_text=f"{text_prefix} (0%)", progress=0.0)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, creationflags=get_subprocess_flags())
    
    for line in process.stdout:
        if line.startswith("out_time_us="):
            us_time = line.split("=")[1].strip()
            if us_time.replace('-', '').isdigit():
                sec_time = int(us_time) / 1000000.0
                if sec_time < 0: sec_time = 0
                if total_duration_sec and total_duration_sec > 0 and app_instance:
                    prog = min(sec_time / total_duration_sec, 1.0)
                    app_instance.trigger_ui_update(left_text=f"{text_prefix} {int(prog*100)}%", progress=prog)
                elif app_instance:
                    app_instance.trigger_ui_update(left_text=f"{text_prefix} {sec_time:.1f}s")
    process.wait()
    return process.returncode

def get_ffmpeg_command_base(job_data):
    return [job_data['ffmpeg_used'], '-y']

def encode_video(file, job_data, app_instance=None, total_duration_sec=0):
    start, end = cut_time(job_data)
    audio_codec, _ = audio_format(job_data)
    video_codec = video_format(job_data)
    output_file = file[:-4] + "-encoded.mp4"
    command = get_ffmpeg_command_base(job_data) + ['-i', file]
    if start: command += ['-ss', start]
    if end: command += ['-to', end]
    command += ['-c:v', video_codec, '-c:a', audio_codec, output_file]
    
    calc_duration = total_duration_sec
    if start and end: 
        calc_duration = time_to_seconds(end) - time_to_seconds(start)
        
    run_ffmpeg_with_progress(command, app_instance, calc_duration, "Encoding video...")
    try: os.remove(file)
    except: pass
    if app_instance: app_instance.trigger_ui_update(progress=1.0)
    return output_file

def encode_audio(file, job_data, app_instance=None, total_duration_sec=0):
    start, end = cut_time(job_data)
    audio_codec, ext = audio_format(job_data)
    output_file = file[:file.rfind('.')] + "-encoded." + ext
    command = get_ffmpeg_command_base(job_data) + ['-i', file]
    if start: command += ['-ss', start]
    if end: command += ['-to', end]
    command += ['-c:a', audio_codec, output_file]
    
    calc_duration = total_duration_sec
    if start and end: 
        calc_duration = time_to_seconds(end) - time_to_seconds(start)
        
    run_ffmpeg_with_progress(command, app_instance, calc_duration, "Encoding audio...")
    try: os.remove(file)
    except: pass
    if app_instance: app_instance.trigger_ui_update(progress=1.0)
    return output_file

def cut_time(job_data):
    if not job_data.get('trim_start') and not job_data.get('trim_end'):
        return None, None
    start = job_data['trim_start'] if job_data['trim_start'] else "00:00:00.000"
    end = job_data['trim_end'] if job_data['trim_end'] else None
    return start, end

def extract_audio_for_transcription(video_path, ffmpeg_exe, app_instance=None, total_duration_sec=0):
    try:
        base, _ = os.path.splitext(video_path)
        uid = str(uuid.uuid4())[:8]
        audio_output_path = f"{base}_temp_audio_{uid}.opus"
        command = [ffmpeg_exe, '-y', '-i', video_path, '-vn', '-acodec', 'copy', audio_output_path]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=get_subprocess_flags())
        process.wait()
        if process.returncode != 0:
            command[-3] = '-c:a'; command[-2] = 'libopus'
            run_ffmpeg_with_progress(command, app_instance, total_duration_sec, "Estrazione Traccia Audio...")
            if not os.path.exists(audio_output_path): return None
        return audio_output_path
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None
    
def get_mime_type(file_path):
    mime_map = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.opus': 'audio/opus', '.ogg': 'audio/ogg', '.aac': 'audio/aac', '.flac': 'audio/flac', '.mp4': 'video/mp4'}
    return mime_map.get(os.path.splitext(file_path)[1].lower())

def transcribe_file_gemini(file_path, api_key, model_name, target_language, ffmpeg_exe, app_instance=None, duration=0, output_txt_path=None):
    is_video = file_path.lower().endswith(('.mp4', '.webm', '.mkv', '.mov', '.avi'))
    temp_audio_path = None
    path_to_upload = file_path
    audio_file = None
    client = None

    try:
        if app_instance: app_instance.trigger_ui_update(left_text="Preparazione ambiente Cloud Gemini...", progress=0.0)
        client = genai.Client(api_key=api_key)
        if is_video:
            temp_audio_path = extract_audio_for_transcription(file_path, ffmpeg_exe, app_instance, duration)
            if not temp_audio_path: return "Errore: impossibile estrarre l'audio dal file video."
            path_to_upload = temp_audio_path
        
        file_mime_type = get_mime_type(path_to_upload)
        if not file_mime_type: return f"Errore: Tipo di file non supportato per la trascrizione."
        
        if app_instance: app_instance.trigger_ui_update(left_text="Caricamento file audio nel Cloud Gemini...")
        audio_file = client.files.upload(file=path_to_upload)

        while audio_file.state.name == "PROCESSING":
            if app_instance: app_instance.trigger_ui_update(left_text="Attesa elaborazione cloud pre-analisi Gemini...")
            time.sleep(5)
            audio_file = client.files.get(name=audio_file.name)

        if audio_file.state.name != "ACTIVE": raise ValueError(f"State: {audio_file.state.name}")
        
        prompt_parts = []
        if target_language == "Original Language": prompt_parts.append("Transcribe the following audio file into its original language. Include accurate punctuation.")
        else: prompt_parts.append(f"Transcribe the following audio file, and then translate the entire transcription into {target_language}.")
        prompt_parts.append(audio_file)

        if app_instance: app_instance.trigger_ui_update(left_text="Generazione trascritta di Gemini in corso...")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt_parts
        )

        transcription = response.text
        if output_txt_path is None:
            base, _ = os.path.splitext(file_path)
            output_txt_path = base + f"_gemini_{target_language}.txt"
        
        with open(output_txt_path, "w", encoding="utf-8") as f: f.write(transcription)
        return transcription

    except Exception as e:
        return f"Errore durante la trascrizione con Gemini: {e}"
    finally:
        if audio_file is not None and client is not None:
            try: client.files.delete(name=audio_file.name)
            except: pass
        if temp_audio_path and os.path.exists(temp_audio_path):
            try: os.remove(temp_audio_path)
            except: pass

def check_and_download_model(lang):
    model_info = VOSK_MODELS.get(lang)
    if not model_info: return
    model_dir = os.path.join(base_dir, model_info["folder"])
    if not os.path.exists(model_dir):
        zip_path = os.path.join(base_dir, "model.zip")
        urllib.request.urlretrieve(model_info["url"], zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(base_dir)
        os.remove(zip_path)

def transcribe_file(file_path, ffmpeg_exe, lang="English", app_instance=None, duration=0, output_txt_path=None):
    if app_instance: app_instance.trigger_ui_update(left_text="Verifica modello VOSK in corso...", progress=0.0)
    check_and_download_model(lang)
    uid = str(uuid.uuid4())[:8]
    audio_file = os.path.join(base_dir, f"temp_audio_{uid}.wav")
    
    try:
        command = [ffmpeg_exe, "-y", "-i", file_path, "-ar", "16000", "-ac", "1", "-f", "wav", audio_file]
        run_ffmpeg_with_progress(command, app_instance, duration, "Estrazione Wav per Vosk...")
        
        if app_instance: app_instance.trigger_ui_update(left_text="Caricamento Traccia Audio per VOSK...", progress=0.0)
        try: wf = wave.open(audio_file, "rb")
        except Exception: return None
            
        model_dir = os.path.join(base_dir, VOSK_MODELS[lang]["folder"])
        model = Model(model_dir)
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        total_frames = wf.getnframes()
        processed_frames = 0
            
        transcription = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0: break
            processed_frames += 4000
            
            if app_instance and total_frames > 0 and (processed_frames % 40000 == 0):
                perc = min(processed_frames / total_frames, 1.0)
                app_instance.trigger_ui_update(left_text=f"Trascrizione VOSK in esecuzione... {int(perc*100)}%", progress=perc)

            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                transcription.append(result.get("text", ""))

        result = json.loads(rec.FinalResult())
        transcription.append(result.get("text", ""))
        
        full_transcription = " ".join(transcription)
        
        if output_txt_path is None:
            base, _ = os.path.splitext(file_path)
            output_txt_path = base + ".txt"
            
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(full_transcription)
        
        wf.close()
        return full_transcription
        
    finally:
        if os.path.exists(audio_file):
            try: os.remove(audio_file)
            except Exception: pass

if __name__ == "__main__":
    app = App()
    app.mainloop()