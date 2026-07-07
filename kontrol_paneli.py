"""
kontrol_paneli.py
------------------
Canavar Asistan - Ana Kontrol Paneli (Enterprise Refactor)

Mimari ozeti:
- LatestRenderState: son uretilen video yolunu tutan Singleton sinif
- Subprocess ciktisi bir queue.Queue'ya akar, Tkinter ana thread'i
  root.after(100, ...) ile bu kuyrugu non-blocking okur (mainloop hic bloke
  olmaz)
- "SON VIDEOYU OYNAT" ve "KLASORLERI AC" butonlari OS seviyesinde
  subprocess/os.startfile ile calisir
- Basari/hata banner'i sabit renklerle: #4CAF50 / #F44336
"""

import os
import sys
import json
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

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
AYARLAR_DOSYASI = os.path.join(BASE_DIR, "kontrol_paneli_ayarlar.json")

RENK_BASARILI = "#4CAF50"
RENK_HATALI = "#F44336"

# --- Buton/alan renk matrisi ---
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


def ayarlari_yukle():
    if os.path.exists(AYARLAR_DOSYASI):
        try:
            with open(AYARLAR_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def ayarlari_kaydet(ayarlar):
    try:
        with open(AYARLAR_DOSYASI, "w", encoding="utf-8") as f:
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


def dosyayi_oynat(yol):
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", yol], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol])
    except Exception as e:
        messagebox.showerror("Oynatilamadi", f"Video oynatilamadi:\n{e}")


def gecmis_videoyu_ac_os_startfile(yol):
    """
    'URETILEN VIDEOLAR' listesinden secilen ESKI bir videoyu, isletim
    sisteminin varsayilan medya oynaticisinda ACIKCA os.startfile() ile
    (Windows'ta) asenkron olarak acar.
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(yol)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol])
    except Exception as e:
        messagebox.showerror("Oynatilamadi", f"Secili video oynatilamadi:\n{e}")


# ============================================================================
# ANA PANEL
# ============================================================================
class KontrolPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan - Kontrol Paneli")
        self.pencere.geometry("720x760")
        self.pencere.minsize(520, 520)
        self.pencere.resizable(True, True)

        self.ayarlar = ayarlari_yukle()
        self.render_durumu = LatestRenderState()
        self._islem_calisiyor = False
        self._log_kuyrugu = queue.Queue()

        self._arayuzu_kur()
        self._scripti_yukle()
        self.video_listesini_yenile()
        self._log_kuyrugunu_dinle()

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

        tk.Button(klasor_buton_satiri, text="Arka Planlar", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  activebackground=RENK_KLASOR_BG, activeforeground=RENK_BEYAZ,
                  command=lambda: klasoru_ac(ARKAPLAN_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(klasor_buton_satiri, text="Karakterler", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  activebackground=RENK_KLASOR_BG, activeforeground=RENK_BEYAZ,
                  command=lambda: klasoru_ac(KARAKTER_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(klasor_buton_satiri, text="Ses", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  activebackground=RENK_KLASOR_BG, activeforeground=RENK_BEYAZ,
                  command=lambda: klasoru_ac(SES_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(klasor_buton_satiri, text="Ciktilar", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  activebackground=RENK_KLASOR_BG, activeforeground=RENK_BEYAZ,
                  command=lambda: klasoru_ac(OUTPUT_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)

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

        self.video_listesi = tk.Listbox(video_cercevesi, activestyle="dotbox")
        self.video_listesi.pack(fill="both", expand=True, pady=(2, 4))
        self.video_listesi.bind("<Double-Button-1>", lambda e: self.secili_videoyu_oynat())

        tk.Button(
            video_cercevesi, text="SECILI VIDEOYU OYNAT", command=self.secili_videoyu_oynat,
            bg=RENK_OYNAT_BG, fg=RENK_BEYAZ, activebackground=RENK_OYNAT_BG, activeforeground=RENK_BEYAZ
        ).pack(fill="x")
        alt_bolme.add(video_cercevesi, stretch="always", width=260)

        self._video_yollari = []  # listedeki her satirin tam dosya yolu (index eslesir)

    # ------------------------------------------------------------
    # URETILEN VIDEOLAR LISTESI
    # ------------------------------------------------------------
    def video_listesini_yenile(self):
        try:
            os.makedirs(OUTPUT_KLASORU, exist_ok=True)
            dosyalar = [
                os.path.join(OUTPUT_KLASORU, f) for f in os.listdir(OUTPUT_KLASORU)
                if f.lower().endswith(".mp4")
            ]
            # guncelden eskiye dogru sirala (degistirme zamanina gore)
            dosyalar.sort(key=lambda p: os.path.getmtime(p), reverse=True)

            self._video_yollari = dosyalar
            self.video_listesi.delete(0, "end")
            for yol in dosyalar:
                self.video_listesi.insert("end", os.path.basename(yol))
        except Exception as e:
            self._log_kuyrugu.put(f"Video listesi yenilenemedi: {e}")

    def secili_videoyu_oynat(self):
        secim = self.video_listesi.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once listeden bir video sec.")
            return
        yol = self._video_yollari[secim[0]]
        if os.path.exists(yol):
            gecmis_videoyu_ac_os_startfile(yol)
            self._log_kuyrugu.put(f"Secili video oynatiliyor: {yol}")
        else:
            messagebox.showwarning("Bulunamadi", "Bu video dosyasi artik mevcut degil.")
            self.video_listesini_yenile()

    # ------------------------------------------------------------
    # SCRIPT.TXT
    # ------------------------------------------------------------
    def _scripti_yukle(self):
        if os.path.exists(SCRIPT_TXT_YOLU):
            try:
                with open(SCRIPT_TXT_YOLU, "r", encoding="utf-8") as f:
                    icerik = f.read()
                self.script_kutusu.delete("1.0", "end")
                self.script_kutusu.insert("1.0", icerik)
                self._log_kuyrugu.put("script.txt yuklendi.")
            except Exception as e:
                self._log_kuyrugu.put(f"script.txt okunamadi: {e}")
        else:
            self._log_kuyrugu.put("script.txt henuz yok. 'Scripti Kaydet' ile olusturabilirsin.")

    def scripti_kaydet(self):
        try:
            icerik = self.script_kutusu.get("1.0", "end-1c")
            with open(SCRIPT_TXT_YOLU, "w", encoding="utf-8") as f:
                f.write(icerik)
            self._log_kuyrugu.put("script.txt kaydedildi.")
            self._banner_guncelle("script.txt kaydedildi.", None)
        except Exception as e:
            self._log_kuyrugu.put(f"script.txt kaydedilemedi: {e}")
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
    # PYTHON KABA KURGUYU BASLAT (thread + queue mimarisi)
    # ------------------------------------------------------------
    def kaba_kurguyu_baslat(self):
        if self._islem_calisiyor:
            messagebox.showinfo("Mesgul", "Zaten bir islem calisiyor.")
            return
        if not os.path.exists(APP_PY_YOLU):
            messagebox.showerror("Bulunamadi", f"app.py bulunamadi: {APP_PY_YOLU}")
            return

        self._islem_calisiyor = True
        self.kurgu_butonu.config(state="disabled", text="ISLENIYOR...")
        self._banner_guncelle("Python kaba kurgu motoru calisiyor...", None)
        self._log_kuyrugu.put("")
        self._log_kuyrugu.put("python app.py baslatildi...")

        threading.Thread(target=self.run_engine, daemon=True).start()

    def run_engine(self):
        ek_parametreler = {}
        if sys.platform.startswith("win"):
            ek_parametreler["creationflags"] = subprocess.CREATE_NO_WINDOW

        yeni_video_yolu = None
        basarili = False

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

            for satir in islem.stdout:
                satir = satir.rstrip()
                if not satir:
                    continue
                self._log_kuyrugu.put(satir)

                if satir.startswith("RENDER_COMPLETE:"):
                    yeni_video_yolu = satir.split("RENDER_COMPLETE:", 1)[1].strip()

            islem.wait()
            basarili = islem.returncode == 0 and yeni_video_yolu is not None and os.path.isfile(yeni_video_yolu)

        except Exception as e:
            self._log_kuyrugu.put(f"HATA: {e}")
            basarili = False

        if basarili:
            self.render_durumu.latest_output_path = yeni_video_yolu
            self._log_kuyrugu.put("Islem basariyla tamamlandi.")
            self._banner_guncelle("RENDER SUCCESSFUL", RENK_BASARILI)
            self.pencere.after(0, lambda: self.oynat_butonu.config(state="normal"))
            self.pencere.after(0, self.video_listesini_yenile)
        else:
            self._log_kuyrugu.put("Islem basarisiz oldu veya video dosyasi bulunamadi.")
            self._banner_guncelle("RENDER FAILED", RENK_HATALI)

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
            dosyayi_oynat(yol)
            self._log_kuyrugu.put(f"Video oynatiliyor: {yol}")
        else:
            messagebox.showwarning("Video yok", "Henuz basariyla uretilmis bir video yok.")

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
            self._banner_guncelle(f"After Effects baslatilamadi: {e}", RENK_HATALI)
            messagebox.showerror("Baslatilamadi", f"After Effects baslatilamadi:\n{e}")

    def _ae_yolunu_sor(self):
        messagebox.showinfo(
            "AfterFX.exe konumu",
            r"After Effects'in kurulu oldugu 'AfterFX.exe' dosyasini sec."
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

    # ------------------------------------------------------------
    # AYARLAR PENCERESI
    # ------------------------------------------------------------
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


if __name__ == "__main__":
    pencere = tk.Tk()
    uygulama = KontrolPaneli(pencere)
    pencere.mainloop()
