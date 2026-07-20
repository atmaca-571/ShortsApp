"""
kontrol_paneli.py
------------------
Canavar Asistan - Ana Kontrol Paneli (Gaming / Cyberpunk Studio Temasi)

Tkinter thread mimarisi: threading.Thread + queue.Queue + root.after() polling.
(QThread/PyQt kavramlarinin gercek Tkinter karsiligidir.)

Ozellikler:
- Premium karanlik tema (antrasit tonlar, neon glow, yuvarlatilmis paneller)
- Canvas tabanli CyberSpinner (kaba kurgu / render sirasinda)
- Hover mikro-etkilesimleri (yumusak renk gecisi)
- Sol: script editor | Sag: Sari Yedekler + Videolar (grid + boluculer)
"""

import os
import sys
import json
import math
import queue
import threading
import subprocess
import shutil
import gc
import re
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    _CTK_VAR = True
except Exception:
    _CTK_VAR = False

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================================
# CYBERPUNK STUDIO TEMA PALETI
# ============================================================================
CYBER_BG_ROOT = "#0a0e14"
CYBER_BG_PRIMARY = "#12171f"
CYBER_BG_PANEL = "#1a212b"
CYBER_BG_ELEVATED = "#222b36"
CYBER_BG_INPUT = "#161d27"
CYBER_BORDER = "#2a3441"
CYBER_BORDER_GLOW = "#3d4f63"

CYBER_NEON_GREEN = "#39ff14"
CYBER_NEON_BLUE = "#00d4ff"
CYBER_NEON_CYAN = "#00ffc8"
CYBER_NEON_PURPLE = "#a855f7"
CYBER_NEON_AMBER = "#ffb020"

CYBER_TEXT_PRIMARY = "#e8edf4"
CYBER_TEXT_MUTED = "#8b9cb3"
CYBER_TEXT_DIM = "#5c6b7f"

CYBER_BTN_KURGU = "#5b21b6"
CYBER_BTN_KURGU_HOVER = "#7c3aed"
CYBER_BTN_AE = "#dc2626"
CYBER_BTN_AE_HOVER = "#ef4444"
CYBER_BTN_PLAY = "#0369a1"
CYBER_BTN_PLAY_HOVER = "#0284c7"
CYBER_BTN_SAVE = "#047857"
CYBER_BTN_SAVE_HOVER = "#059669"
CYBER_BTN_MUTED = "#334155"
CYBER_BTN_MUTED_HOVER = "#475569"
CYBER_BTN_DANGER = "#991b1b"
CYBER_BTN_DANGER_HOVER = "#b91c1c"

CYBER_LOG_BG = "#0d1117"
CYBER_LOG_FG = CYBER_NEON_GREEN
CYBER_LOG_ERR = "#ff4466"

FONT_UI = ("Segoe UI", 10)
FONT_UI_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_MONO = ("Consolas", 9)
FONT_SMALL = ("Segoe UI", 8)

VARSAYILAN_PENCERE_GENISLIK = 1180
VARSAYILAN_PENCERE_YUKSEKLIK = 820


def _hex_to_rgb(hex_renk):
    h = hex_renk.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r, g, b):
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def _blend_hex(renk_a, renk_b, oran):
    """oran=0 -> renk_a, oran=1 -> renk_b"""
    ra, ga, ba = _hex_to_rgb(renk_a)
    rb, gb, bb = _hex_to_rgb(renk_b)
    t = max(0.0, min(1.0, oran))
    return _rgb_to_hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def _lighten_hex(hex_renk, faktor=1.12):
    r, g, b = _hex_to_rgb(hex_renk)
    return _rgb_to_hex(r * faktor, g * faktor, b * faktor)


# ============================================================================
# CYBER SPINNER (Canvas - thread-safe, ana thread'de after() ile calisir)
# ============================================================================
class CyberSpinner(tk.Canvas):
    """Donen neon halka - gercek canvas animasyonu, nokta/nokta degil."""

    SEGMENT_SAYISI = 14

    def __init__(self, parent, size=72, kalinlik=5, renk=CYBER_NEON_CYAN, **kwargs):
        arka = kwargs.pop("bg", CYBER_BG_ELEVATED)
        super().__init__(parent, width=size, height=size, bg=arka,
                         highlightthickness=0, bd=0, **kwargs)
        self._size = size
        self._kalinlik = kalinlik
        self._renk = renk
        self._aci = 0.0
        self._calisiyor = False
        self._after_id = None

    def start(self):
        if self._calisiyor:
            return
        self._calisiyor = True
        self._tick()

    def stop(self):
        self._calisiyor = False
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self.delete("all")

    def _tick(self):
        if not self._calisiyor:
            return
        self.delete("all")
        cx = cy = self._size // 2
        yaricap = (self._size - self._kalinlik * 2) // 2
        adim = 360.0 / self.SEGMENT_SAYISI

        for i in range(self.SEGMENT_SAYISI):
            parlaklik = 1.0 - (i / self.SEGMENT_SAYISI) * 0.88
            renk = _blend_hex(self._renk, CYBER_BG_ELEVATED, 1.0 - parlaklik)
            baslangic = self._aci + i * adim
            self.create_arc(
                cx - yaricap, cy - yaricap, cx + yaricap, cy + yaricap,
                start=baslangic, extent=adim * 0.55,
                style=tk.ARC, outline=renk, width=self._kalinlik
            )

        self._aci = (self._aci + 14) % 360
        self._after_id = self.after(33, self._tick)


# ============================================================================
# CYBER BUTON (hover gecisi + aktif glow cerceve)
# ============================================================================
class CyberButton(tk.Frame):
    """Neon glow cerceveli buton; hover'da yumusak renk interpolasyonu."""

    def __init__(self, parent, text, command, bg_normal, bg_hover=None,
                 glow_renk=CYBER_NEON_BLUE, font=None, height=2, **kwargs):
        bg_hover = bg_hover or _lighten_hex(bg_normal, 1.14)
        super().__init__(parent, bg=CYBER_BORDER, padx=1, pady=1)
        self._bg_normal = bg_normal
        self._bg_hover = bg_hover
        self._glow_renk = glow_renk
        self._mevcut_bg = bg_normal
        self._anim_id = None
        self._aktif = False

        pady_val = 10 if height > 1 else 6
        self._btn = tk.Button(
            self, text=text, command=command,
            bg=bg_normal, fg=CYBER_TEXT_PRIMARY,
            activebackground=bg_hover, activeforeground=CYBER_TEXT_PRIMARY,
            relief="flat", bd=0, padx=14, pady=pady_val,
            font=font or FONT_UI_BOLD, cursor="hand2",
            **kwargs
        )
        self._btn.pack(fill="both", expand=True)
        self._btn.bind("<Enter>", self._hover_gir)
        self._btn.bind("<Leave>", self._hover_cik)
        self._btn.bind("<FocusIn>", lambda e: self.set_aktif(True))
        self._btn.bind("<FocusOut>", lambda e: self.set_aktif(False))

    def config(self, **kwargs):
        if "state" in kwargs:
            self._btn.config(state=kwargs.pop("state"))
        if "text" in kwargs:
            self._btn.config(text=kwargs.pop("text"))
        if kwargs:
            self._btn.config(**kwargs)

    def set_aktif(self, aktif):
        self._aktif = aktif
        self.configure(bg=self._glow_renk if aktif else CYBER_BORDER)

    def _hover_gir(self, _event=None):
        self._renge_gec(self._bg_hover)

    def _hover_cik(self, _event=None):
        self._renge_gec(self._bg_normal)

    def _renge_gec(self, hedef, adim=0, toplam=8):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        oran = adim / toplam
        ara = _blend_hex(self._mevcut_bg, hedef, oran)
        self._btn.configure(bg=ara)
        if adim < toplam:
            self._mevcut_bg = ara
            self._anim_id = self.after(18, lambda: self._renge_gec(hedef, adim + 1, toplam))
        else:
            self._mevcut_bg = hedef


