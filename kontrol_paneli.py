"""
kontrol_paneli.py
------------------
Canavar Asistan - Ana Kontrol Paneli (Enterprise+ Surum)

ONEMLI NOT (dogruluk icin): Istekte "QThread / Signal-Slot mimarisi" istenmisti.
Bu, PyQt/PySide'a ait bir kavramdir; Tkinter'da boyle bir sey YOKTUR. Burada
onun gercek Tkinter karsiligi olan, zaten kanitlanmis calisan yontem
kullanildi: threading.Thread (arka plan islemi) + queue.Queue (thread-safe
veri aktarimi) + root.after() polling (ana thread'de guvenli UI guncelleme).
Sahte bir "QThread" ismi kullanip sizi yanlis bilgilendirmek istemedim.

Mimari ozeti:
- LatestRenderState: son uretilen video yolunu tutan Singleton sinif
- Tum arka plan islemleri (motor calistirma, dosya tarama) ayri thread'lerde,
  sonuclar queue.Queue uzerinden ana thread'e guvenli sekilde tasiniyor
- panel_config.json: pencere boyutu, AE/JSX yollari, ve "kaydedilmemis taslak"
  (crash recovery) burada saklaniyor
- Scripti Kaydet -> otomatik olarak eski hali output_shorts/backups/'a
  zaman damgasiyla yedekleniyor
- Crash-Recovery: uygulama duzgun kapanmadan once yazilan ama kaydedilmemis
  script metni, bir sonraki acilista geri yuklenmesi icin sorulur
- prepare_ae_payload(): son videonun JSON metadata'sini After Effects'in
  hep ayni sabit isimden okuyacagi bir "kopru" dosyasina hazirlar
- Gercek zamanli % ilerleme cubugu: motor ciktisindaki "X sahne bulundu" ve
  "Sahne N:" satirlarini ayristirarak hesaplanir
- Kapatirken (WM_DELETE_WINDOW): calisan alt surec varsa sonlandirilir,
  gc.collect() ile bellek temizlenir, pencere boyutu kaydedilir
"""

import os
import sys
import json
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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

RENK_BASARILI = "#4CAF50"
RENK_HATALI = "#F44336"

RENK_KURGU_BG = "#673AB7"
RENK_AE_BG = "#E53935"
RENK_OYNAT_BG = "#1E88E5"
RENK_KLASOR_BG = "#37474F"
RENK_KAYDET_BG = "#2E7D32"
RENK_BEYAZ = "#FFFFFF"

RENK_SCRIPT_KUTUSU_BG = "#FAFAFA"
RENK_SCRIPT_KUTUSU_FG = "#000000"

RENK_LOG_BG = "#000000"
RENK_LOG_FG = "#00FF00"
RENK_LOG_HATA_FG = "#FF3333"

RENK_MENU_BG = "#263238"
RENK_MENU_FG = "#ECEFF1"

VARSAYILAN_PENCERE_GENISLIK = 900
VARSAYILAN_PENCERE_YUKSEKLIK = 780

# Log satirlarindan gercek zamanli ilerleme yuzdesi cikarmak icin kullanilan
# regex'ler (app.py'nin log formatiyla birebir eslesir).
_TOPLAM_SAHNE_REGEX = re.compile(r"(\d+)\s+sahne bulundu", re.IGNORECASE)
_SAHNE_ISLENIYOR_REGEX = re.compile(r"Sahne\s+(\d+):", re.IGNORECASE)


# ============================================================================
# AYAR / CONFIG YONETIMI (panel_config.json)
# ============================================================================
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


# ============================================================================
# SINGLETON: LatestRenderState
# ============================================================================
class LatestRenderState:
    _ornek = None

    def __new__(cls):
        if cls._ornek is None:
            cls._ornek = super().__new__(cls)
            cls._ornek.latest_output_path = None
        return cls._ornek


# ============================================================================
# OS SEVIYESI YARDIMCILAR
# ============================================================================
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
    """Uretilen Videolar listesinden secilen bir videoyu os.startfile ile acar."""
    if sys.platform.startswith("win"):
        os.startfile(yol)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", yol])
    else:
        subprocess.Popen(["xdg-open", yol])


def dosya_konumunu_goster(yol):
    """Windows Gezgini'nde dosyayi SECILI (mavi vurgulu) halde gosterir."""
    tam_yol = os.path.normpath(os.path.abspath(yol))
    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer /select,"{tam_yol}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", tam_yol])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(tam_yol)])


