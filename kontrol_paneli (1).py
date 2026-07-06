"""
kontrol_paneli.py
------------------
Canavar Asistan - Ana Kontrol Paneli (SADE / KARARLI SURUM)

Bu dosyayi, LayerEngine projenin (app.py, script.txt'nin bulundugu) AYNI
klasorune koy ve calistir:
    python kontrol_paneli.py

Bu surumde:
- Tasarim tamamen sade, standart Tkinter (renk suslemesi yok).
- script.txt panelin icinden okunup duzenlenip kaydedilebiliyor (Not Defteri
  ACILMIYOR).
- Tum emoji/ozel karakterler loglardan temizlendi (Windows konsolunda
  UnicodeEncodeError vermesin diye).
- Pencere buyutulebilir, ic bilesenler pencereyle birlikte esniyor.
"""

import os
import sys
import json
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# Windows'ta bu script konsolsuz (pyw) calistirilsa bile, olasi print()
# cagrilarinda UnicodeEncodeError almamak icin stdout/stderr'i UTF-8'e zorla.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================================
# YOLLAR VE AYARLAR
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_TXT_YOLU = os.path.join(BASE_DIR, "script.txt")
APP_PY_YOLU = os.path.join(BASE_DIR, "app.py")
OUTPUT_KLASORU = os.path.join(BASE_DIR, "output_shorts")
AYARLAR_DOSYASI = os.path.join(BASE_DIR, "kontrol_paneli_ayarlar.json")

RENK_YESIL = "#2ecc71"
RENK_KIRMIZI = "#e74c3c"


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


class KontrolPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan - Kontrol Paneli")
        self.pencere.geometry("700x700")
        self.pencere.minsize(500, 500)
        self.pencere.resizable(True, True)

        self.ayarlar = ayarlari_yukle()
        self._islem_calisiyor = False

        self._arayuzu_kur()
        self._scripti_yukle()

    # ------------------------------------------------------------
    # ARAYUZ (tamamen standart Tkinter, ozel renk yok)
    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        ana_cerceve = tk.Frame(self.pencere)
        ana_cerceve.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(
            ana_cerceve, text="Canavar Asistan - Kontrol Paneli",
            font=("Segoe UI", 14, "bold")
        ).pack(anchor="w")

        # --- Script.txt duzenleyici ---
        tk.Label(ana_cerceve, text="script.txt icerigi:", font=("Segoe UI", 10)).pack(
            anchor="w", pady=(12, 2)
        )

        self.script_kutusu = tk.Text(ana_cerceve, height=12, wrap="word", undo=True)
        self.script_kutusu.pack(fill="both", expand=True)

        tk.Button(
            ana_cerceve, text="Scripti Kaydet", command=self.scripti_kaydet
        ).pack(anchor="e", pady=(6, 12))

        # --- Ana islem butonlari ---
        buton_cercevesi = tk.Frame(ana_cerceve)
        buton_cercevesi.pack(fill="x", pady=(0, 6))

        self.kurgu_butonu = tk.Button(
            buton_cercevesi, text="PYTHON KABA KURGUYU BASLAT",
            command=self.kaba_kurguyu_baslat, font=("Segoe UI", 10, "bold"),
            height=2
        )
        self.kurgu_butonu.pack(fill="x", pady=3)

        self.ae_butonu = tk.Button(
            buton_cercevesi, text="AFTER EFFECTS ASISTANINI ATESLE",
            command=self.after_effects_baslat, font=("Segoe UI", 10, "bold"),
            height=2
        )
        self.ae_butonu.pack(fill="x", pady=3)

        tk.Button(
            buton_cercevesi, text="AE Yolu / Script Ayarlari",
            command=self.ayarlari_duzenle, font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(4, 0))

        # --- Durum banner'i (yesil/kirmizi - suslemesiz, sadece durum icin) ---
        self.durum_etiketi = tk.Label(
            ana_cerceve, text="Hazir.", font=("Segoe UI", 10, "bold"),
            relief="groove", pady=8
        )
        self.durum_etiketi.pack(fill="x", pady=(6, 6))

        # --- Log alani ---
        tk.Label(ana_cerceve, text="Islem Gunlugu:", font=("Segoe UI", 9)).pack(anchor="w")

        self.log_kutusu = scrolledtext.ScrolledText(ana_cerceve, height=10, wrap="word")
        self.log_kutusu.pack(fill="both", expand=True, pady=(2, 0))
        self.log_kutusu.configure(state="disabled")

    # ------------------------------------------------------------
    # SCRIPT.TXT: PANEL ICINDEN OKU / KAYDET
    # ------------------------------------------------------------
    def _scripti_yukle(self):
        if os.path.exists(SCRIPT_TXT_YOLU):
            try:
                with open(SCRIPT_TXT_YOLU, "r", encoding="utf-8") as f:
                    icerik = f.read()
                self.script_kutusu.delete("1.0", "end")
                self.script_kutusu.insert("1.0", icerik)
                self.log_yaz("script.txt yuklendi.")
            except Exception as hata:
                self.log_yaz("script.txt okunamadi: " + str(hata))
        else:
            self.log_yaz("script.txt henuz yok. 'Scripti Kaydet' ile yeni bir tane olusturabilirsin.")

    def scripti_kaydet(self):
        try:
            icerik = self.script_kutusu.get("1.0", "end-1c")
            with open(SCRIPT_TXT_YOLU, "w", encoding="utf-8") as f:
                f.write(icerik)
            self.log_yaz("script.txt kaydedildi.")
            self.durumu_guncelle("script.txt kaydedildi.", RENK_YESIL, "white")
        except Exception as hata:
            self.log_yaz("script.txt kaydedilemedi: " + str(hata))
            self.durumu_guncelle("script.txt kaydedilemedi: " + str(hata), RENK_KIRMIZI, "white")

    # ------------------------------------------------------------
    # LOG / DURUM YARDIMCILARI
    # ------------------------------------------------------------
    def log_yaz(self, mesaj):
        def _yaz():
            self.log_kutusu.configure(state="normal")
            self.log_kutusu.insert("end", mesaj + "\n")
            self.log_kutusu.see("end")
            self.log_kutusu.configure(state="disabled")
        self.pencere.after(0, _yaz)

    def durumu_guncelle(self, mesaj, renk=None, yazi_rengi=None):
        def _guncelle():
            if renk:
                self.durum_etiketi.config(text=mesaj, bg=renk, fg=yazi_rengi or "black")
            else:
                self.durum_etiketi.config(text=mesaj, bg=self.pencere.cget("bg"), fg="black")
        self.pencere.after(0, _guncelle)

    # ------------------------------------------------------------
    # PYTHON KABA KURGUYU BASLAT
    # ------------------------------------------------------------
    def kaba_kurguyu_baslat(self):
        if self._islem_calisiyor:
            messagebox.showinfo("Mesgul", "Zaten bir islem calisiyor, bitmesini bekle.")
            return
        if not os.path.exists(APP_PY_YOLU):
            messagebox.showerror("Bulunamadi", "app.py bulunamadi: " + APP_PY_YOLU)
            return

        self._islem_calisiyor = True
        self.kurgu_butonu.config(state="disabled", text="ISLENIYOR...")
        self.durumu_guncelle("Python kaba kurgu motoru calisiyor, lutfen bekle...")
        self.log_yaz("")
        self.log_yaz("python app.py baslatildi...")

        threading.Thread(target=self._kaba_kurgu_arka_plan, daemon=True).start()

    def _kaba_kurgu_arka_plan(self):
        ek_parametreler = {}
        if sys.platform.startswith("win"):
            ek_parametreler["creationflags"] = subprocess.CREATE_NO_WINDOW

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

            tam_cikti = []
            for satir in islem.stdout:
                satir = satir.rstrip()
                if satir:
                    self.log_yaz(satir)
                    tam_cikti.append(satir)

            islem.wait()
            cikti_metni = "\n".join(tam_cikti)
            basarili = islem.returncode == 0 and "BITTI" in cikti_metni.upper()

            if basarili:
                self.durumu_guncelle(
                    "Kaba Kurgu Videosu 'output_shorts' klasorunde hazir.",
                    RENK_YESIL, "white"
                )
                self.log_yaz("Islem basariyla tamamlandi.")
            elif islem.returncode == 0:
                self.durumu_guncelle(
                    "Islem bitti ama video uretilememis olabilir. Gunlugu kontrol et.",
                    RENK_KIRMIZI, "white"
                )
            else:
                self.durumu_guncelle("Hata olustu (cikis kodu " + str(islem.returncode) + ").", RENK_KIRMIZI, "white")
                self.log_yaz("Cikis kodu: " + str(islem.returncode))

        except Exception as hata:
            self.durumu_guncelle("Beklenmeyen hata: " + str(hata), RENK_KIRMIZI, "white")
            self.log_yaz("HATA: " + str(hata))
        finally:
            self._islem_calisiyor = False
            self.pencere.after(0, lambda: self.kurgu_butonu.config(
                state="normal", text="PYTHON KABA KURGUYU BASLAT"
            ))

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

        self.log_yaz("")
        self.log_yaz("After Effects baslatiliyor: " + ae_yolu)
        self.log_yaz("Script: " + jsx_yolu)
        self.durumu_guncelle("After Effects baslatiliyor...")

        try:
            subprocess.Popen([ae_yolu, "-r", jsx_yolu])
            self.durumu_guncelle("After Effects baslatildi.", RENK_YESIL, "white")
            self.log_yaz("After Effects komutu gonderildi.")
        except Exception as hata:
            self.durumu_guncelle("After Effects baslatilamadi: " + str(hata), RENK_KIRMIZI, "white")
            messagebox.showerror(
                "Baslatilamadi",
                "After Effects baslatilamadi:\n" + str(hata) +
                "\n\nAE yolunu 'AE Yolu / Script Ayarlari' uzerinden tekrar secmeyi dene."
            )

    def _ae_yolunu_sor(self):
        messagebox.showinfo(
            "AfterFX.exe konumu",
            "After Effects'in kurulu oldugu 'AfterFX.exe' dosyasini secmen gerekiyor.\n"
            r"Genelde suradadir: C:\Program Files\Adobe\Adobe After Effects <surum>\Support Files\AfterFX.exe"
        )
        yol = filedialog.askopenfilename(
            title="AfterFX.exe dosyasini sec",
            filetypes=[("Uygulama", "*.exe"), ("Tum dosyalar", "*.*")]
        )
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

        messagebox.showinfo(
            "canavar_asistan.jsx konumu",
            "'canavar_asistan.jsx' dosyasini secmen gerekiyor."
        )
        yol = filedialog.askopenfilename(
            title="canavar_asistan.jsx dosyasini sec",
            filetypes=[("JSX Script", "*.jsx"), ("Tum dosyalar", "*.*")]
        )
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

        tk.Label(pencere, text="AfterFX.exe yolu:", font=("Segoe UI", 10)).pack(
            pady=(15, 5), padx=15, anchor="w"
        )
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

        tk.Label(pencere, text="canavar_asistan.jsx yolu:", font=("Segoe UI", 10)).pack(
            pady=(0, 5), padx=15, anchor="w"
        )
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