# ============================================================================
# GLOW PANEL (secili/aktif listeler icin parlayan cerceve)
# ============================================================================
class GlowPanel(tk.Frame):
    def __init__(self, parent, baslik="", glow_renk=CYBER_NEON_GREEN, **kwargs):
        super().__init__(parent, bg=CYBER_BORDER, padx=1, pady=1)
        self._glow_renk = glow_renk
        self._aktif = False
        self._icerik = tk.Frame(self, bg=CYBER_BG_PANEL)
        self._icerik.pack(fill="both", expand=True)

        if baslik:
            baslik_satir = tk.Frame(self._icerik, bg=CYBER_BG_PANEL)
            baslik_satir.pack(fill="x", padx=12, pady=(10, 4))
            tk.Label(
                baslik_satir, text=baslik, font=FONT_UI_BOLD,
                bg=CYBER_BG_PANEL, fg=CYBER_TEXT_PRIMARY, anchor="w"
            ).pack(side="left")

    @property
    def body(self):
        return self._icerik

    def set_aktif(self, aktif):
        self._aktif = aktif
        self.configure(bg=self._glow_renk if aktif else CYBER_BORDER)


class CyberDivider(tk.Frame):
    """Ince neon bolucu cizgi."""
    def __init__(self, parent, yatay=True, renk=CYBER_BORDER_GLOW, **kwargs):
        if yatay:
            super().__init__(parent, bg=renk, height=1, **kwargs)
        else:
            super().__init__(parent, bg=renk, width=2, **kwargs)


# ============================================================================
# YUKLEME OVERLAY (kaba kurgu / render sirasinda)
# ============================================================================
class LoadingOverlay(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=CYBER_BG_ROOT)
        self._kart = tk.Frame(self, bg=CYBER_BG_ELEVATED, padx=36, pady=28)
        self._kart.place(relx=0.5, rely=0.5, anchor="center")

        glow_cerceve = tk.Frame(self._kart, bg=CYBER_NEON_CYAN, padx=1, pady=1)
        glow_cerceve.pack()
        ic = tk.Frame(glow_cerceve, bg=CYBER_BG_ELEVATED, padx=24, pady=20)
        ic.pack()

        self.spinner = CyberSpinner(ic, size=80, kalinlik=5, renk=CYBER_NEON_CYAN, bg=CYBER_BG_ELEVATED)
        self.spinner.pack()
        self.mesaj = tk.Label(
            ic, text="", font=("Segoe UI", 11, "bold"),
            bg=CYBER_BG_ELEVATED, fg=CYBER_NEON_BLUE
        )
        self.mesaj.pack(pady=(14, 0))
        self.alt_mesaj = tk.Label(
            ic, text="Motor calisiyor, lutfen bekleyin",
            font=FONT_SMALL, bg=CYBER_BG_ELEVATED, fg=CYBER_TEXT_MUTED
        )
        self.alt_mesaj.pack(pady=(4, 0))
        self.place_forget()

    def goster(self, mesaj="Kaba kurgu isleniyor..."):
        self.mesaj.config(text=mesaj)
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self.spinner.start()

    def gizle(self):
        self.spinner.stop()
        self.place_forget()


# ============================================================================
# YOLLAR
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_TXT_YOLU = os.path.join(BASE_DIR, "script.txt")
APP_PY_YOLU = os.path.join(BASE_DIR, "app.py")
OUTPUT_KLASORU = os.path.join(BASE_DIR, "output_shorts")
ARKAPLAN_KLASORU = os.path.join(BASE_DIR, "input_backgrounds")
KARAKTER_KLASORU = os.path.join(BASE_DIR, "input_characters")
SES_KLASORU = os.path.join(BASE_DIR, "input_audio")
BACKUP_KLASORU = os.path.join(OUTPUT_KLASORU, "backups")
PANEL_CONFIG_YOLU = os.path.join(BASE_DIR, "panel_config.json")
AE_PAYLOAD_YOLU = os.path.join(BASE_DIR, "ae_render_payload.json")

RENK_BASARILI = CYBER_NEON_GREEN
RENK_HATALI = "#ff4466"

_TOPLAM_SAHNE_REGEX = re.compile(r"(\d+)\s+sahne bulundu", re.IGNORECASE)
_SAHNE_ISLENIYOR_REGEX = re.compile(r"Sahne\s+(\d+):", re.IGNORECASE)


def ayarlari_yukle():
    if os.path.exists(PANEL_CONFIG_YOLU):
        try:
            with open(PANEL_CONFIG_YOLU, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def ayarlari_kaydet(ayarlar):
    try:
        with open(PANEL_CONFIG_YOLU, "w", encoding="utf-8") as f:
            json.dump(ayarlar, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class LatestRenderState:
    _ornek = None

    def __new__(cls):
        if cls._ornek is None:
            cls._ornek = super().__new__(cls)
            cls._ornek.latest_output_path = None
        return cls._ornek


def klasoru_ac(yol):
    try:
        os.makedirs(yol, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(yol)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol])
    except Exception as e:
        messagebox.showerror("Acilamadi", f"Klasor acilamadi:\n{e}")


def gecmis_videoyu_ac_os_startfile(yol):
    if sys.platform.startswith("win"):
        os.startfile(yol)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", yol])
    else:
        subprocess.Popen(["xdg-open", yol])


def dosya_konumunu_goster(yol):
    tam_yol = os.path.normpath(os.path.abspath(yol))
    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer /select,"{tam_yol}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", tam_yol])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(tam_yol)])