def format_dosya_boyutu(bayt):
    """1234567 -> '1.18 MB' seklinde okunabilir bir string uretir."""
    try:
        mb = bayt / (1024 * 1024)
        return f"{mb:.2f} MB"
    except Exception:
        return "? MB"


def prepare_ae_payload(video_yolu):
    """
    'Kopru' fonksiyonu: app.py'nin urettigi <video>.json metadata dosyasini
    bulur ve After Effects scriptinin HER ZAMAN AYNI SABIT isimden
    okuyabilecegi 'ae_render_payload.json' dosyasina kopyalar.
    Basarili olursa hedef yolu, bulunamazsa None doner.
    """
    try:
        json_yolu = os.path.splitext(video_yolu)[0] + ".json"
        if not os.path.exists(json_yolu):
            return None
        shutil.copyfile(json_yolu, AE_PAYLOAD_YOLU)
        return AE_PAYLOAD_YOLU
    except Exception:
        return None


# ============================================================================
# ANA PANEL
# ============================================================================
class KontrolPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan - Kontrol Paneli")

        self.ayarlar = ayarlari_yukle()
        genislik = self.ayarlar.get("pencere_genislik", VARSAYILAN_PENCERE_GENISLIK)
        yukseklik = self.ayarlar.get("pencere_yukseklik", VARSAYILAN_PENCERE_YUKSEKLIK)
        self.pencere.geometry(f"{genislik}x{yukseklik}")
        self.pencere.minsize(700, 600)
        self.pencere.resizable(True, True)

        self.render_durumu = LatestRenderState()
        self._islem_calisiyor = False
        self._islem_kilidi = threading.Lock()  # thread-safe mutex (Qt Mutex karsiligi)
        self._calisan_islem = None  # su an calisan subprocess.Popen referansi (temiz kapatma icin)

        self._log_kuyrugu = queue.Queue()
        self._video_sonuc_kuyrugu = queue.Queue()
        self._ilerleme_kuyrugu = queue.Queue()

        self._video_taraniyor = False
        self._video_yollari = []
        self._pencere_boyutu_kaydet_id = None
        self._taslak_kaydet_id = None
        self._son_kaydedilen_script_icerigi = ""

        self._arayuzu_kur()
        self._crash_recovery_kontrol_et()
        self._scripti_yukle()
        self.video_listesini_yenile()

        self._log_kuyrugunu_dinle()
        self._video_kuyrugunu_dinle()
        self._ilerleme_kuyrugunu_dinle()
        self._otomatik_taslak_dongusu()

        self.pencere.bind("<Configure>", self._pencere_boyutu_degisti)
        self.pencere.protocol("WM_DELETE_WINDOW", self._kapatilirken)

    # ------------------------------------------------------------
    # ARAYUZ
    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        ana = tk.Frame(self.pencere)
        ana.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(ana, text="Canavar Asistan - Kontrol Paneli", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        tk.Label(ana, text="script.txt icerigi:", font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 2))
        self.script_kutusu = tk.Text(
            ana, height=10, wrap="word", undo=True,
            bg=RENK_SCRIPT_KUTUSU_BG, fg=RENK_SCRIPT_KUTUSU_FG, insertbackground=RENK_SCRIPT_KUTUSU_FG
        )
        self.script_kutusu.pack(fill="both", expand=True)

        tk.Button(
            ana, text="Scripti Kaydet", command=self.scripti_kaydet,
            bg=RENK_KAYDET_BG, fg=RENK_BEYAZ, activebackground=RENK_KAYDET_BG, activeforeground=RENK_BEYAZ
        ).pack(anchor="e", pady=(6, 12))

        # --- Ana islem butonlari ---
        buton_cercevesi = tk.Frame(ana)
        buton_cercevesi.pack(fill="x", pady=(0, 6))

        self.kurgu_butonu = tk.Button(
            buton_cercevesi, text="PYTHON KABA KURGUYU BASLAT",
            command=self.kaba_kurguyu_baslat, font=("Segoe UI", 10, "bold"), height=2,
            bg=RENK_KURGU_BG, fg=RENK_BEYAZ, activebackground=RENK_KURGU_BG, activeforeground=RENK_BEYAZ,
            disabledforeground=RENK_BEYAZ
        )
        self.kurgu_butonu.pack(fill="x", pady=3)

        # --- Gercek zamanli ilerleme cubugu ---
        stil = ttk.Style()
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass
        stil.configure("Kurgu.Horizontal.TProgressbar", troughcolor="#222222", background=RENK_KURGU_BG)

        self.ilerleme_cubugu = ttk.Progressbar(
            buton_cercevesi, style="Kurgu.Horizontal.TProgressbar",
            mode="determinate", maximum=100, value=0
        )
        self.ilerleme_cubugu.pack(fill="x", pady=(0, 6))
        self.ilerleme_yuzde_etiketi = tk.Label(buton_cercevesi, text="", font=("Segoe UI", 8))
        self.ilerleme_yuzde_etiketi.pack(anchor="e")

        self.ae_butonu = tk.Button(
            buton_cercevesi, text="AFTER EFFECTS ASISTANINI ATESLE",
            command=self.after_effects_baslat, font=("Segoe UI", 10, "bold"), height=2,
            bg=RENK_AE_BG, fg=RENK_BEYAZ, activebackground=RENK_AE_BG, activeforeground=RENK_BEYAZ
        )
        self.ae_butonu.pack(fill="x", pady=3)

        self.oynat_butonu = tk.Button(
            buton_cercevesi, text="SON VIDEOYU OYNAT",
            command=self.son_videoyu_oynat, font=("Segoe UI", 10, "bold"), height=2,
            state="disabled",
            bg=RENK_OYNAT_BG, fg=RENK_BEYAZ, activebackground=RENK_OYNAT_BG, activeforeground=RENK_BEYAZ,
            disabledforeground=RENK_BEYAZ
        )
        self.oynat_butonu.pack(fill="x", pady=3)

        # --- Klasor kisayollari ---
        klasor_cercevesi = tk.Frame(ana)
        klasor_cercevesi.pack(fill="x", pady=(0, 6))
        tk.Label(klasor_cercevesi, text="Klasorleri Ac:", font=("Segoe UI", 9)).pack(anchor="w")
        klasor_buton_satiri = tk.Frame(klasor_cercevesi)
        klasor_buton_satiri.pack(fill="x")
        for etiket, klasor in [
            ("Arka Planlar", ARKAPLAN_KLASORU), ("Karakterler", KARAKTER_KLASORU),
            ("Ses", SES_KLASORU), ("Ciktilar", OUTPUT_KLASORU),
        ]:
            tk.Button(klasor_buton_satiri, text=etiket, bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                      activebackground=RENK_KLASOR_BG, activeforeground=RENK_BEYAZ,
                      command=lambda k=klasor: klasoru_ac(k)).pack(side="left", expand=True, fill="x", padx=2)

        tk.Button(
            ana, text="AE Yolu / Script Ayarlari", command=self.ayarlari_duzenle, font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(4, 0))

        # --- Durum banner'i ---
        self.durum_etiketi = tk.Label(
            ana, text="Hazir.", font=("Segoe UI", 10, "bold"), relief="groove", pady=8
        )
        self.durum_etiketi.pack(fill="x", pady=(6, 6))

        # --- Log alani + Uretilen Videolar (yan yana, PanedWindow ile) ---
        alt_bolme = tk.PanedWindow(ana, orient="horizontal", sashrelief="raised", sashwidth=6)
        alt_bolme.pack(fill="both", expand=True, pady=(6, 0))

        log_cercevesi = tk.Frame(alt_bolme)
        tk.Label(log_cercevesi, text="Islem Gunlugu:", font=("Segoe UI", 9)).pack(anchor="w")
        self.log_kutusu = scrolledtext.ScrolledText(
            log_cercevesi, height=10, wrap="word", bg=RENK_LOG_BG, fg=RENK_LOG_FG, insertbackground=RENK_LOG_FG
        )
        self.log_kutusu.tag_configure("hata_satiri", foreground=RENK_LOG_HATA_FG)
        self.log_kutusu.pack(fill="both", expand=True, pady=(2, 0))
        self.log_kutusu.configure(state="disabled")
        alt_bolme.add(log_cercevesi, stretch="always", width=420)

        video_cercevesi = tk.Frame(alt_bolme)
        ust_satir = tk.Frame(video_cercevesi)
        ust_satir.pack(fill="x")
        tk.Label(ust_satir, text="URETILEN VIDEOLAR:", font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(ust_satir, text="Yenile", font=("Segoe UI", 8),
                  command=self.video_listesini_yenile).pack(side="right")

        self.video_listesi = tk.Listbox(video_cercevesi, activestyle="dotbox", font=("Consolas", 9))
        self.video_listesi.pack(fill="both", expand=True, pady=(2, 4))
        self.video_listesi.bind("<Double-Button-1>", lambda e: self.secili_videoyu_oynat())
        self.video_listesi.bind("<Button-3>", self._sag_tik_menusunu_goster)

        # --- Sag tik (context) menusu - koyu tema ---
        self._sag_tik_menusu = tk.Menu(
            self.pencere, tearoff=0, bg=RENK_MENU_BG, fg=RENK_MENU_FG,
            activebackground=RENK_KURGU_BG, activeforeground=RENK_BEYAZ, bd=0
        )
        self._sag_tik_menusu.add_command(label="Guvenli Oynat", command=self.secili_videoyu_oynat)
        self._sag_tik_menusu.add_command(label="Akilli Yeniden Adlandir", command=self.secili_videoyu_yeniden_adlandir)
        self._sag_tik_menusu.add_command(label="Dosya Konumunu Goster", command=self.secili_video_konumunu_goster)
        self._sag_tik_menusu.add_separator()
        self._sag_tik_menusu.add_command(label="Sil", command=self.secili_videoyu_sil)

        tk.Button(
            video_cercevesi, text="OYNAT", command=self.secili_videoyu_oynat,
            bg=RENK_OYNAT_BG, fg=RENK_BEYAZ, activebackground=RENK_OYNAT_BG, activeforeground=RENK_BEYAZ
        ).pack(fill="x", pady=1)

        kontrol_satiri = tk.Frame(video_cercevesi)
        kontrol_satiri.pack(fill="x", pady=1)
        tk.Button(kontrol_satiri, text="Yeniden Adlandir", font=("Segoe UI", 8),
                  command=self.secili_videoyu_yeniden_adlandir).pack(side="left", expand=True, fill="x", padx=1)
        tk.Button(kontrol_satiri, text="Konumu Goster", font=("Segoe UI", 8),
                  command=self.secili_video_konumunu_goster).pack(side="left", expand=True, fill="x", padx=1)

        tk.Button(
            video_cercevesi, text="SIL", font=("Segoe UI", 8),
            bg=RENK_HATALI, fg=RENK_BEYAZ, activebackground=RENK_HATALI, activeforeground=RENK_BEYAZ,
            command=self.secili_videoyu_sil
        ).pack(fill="x", pady=1)

        alt_bolme.add(video_cercevesi, stretch="always", width=300)

    # ------------------------------------------------------------
    # CRASH RECOVERY (cokme kurtarma)
    # ------------------------------------------------------------
    def _crash_recovery_kontrol_et(self):
        taslak = self.ayarlar.get("unsaved_draft", "").strip()
        if not taslak:
            return

        mevcut_script_icerigi = ""
        if os.path.exists(SCRIPT_TXT_YOLU):
            try:
                with open(SCRIPT_TXT_YOLU, "r", encoding="utf-8") as f:
                    mevcut_script_icerigi = f.read().strip()
            except Exception:
                pass

        if taslak == mevcut_script_icerigi:
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)
            return

        geri_yukle = messagebox.askyesno(
            "Kaydedilmemis Taslak Bulundu",
            "Onceki oturumdan KAYDEDILMEMIS bir script taslagi bulundu "
            "(uygulama duzgun kapatilmamis olabilir).\n\n"
            "Bu taslagi geri yuklemek ister misin?"
        )
        if geri_yukle:
            self.script_kutusu.delete("1.0", "end")
            self.script_kutusu.insert("1.0", taslak)
            self._log_kuyrugu.put("Kaydedilmemis taslak geri yuklendi. Kalici hale getirmek icin 'Scripti Kaydet'e bas.")
        else:
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)

    def _otomatik_taslak_dongusu(self):
        try:
            mevcut_icerik = self.script_kutusu.get("1.0", "end-1c")
            if mevcut_icerik.strip() != self._son_kaydedilen_script_icerigi.strip():
                self.ayarlar["unsaved_draft"] = mevcut_icerik
                ayarlari_kaydet(self.ayarlar)
        except Exception:
            pass
        finally:
            self._taslak_kaydet_id = self.pencere.after(5000, self._otomatik_taslak_dongusu)

    # ------------------------------------------------------------
    # PENCERE BOYUTU AUTO-SAVE (debounce'lu)
    # ------------------------------------------------------------
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
    # SCRIPT.TXT (yukleme, kaydetme + otomatik yedekleme)
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
            self._log_kuyrugu.put("script.txt henuz yok. 'Scripti Kaydet' ile olusturabilirsin.")

    def scripti_kaydet(self):
        try:
            icerik = self.script_kutusu.get("1.0", "end-1c")

            if os.path.exists(SCRIPT_TXT_YOLU):
                try:
                    os.makedirs(BACKUP_KLASORU, exist_ok=True)
                    zaman_damgasi = datetime.now().strftime("%Y%m%d_%H%M%S")
                    yedek_yolu = os.path.join(BACKUP_KLASORU, f"script_{zaman_damgasi}.txt")
                    shutil.copyfile(SCRIPT_TXT_YOLU, yedek_yolu)
                    self._log_kuyrugu.put(f"Onceki script yedeklendi: backups/{os.path.basename(yedek_yolu)}")
                except Exception as e:
                    self._log_kuyrugu.put(f"[HATA] Yedekleme basarisiz oldu (kayit yine de devam ediyor): {e}")

            with open(SCRIPT_TXT_YOLU, "w", encoding="utf-8") as f:
                f.write(icerik)

            self._son_kaydedilen_script_icerigi = icerik
            self.ayarlar.pop("unsaved_draft", None)
            ayarlari_kaydet(self.ayarlar)

            self._log_kuyrugu.put("script.txt kaydedildi.")
            self._banner_guncelle("script.txt kaydedildi.", None)
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] script.txt kaydedilemedi: {e}")
            self._banner_guncelle(f"script.txt kaydedilemedi: {e}", RENK_HATALI)

    # ------------------------------------------------------------
    # LOG KUYRUGU (non-blocking, queue.Queue + root.after)
    # ------------------------------------------------------------
    def _log_kuyrugunu_dinle(self):
        try:
            while True:
                mesaj = self._log_kuyrugu.get_nowait()
                self.log_kutusu.configure(state="normal")
                if "[HATA]" in mesaj.upper() or "HATA:" in mesaj.upper() or "ERROR" in mesaj.upper():
                    self.log_kutusu.insert("end", mesaj + "\n", "hata_satiri")
                else:
                    self.log_kutusu.insert("end", mesaj + "\n")
                self.log_kutusu.see("end")
                self.log_kutusu.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.pencere.after(100, self._log_kuyrugunu_dinle)

    def _banner_guncelle(self, mesaj, renk):
        def _guncelle():
            if renk:
                self.durum_etiketi.config(text=mesaj, bg=renk, fg="white")
            else:
                self.durum_etiketi.config(text=mesaj, bg=self.pencere.cget("bg"), fg="black")
        self.pencere.after(0, _guncelle)

    # ------------------------------------------------------------
    # ILERLEME CUBUGU KUYRUGU
    # ------------------------------------------------------------
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
    # PYTHON KABA KURGUYU BASLAT (thread + queue + mutex)
    # ------------------------------------------------------------
    def kaba_kurguyu_baslat(self):
        with self._islem_kilidi:
            if self._islem_calisiyor:
                messagebox.showinfo("Mesgul", "Zaten bir islem calisiyor.")
                return
            if not os.path.exists(APP_PY_YOLU):
                messagebox.showerror("Bulunamadi", f"app.py bulunamadi: {APP_PY_YOLU}")
                return
            self._islem_calisiyor = True

        self.kurgu_butonu.config(state="disabled", text="ISLENIYOR...")
        self._banner_guncelle("Python kaba kurgu motoru calisiyor...", None)
        self._ilerleme_kuyrugu.put(0)
        self._log_kuyrugu.put("")
        self._log_kuyrugu.put("python app.py baslatildi...")

        threading.Thread(target=self.run_engine, daemon=True).start()

    def run_engine(self):
        ek_parametreler = {}
        if sys.platform.startswith("win"):
            ek_parametreler["creationflags"] = subprocess.CREATE_NO_WINDOW

        yeni_video_yolu = None
        basarili = False
        toplam_sahne = None
        islenen_sahne = 0

        try:
            islem = subprocess.Popen(
                [sys.executable, APP_PY_YOLU],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **ek_parametreler,
            )
            self._calisan_islem = islem

            for satir in islem.stdout:
                satir = satir.rstrip()
                if not satir:
                    continue
                self._log_kuyrugu.put(satir)

                if toplam_sahne is None:
                    eslesme = _TOPLAM_SAHNE_REGEX.search(satir)
                    if eslesme:
                        try:
                            toplam_sahne = int(eslesme.group(1))
                        except ValueError:
                            toplam_sahne = None
                else:
                    eslesme2 = _SAHNE_ISLENIYOR_REGEX.search(satir)
                    if eslesme2:
                        try:
                            islenen_sahne = int(eslesme2.group(1))
                            yuzde = min(95, (islenen_sahne / toplam_sahne) * 90)
                            self._ilerleme_kuyrugu.put(yuzde)
                        except (ValueError, ZeroDivisionError):
                            pass

                if satir.startswith("RENDER_COMPLETE:"):
                    yeni_video_yolu = satir.split("RENDER_COMPLETE:", 1)[1].strip()

            islem.wait()
            basarili = islem.returncode == 0 and yeni_video_yolu is not None and os.path.isfile(yeni_video_yolu)

        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] {e}")
            basarili = False
        finally:
            self._calisan_islem = None

        if basarili:
            self._ilerleme_kuyrugu.put(100)
            self.render_durumu.latest_output_path = yeni_video_yolu
            self._log_kuyrugu.put("Islem basariyla tamamlandi.")
            self._banner_guncelle("RENDER SUCCESSFUL", RENK_BASARILI)
            self.pencere.after(0, lambda: self.oynat_butonu.config(state="normal"))
            self.pencere.after(0, self.video_listesini_yenile)

            payload_yolu = prepare_ae_payload(yeni_video_yolu)
            if payload_yolu:
                self._log_kuyrugu.put(f"AE render payload hazir: {os.path.basename(payload_yolu)}")
        else:
            self._ilerleme_kuyrugu.put(0)
            self._log_kuyrugu.put("[HATA] Islem basarisiz oldu veya video dosyasi bulunamadi.")
            self._banner_guncelle("RENDER FAILED", RENK_HATALI)

        gc.collect()

        with self._islem_kilidi:
            self._islem_calisiyor = False
        self.pencere.after(0, lambda: self.kurgu_butonu.config(
            state="normal", text="PYTHON KABA KURGUYU BASLAT"
        ))

    # ------------------------------------------------------------
    # SON VIDEOYU OYNAT
    # ------------------------------------------------------------
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
                self._log_kuyrugu.put(f"[HATA] Video oynatilamadi: {e}")
                messagebox.showerror("Oynatilamadi", f"Video oynatilamadi:\n{e}")
        else:
            messagebox.showwarning("Video yok", "Henuz basariyla uretilmis bir video yok.")

    # ------------------------------------------------------------
    # URETILEN VIDEOLAR LISTESI (Metadata-Driven: tarih + boyut)
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
                tam_yol = os.path.join(OUTPUT_KLASORU, f)
                try:
                    zaman_damgasi = os.path.getmtime(tam_yol)
                    boyut = os.path.getsize(tam_yol)
                except OSError:
                    continue
                kayitlar.append((tam_yol, f, zaman_damgasi, boyut))

            kayitlar.sort(key=lambda k: k[2], reverse=True)
            self._video_sonuc_kuyrugu.put(kayitlar)
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Video listesi taranamadi: {e}")
            self._video_taraniyor = False

    def _video_kuyrugunu_dinle(self):
        try:
            while True:
                kayitlar = self._video_sonuc_kuyrugu.get_nowait()
                self._video_listesini_guncelle(kayitlar)
        except queue.Empty:
            pass
        finally:
            self.pencere.after(100, self._video_kuyrugunu_dinle)

    def _video_listesini_guncelle(self, kayitlar):
        try:
            self._video_yollari = [k[0] for k in kayitlar]
            self.video_listesi.delete(0, "end")
            for tam_yol, dosya_adi, zaman_damgasi, boyut in kayitlar:
                tarih_metni = datetime.fromtimestamp(zaman_damgasi).strftime("%d.%m.%Y - %H:%M")
                boyut_metni = format_dosya_boyutu(boyut)
                self.video_listesi.insert("end", f"[{tarih_metni}] | [{boyut_metni}] | {dosya_adi}")
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Video listesi guncellenemedi: {e}")
        finally:
            self._video_taraniyor = False

    def _secili_video_yolunu_al(self):
        secim = self.video_listesi.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once listeden bir video sec.")
            return None
        indeks = secim[0]
        if indeks >= len(self._video_yollari):
            messagebox.showwarning("Gecersiz secim", "Liste guncel degil, yenileniyor.")
            self.video_listesini_yenile()
            return None
        return self._video_yollari[indeks]

    def _sag_tik_menusunu_goster(self, event):
        try:
            tiklanan_indeks = self.video_listesi.nearest(event.y)
            if tiklanan_indeks >= 0:
                self.video_listesi.selection_clear(0, "end")
                self.video_listesi.selection_set(tiklanan_indeks)
                self.video_listesi.activate(tiklanan_indeks)
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
                self._log_kuyrugu.put(f"Video oynatiliyor: {yol}")
            except Exception as e:
                self._log_kuyrugu.put(f"[HATA] Video oynatilamadi: {e}")
                messagebox.showerror("Oynatilamadi", f"Video oynatilamadi:\n{e}")
        else:
            self._log_kuyrugu.put(f"[HATA] Dosya bulunamadi (silinmis/tasinmis olabilir): {yol}")
            messagebox.showwarning("Bulunamadi", "Bu video dosyasi artik mevcut degil (silinmis veya tasinmis olabilir).")
            self.video_listesini_yenile()

    def secili_videoyu_yeniden_adlandir(self):
        yol = self._secili_video_yolunu_al()
        if not yol:
            return
        if not os.path.exists(yol):
            messagebox.showwarning("Bulunamadi", "Dosya artik mevcut degil.")
            self.video_listesini_yenile()
            return

        eski_ad = os.path.basename(yol)
        eski_govde = os.path.splitext(eski_ad)[0]

        yeni_govde = simpledialog.askstring(
            "Yeniden Adlandir", "Yeni dosya adi (uzanti otomatik korunur):",
            initialvalue=eski_govde, parent=self.pencere
        )
        if not yeni_govde or not yeni_govde.strip():
            return

        yeni_govde = os.path.splitext(yeni_govde.strip())[0]
        yeni_ad = yeni_govde + ".mp4"
        yeni_yol = os.path.join(OUTPUT_KLASORU, yeni_ad)

        if os.path.abspath(yeni_yol) == os.path.abspath(yol):
            return

        if os.path.exists(yeni_yol):
            messagebox.showerror(
                "Ayni isimde dosya var",
                f"'{yeni_ad}' zaten mevcut. Uzerine yazilmasini engellemek icin farkli bir isim sec."
            )
            return

        try:
            os.rename(yol, yeni_yol)
            self._log_kuyrugu.put(f"Yeniden adlandirildi: {eski_ad} -> {yeni_ad}")

            if self.render_durumu.latest_output_path == yol:
                self.render_durumu.latest_output_path = yeni_yol

            self.video_listesini_yenile()
        except PermissionError:
            self._log_kuyrugu.put(f"[HATA] Dosya kullanimda, yeniden adlandirilamadi: {eski_ad}")
            messagebox.showerror(
                "Dosya kullanimda",
                "Bu dosya su anda baska bir program tarafindan kullaniliyor "
                "(orn. bir medya oynaticida acik). Once o programi kapatip tekrar dene."
            )
        except OSError as e:
            self._log_kuyrugu.put(f"[HATA] Yeniden adlandirilamadi: {e}")
            messagebox.showerror("Yeniden adlandirilamadi", f"Bir hata olustu:\n{e}")

    def secili_videoyu_sil(self):
        yol = self._secili_video_yolunu_al()
        if not yol:
            return
        if not os.path.exists(yol):
            messagebox.showwarning("Bulunamadi", "Dosya zaten mevcut degil.")
            self.video_listesini_yenile()
            return

        onay = messagebox.askyesno(
            "Silmeyi Onayla",
            f"'{os.path.basename(yol)}' KALICI OLARAK silinecek.\nBu islem geri alinamaz. Emin misin?"
        )
        if not onay:
            return

        try:
            os.remove(yol)
            self._log_kuyrugu.put(f"Silindi: {os.path.basename(yol)}")

            if self.render_durumu.latest_output_path == yol:
                self.render_durumu.latest_output_path = None
                self.pencere.after(0, lambda: self.oynat_butonu.config(state="disabled"))

            self.video_listesini_yenile()
        except PermissionError:
            self._log_kuyrugu.put(f"[HATA] Dosya kullanimda, silinemedi: {os.path.basename(yol)}")
            messagebox.showerror(
                "Dosya kullanimda",
                "Bu dosya su anda baska bir program tarafindan kullaniliyor "
                "(orn. bir medya oynaticida acik) ve silinemedi. Once o programi kapat."
            )
        except OSError as e:
            self._log_kuyrugu.put(f"[HATA] Silinemedi: {e}")
            messagebox.showerror("Silinemedi", f"Dosya silinirken bir hata olustu:\n{e}")

    def secili_video_konumunu_goster(self):
        yol = self._secili_video_yolunu_al()
        if not yol:
            return
        if not os.path.exists(yol):
            messagebox.showwarning("Bulunamadi", "Dosya artik mevcut degil.")
            self.video_listesini_yenile()
            return
        try:
            dosya_konumunu_goster(yol)
            self._log_kuyrugu.put(f"Dosya konumu gosteriliyor: {yol}")
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] Dosya konumu gosterilemedi: {e}")
            messagebox.showerror("Gosterilemedi", f"Dosya konumu gosterilemedi:\n{e}")

    # ------------------------------------------------------------
    # AFTER EFFECTS ASISTANINI ATESLE
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

        self._log_kuyrugu.put("")
        self._log_kuyrugu.put(f"After Effects baslatiliyor: {ae_yolu}")
        self._banner_guncelle("After Effects baslatiliyor...", None)

        try:
            subprocess.Popen([ae_yolu, "-r", jsx_yolu])
            self._banner_guncelle("After Effects baslatildi.", RENK_BASARILI)
            self._log_kuyrugu.put("After Effects komutu gonderildi.")
        except Exception as e:
            self._log_kuyrugu.put(f"[HATA] After Effects baslatilamadi: {e}")
            self._banner_guncelle(f"After Effects baslatilamadi: {e}", RENK_HATALI)
            messagebox.showerror("Baslatilamadi", f"After Effects baslatilamadi:\n{e}")

    def _ae_yolunu_sor(self):
        messagebox.showinfo(
            "AfterFX.exe konumu",
            r"After Effects'in kurulu oldugu 'AfterFX.exe' dosyasini sec. "
            r"Genelde: C:\Program Files\Adobe\Adobe After Effects <surum>\Support Files\AfterFX.exe"
        )
        yol = filedialog.askopenfilename(title="AfterFX.exe sec", filetypes=[("Uygulama", "*.exe"), ("Tumu", "*.*")])
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

        messagebox.showinfo("canavar_asistan.jsx konumu", "'canavar_asistan.jsx' dosyasini sec.")
        yol = filedialog.askopenfilename(title="canavar_asistan.jsx sec", filetypes=[("JSX", "*.jsx")])
        if yol:
            self.ayarlar["jsx_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
        return yol or None

    def ayarlari_duzenle(self):
        pencere = tk.Toplevel(self.pencere)
        pencere.title("Ayarlar")
        pencere.geometry("480x220")

        tk.Label(pencere, text="AfterFX.exe yolu:", font=("Segoe UI", 10)).pack(pady=(15, 5), padx=15, anchor="w")
        ae_etiketi = tk.Label(
            pencere, text=self.ayarlar.get("ae_yolu", "(secilmedi)"),
            font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w"
        )
        ae_etiketi.pack(fill="x", padx=15)

        def ae_sec():
            yol = self._ae_yolunu_sor()
            if yol:
                ae_etiketi.config(text=yol)

        tk.Button(pencere, text="AfterFX.exe Sec", command=ae_sec).pack(pady=(5, 15), padx=15, anchor="w")

        tk.Label(pencere, text="canavar_asistan.jsx yolu:", font=("Segoe UI", 10)).pack(pady=(0, 5), padx=15, anchor="w")
        jsx_etiketi = tk.Label(
            pencere, text=self.ayarlar.get("jsx_yolu", "(secilmedi)"),
            font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w"
        )
        jsx_etiketi.pack(fill="x", padx=15)

        def jsx_sec():
            yol = filedialog.askopenfilename(title="canavar_asistan.jsx sec", filetypes=[("JSX", "*.jsx")])
            if yol:
                self.ayarlar["jsx_yolu"] = yol
                ayarlari_kaydet(self.ayarlar)
                jsx_etiketi.config(text=yol)

        tk.Button(pencere, text="canavar_asistan.jsx Sec", command=jsx_sec).pack(pady=(5, 15), padx=15, anchor="w")

    # ------------------------------------------------------------
    # TEMIZ KAPATMA (WM_DELETE_WINDOW)
    # ------------------------------------------------------------
    def _kapatilirken(self):
        try:
            if self._calisan_islem is not None and self._calisan_islem.poll() is None:
                devam = messagebox.askyesno(
                    "Islem devam ediyor",
                    "Kaba kurgu motoru hala calisiyor. Yine de kapatilsin mi? "
                    "(Calisan islem sonlandirilacak)"
                )
                if not devam:
                    return
                try:
                    self._calisan_islem.terminate()
                except Exception:
                    pass

            if self._taslak_kaydet_id:
                self.pencere.after_cancel(self._taslak_kaydet_id)
            if self._pencere_boyutu_kaydet_id:
                self.pencere.after_cancel(self._pencere_boyutu_kaydet_id)

            self._pencere_boyutunu_kaydet()
            gc.collect()
        finally:
            self.pencere.destroy()


if __name__ == "__main__":
    pencere = tk.Tk()
    uygulama = KontrolPaneli(pencere)
    pencere.mainloop()