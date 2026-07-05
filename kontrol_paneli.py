"""
kontrol_paneli.py
------------------
Canavar Asistan - Masaustu Ana Kontrol Paneli

Bu dosyayi, LayerEngine projenin (app.py, script.txt'nin bulundugu) AYNI
klasorune koy ve calistir:
    python kontrol_paneli.py

Ne yapar:
- script.txt'yi Not Defteri ile acar
- 'python app.py' isini arka planda (terminal penceresi acmadan) calistirir
- After Effects'i, canavar_asistan.jsx'i otomatik yukleyerek baslatir
"""

import os
import sys
import json
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# ============================================================================
# YOLLAR VE AYARLAR
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_TXT_YOLU = os.path.join(BASE_DIR, "script.txt")
APP_PY_YOLU = os.path.join(BASE_DIR, "app.py")
OUTPUT_KLASORU = os.path.join(BASE_DIR, "output_shorts")
AYARLAR_DOSYASI = os.path.join(BASE_DIR, "kontrol_paneli_ayarlar.json")

RENK_ZEMIN = "#1a1a2e"
RENK_KUTU = "#25253d"
RENK_VURGU = "#7b2ff7"
RENK_YESIL = "#2ecc71"
RENK_KIRMIZI = "#e74c3c"
RENK_SOLUK = "#9a9ab0"


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
        self.pencere.title("🎬 Canavar Asistan - Ana Kontrol Paneli")
        self.pencere.geometry("560x620")
        self.pencere.configure(bg=RENK_ZEMIN)
        self.pencere.resizable(False, False)

        self.ayarlar = ayarlari_yukle()
        self._islem_calisiyor = False

        self._arayuzu_kur()

    # ------------------------------------------------------------
    # ARAYUZ
    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        tk.Label(
            self.pencere, text="🎬 CANAVAR ASİSTAN", font=("Segoe UI", 20, "bold"),
            bg=RENK_ZEMIN, fg="white"
        ).pack(pady=(25, 0))

        tk.Label(
            self.pencere, text="Manga Shorts Otomasyon - Ana Kontrol Paneli",
            font=("Segoe UI", 10), bg=RENK_ZEMIN, fg=RENK_SOLUK
        ).pack(pady=(0, 25))

        # --- Buton 1: script.txt duzenle ---
        self._buyuk_buton(
            "📝  Script.txt Düzenle", self.script_duzenle,
            RENK_KUTU, "Not Defteri ile script.txt dosyasını açar"
        )

        # --- Buton 2: Python kaba kurgu ---
        self.kurgu_butonu = self._buyuk_buton(
            "🎞️  PYTHON KABA KURGUYU BAŞLAT", self.kaba_kurguyu_baslat,
            RENK_VURGU, "Panelleri/karakterleri işleyip taslak videoyu üretir"
        )

        # --- Buton 3: After Effects ---
        self.ae_butonu = self._buyuk_buton(
            "🔥  AFTER EFFECTS ASİSTANINI ATEŞLE", self.after_effects_baslat,
            "#c0392b", "AE'yi açıp canavar_asistan.jsx'i otomatik yükler"
        )

        # --- Ayarlar (AE yolu / jsx yolu) kucuk link ---
        ayar_cerceve = tk.Frame(self.pencere, bg=RENK_ZEMIN)
        ayar_cerceve.pack(pady=(5, 15))
        tk.Button(
            ayar_cerceve, text="⚙ AE Yolu / Script Ayarları", command=self.ayarlari_duzenle,
            bg=RENK_ZEMIN, fg=RENK_SOLUK, relief="flat", font=("Segoe UI", 8, "underline"),
            activebackground=RENK_ZEMIN, activeforeground="white", bd=0
        ).pack()

        # --- Durum banner'i ---
        self.durum_etiketi = tk.Label(
            self.pencere, text="Hazır.", font=("Segoe UI", 11, "bold"),
            bg=RENK_KUTU, fg=RENK_SOLUK, wraplength=500, justify="center", pady=12
        )
        self.durum_etiketi.pack(fill="x", padx=20, pady=(10, 10))

        # --- Log alani ---
        tk.Label(self.pencere, text="İşlem Günlüğü:", font=("Segoe UI", 9),
                 bg=RENK_ZEMIN, fg=RENK_SOLUK).pack(anchor="w", padx=20)

        self.log_kutusu = scrolledtext.ScrolledText(
            self.pencere, height=10, bg="#0f0f1a", fg="#7ee787",
            font=("Consolas", 9), relief="flat", wrap="word"
        )
        self.log_kutusu.pack(fill="both", expand=True, padx=20, pady=(5, 20))
        self.log_kutusu.configure(state="disabled")

    def _buyuk_buton(self, metin, komut, renk, aciklama):
        cerceve = tk.Frame(self.pencere, bg=RENK_ZEMIN)
        cerceve.pack(fill="x", padx=20, pady=6)

        buton = tk.Button(
            cerceve, text=metin, command=komut, font=("Segoe UI", 12, "bold"),
            bg=renk, fg="white", relief="flat", pady=14, cursor="hand2"
        )
        buton.pack(fill="x")

        tk.Label(cerceve, text=aciklama, font=("Segoe UI", 8), bg=RENK_ZEMIN, fg=RENK_SOLUK).pack(pady=(2, 0))
        return buton

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

    def durumu_guncelle(self, mesaj, renk=RENK_KUTU, yazi_rengi=RENK_SOLUK):
        def _guncelle():
            self.durum_etiketi.config(text=mesaj, bg=renk, fg=yazi_rengi)
        self.pencere.after(0, _guncelle)

    # ------------------------------------------------------------
    # BUTON 1: SCRIPT.TXT DUZENLE
    # ------------------------------------------------------------
    def script_duzenle(self):
        if not os.path.exists(SCRIPT_TXT_YOLU):
            messagebox.showwarning(
                "script.txt bulunamadı",
                f"'{SCRIPT_TXT_YOLU}' bulunamadı.\n"
                "Önce 'PYTHON KABA KURGUYU BAŞLAT' butonuna bir kere basarak "
                "otomatik şablonun oluşmasını sağlayabilirsin."
            )
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["notepad.exe", SCRIPT_TXT_YOLU])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-e", SCRIPT_TXT_YOLU])
            else:
                subprocess.Popen(["xdg-open", SCRIPT_TXT_YOLU])
            self.log_yaz("📝 script.txt Not Defteri ile açıldı.")
        except Exception as hata:
            messagebox.showerror("Açılamadı", f"script.txt açılamadı:\n{hata}")

    # ------------------------------------------------------------
    # BUTON 2: PYTHON KABA KURGUYU BASLAT
    # ------------------------------------------------------------
    def kaba_kurguyu_baslat(self):
        if self._islem_calisiyor:
            messagebox.showinfo("Meşgul", "Zaten bir işlem çalışıyor, bitmesini bekle.")
            return
        if not os.path.exists(APP_PY_YOLU):
            messagebox.showerror("app.py bulunamadı", f"'{APP_PY_YOLU}' bulunamadı.")
            return

        self._islem_calisiyor = True
        self.kurgu_butonu.config(state="disabled", text="⏳ İşleniyor...")
        self.durumu_guncelle("Python kaba kurgu motoru çalışıyor, lütfen bekle...", RENK_KUTU, "white")
        self.log_yaz("\n▶ python app.py başlatıldı...")

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
            basarili = islem.returncode == 0 and ("BİTTİ" in cikti_metni or "✅" in cikti_metni)

            if basarili:
                self.durumu_guncelle(
                    "✅ Kaba Kurgu Videosu 'output_shorts' Klasöründe Hazır!",
                    RENK_YESIL, "white"
                )
                self.log_yaz("✅ İşlem başarıyla tamamlandı.")
            elif islem.returncode == 0:
                self.durumu_guncelle(
                    "⚠️ İşlem bitti ama video üretilememiş olabilir. Günlüğü kontrol et.",
                    "#f39c12", "white"
                )
            else:
                self.durumu_guncelle(f"❌ Hata oluştu (çıkış kodu {islem.returncode}).", RENK_KIRMIZI, "white")
                self.log_yaz(f"❌ Çıkış kodu: {islem.returncode}")

        except Exception as hata:
            self.durumu_guncelle(f"❌ Beklenmeyen hata: {hata}", RENK_KIRMIZI, "white")
            self.log_yaz(f"❌ HATA: {hata}")
        finally:
            self._islem_calisiyor = False
            self.pencere.after(0, lambda: self.kurgu_butonu.config(
                state="normal", text="🎞️  PYTHON KABA KURGUYU BAŞLAT"
            ))

    # ------------------------------------------------------------
    # BUTON 3: AFTER EFFECTS ASISTANINI ATESLE
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

        self.log_yaz(f"\n▶ After Effects başlatılıyor: {ae_yolu}")
        self.log_yaz(f"   Script: {jsx_yolu}")
        self.durumu_guncelle("🔥 After Effects başlatılıyor...", RENK_KUTU, "white")

        try:
            subprocess.Popen([ae_yolu, "-r", jsx_yolu])
            self.durumu_guncelle(
                "🔥 After Effects başlatıldı! AE açılınca script paneli görünmeli.",
                RENK_YESIL, "white"
            )
            self.log_yaz("✅ After Effects komutu gönderildi.")
        except Exception as hata:
            self.durumu_guncelle(f"❌ After Effects başlatılamadı: {hata}", RENK_KIRMIZI, "white")
            messagebox.showerror(
                "Başlatılamadı",
                f"After Effects başlatılamadı:\n{hata}\n\n"
                "AE'nin kurulu yolunu 'AE Yolu / Script Ayarları' üzerinden tekrar seçmeyi dene."
            )

    def _ae_yolunu_sor(self):
        messagebox.showinfo(
            "AfterFX.exe konumu",
            "After Effects'in kurulu olduğu 'AfterFX.exe' dosyasını seçmen gerekiyor.\n"
            r"Genelde şurada bulunur: C:\Program Files\Adobe\Adobe After Effects <sürüm>\Support Files\AfterFX.exe"
        )
        yol = filedialog.askopenfilename(
            title="AfterFX.exe dosyasını seç",
            filetypes=[("Uygulama", "*.exe"), ("Tüm dosyalar", "*.*")]
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
            "'canavar_asistan.jsx' dosyasını seçmen gerekiyor."
        )
        yol = filedialog.askopenfilename(
            title="canavar_asistan.jsx dosyasını seç",
            filetypes=[("JSX Script", "*.jsx"), ("Tüm dosyalar", "*.*")]
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
        pencere.configure(bg=RENK_ZEMIN)

        tk.Label(pencere, text="AfterFX.exe yolu:", bg=RENK_ZEMIN, fg="white",
                 font=("Segoe UI", 10)).pack(pady=(15, 5), padx=15, anchor="w")
        ae_etiketi = tk.Label(
            pencere, text=self.ayarlar.get("ae_yolu", "(seçilmedi)"),
            bg=RENK_KUTU, fg=RENK_SOLUK, font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w"
        )
        ae_etiketi.pack(fill="x", padx=15)

        def ae_sec():
            yol = self._ae_yolunu_sor()
            if yol:
                ae_etiketi.config(text=yol)

        tk.Button(pencere, text="AfterFX.exe Seç", command=ae_sec, bg=RENK_VURGU, fg="white",
                  relief="flat", padx=10, pady=6).pack(pady=(5, 15), padx=15, anchor="w")

        tk.Label(pencere, text="canavar_asistan.jsx yolu:", bg=RENK_ZEMIN, fg="white",
                 font=("Segoe UI", 10)).pack(pady=(0, 5), padx=15, anchor="w")
        jsx_etiketi = tk.Label(
            pencere, text=self.ayarlar.get("jsx_yolu", "(seçilmedi)"),
            bg=RENK_KUTU, fg=RENK_SOLUK, font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w"
        )
        jsx_etiketi.pack(fill="x", padx=15)

        def jsx_sec():
            yol = filedialog.askopenfilename(title="canavar_asistan.jsx seç", filetypes=[("JSX", "*.jsx")])
            if yol:
                self.ayarlar["jsx_yolu"] = yol
                ayarlari_kaydet(self.ayarlar)
                jsx_etiketi.config(text=yol)

        tk.Button(pencere, text="canavar_asistan.jsx Seç", command=jsx_sec, bg=RENK_VURGU, fg="white",
                  relief="flat", padx=10, pady=6).pack(pady=(5, 15), padx=15, anchor="w")


if __name__ == "__main__":
    pencere = tk.Tk()
    uygulama = KontrolPaneli(pencere)
    pencere.mainloop()