def format_dosya_boyutu(bayt):
    try:
        return f"{bayt / (1024 * 1024):.2f} MB"
    except Exception:
        return "? MB"


def prepare_ae_payload(video_yolu):
    try:
        json_yolu = os.path.splitext(video_yolu)[0] + ".json"
        if not os.path.exists(json_yolu):
            return None
        shutil.copyfile(json_yolu, AE_PAYLOAD_YOLU)
        return AE_PAYLOAD_YOLU
    except Exception:
        return None


def _tema_stili_kur():
    stil = ttk.Style()
    try:
        stil.theme_use("clam")
    except tk.TclError:
        pass
    stil.configure(
        "Cyber.Horizontal.TProgressbar",
        troughcolor=CYBER_BG_INPUT,
        background=CYBER_NEON_PURPLE,
        bordercolor=CYBER_BORDER,
        lightcolor=CYBER_NEON_PURPLE,
        darkcolor=CYBER_NEON_PURPLE,
        thickness=8
    )


# ============================================================================
# ANA PANEL
# ============================================================================
class KontrolPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan // Cyber Studio")
        self.pencere.configure(bg=CYBER_BG_ROOT)

        self.ayarlar = ayarlari_yukle()
        genislik = self.ayarlar.get("pencere_genislik", VARSAYILAN_PENCERE_GENISLIK)
        yukseklik = self.ayarlar.get("pencere_yukseklik", VARSAYILAN_PENCERE_YUKSEKLIK)
        self.pencere.geometry(f"{genislik}x{yukseklik}")
        self.pencere.minsize(960, 680)
        self.pencere.resizable(True, True)

        _tema_stili_kur()

        self.render_durumu = LatestRenderState()
        self._islem_calisiyor = False
        self._islem_kilidi = threading.Lock()
        self._calisan_islem = None

        self._log_kuyrugu = queue.Queue()
        self._video_sonuc_kuyrugu = queue.Queue()
        self._yedek_sonuc_kuyrugu = queue.Queue()
        self._ilerleme_kuyrugu = queue.Queue()

        self._video_taraniyor = False
        self._yedek_taraniyor = False
        self._video_yollari = []
        self._yedek_yollari = []
        self._pencere_boyutu_kaydet_id = None
        self._taslak_kaydet_id = None
        self._son_kaydedilen_script_icerigi = ""

        self._arayuzu_kur()
        self._loading_overlay = LoadingOverlay(self.pencere)

        self._crash_recovery_kontrol_et()
        self._scripti_yukle()
        self.video_listesini_yenile()
        self.yedek_listesini_yenile()

        self._log_kuyrugunu_dinle()
        self._video_kuyrugunu_dinle()
        self._yedek_kuyrugunu_dinle()
        self._ilerleme_kuyrugunu_dinle()
        self._otomatik_taslak_dongusu()

        self.pencere.bind("<Configure>", self._pencere_boyutu_degisti)
        self.pencere.protocol("WM_DELETE_WINDOW", self._kapatilirken)

    # ------------------------------------------------------------
    # ARAYUZ - GRID DUZENI
    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        ana = tk.Frame(self.pencere, bg=CYBER_BG_ROOT)
        ana.pack(fill="both", expand=True, padx=16, pady=14)

        # --- Baslik bandi ---
        baslik_cerceve = tk.Frame(ana, bg=CYBER_BG_ROOT)
        baslik_cerceve.pack(fill="x", pady=(0, 12))
        tk.Label(
            baslik_cerceve, text="CANAVAR ASISTAN", font=FONT_TITLE,
            bg=CYBER_BG_ROOT, fg=CYBER_NEON_CYAN
        ).pack(side="left")
        tk.Label(
            baslik_cerceve, text="  //  Cyber Studio Control", font=("Segoe UI", 11),
            bg=CYBER_BG_ROOT, fg=CYBER_TEXT_MUTED
        ).pack(side="left")
        tk.Label(
            baslik_cerceve, text="Premium Pipeline", font=FONT_SMALL,
            bg=CYBER_BG_ELEVATED, fg=CYBER_NEON_GREEN, padx=8, pady=2
        ).pack(side="right")

        # --- Ana yatay bolme: Sol (script + aksiyon) | Sag (listeler) ---
        ana_paned = tk.PanedWindow(
            ana, orient="horizontal", sashrelief="flat", sashwidth=8,
            bg=CYBER_BG_ROOT, bd=0, opaqueresize=True
        )
        ana_paned.pack(fill="both", expand=True)

        # ===================== SOL KOLON =====================
        sol = tk.Frame(ana_paned, bg=CYBER_BG_ROOT)
        ana_paned.add(sol, stretch="always", minsize=420)

        script_panel = GlowPanel(sol, baslik="Script Editor  //  script.txt", glow_renk=CYBER_NEON_BLUE)
        script_panel.pack(fill="both", expand=True, pady=(0, 10))
        self._script_glow = script_panel

        script_govde = script_panel.body
        tk.Label(
            script_govde, text="Sahne senaryonu (sol panel)", font=FONT_SMALL,
            bg=CYBER_BG_PANEL, fg=CYBER_TEXT_MUTED
        ).pack(anchor="w", padx=12, pady=(0, 4))

        script_ic = tk.Frame(script_govde, bg=CYBER_BORDER, padx=1, pady=1)
        script_ic.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.script_kutusu = tk.Text(
            script_ic, wrap="word", undo=True, font=FONT_MONO,
            bg=CYBER_BG_INPUT, fg=CYBER_TEXT_PRIMARY,
            insertbackground=CYBER_NEON_CYAN,
            selectbackground=CYBER_NEON_PURPLE, selectforeground=CYBER_TEXT_PRIMARY,
            relief="flat", padx=10, pady=10, height=14
        )
        self.script_kutusu.pack(fill="both", expand=True)
        self.script_kutusu.bind("<FocusIn>", lambda e: script_panel.set_aktif(True))
        self.script_kutusu.bind("<FocusOut>", lambda e: script_panel.set_aktif(False))

        kaydet_satiri = tk.Frame(script_govde, bg=CYBER_BG_PANEL)
        kaydet_satiri.pack(fill="x", padx=12, pady=(0, 10))
        self.kaydet_butonu = CyberButton(
            kaydet_satiri, "Scripti Kaydet", self.scripti_kaydet,
            CYBER_BTN_SAVE, CYBER_BTN_SAVE_HOVER, glow_renk=CYBER_NEON_GREEN, height=1
        )
        self.kaydet_butonu.pack(side="right")

        # Aksiyon butonlari
        aksiyon_panel = GlowPanel(sol, baslik="Pipeline Aksiyonlari", glow_renk=CYBER_NEON_PURPLE)
        aksiyon_panel.pack(fill="x", pady=(0, 10))
        aksiyon_govde = aksiyon_panel.body

        self.kurgu_butonu = CyberButton(
            aksiyon_govde, "PYTHON KABA KURGUYU BASLAT", self.kaba_kurguyu_baslat,
            CYBER_BTN_KURGU, CYBER_BTN_KURGU_HOVER, glow_renk=CYBER_NEON_PURPLE, height=2
        )
        self.kurgu_butonu.pack(fill="x", padx=12, pady=(4, 6))

        self.ilerleme_cubugu = ttk.Progressbar(
            aksiyon_govde, style="Cyber.Horizontal.TProgressbar",
            mode="determinate", maximum=100, value=0
        )
        self.ilerleme_cubugu.pack(fill="x", padx=12, pady=(0, 4))
        self.ilerleme_yuzde_etiketi = tk.Label(
            aksiyon_govde, text="", font=FONT_SMALL,
            bg=CYBER_BG_PANEL, fg=CYBER_NEON_CYAN
        )
        self.ilerleme_yuzde_etiketi.pack(anchor="e", padx=12)

        self.ae_butonu = CyberButton(
            aksiyon_govde, "AFTER EFFECTS ASISTANINI ATESLE", self.after_effects_baslat,
            CYBER_BTN_AE, CYBER_BTN_AE_HOVER, glow_renk=CYBER_NEON_BLUE, height=2
        )
        self.ae_butonu.pack(fill="x", padx=12, pady=6)

        self.oynat_butonu = CyberButton(
            aksiyon_govde, "SON VIDEOYU OYNAT", self.son_videoyu_oynat,
            CYBER_BTN_PLAY, CYBER_BTN_PLAY_HOVER, glow_renk=CYBER_NEON_BLUE, height=2
        )
        self.oynat_butonu.pack(fill="x", padx=12, pady=(0, 6))
        self.oynat_butonu.config(state="disabled")

        # Klasor kisayollari
        klasor_satiri = tk.Frame(aksiyon_govde, bg=CYBER_BG_PANEL)
        klasor_satiri.pack(fill="x", padx=12, pady=(0, 10))
        for etiket, klasor in [
            ("Arka Plan", ARKAPLAN_KLASORU), ("Karakter", KARAKTER_KLASORU),
            ("Ses", SES_KLASORU), ("Cikti", OUTPUT_KLASORU),
        ]:
            cb = CyberButton(
                klasor_satiri, etiket, lambda k=klasor: klasoru_ac(k),
                CYBER_BTN_MUTED, CYBER_BTN_MUTED_HOVER, height=1, font=FONT_SMALL
            )
            cb.pack(side="left", expand=True, fill="x", padx=2)

        tk.Button(
            aksiyon_govde, text="AE Yolu / Script Ayarlari", command=self.ayarlari_duzenle,
            font=FONT_SMALL, bg=CYBER_BG_PANEL, fg=CYBER_TEXT_MUTED,
            activebackground=CYBER_BG_ELEVATED, activeforeground=CYBER_TEXT_PRIMARY,
            relief="flat", bd=0, cursor="hand2"
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # Durum banner
        self.durum_etiketi = tk.Label(
            aksiyon_govde, text="Hazir.", font=FONT_UI_BOLD,
            bg=CYBER_BG_ELEVATED, fg=CYBER_TEXT_PRIMARY, pady=8, padx=10
        )
        self.durum_etiketi.pack(fill="x", padx=12, pady=(0, 10))

        # Log
        log_panel = GlowPanel(sol, baslik="Islem Gunlugu", glow_renk=CYBER_NEON_GREEN)
        log_panel.pack(fill="both", expand=True)
        log_ic = tk.Frame(log_panel.body, bg=CYBER_BORDER, padx=1, pady=1)
        log_ic.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.log_kutusu = scrolledtext.ScrolledText(
            log_ic, height=8, wrap="word", bg=CYBER_LOG_BG, fg=CYBER_LOG_FG,
            insertbackground=CYBER_LOG_FG, font=FONT_MONO, relief="flat"
        )
        self.log_kutusu.tag_configure("hata_satiri", foreground=CYBER_LOG_ERR)
        self.log_kutusu.pack(fill="both", expand=True)
        self.log_kutusu.configure(state="disabled")

        # ===================== SAG KOLON =====================
        sag = tk.Frame(ana_paned, bg=CYBER_BG_ROOT)
        ana_paned.add(sag, stretch="always", minsize=340)

        # Sari Yedekler
        yedek_panel = GlowPanel(sag, baslik="SARI YEDEKLER  //  Script Arsivi", glow_renk=CYBER_NEON_AMBER)
        yedek_panel.pack(fill="both", expand=True, pady=(0, 8))
        self._yedek_glow = yedek_panel
        yedek_govde = yedek_panel.body

        yedek_ust = tk.Frame(yedek_govde, bg=CYBER_BG_PANEL)
        yedek_ust.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(
            yedek_ust, text="Kayitli script yedekleri", font=FONT_SMALL,
            bg=CYBER_BG_PANEL, fg=CYBER_NEON_AMBER
        ).pack(side="left")
        tk.Button(
            yedek_ust, text="Yenile", font=FONT_SMALL, command=self.yedek_listesini_yenile,
            bg=CYBER_BG_ELEVATED, fg=CYBER_TEXT_PRIMARY, relief="flat", bd=0, cursor="hand2",
            activebackground=CYBER_BTN_MUTED, padx=8, pady=2
        ).pack(side="right")

        yedek_ic = tk.Frame(yedek_govde, bg=CYBER_NEON_AMBER, padx=1, pady=1)
        yedek_ic.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        yedek_liste_kapsul = tk.Frame(yedek_ic, bg=CYBER_BG_INPUT)
        yedek_liste_kapsul.pack(fill="both", expand=True)
        self.yedek_listesi = tk.Listbox(
            yedek_liste_kapsul, activestyle="none", font=FONT_MONO,
            bg=CYBER_BG_INPUT, fg=CYBER_NEON_AMBER,
            selectbackground="#4a3800", selectforeground=CYBER_NEON_AMBER,
            highlightthickness=0, bd=0, relief="flat"
        )
        yedek_scroll = ttk.Scrollbar(yedek_liste_kapsul, orient="vertical", command=self.yedek_listesi.yview)
        self.yedek_listesi.configure(yscrollcommand=yedek_scroll.set)
        self.yedek_listesi.pack(side="left", fill="both", expand=True)
        yedek_scroll.pack(side="right", fill="y")
        self.yedek_listesi.bind("<Double-Button-1>", lambda e: self.secili_yedegi_yukle())
        self.yedek_listesi.bind("<FocusIn>", lambda e: yedek_panel.set_aktif(True))
        self.yedek_listesi.bind("<FocusOut>", lambda e: yedek_panel.set_aktif(False))

        CyberButton(
            yedek_govde, "Secili Yedegi Editor'e Yukle", self.secili_yedegi_yukle,
            "#854d0e", "#a16207", glow_renk=CYBER_NEON_AMBER, height=1, font=FONT_SMALL
        ).pack(fill="x", padx=12, pady=(0, 10))

        CyberDivider(sag, yatay=True, renk=CYBER_BORDER_GLOW).pack(fill="x", pady=6)

        # Videolar
        video_panel = GlowPanel(sag, baslik="URETILEN VIDEOLAR", glow_renk=CYBER_NEON_BLUE)
        video_panel.pack(fill="both", expand=True)
        self._video_glow = video_panel
        video_govde = video_panel.body

        video_ust = tk.Frame(video_govde, bg=CYBER_BG_PANEL)
        video_ust.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(
            video_ust, text="output_shorts / mp4", font=FONT_SMALL,
            bg=CYBER_BG_PANEL, fg=CYBER_TEXT_MUTED
        ).pack(side="left")
        tk.Button(
            video_ust, text="Yenile", font=FONT_SMALL, command=self.video_listesini_yenile,
            bg=CYBER_BG_ELEVATED, fg=CYBER_TEXT_PRIMARY, relief="flat", bd=0, cursor="hand2",
            activebackground=CYBER_BTN_MUTED, padx=8, pady=2
        ).pack(side="right")

        video_ic = tk.Frame(video_govde, bg=CYBER_NEON_BLUE, padx=1, pady=1)
        video_ic.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        video_liste_kapsul = tk.Frame(video_ic, bg=CYBER_BG_INPUT)
        video_liste_kapsul.pack(fill="both", expand=True)
        self.video_listesi = tk.Listbox(
            video_liste_kapsul, activestyle="none", font=FONT_MONO,
            bg=CYBER_BG_INPUT, fg=CYBER_TEXT_PRIMARY,
            selectbackground="#0c4a6e", selectforeground=CYBER_NEON_BLUE,
            highlightthickness=0, bd=0, relief="flat"
        )
        video_scroll = ttk.Scrollbar(video_liste_kapsul, orient="vertical", command=self.video_listesi.yview)
        self.video_listesi.configure(yscrollcommand=video_scroll.set)
        self.video_listesi.pack(side="left", fill="both", expand=True)
        video_scroll.pack(side="right", fill="y")
        self.video_listesi.bind("<Double-Button-1>", lambda e: self.secili_videoyu_oynat())
        self.video_listesi.bind("<Button-3>", self._sag_tik_menusunu_goster)
        self.video_listesi.bind("<FocusIn>", lambda e: video_panel.set_aktif(True))
        self.video_listesi.bind("<FocusOut>", lambda e: video_panel.set_aktif(False))

        self._sag_tik_menusu = tk.Menu(
            self.pencere, tearoff=0, bg=CYBER_BG_ELEVATED, fg=CYBER_TEXT_PRIMARY,
            activebackground=CYBER_BTN_KURGU, activeforeground=CYBER_TEXT_PRIMARY, bd=0
        )
        self._sag_tik_menusu.add_command(label="Guvenli Oynat", command=self.secili_videoyu_oynat)
        self._sag_tik_menusu.add_command(label="Akilli Yeniden Adlandir", command=self.secili_videoyu_yeniden_adlandir)
        self._sag_tik_menusu.add_command(label="Dosya Konumunu Goster", command=self.secili_video_konumunu_goster)
        self._sag_tik_menusu.add_separator()
        self._sag_tik_menusu.add_command(label="Sil", command=self.secili_videoyu_sil)

        CyberButton(
            video_govde, "OYNAT", self.secili_videoyu_oynat,
            CYBER_BTN_PLAY, CYBER_BTN_PLAY_HOVER, glow_renk=CYBER_NEON_BLUE, height=1
        ).pack(fill="x", padx=12, pady=(0, 4))

        video_kontrol = tk.Frame(video_govde, bg=CYBER_BG_PANEL)
        video_kontrol.pack(fill="x", padx=12, pady=(0, 4))
        for metin, komut, renk in [
            ("Yeniden Adlandir", self.secili_videoyu_yeniden_adlandir, CYBER_BTN_MUTED),
            ("Konumu Goster", self.secili_video_konumunu_goster, CYBER_BTN_MUTED),
        ]:
            CyberButton(
                video_kontrol, metin, komut, renk, CYBER_BTN_MUTED_HOVER, height=1, font=FONT_SMALL
            ).pack(side="left", expand=True, fill="x", padx=2)

        CyberButton(
            video_govde, "SIL", self.secili_videoyu_sil,
            CYBER_BTN_DANGER, CYBER_BTN_DANGER_HOVER, glow_renk=RENK_HATALI, height=1, font=FONT_SMALL
        ).pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------
    # YUKLEME OVERLAY YARDIMCILARI
    # ------------------------------------------------------------
    def _loading_goster(self, mesaj):
        self.pencere.after(0, lambda: self._loading_overlay.goster(mesaj))

    def _loading_gizle(self):
        self.pencere.after(0, self._loading_overlay.gizle)

    # ------------------------------------------------------------
    # CRASH RECOVERY
    # ------------------------------------------------------------
    def _crash_recovery_kontrol_et(self):
        taslak = self.ayarlar.get("unsaved_draft", "").strip()
        if not taslak:
            return
        mevcut = ""
        if os.path.exists(SCRIPT_TXT_YOLU):
            try:
                with open(SCRIPT_TXT_YOLU, "r", encoding="utf-8") as f:
                    mevcut = f.read().strip()
            except Exception:
                pass
        if taslak == mevcut:
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)
            return
        if messagebox.askyesno(
            "Kaydedilmemis Taslak",
            "Onceki oturumdan kaydedilmemis bir script taslagi bulundu.\nGeri yuklensin mi?"
        ):
            self.script_kutusu.delete("1.0", "end")
            self.script_kutusu.insert("1.0", taslak)
            self._log_kuyrugu.put("Kaydedilmemis taslak geri yuklendi.")
        else:
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)

    def _otomatik_taslak_dongusu(self):
        try:
            mevcut = self.script_kutusu.get("1.0", "end-1c")
            if mevcut.strip() != self._son_kaydedilen_script_icerigi.strip():
                self.ayarlar["unsaved_draft"] = mevcut
                ayarlari_kaydet(self.ayarlar)
        except Exception:
            pass
        finally:
            self._taslak_kaydet_id = self.pencere.after(5000, self._otomatik_taslak_dongusu)

    def _pencere_boyutu_degisti(self, event=None):
        if event is not None and event.widget is not self.pencere:
            return
        if self._pencere_boyutu_kaydet_id:
            self.pencere.after_cancel(self._pencere_boyutu_kaydet_id)
        self._pencere_boyutu_kaydet_id = self.pencere.after(500, self._pencere_boyutunu_kaydet)

    def _pencere_boyutunu_kaydet(self):
        try:
            self.ayarlar["pencere_genislik"] = self.pencere.winfo_width()
            self.ayarlar["pencere_yukseklik"] = self.pencere.winfo_height()
            ayarlari_kaydet(self.ayarlar)
        except Exception:
            pass

    # ------------------------------------------------------------
    # SCRIPT
    # ------------------------------------------------------------
    def _scripti_yukle(self):
        if os.path.exists(SCRIPT_TXT_YOLU):
            try:
                with open(SCRIPT_TXT_YOLU, "r", encoding="utf-8") as f:
                    icerik = f.read()
                if not self.script_kutusu.get("1.0", "end-1c").strip():
                    self.script_kutusu.delete("1.0", "end")
                    self.script_kutusu.insert("1.0", icerik)
                self._son_kaydedilen_script_icerigi = icerik
                self._log_kuyrugu.put("script.txt yuklendi.")
            except Exception as e:
                self._log_kuyrugu.put(f"script.txt okunamadi: {e}")
        else:
            self._log_kuyrugu.put("script.txt henuz yok.")

    def scripti_kaydet(self):
        try:
            icerik = self.script_kutusu.get("1.0", "end-1c")
            if os.path.exists(SCRIPT_TXT_YOLU):
                try:
                    os.makedirs(BACKUP_KLASORU, exist_ok=True)
                    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
                    yedek_yolu = os.path.join(BACKUP_KLASORU, f"script_{zaman}.txt")
                    shutil.copyfile(SCRIPT_TXT_YOLU, yedek_yolu)
                    self._log_kuyrugu.put(f"Yedek: backups/{os.path.basename(yedek_yolu)}")
                except Exception as e:
                    self._log_kuyrugu.put(f"[HATA] Yedekleme: {e}")
            with open(SCRIPT_TXT_YOLU, "w", encoding="utf-8") as f:
                f.write(icerik)
            self._son_kaydedilen_script_icerigi = icerik
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)
            self._log_kuyrugu.put("script.txt kaydedildi.")
            self._banner_guncelle("script.txt kaydedildi.", CYBER_BG_ELEVATED, CYBER_NEON_GREEN)
            self.yedek_listesini_yenile()
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Kayit basarisiz: {e}")
            self._banner_guncelle(f"Kayit basarisiz: {e}", "#3b1219", RENK_HATALI)

    # ------------------------------------------------------------
    # SARI YEDEKLER LISTESI
    # ------------------------------------------------------------
    def yedek_listesini_yenile(self):
        if self._yedek_taraniyor:
            return
        self._yedek_taraniyor = True
        threading.Thread(target=self._yedek_tarama_arka_plan, daemon=True).start()

    def _yedek_tarama_arka_plan(self):
        try:
            os.makedirs(BACKUP_KLASORU, exist_ok=True)
            kayitlar = []
            for f in os.listdir(BACKUP_KLASORU):
                if not f.lower().endswith(".txt"):
                    continue
                tam = os.path.join(BACKUP_KLASORU, f)
                try:
                    kayitlar.append((tam, f, os.path.getmtime(tam), os.path.getsize(tam)))
                except OSError:
                    continue
            kayitlar.sort(key=lambda k: k[2], reverse=True)
            self._yedek_sonuc_kuyrugu.put(kayitlar)
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Yedek listesi taranamadi: {e}")
            self._yedek_taraniyor = False

    def _yedek_kuyrugunu_dinle(self):
        try:
            while True:
                kayitlar = self._yedek_sonuc_kuyrugu.get_nowait()
                self._yedek_listesini_guncelle(kayitlar)
        except queue.Empty:
            pass
        finally:
            self.pencere.after(100, self._yedek_kuyrugunu_dinle)

    def _yedek_listesini_guncelle(self, kayitlar):
        try:
            self._yedek_yollari = [k[0] for k in kayitlar]
            self.yedek_listesi.delete(0, "end")
            for tam, ad, ts, boyut in kayitlar:
                tarih = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
                kb = boyut / 1024
                self.yedek_listesi.insert("end", f"[{tarih}]  {kb:.1f} KB  |  {ad}")
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Yedek listesi guncellenemedi: {e}")
        finally:
            self._yedek_taraniyor = False

    def secili_yedegi_yukle(self):
        secim = self.yedek_listesi.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once bir yedek sec.")
            return
        indeks = secim[0]
        if indeks >= len(self._yedek_yollari):
            self.yedek_listesini_yenile()
            return
        yol = self._yedek_yollari[indeks]
        try:
            with open(yol, "r", encoding="utf-8") as f:
                icerik = f.read()
            self.script_kutusu.delete("1.0", "end")
            self.script_kutusu.insert("1.0", icerik)
            self._log_kuyrugu.put(f"Yedek yuklendi: {os.path.basename(yol)}")
            self._banner_guncelle(f"Yedek yuklendi: {os.path.basename(yol)}", CYBER_BG_ELEVATED, CYBER_NEON_AMBER)
        except Exception as e:
            messagebox.showerror("Hata", f"Yedek okunamadi:\n{e}")

    # ------------------------------------------------------------
    # LOG / BANNER / ILERLEME
    # ------------------------------------------------------------
    def _log_kuyrugunu_dinle(self):
        try:
            while True:
                mesaj = self._log_kuyrugu.get_nowait()
                self.log_kutusu.configure(state="normal")
                if any(k in mesaj.upper() for k in ("[HATA]", "HATA:", "ERROR")):
                    self.log_kutusu.insert("end", mesaj + "\n", "hata_satiri")
                else:
                    self.log_kutusu.insert("end", mesaj + "\n")
                self.log_kutusu.see("end")
                self.log_kutusu.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.pencere.after(100, self._log_kuyrugunu_dinle)

    def _banner_guncelle(self, mesaj, bg, fg):
        def _g():
            self.durum_etiketi.config(text=mesaj, bg=bg, fg=fg)
        self.pencere.after(0, _g)

    def _ilerleme_kuyrugunu_dinle(self):
        try:
            while True:
                yuzde = self._ilerleme_kuyrugu.get_nowait()
                self.ilerleme_cubugu["value"] = yuzde
                self.ilerleme_yuzde_etiketi.config(text=f"%{yuzde:.0f}")
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._ilerleme_kuyrugunu_dinle)

    # ------------------------------------------------------------
    # KABA KURGU
    # ------------------------------------------------------------
    def kaba_kurguyu_baslat(self):
        with self._islem_kilidi:
            if self._islem_calisiyor:
                messagebox.showinfo("Mesgul", "Zaten bir islem calisiyor.")
                return
            if not os.path.exists(APP_PY_YOLU):
                messagebox.showerror("Bulunamadi", f"app.py bulunamadi:\n{APP_PY_YOLU}")
                return
            self._islem_calisiyor = True

        self.kurgu_butonu.config(state="disabled", text="ISLENIYOR...")
        self._loading_goster("Kaba kurgu motoru calisiyor...")
        self._banner_guncelle("Python kaba kurgu calisiyor...", CYBER_BG_ELEVATED, CYBER_NEON_PURPLE)
        self._ilerleme_kuyrugu.put(0)
        self._log_kuyrugu.put("")
        self._log_kuyrugu.put("python app.py baslatildi...")
        threading.Thread(target=self.run_engine, daemon=True).start()

    def run_engine(self):
        ek = {}
        if sys.platform.startswith("win"):
            ek["creationflags"] = subprocess.CREATE_NO_WINDOW

        yeni_video = None
        basarili = False
        toplam_sahne = None
        islenen = 0

        try:
            islem = subprocess.Popen(
                [sys.executable, APP_PY_YOLU], cwd=BASE_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, **ek
            )
            self._calisan_islem = islem

            for satir in islem.stdout:
                satir = satir.rstrip()
                if not satir:
                    continue
                self._log_kuyrugu.put(satir)
                if toplam_sahne is None:
                    m = _TOPLAM_SAHNE_REGEX.search(satir)
                    if m:
                        try:
                            toplam_sahne = int(m.group(1))
                        except ValueError:
                            pass
                elif toplam_sahne:
                    m2 = _SAHNE_ISLENIYOR_REGEX.search(satir)
                    if m2:
                        try:
                            islenen = int(m2.group(1))
                            self._ilerleme_kuyrugu.put(min(95, (islenen / toplam_sahne) * 90))
                        except (ValueError, ZeroDivisionError):
                            pass
                if satir.startswith("RENDER_COMPLETE:"):
                    yeni_video = satir.split("RENDER_COMPLETE:", 1)[1].strip()

            islem.wait()
            basarili = islem.returncode == 0 and yeni_video and os.path.isfile(yeni_video)
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] {e}")
        finally:
            self._calisan_islem = None

        if basarili:
            self._ilerleme_kuyrugu.put(100)
            self.render_durumu.latest_output_path = yeni_video
            self._log_kuyrugu.put("Islem basariyla tamamlandi.")
            self._banner_guncelle("RENDER SUCCESSFUL", "#0d2b1a", CYBER_NEON_GREEN)
            self.pencere.after(0, lambda: self.oynat_butonu.config(state="normal"))
            self.pencere.after(0, self.video_listesini_yenile)
            payload = prepare_ae_payload(yeni_video)
            if payload:
                self._log_kuyrugu.put(f"AE payload hazir: {os.path.basename(payload)}")
        else:
            self._ilerleme_kuyrugu.put(0)
            self._log_kuyrugu.put("[HATA] Islem basarisiz.")
            self._banner_guncelle("RENDER FAILED", "#3b1219", RENK_HATALI)

        gc.collect()
        self._loading_gizle()
        with self._islem_kilidi:
            self._islem_calisiyor = False
        self.pencere.after(0, lambda: self.kurgu_butonu.config(
            state="normal", text="PYTHON KABA KURGUYU BASLAT"
        ))

    def son_videoyu_oynat(self):
        yol = self.render_durumu.latest_output_path
        if yol and os.path.exists(yol):
            try:
                if sys.platform.startswith("win"):
                    subprocess.Popen(["cmd", "/c", "start", "", yol], shell=True)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", yol])
                else:
                    subprocess.Popen(["xdg-open", yol])
                self._log_kuyrugu.put(f"Video oynatiliyor: {yol}")
            except Exception as e:
                messagebox.showerror("Oynatilamadi", str(e))
        else:
            messagebox.showwarning("Video yok", "Henuz basariyla uretilmis bir video yok.")

    # ------------------------------------------------------------
    # VIDEOLAR LISTESI
    # ------------------------------------------------------------
    def video_listesini_yenile(self):
        if self._video_taraniyor:
            return
        self._video_taraniyor = True
        threading.Thread(target=self._video_tarama_arka_plan, daemon=True).start()

    def _video_tarama_arka_plan(self):
        try:
            os.makedirs(OUTPUT_KLASORU, exist_ok=True)
            kayitlar = []
            for f in os.listdir(OUTPUT_KLASORU):
                if not f.lower().endswith(".mp4"):
                    continue
                tam = os.path.join(OUTPUT_KLASORU, f)
                try:
                    kayitlar.append((tam, f, os.path.getmtime(tam), os.path.getsize(tam)))
                except OSError:
                    continue
            kayitlar.sort(key=lambda k: k[2], reverse=True)
            self._video_sonuc_kuyrugu.put(kayitlar)
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Video listesi: {e}")
            self._video_taraniyor = False

    def _video_kuyrugunu_dinle(self):
        try:
            while True:
                self._video_listesini_guncelle(self._video_sonuc_kuyrugu.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.pencere.after(100, self._video_kuyrugunu_dinle)

    def _video_listesini_guncelle(self, kayitlar):
        try:
            self._video_yollari = [k[0] for k in kayitlar]
            self.video_listesi.delete(0, "end")
            for tam, ad, ts, boyut in kayitlar:
                tarih = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
                self.video_listesi.insert("end", f"[{tarih}]  {format_dosya_boyutu(boyut)}  |  {ad}")
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Video listesi guncellenemedi: {e}")
        finally:
            self._video_taraniyor = False

    def _secili_video_yolunu_al(self):
        secim = self.video_listesi.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once bir video sec.")
            return None
        i = secim[0]
        if i >= len(self._video_yollari):
            self.video_listesini_yenile()
            return None
        return self._video_yollari[i]

    def _sag_tik_menusunu_goster(self, event):
        try:
            idx = self.video_listesi.nearest(event.y)
            if idx >= 0:
                self.video_listesi.selection_clear(0, "end")
                self.video_listesi.selection_set(idx)
            self._sag_tik_menusu.tk_popup(event.x_root, event.y_root)
        finally:
            self._sag_tik_menusu.grab_release()

    def secili_videoyu_oynat(self):
        yol = self._secili_video_yolunu_al()
        if not yol:
            return
        if os.path.exists(yol):
            try:
                gecmis_videoyu_ac_os_startfile(yol)
                self._log_kuyrugu.put(f"Oynatiliyor: {yol}")
            except Exception as e:
                messagebox.showerror("Oynatilamadi", str(e))
        else:
            messagebox.showwarning("Bulunamadi", "Dosya mevcut degil.")
            self.video_listesini_yenile()

    def secili_videoyu_yeniden_adlandir(self):
        yol = self._secili_video_yolunu_al()
        if not yol or not os.path.exists(yol):
            messagebox.showwarning("Bulunamadi", "Dosya mevcut degil.")
            return
        eski = os.path.basename(yol)
        yeni_govde = simpledialog.askstring(
            "Yeniden Adlandir", "Yeni ad:", initialvalue=os.path.splitext(eski)[0], parent=self.pencere
        )
        if not yeni_govde or not yeni_govde.strip():
            return
        yeni_yol = os.path.join(OUTPUT_KLASORU, os.path.splitext(yeni_govde.strip())[0] + ".mp4")
        if os.path.abspath(yeni_yol) == os.path.abspath(yol):
            return
        if os.path.exists(yeni_yol):
            messagebox.showerror("Cakisma", "Ayni isimde dosya var.")
            return
        try:
            os.rename(yol, yeni_yol)
            if self.render_durumu.latest_output_path == yol:
                self.render_durumu.latest_output_path = yeni_yol
            self.video_listesini_yenile()
        except OSError as e:
            messagebox.showerror("Hata", str(e))

    def secili_videoyu_sil(self):
        yol = self._secili_video_yolunu_al()
        if not yol or not os.path.exists(yol):
            return
        if not messagebox.askyesno("Sil", f"'{os.path.basename(yol)}' kalici silinsin mi?"):
            return
        try:
            os.remove(yol)
            if self.render_durumu.latest_output_path == yol:
                self.render_durumu.latest_output_path = None
                self.pencere.after(0, lambda: self.oynat_butonu.config(state="disabled"))
            self.video_listesini_yenile()
        except OSError as e:
            messagebox.showerror("Silinemedi", str(e))

    def secili_video_konumunu_goster(self):
        yol = self._secili_video_yolunu_al()
        if yol and os.path.exists(yol):
            dosya_konumunu_goster(yol)

    # ------------------------------------------------------------
    # AFTER EFFECTS
    # ------------------------------------------------------------
    def after_effects_baslat(self):
        ae_yolu = self.ayarlar.get("ae_yolu")
        jsx_yolu = self.ayarlar.get("jsx_yolu")
        if not ae_yolu or not os.path.exists(ae_yolu):
            ae_yolu = self._ae_yolunu_sor()
            if not ae_yolu:
                return
        if not jsx_yolu or not os.path.exists(jsx_yolu):
            jsx_yolu = self._jsx_yolunu_sor()
            if not jsx_yolu:
                return

        self._loading_goster("After Effects baslatiliyor...")
        self._log_kuyrugu.put(f"AE baslatiliyor: {ae_yolu}")
        try:
            subprocess.Popen([ae_yolu, "-r", jsx_yolu])
            self._banner_guncelle("After Effects baslatildi.", "#0d2b1a", CYBER_NEON_GREEN)
            self._log_kuyrugu.put("AE komutu gonderildi.")
        except Exception as e:
            self._banner_guncelle(f"AE baslatilamadi: {e}", "#3b1219", RENK_HATALI)
            messagebox.showerror("Baslatilamadi", str(e))
        finally:
            self.pencere.after(800, self._loading_gizle)

    def _ae_yolunu_sor(self):
        messagebox.showinfo("AfterFX.exe", r"AfterFX.exe dosyasini sec.")
        yol = filedialog.askopenfilename(title="AfterFX.exe", filetypes=[("Uygulama", "*.exe")])
        if yol:
            self.ayarlar["ae_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
        return yol or None

    def _jsx_yolunu_sor(self):
        varsayilan = os.path.join(BASE_DIR, "canavar_asistan.jsx")
        if os.path.exists(varsayilan):
            self.ayarlar["jsx_yolu"] = varsayilan
            ayarlari_kaydet(self.ayarlar)
            return varsayilan
        yol = filedialog.askopenfilename(title="canavar_asistan.jsx", filetypes=[("JSX", "*.jsx")])
        if yol:
            self.ayarlar["jsx_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
        return yol or None

    def ayarlari_duzenle(self):
        pencere = tk.Toplevel(self.pencere)
        pencere.title("Ayarlar")
        pencere.geometry("500x240")
        pencere.configure(bg=CYBER_BG_PANEL)
        pencere.grab_set()

        for metin, anahtar, komut in [
            ("AfterFX.exe:", "ae_yolu", self._ae_yolunu_sor),
            ("canavar_asistan.jsx:", "jsx_yolu", None),
        ]:
            tk.Label(pencere, text=metin, font=FONT_UI, bg=CYBER_BG_PANEL, fg=CYBER_TEXT_PRIMARY
                     ).pack(pady=(12, 2), padx=16, anchor="w")
            etiket = tk.Label(pencere, text=self.ayarlar.get(anahtar, "(secilmedi)"),
                              font=FONT_SMALL, bg=CYBER_BG_INPUT, fg=CYBER_TEXT_MUTED,
                              wraplength=460, justify="left", padx=8, pady=4)
            etiket.pack(fill="x", padx=16)

            if komut:
                tk.Button(pencere, text="Sec", command=lambda k=anahtar, fn=komut, lb=etiket: self._ayar_sec(fn, lb),
                          bg=CYBER_BTN_MUTED, fg=CYBER_TEXT_PRIMARY, relief="flat").pack(padx=16, anchor="w")
            else:
                tk.Button(
                    pencere, text="Sec",
                    command=lambda k=anahtar, lb=etiket: self._jsx_sec(lb),
                    bg=CYBER_BTN_MUTED, fg=CYBER_TEXT_PRIMARY, relief="flat"
                ).pack(padx=16, anchor="w")

    def _ayar_sec(self, fn, etiket):
        yol = fn()
        if yol:
            etiket.config(text=yol)

    def _jsx_sec(self, etiket):
        yol = filedialog.askopenfilename(title="canavar_asistan.jsx", filetypes=[("JSX", "*.jsx")])
        if yol:
            self.ayarlar["jsx_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
            etiket.config(text=yol)

    def _kapatilirken(self):
        try:
            if self._calisan_islem and self._calisan_islem.poll() is None:
                if not messagebox.askyesno("Islem devam ediyor", "Kaba kurgu hala calisiyor. Kapatilsin mi?"):
                    return
                try:
                    self._calisan_islem.terminate()
                except Exception:
                    pass
            if self._taslak_kaydet_id:
                self.pencere.after_cancel(self._taslak_kaydet_id)
            if self._pencere_boyutu_kaydet_id:
                self.pencere.after_cancel(self._pencere_boyutu_kaydet_id)
            self._loading_gizle()
            self._pencere_boyutunu_kaydet()
            gc.collect()
        finally:
            self.pencere.destroy()


if __name__ == "__main__":
    pencere = tk.Tk()
    uygulama = KontrolPaneli(pencere)
    pencere.mainloop()
