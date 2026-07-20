"""
krita_studio_paneli.py
------------------------
Canavar Asistan - Krita Studio Paneli

AE panelimizle (ae_studio_paneli.py) AYNI MANTIK, Krita'ya baglanmis hali:
  1) Ana karakterin referans resmini sec
  2) "Ne tur bir animasyon istiyorsun" - duz yazi ile anlat
  3) Gemini (metin) bunu KAC KARE gerektigini ve HER KARENIN ne
     gosterecegini planlayan bir listeye cevirir
  4) Gemini (gorsel) HER KARE ICIN, referans karaktere uygun/tutarli bir
     gorsel uretir (bizim AI Cizim Asistani ile ayni mekanizma)
  5) Panel, Krita'yi ARKA PLANDA (hic acilmadan) "kritarunner" araciyla
     baslatir, uretilen kareleri gercek bir Krita animasyon dosyasina
     (.kra) ve PNG cikisina donusturur

NASIL CALISTIRILIR:
    python krita_studio_paneli.py

ONEMLI KURULUM NOTU: Bu panelin "Krita'yi Baslat" butonu calismasi icin,
"kritarunner.exe"nin Krita kurulum klasorunde olmasi lazim (genelde Krita'nin
kendisiyle birlikte otomatik kurulur). Panelde "Krita Yolu Ayarlari"ndan bu
dosyayi (kritarunner.exe) gostermen gerekecek.
"""

import os
import sys
import json
import math
import glob
import queue
import shutil
import threading
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, scrolledtext, ttk

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    _CTK_VAR = True
except Exception:
    _CTK_VAR = False

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================================
# HATA LOG DOSYASI (guvenlik agi - pythonw ile calisirken konsol gorunmez)
# ============================================================================
import logging
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_HATA_LOG_YOLU = os.path.join(BASE_DIR, "krita_studio_hata_log.txt")
logging.basicConfig(
    filename=_HATA_LOG_YOLU, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8"
)

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def _beklenmeyen_hata_yakala(exc_type, exc_value, exc_tb):
    logging.error("YAKALANMAMIS HATA:\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    try:
        messagebox.showerror("Beklenmeyen Hata", f"Program beklenmedik bir hatayla karsilasti.\n\nDetaylar icin:\n{_HATA_LOG_YOLU}")
    except Exception:
        pass


sys.excepthook = _beklenmeyen_hata_yakala

# ============================================================================
# YOLLAR
# ============================================================================
KARE_KLASORU = os.path.join(BASE_DIR, "input_karakter_kareleri")
CIKTI_KLASORU = os.path.join(BASE_DIR, "krita_ciktilari")
BUYUTULMUS_KLASORU = os.path.join(BASE_DIR, "buyutulmus_kareler")
POZ_KUTUPHANESI_KLASORU = os.path.join(BASE_DIR, "poz_kutuphanesi")
KARE_ARSIVI_KLASORU = os.path.join(BASE_DIR, "kare_klasoru_arsivi")
VIDEO_REF_KLASORU = os.path.join(BASE_DIR, "video_referans_kareleri")
KRITA_AYAR_DOSYASI = os.path.join(BASE_DIR, "krita_ayarlar.json")
KRITA_SCRIPT_YOLU = os.path.join(BASE_DIR, "krita_kare_animasyon.py")
PANEL_CONFIG_YOLU = os.path.join(BASE_DIR, "krita_studio_config.json")
SHORTS_PARTLAR_YOLU = os.path.join(BASE_DIR, "shorts_3part.json")
AE_EDIT_NOTES_YOLU = os.path.join(BASE_DIR, "ae_edit_notes.txt")

for _k in (
    KARE_KLASORU, CIKTI_KLASORU, BUYUTULMUS_KLASORU, POZ_KUTUPHANESI_KLASORU,
    KARE_ARSIVI_KLASORU, VIDEO_REF_KLASORU,
):
    os.makedirs(_k, exist_ok=True)


def kare_klasorunu_arsivle():
    """Madde: 'her yeni video icin Kare Klasorunu elle bosaltmam sacma' -
    KARE_KLASORU'ndeki dosyalar YENI bir video icin karisip bozuk sonuc
    vermesin diye ELLE silinmesi gerekiyordu. Bunun yerine: icindeki HER
    SEYI SILMEDEN, tarih-damgali bir ARSIV alt klasorune TASIR - hicbir
    kare kaybolmaz, Kare Klasoru ise yeni video icin BOMBOS kalir.

    Donus: (True, tasinan_dosya_sayisi) basarili, (False, hata_mesaji) basarisiz.
    """
    try:
        dosyalar = [f for f in os.listdir(KARE_KLASORU) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not dosyalar:
            return True, 0
        from datetime import datetime
        hedef_klasor = os.path.join(KARE_ARSIVI_KLASORU, f"arsiv_{datetime.now():%Y%m%d_%H%M%S}")
        os.makedirs(hedef_klasor, exist_ok=True)
        for dosya_adi in dosyalar:
            shutil.move(os.path.join(KARE_KLASORU, dosya_adi), os.path.join(hedef_klasor, dosya_adi))
        return True, len(dosyalar)
    except Exception as e:
        return False, str(e)


def poz_dosya_adini_temizle(metin):
    """Bir poz aciklamasini/adini guvenli bir dosya adina cevirir."""
    temiz = "".join(c if c.isalnum() or c in (" ", "_", "-") else "" for c in metin)
    temiz = temiz.strip().replace(" ", "_").lower()
    return temiz[:60] or "poz"


def karakterin_kutuphane_klasoru(karakter_adi):
    klasor = os.path.join(POZ_KUTUPHANESI_KLASORU, poz_dosya_adini_temizle(karakter_adi))
    os.makedirs(klasor, exist_ok=True)
    return klasor


def karakterin_mevcut_pozlari(karakter_adi):
    """Bu karakter icin daha once uretilip KAYDEDILMIS poz isimlerini doner."""
    klasor = karakterin_kutuphane_klasoru(karakter_adi)
    return sorted(os.path.splitext(f)[0] for f in os.listdir(klasor) if f.lower().endswith(".png"))

# --- Madde: 'siyah konsol penceresi acilip kapaniyor, gizleyelim' -
# Windows'ta subprocess.run() bazen kisa sureli bir siyah cmd penceresi
# gosterir. Bu ayarlar, o pencerenin HIC GORUNMEMESINI saglar. ---
def sessiz_subprocess_ayarlari():
    ayarlar = {}
    if os.name == "nt":
        ayarlar["creationflags"] = subprocess.CREATE_NO_WINDOW
    return ayarlar


def _renk_koyulastir(hex_renk, oran=0.82):
    """Bir hex rengi hover efekti icin biraz koyulastirir."""
    try:
        hex_renk = hex_renk.lstrip("#")
        r, g, b = (int(hex_renk[i:i + 2], 16) for i in (0, 2, 4))
        return f"#{int(r * oran):02x}{int(g * oran):02x}{int(b * oran):02x}"
    except Exception:
        return hex_renk


def modern_buton(parent, text, command, bg, fg="#FFFFFF", font=None, height=2, **kwargs):
    """Madde: 'arayuzu modernlestir'. customtkinter kuruluysa YUVARLAK
    KOSELI, hover efektli modern bir buton dondurur. KURULU DEGILSE
    (guvenli geri dusme) eski duz tk.Button'a doner - uygulama HER
    KOSULDA calismaya devam eder, customtkinter zorunlu bagimlilik degildir."""
    if _CTK_VAR:
        yukseklik_px = 42 if height and height > 1 else 32
        buton = ctk.CTkButton(
            parent, text=text, command=command, fg_color=bg, hover_color=_renk_koyulastir(bg),
            text_color=fg, corner_radius=10, height=yukseklik_px,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        if kwargs:
            buton.configure(**kwargs)
        return buton
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                      font=font or ("Segoe UI", 10, "bold"), height=height, **kwargs)


def modern_cerceve(parent, baslik=None, bg=None, baslik_renk="#FFFFFF"):
    """Madde: 'digerleriyle kiyasla, kart gibi olsun'. customtkinter
    kuruluysa YUVARLAK KOSELI bir 'kart' cercevesi + (varsa) kalin baslik
    etiketi dondurur - LabelFrame'in kare koseli/eski gorunumu yerine.
    Degilse eski tk.LabelFrame/Frame'e guvenli sekilde duser (uygulama
    HER KOSULDA calisir)."""
    if _CTK_VAR:
        cerceve = ctk.CTkFrame(parent, corner_radius=14, fg_color=bg or "#2B2B2B")
        if baslik:
            ctk.CTkLabel(
                cerceve, text=baslik, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=baslik_renk
            ).pack(anchor="w", padx=12, pady=(10, 2))
        return cerceve
    if baslik:
        return tk.LabelFrame(parent, text=baslik, font=("Segoe UI", 9, "bold"), bg=bg, fg=baslik_renk)
    return tk.Frame(parent, bg=bg)


RENK_MOR = "#673AB7"
RENK_YESIL = "#2E7D32"
RENK_TEAL = "#00897B"
RENK_KOYU = "#37474F"
RENK_BEYAZ = "#FFFFFF"
RENK_LOG_BG = "#000000"
RENK_LOG_FG = "#00FF00"

# --- Bolum arkaplan renkleri (her bolum gorsel olarak ayirt edilsin diye) ---
RENK_BG_KARAKTER = "#42A5F5"   # canli mavi - Sahnedeki Karakterler
RENK_BG_STIL = "#EC407A"       # canli pembe - Cizim Tarzi (butonlarin moruyla karismasin diye pembe secildi)
RENK_BG_GELISMIS = "#FFA726"   # canli turuncu - Gelismis/Ucretli (gizli bolum)
RENK_BG_AYAR = "#78909C"       # canli mavi-gri - Ayar butonlari
RENK_BG_POZ = "#66BB6A"        # canli yesil - Poz/Kare Uret
RENK_FG_ACIK = "#FFFFFF"       # koyu/canli arkaplanlarda kullanilan beyaz yazi
RENK_FG_KOYU = "#212121"       # acik/parlak arkaplanlarda kullanilan koyu yazi

# --- Animasyon turu -> aciklama sablonu (madde: "ne cizilsin" alanini MANUEL
# yazmak yerine, ae_studio_paneli.py'daki AYNI animasyon kelime dagarcigindan
# SECEREK otomatik doldurmak icin). Boylece iki panel arasinda TUTARLILIK olur
# ve kullanici serbest metin yazmak zorunda kalmaz. ---
ANIMASYON_TURLERI = ["sabit", "zipla", "titre", "yuru_sagdan_sola", "yuru_soldan_saga"]

# Madde: kullanici FPS/kare sayisi hesabi YAPMASIN diye - sahne suresini
# (saniye) bu STANDART FPS ile carpip kare sayisini OTOMATIK hesapliyoruz.
# Bu, Krita projesinin varsayilan FPS'i ile ayni (krita_kare_animasyon.py).
STANDART_ANIMASYON_FPS = 24

ANIMASYON_ACIKLAMA_SABLONLARI = {
    "sabit": "{karakter} sabit duruyor, tam boy, on cepheden, dogal bir durus",
    "zipla": "{karakter} zipliyor, enerjik ve ani bir hareketle, havada",
    "titre": "{karakter} titriyor/sarsiliyor, saskin veya tedirgin bir tepkiyle",
    "yuru_sagdan_sola": "{karakter} sagdan sola dogru yuruyor, yan profilden, dogal adim hareketi",
    "yuru_soldan_saga": "{karakter} soldan saga dogru yuruyor, yan profilden, dogal adim hareketi",
}


def animasyon_aciklamasi_olustur(karakter_adi, animasyon_turu):
    """Karakter adi + animasyon turunden (ae_studio_paneli.py ile AYNI
    kelime dagarcigi) otomatik bir 'ne cizilsin' aciklamasi uretir - boylece
    kullanici serbest metin yazmak ZORUNDA kalmaz."""
    sablon = ANIMASYON_ACIKLAMA_SABLONLARI.get(animasyon_turu, "{karakter} " + str(animasyon_turu))
    return sablon.format(karakter=karakter_adi or "Karakter")

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_GORSEL_MODEL = "gemini-3.1-flash-image"
GEMINI_GORSEL_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_GORSEL_MODEL}:generateContent"


# ============================================================================
# AYAR YONETIMI
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


def _masaustu_ffmpeg_ara():
    """Desktop'taki essentials ffmpeg.exe (varsa)."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        return None
    for kok in glob.glob(os.path.join(desktop, "ffmpeg*")):
        aday = os.path.join(kok, "bin", "ffmpeg.exe")
        if os.path.exists(aday):
            return aday
        for alt in glob.glob(os.path.join(kok, "*", "bin", "ffmpeg.exe")):
            if os.path.exists(alt):
                return alt
    return None


def arac_yollarini_otomatik_doldur(ayarlar):
    """FFmpeg / kritarunner zaten kuruluysa elle secmeden bagla."""
    degisti = False
    ff = (ayarlar.get("ffmpeg_yolu") or "").strip()
    if not ff or not os.path.exists(ff):
        for aday in (
            _masaustu_ffmpeg_ara(),
            r"C:\Program Files\Krita (x64)\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
        ):
            if aday and os.path.exists(aday):
                ayarlar["ffmpeg_yolu"] = aday
                degisti = True
                break
    kr = (ayarlar.get("kritarunner_yolu") or "").strip()
    if not kr or not os.path.exists(kr):
        for aday in (
            r"C:\Program Files\Krita (x64)\bin\kritarunner.exe",
            r"C:\Program Files\Krita\bin\kritarunner.exe",
        ):
            if os.path.exists(aday):
                ayarlar["kritarunner_yolu"] = aday
                degisti = True
                break
    rs = (ayarlar.get("realesrgan_yolu") or "").strip()
    if not rs or not os.path.exists(rs):
        masa = os.path.join(os.path.expanduser("~"), "Desktop")
        adaylar = [
            os.path.join(BASE_DIR, "realesrgan-ncnn-vulkan.exe"),
            os.path.join(BASE_DIR, "realesrgan", "realesrgan-ncnn-vulkan.exe"),
            os.path.join(masa, "realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe"),
            os.path.join(masa, "realesrgan-ncnn-vulkan.exe"),
        ]
        for kok in glob.glob(os.path.join(masa, "realesrgan*")):
            adaylar.append(os.path.join(kok, "realesrgan-ncnn-vulkan.exe"))
        for aday in adaylar:
            if aday and os.path.exists(aday):
                ayarlar["realesrgan_yolu"] = aday
                degisti = True
                break
    if degisti:
        ayarlari_kaydet(ayarlar)
    return ayarlar


# Kanal kadrosu KILITLI (begendigin elle-cizilmis ref'ler). Hikaye sonradan gelir.
KANAL_KIZ_AKI = (
    "AKI (channel heroine, match assets/aki_karakter_ref.png): "
    "long messy dark burgundy bordo hair, small ahoge, "
    "simple oval eyes with tiny black dot pupils, dash mouth, no detailed nose, "
    "tasteful fuller bust under clothes, "
    "dark grey school vest over white shirt, small red bow, short red pleated skirt, "
    "white socks, brown loafers — amateur hand-drawn Dangoheart/Ganzouomo look"
)
KANAL_ERKEK_REN = (
    "REN (channel hero, match assets/ren_karakter_ref.png): "
    "messy spiky BLACK hair, simple big white sclera eyes with tiny dark pupils like Dangoheart Steve, "
    "dash mouth, soft blush, "
    "black turtleneck, long open BLACK trench coat, grey scarf, "
    "black pants, chunky brown boots, hands in pockets — same amateur hand-drawn look"
)
KANAL_STIL_DANGO = (
    "art style EXACTLY like indie YouTube shorts by DangoheartAnimation and Ganzouomo "
    "(also similar to SeanWayStudio simplicity): "
    "intentionally amateur hand-drawn web animation, thick UNEVEN shaky black marker outlines, "
    "FLAT fill-bucket colors ONLY, almost ZERO gradients, ZERO bloom, ZERO soft airbrush, "
    "simple faces (oval eyes, tiny pupils, dash mouth, little/no nose), "
    "wonky slightly off proportions like a beginner drew it on a tablet for a flipbook, "
    "hair as big flat clumps not detailed strands, low detail backgrounds, "
    "looks handmade NOT AI-polished, NOT official anime studio quality, NOT photoreal, NOT 3D"
)

# PixAI/Tensor negatif — "AI bagirmasin"
KANAL_NEGATIVE_AI = (
    "ai generated look, overly smooth, perfect symmetry, hyper detailed hair strands, "
    "beautiful detailed eyes, glossy eyes, shiny skin, intricate shading, soft gradient lighting, "
    "bloom, glow, photorealistic, 3d, cgi, western cartoon, watercolor, oil painting, "
    "official art, polished digital painting, ultra detailed, cartoon network, plastic skin, "
    "multiple panels, comic grid, speech bubble"
)

# Zombie kiz — mini short / Tensor ana kadro
KANAL_ZOMBIE_KIZ = (
    "mint pale green-gray skin zombie doll girl, messy dark bob hair with single ahoge, "
    "flat tired glowing purple-pink eyes NO gloss NO highlights, tiny dash mouth, "
    "thin black outlines, flat matte hand-drawn anime, oversized dark purple-grey hoodie, "
    "dark shorts, barefoot, slender lanky body — match kimlik_aktif.png exactly"
)
KANAL_ZOMBIE_STIL = (
    "flat matte fill colors only, thin uneven black outlines, cream or dark simple bg, "
    "handmade tablet sketch feel like indie YouTube short, ZERO soft airbrush, "
    "NOT glossy AI, NOT 3D, NOT photoreal, NOT Cartoon Network"
)

# Cizim motoru (kredi: tek kare). Varsayilan Tensor + Flanime.
CIZIM_SITE_TENSOR = "https://tensor.art"
CIZIM_SITE_NOVELAI = "https://novelai.net"
CIZIM_MODEL_NOTU = "FlatIron Anime RIPROAD — tek kare, grid/sheet YOK"

# Hikaye BOS birakilir — kullanici sonra yazar. Eski dusman-asiklar sadece yedek ornek.
KANAL_HIKAYE_YER_TUTUCU = (
    "(Hikaye sonra gelecek.)\n"
    "Simdilik sadece kadro hazir: AKI + REN, Dangoheart/Ganzouomo cizim tarzi.\n"
    "Buraya kisa bir short hikayesi yazinca Metni Topla calisir."
)

KANAL_ILK_HIKAYE = KANAL_HIKAYE_YER_TUTUCU  # geriye uyum

# 20sn cift karakter test — kanallar gibi storytime Short
TEST_HIKAYE_AKI_REN_20SN = (
    "Okul bahcesinin kenarinda yagmur yeni dinmis. "
    "AKI (koyu bordo sacli, gri yelek + kirmizi etek) tek basina duruyor, gokyuzune bakiyor. "
    "REN (kestane sac, lacivert trenc, gri atki) uzaktan gelir, elleri cebinde, yuzu bikkin. "
    "Ikisi birbirini fark eder — once sert / uzak bakarlar (dusman gibi). "
    "AKI omzunu cevirip kacmak ister ama ayakkabi bagi cozulur, egilir. "
    "REN istemeden yaninda durur, baga bakip hicbir sey demeden bekler. "
    "AKI basini kaldirir, sasirir. Ikisi de kizarir / utangac basit yuz. "
    "Kisa bir an yan yana dururlar, konusma yok. "
    "Sonra REN ters yone yurur; AKI arkasindan bakar. "
    "Son: ikisi de ayni anda geri donup bakar — birbirlerinden uzakta — kisa 'acaba?' hissi. "
    "Konusma balonu YOK. Indie YouTube Short ritmi (Dangoheart/Ganzouomo), duygusal net pozlar."
)

# 20sn ucuz test senaryosu (kopyala-yapistir yolu)
TEST_HIKAYE_20SN = (
    "Karakter masada oturuyor, telefona bakip sasiriyor. "
    "Ayağa kalkıyor, kapıya yürüyor, kapıyı açıyor, dışarı bakıp hafif gülümsüyor. "
    "Kapanışta kameraya hafif el sallar. Temiz 2D anime, elle çizilmiş gibi, beyaz zemin."
)


TEST_REHBERI_20SN = """\
=== 20 SANİYE TEST (kopyala-yapıştır, ucuz yol) ===

Hazırlık (bir kez):
1) Ana Panel aç (Ana_Panelleri_Ac / Ana_Paneli_Ac.bat)
2) FFmpeg otomatik bağlandı mı bak (ayar çubuğu) — yoksa FFmpeg butonundan seç
3) Karakter fotoğrafın hazır olsun (net, düz arka plan iyi)

Akış (~20 sn video):
1) "20sn Test Hazırla"ya bas (hikaye + süre dolar)
2) 1) Karakter → foto seç
3) 2) Stil (opsiyonel) — kanal tarzı veya Ornek Video
4) Video süresi = 20 (panel sayısı otomatik ~6-7)
5) "Metni Topla (AI)" — alt chat dolar (API anahtarı varsa online, yoksa lokal)
6) "4) Metni Al" → gemini.google.com'a Ctrl+V
7) "5) Resimleri Al" → önce karakter, sonra stil → Gemini'ye Ctrl+V
8) Gemini TEK görsel üretsin (içinde numaralı paneller) → indir
9) "6) Gemini Çıktısını Ekle" → kes + sırala
10) "7) Krita Video" → kaba 20sn mp4
11) "8) AE Panel" → Edit Chat'e not yaz (şarkı / timing) → EDIT'E BASLA → düzenle → DEVAM ET

Ne test etmiş olursun: kırpma, sıra, süre, kaba video, AE edit, müzik/detay.
API ile çizdirme YOK — sadece web Gemini (daha ucuz).
"""


# ============================================================================
# GEMINI: HIKAYEDEN KARE PLANI CIKARMA
# ============================================================================
def _kare_plani_sistem_talimati(karakterler_ve_pozlari):
    """
    karakterler_ve_pozlari: [{"ad": "Rias", "mevcut_pozlar": ["yuruyor_1", "el_sallar", ...]}, ...]
    """
    isim_listesi = ", ".join(k["ad"] for k in karakterler_ve_pozlari) if karakterler_ve_pozlari else "(isim verilmedi, tek karakter varsay)"

    poz_kutuphanesi_metni = ""
    for k in karakterler_ve_pozlari:
        pozlar = k.get("mevcut_pozlar", [])
        if pozlar:
            poz_kutuphanesi_metni += f"\n- {k['ad']} icin ZATEN CIZILMIS pozlar: {', '.join(pozlar)}"
    if not poz_kutuphanesi_metni:
        poz_kutuphanesi_metni = "\n(Hicbir karakterin daha once cizilmis pozu yok, hepsi YENI cizilecek.)"

    return (
        "Sen bir animasyon kare planlayicisisin. Kullanicinin tarif ettigi "
        "hareketi/animasyonu, ardisik KARE (frame) aciklamalarina bolersin.\n\n"
        f"Sahnedeki karakterler: {isim_listesi}\n\n"
        "COK ONEMLI - TEKRAR KULLANIM (MALIYET TASARRUFU ICIN): Her karakterin "
        f"daha once cizilmis (kutuphanede kayitli) pozlari sunlardir:{poz_kutuphanesi_metni}\n\n"
        "Eger planladigin bir kare, YUKARIDAKI mevcut pozlardan birine YETERINCE "
        "BENZIYORSA (ayni hareket/durus), YENI GORSEL UYDURMA - onun yerine "
        "'tekrar_kullan' alanina o pozun TAM ADINI yaz. SADECE gercekten "
        "FARKLI/YENI bir poz gerekiyorsa 'aciklama' ile yeni bir sey tarif et "
        "ve 'yeni_poz_adi' alanina KISA, TEKRAR KULLANILABILIR bir isim ver "
        "(orn: 'yuruyor_sol_on', 'el_sallar', 'oturuyor') - bu isim ILERIDE "
        "AYNI POZ TEKRAR GEREKTIGINDE kullanilacak, bu yuzden GENEL/TANIDIK "
        "bir isim sec, cok spesifik olmasin.\n\n"
        "COK ONEMLI - SADE TUT: Kullanici sadece ANA hareketi tarif eder, sen "
        "KENDI AKLINLA gerekli TEMEL poz detaylarini eklersin ama GEREKSIZ "
        "detay UYDURMA. Ornegin:\n"
        "- Birden fazla karakter varsa: her karede HANGI karakterin/karakterlerin "
        "goruntuye girdigini, nerede durduğunu, birbirlerine gore konumunu "
        "AÇIKLA (isimleriyle belirt, yukaridaki listeden)\n"
        "- Yuruyus/hareket ise: kollarin, bacaklarin, vucudun dogal pozisyonunu "
        "KISACA belirt (kullanici 'yuruyor' dese bile sen 'sol ayak one, sag kol "
        "geride' gibi TEMEL pozu somutlastir)\n"
        "- Hikayede KONUSMA yoksa: agiz/goz mikro mimige GIRME, sadece ANA poz.\n"
        "- Hikayede KONUSMA varsa: konusani belirt ve agzi flipbook icin "
        "ACIK/KAPALI (mouth open small oval / mouth closed dash) diye NOBETLESE yaz — "
        "Krita video cevirince agiz oynuyormus gibi gorunsun.\n\n"
        "Her kare aciklamasinda, o karede GORUNEN karakter(ler)in ismini de "
        "belirt (orn: '(Rias) sol ayak one atilmis, saga bakiyor').\n\n"
        "SADECE gecerli JSON dizi don, baska hicbir aciklama/markdown EKLEME. "
        "Format (iki ornek - biri tekrar kullanim, biri yeni):\n"
        '[{"kare_no": 1, "tekrar_kullan": "el_sallar", "aciklama": null}, '
        '{"kare_no": 2, "tekrar_kullan": null, "yeni_poz_adi": "yuruyor_sag_on", '
        '"aciklama": "(Rias) sag ayak one atilmis, saga bakiyor, agzi hafif acik"}]\n\n'
        "Kare sayisi genelde 3 ile 8 arasinda olsun - cok fazla kare gereksiz "
        "yer/sure/API maliyeti demektir."
    )


def gemini_ile_kare_plani_uret(api_key, hikaye_metni, karakterler_ve_pozlari=None):
    """Donus: (kare_listesi, hata_veya_None). Exception firlatmaz."""
    try:
        istek_govdesi = json.dumps({
            "system_instruction": {"parts": [{"text": _kare_plani_sistem_talimati(karakterler_ve_pozlari or [])}]},
            "contents": [{"role": "user", "parts": [{"text": hikaye_metni}]}],
        }).encode("utf-8")

        istek = urllib.request.Request(
            GEMINI_ENDPOINT, data=istek_govdesi,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )

        try:
            with urllib.request.urlopen(istek, timeout=30) as yanit:
                yanit_json = json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return None, f"Gemini API HTTP hatasi ({e.code}): {e.read().decode('utf-8', errors='replace')[:300]}"
        except urllib.error.URLError as e:
            return None, f"Internet baglantisi/Gemini API'ye ulasilamadi: {e.reason}"

        try:
            metin = yanit_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return None, f"Gemini'den beklenmeyen bir yanit geldi: {json.dumps(yanit_json)[:300]}"

        metin_temiz = metin.strip()
        if metin_temiz.startswith("```"):
            metin_temiz = metin_temiz.split("\n", 1)[1] if "\n" in metin_temiz else metin_temiz
            if metin_temiz.rstrip().endswith("```"):
                metin_temiz = metin_temiz.rstrip()[:-3]
            metin_temiz = metin_temiz.replace("```json", "").replace("```", "").strip()

        try:
            kare_listesi = json.loads(metin_temiz)
        except json.JSONDecodeError as e:
            return None, f"AI'nin cevabi gecerli JSON degildi: {e}\n\nHam cevap: {metin_temiz[:300]}"

        if not isinstance(kare_listesi, list) or not kare_listesi:
            return None, "AI bos veya gecersiz bir kare listesi uretti."

        return kare_listesi, None

    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"


def gemini_ile_sira_dogrula(api_key, gorsel_yolu, kare_sayisi, aciklama, zaman_asimi=30):
    """
    Madde: 'bir gorsel okuyucu olsun, hikayeyle uyumlu mu baksin, dogru
    sirada mi'. Gemini'nin METIN modelini kullanir - GORSEL URETMIYORUZ,
    sadece VAR OLAN gorsele BAKIP yorum yaptiriyoruz. Bu, gorsel uretmekten
    COK DAHA UCUZ bir islemdir (cogu zaman ucretsiz kotaya girer).

    Indirilen coklu panel gorselindeki numarali karelerin, aciklanan
    animasyon icin DOGRU OYNATMA SIRASINDA olup olmadigini kontrol eder,
    degilse dogru sirayi onerir.

    Donus: (sira_listesi, hata_veya_None). sira_listesi, 1'den kare_sayisi'na
    kadar panel numaralarinin ONERILEN oynatma sirasidir. Exception firlatmaz.
    """
    try:
        veri_b64, mime = _resmi_base64_kodla(gorsel_yolu)
        talimat = (
            "Sana anime/manga tarzinda, icinde numaralanmis paneller olan (1'den "
            f"{kare_sayisi}'e kadar, her panelin kosesinde bir sira numarasi var) TEK bir "
            "gorsel gonderiyorum. Bu paneller, asagida tarif edilen animasyonun ardisik "
            "kareleri olmali:\n\n"
            f"Istenen animasyon: {aciklama}\n\n"
            "Panellerdeki numaralari ve icerigi (poz/durus) incele. Eger paneller, "
            "DOGAL/AKICI bir hareket icin DOGRU SIRADA CIZILMEMISSE (orn. bacak/kol "
            "pozisyonlari mantikli bir hareket dongusu OLUSTURMUYORSA), onlari DOGRU "
            "OYNATMA SIRASINA diz.\n\n"
            "SADECE su formatta cevap ver, baska HICBIR aciklama/markdown EKLEME:\n"
            "SIRA: 1,2,3,4,5\n"
            "(panel numaralarini, olmasi gereken oynatma sirasiyla, virgulle ayirarak "
            "yaz - her numara 1'den " + str(kare_sayisi) + "'e kadar TAM OLARAK bir kez gecmeli)"
        )

        istek_govdesi = json.dumps({
            "contents": [{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": veri_b64}},
                    {"text": talimat},
                ]
            }],
        }).encode("utf-8")

        istek = urllib.request.Request(
            GEMINI_ENDPOINT, data=istek_govdesi,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
                yanit_json = json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return None, f"Gemini API HTTP hatasi ({e.code}): {e.read().decode('utf-8', errors='replace')[:300]}"
        except urllib.error.URLError as e:
            return None, f"Internet baglantisi/Gemini API'ye ulasilamadi: {e.reason}"

        try:
            metin = yanit_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return None, f"Gemini'den beklenmeyen bir yanit geldi: {json.dumps(yanit_json)[:300]}"

        import re
        eslesme = re.search(r"SIRA:\s*([0-9,\s]+)", metin)
        if not eslesme:
            return None, f"Gemini'nin cevabinda 'SIRA:' formati bulunamadi. Ham cevap: {metin[:300]}"
        try:
            sira_listesi = [int(x.strip()) for x in eslesme.group(1).split(",") if x.strip()]
        except ValueError:
            return None, f"Sira listesi sayilara cevrilemedi. Ham cevap: {metin[:300]}"

        beklenen_kume = set(range(1, kare_sayisi + 1))
        if set(sira_listesi) != beklenen_kume or len(sira_listesi) != kare_sayisi:
            return None, (f"Gemini'nin verdigi sira gecersiz (beklenen: 1..{kare_sayisi}, "
                           f"her biri bir kez). Gelen: {sira_listesi}")

        return sira_listesi, None
    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"


# ============================================================================
# GEMINI: HER KARE ICIN GORSEL URETME (referans karaktere tutarli)
# ============================================================================
def _lokal_poz_beatlerine_cevir(ham, panel_sayisi=4):
    """API yoksa bile hikayeyi INGILIZCE farkli poz listesine indirger (PixAI/SD)."""
    n = max(2, min(12, int(panel_sayisi or 4)))
    h = " ".join((ham or "").lower().replace("ö", "o").replace("ü", "u").replace("ş", "s")
                 .replace("ı", "i").replace("ğ", "g").replace("ç", "c").split())

    # 20sn AKI+REN okul bahcesi testi (sabit net pozlar — tum hikayeyi her satira kopyalama)
    if ("aki" in h and "ren" in h) or ("ayakkabi" in h and "bahce" in h) or ("trenc" in h and "bordo" in h):
        dokuz = [
            "1) AKI alone in wet schoolyard after rain, looking up at cloudy sky, full body, REN not in frame",
            "2) REN enters from side walking, hands in trench coat pockets, bored half-lidded eyes, full body, AKI small in background",
            "3) AKI and REN notice each other across the yard, stiff distant enemy stare, both full body readable",
            "4) AKI turns away to leave, one foot forward, looking down, ahoge tilting, REN still watching from distance",
            "5) AKI kneels tying loose shoelace, REN stands awkwardly nearby looking away, both full body",
            "6) AKI looks up surprised (oval eyes wider), REN glances at her then looks away, simple blush lines optional",
            "7) Both stand side by side silently facing forward, awkward gap between them, no talking, full body",
            "8) REN walks away opposite direction, scarf ends moving, AKI watches his back, full body",
            "9) Both look back over their shoulders at the same time from a distance, soft almost-connection, no kiss, no speech bubbles",
        ]
        if n <= 9:
            return "EACH PANEL = DIFFERENT ACTION:\n" + "\n".join(dokuz[:n])
        return "EACH PANEL = DIFFERENT ACTION:\n" + "\n".join(
            dokuz + [f"{i}) extra unique beat continuing the reunion tension" for i in range(10, n + 1)]
        )

    if "opucuk" in h or "kiss" in h:
        dort = [
            "1) walking toward camera, full body, face forward",
            "2) body turning sideways, three-quarter transition pose, mid-step",
            "3) facing camera blowing a kiss, hand near lips (REQUIRED kiss pose)",
            "4) looking back over shoulder while walking away, three-quarter rear",
        ]
        if n <= 4:
            satirlar = dort[:n]
            if n == 3:
                satirlar = [dort[0], dort[2], dort[3]]
            if n == 2:
                satirlar = [dort[2], dort[3]]
        else:
            satirlar = dort + [
                f"{i}) clearly different in-between pose between previous and next"
                for i in range(5, n + 1)
            ]
        return (
            "EACH PANEL = DIFFERENT ACTION (no repeated walk-cycle):\n"
            + "\n".join(satirlar)
        )

    # Genel: cumleleri bol; her panele KISA farkli Ingilizce beat (tum hikayeyi tekrarlama)
    parcalar = [p.strip() for p in (ham or "").replace("!", ".").replace("?", ".").split(".") if p.strip()]
    if len(parcalar) < 2:
        parcalar = [p.strip() for p in (ham or "").split(",") if p.strip()]
    satirlar = []
    for i in range(1, n + 1):
        parca = parcalar[(i - 1) % max(1, len(parcalar))] if parcalar else "character in a clear new pose"
        kisa = parca[:120]
        satirlar.append(
            f"{i}) full body keyframe beat {i}/{n}: {kisa} "
            f"(unique pose, different from other panels)"
        )
    return (
        "EACH PANEL = DIFFERENT ACTION:\n"
        + "\n".join(satirlar)
        + "\nNo duplicated walking frames. Keep character identity consistent."
    )


def gemini_ile_hikaye_temizle(api_key, ham_hikaye, zaman_asimi=45, panel_sayisi=4):
    """
    Hikayeyi gorsel AI (PixAI/Gemini) icin INGILIZCE POZ-BEAT listesine cevirir.
    """
    ham = (ham_hikaye or "").strip()
    if not ham:
        return None, "Hikaye bos"
    n = max(2, min(12, int(panel_sayisi or 4)))

    if not api_key:
        return _lokal_poz_beatlerine_cevir(ham, n), None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + api_key
    )
    sistem = (
        f"You are an animation pose planner. Write EXACTLY {n} DIFFERENT poses.\n"
        "RULES:\n"
        "- Output MUST be in English only.\n"
        "- Numbered list only, no markdown.\n"
        f"- {n} lines, one panel each, each line a CLEARLY different action.\n"
        "- Forbidden: 4 near-identical walk steps / walk-cycle copies.\n"
        "- If the story has a kiss, one line MUST be 'blowing a kiss (hand near lips)'.\n"
        "- Example 4-pack: (1) walk forward (2) turn sideways (3) blow kiss (4) look back and leave.\n"
        "User may write Turkish; you translate beats into English pose lines.\n"
    )
    govde = {
        "contents": [{"role": "user", "parts": [
            {"text": sistem + "\n\nUSER STORY:\n" + ham}
        ]}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": 800},
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=zaman_asimi) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        metin = veri["candidates"][0]["content"]["parts"][0]["text"].strip()
        return metin, None
    except Exception as e:
        return _lokal_poz_beatlerine_cevir(ham, n), str(e)


def gemini_ile_uc_part_shorts_hikaye(api_key, tema_veya_ipucu="", zaman_asimi=60):
    """
    3-part YouTube Shorts serisi hikayesi uretir.
    Donus: ({'birlesik', 'partlar':[{baslik, hikaye, kanca}], 'ae_notu'}, hata)
    """
    ipucu = (tema_veya_ipucu or "").strip() or "orijinal kombinasyon: korku + tatli anime comedy"

    lokal_ornek = {
        "birlesik": (
            "PART 1: Karakter gece koridorda ayak sesi duyar, kapı aralanır, "
            "'Part 2'de görüşürüz...' yazısıyla biter.\n"
            "PART 2: Kapının ardında yanlış alarm (kedi) ama asıl gölge arkada belirir; "
            "yine cliffhanger.\n"
            "PART 3: Karakter cesaret bulur, gölge dost çıkar / twist, short biter."
        ),
        "partlar": [
            {"baslik": "Part 1", "hikaye": "Gece koridor, ayak sesi, kapı aralanır.",
             "kanca": "Part 2'de görüşürüz..."},
            {"baslik": "Part 2", "hikaye": "Kedi çıkar ama asıl gölge arkada.",
             "kanca": "Part 3'te bitiriyoruz!"},
            {"baslik": "Part 3", "hikaye": "Cesaret + twist son.",
             "kanca": "Like & Part 1'e dön link"},
        ],
        "ae_notu": "AE'de timeline'i 3'e bol; her part sonuna kanca yazisi ekle.",
    }

    if not api_key:
        return lokal_ornek, None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + api_key
    )
    sistem = (
        "YouTube Shorts icin 3 PARCALI anime short senaryosu yaz.\n"
        "Her part ~15-25 saniye, dikey short ritminde.\n"
        "Part 1 ve 2 CLIFFHANGER ile bitsin (orn. 'Part 2'de gorusuruz').\n"
        "Part 3 tatmin edici son + istege bagli twist.\n"
        "Cizilebilir net pozlar olsun (soyut felsefe degil).\n"
        "SADECE su JSON'u yaz (baska metin yok):\n"
        '{"partlar":[{"baslik":"Part 1","hikaye":"...","kanca":"..."},'
        '{"baslik":"Part 2","hikaye":"...","kanca":"..."},'
        '{"baslik":"Part 3","hikaye":"...","kanca":"..."}],'
        '"ae_notu":"AE bolme notu"}'
    )
    govde = {
        "contents": [{"role": "user", "parts": [
            {"text": sistem + "\n\nTEMA / IPUCU:\n" + ipucu}
        ]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2500},
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=zaman_asimi) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        metin = veri["candidates"][0]["content"]["parts"][0]["text"].strip()
        if metin.startswith("```"):
            metin = metin.strip("`")
            if metin.lower().startswith("json"):
                metin = metin[4:].strip()
        veri_j = json.loads(metin)
        partlar = veri_j.get("partlar") or []
        if len(partlar) < 3:
            return None, "AI 3 part uretemedi"
        birlesik_satirlar = []
        for i, p in enumerate(partlar[:3], start=1):
            birlesik_satirlar.append(
                f"PART {i}: {p.get('hikaye', '').strip()} "
                f"(Kanca: {p.get('kanca', '').strip()})"
            )
        return {
            "birlesik": "\n".join(birlesik_satirlar),
            "partlar": partlar[:3],
            "ae_notu": veri_j.get("ae_notu") or (
                "AE'de 3 part'a bol; her part sonuna kanca yazisi koy."
            ),
        }, None
    except Exception as e:
        return None, str(e)


def ffmpeg_videodan_kareler(ffmpeg_yolu, video_yolu, cikti_klasoru, adet=4):
    """Ornek videodan esit aralikli kareler cikarir. Donus: (yollar, hata)."""
    if not ffmpeg_yolu or not os.path.exists(ffmpeg_yolu):
        return [], "FFmpeg yolu yok"
    if not video_yolu or not os.path.exists(video_yolu):
        return [], "Video yok"
    os.makedirs(cikti_klasoru, exist_ok=True)
    for eski in glob.glob(os.path.join(cikti_klasoru, "ref_*.png")):
        try:
            os.remove(eski)
        except Exception:
            pass
    # fps filtresiyle ~adet kare
    desen = os.path.join(cikti_klasoru, "ref_%02d.png")
    try:
        # once sureyi ogren
        probe = subprocess.run(
            [ffmpeg_yolu, "-i", video_yolu],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        # fps dusuk ornekleme
        cmd = [
            ffmpeg_yolu, "-y", "-i", video_yolu,
            "-vf", f"fps={max(0.2, adet / 12.0)},scale=512:-1",
            "-vframes", str(adet),
            desen,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        yollar = sorted(glob.glob(os.path.join(cikti_klasoru, "ref_*.png")))
        if not yollar:
            return [], (r.stderr or probe.stderr or "Kare cikarilamadi")[:400]
        return yollar, None
    except Exception as e:
        return [], str(e)


def _renk_adi_yaklasik(r, g, b):
    """Basit RGB → Ingilizce renk adi (stil metni icin)."""
    if max(r, g, b) < 40:
        return "near-black"
    if min(r, g, b) > 220:
        return "near-white"
    if r > 180 and g < 90 and b < 90:
        return "crimson-red"
    if r > 160 and g > 100 and b < 80:
        return "warm-orange"
    if r > 180 and g > 160 and b < 100:
        return "gold-yellow"
    if g > r and g > b and g > 120:
        return "green"
    if b > r and b > g and b > 120:
        return "blue"
    if r > 140 and b > 140 and g < 120:
        return "magenta-purple"
    if abs(r - g) < 25 and abs(g - b) < 25:
        return "gray"
    if r > g and r > b:
        return "warm-reddish"
    if g > r and g > b:
        return "greenish"
    return "cool-bluish"


def stil_resmini_lokal_metne_cevir(stil_yolu):
    """
    Stil PNG/JPG'den API olmadan: palet + cizgi/zemin tahmini → Ingilizce stil blogu.
    PixAI resmi kabul etmese bile prompt METINDE stil gorunsun.
    """
    ad = os.path.basename(stil_yolu) if stil_yolu else "style.png"
    temel = KANAL_STIL_DANGO
    if not stil_yolu or not os.path.exists(stil_yolu):
        return KANAL_STIL_DANGO + " (no style file selected — match this look)"
    try:
        from PIL import Image
        from collections import Counter

        im = Image.open(stil_yolu).convert("RGB")
        w, h = im.size
        _bil = Image.BILINEAR
        kucuk = im.resize((64, 64), _bil)
        pikseller = list(kucuk.getdata())
        # Yuvarlak renk kovaları
        kovalar = []
        for r, g, b in pikseller:
            kovalar.append((r // 32 * 32, g // 32 * 32, b // 32 * 32))
        en_cok = [c for c, _ in Counter(kovalar).most_common(5)]
        renkler = [_renk_adi_yaklasik(*c) for c in en_cok]
        renk_str = ", ".join(dict.fromkeys(renkler))  # tekrarsiz sira koru

        # Kenar yogunlugu ~ cizgi sertligi
        gri = im.convert("L").resize((96, 96), _bil)
        px = list(gri.getdata())
        kenar = 0
        for y in range(95):
            for x in range(95):
                i = y * 96 + x
                if abs(px[i] - px[i + 1]) > 40 or abs(px[i] - px[i + 96]) > 40:
                    kenar += 1
        kenar_oran = kenar / (95 * 95)
        if kenar_oran > 0.22:
            cizgi = "bold crisp black lineart, high-contrast outlines"
        elif kenar_oran > 0.12:
            cizgi = "medium clean anime outlines, readable shapes"
        else:
            cizgi = "softer linework, gentler edges, less harsh outlines"

        ort = sum(sum(p) for p in pikseller) / (len(pikseller) * 3)
        if ort > 180:
            zemin = "bright / airy background, lots of light negative space"
        elif ort < 90:
            zemin = "darker moody background, night or shadowed scene"
        else:
            zemin = "mid-tone readable background, not cluttered"

        oran = "portrait tall" if h > w * 1.15 else ("landscape wide" if w > h * 1.15 else "near-square")
        return (
            f"MATCH THIS REFERENCE LOOK (from file '{ad}', {w}x{h} {oran}): "
            f"{cizgi}; {zemin}; dominant colors roughly [{renk_str}]; "
            f"{temel}; same brush feel and color temperature as that reference; "
            "keep character identity separate — copy STYLE only (line, shade, palette, vibe)."
        )
    except Exception as e:
        return f"{temel}, match file '{ad}' as closely as possible ({e})"


def stil_resmini_metne_cevir(stil_yolu, api_key="", zaman_asimi=45):
    """
    Stil gorselini DETAYLI Ingilizce stil metnine cevirir.
    API varsa Gemini vision; yoksa lokal palet. Hepsi TEXT — yapistirinca kabul edilir.
    """
    lokal = stil_resmini_lokal_metne_cevir(stil_yolu)
    if not api_key or not stil_yolu or not os.path.exists(stil_yolu):
        return lokal
    try:
        veri_b64, mime = _resmi_base64_kodla(stil_yolu)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + api_key
        )
        soru = (
            "Describe ONLY the ART STYLE of this image for a PixAI / Stable Diffusion prompt. "
            "English only. Comma-separated detailed tags + 2-3 short sentences. "
            "Cover: line weight, cel vs soft shading, color palette, background treatment, "
            "anime era vibe, indie YouTube short look if any. "
            "Do NOT describe the character identity or clothing as the main point — STYLE only. "
            "No markdown. Start with 'Art style:'"
        )
        govde = {
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": mime, "data": veri_b64}},
                {"text": soru},
            ]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
        }
        req = urllib.request.Request(
            url, data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=zaman_asimi) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
        ai = veri["candidates"][0]["content"]["parts"][0]["text"].strip()
        if len(ai) < 40:
            return lokal
        return ai + "\n(Also local palette hint: " + lokal + ")"
    except Exception:
        return lokal


def _defter_flipbook_aciklamasi(kare_sayisi, satir, sutun):
    """Defter/flipbook mantigi — promptta METIN olarak (unutulmasin)."""
    return (
        "=== FLIPBOOK / NOTEBOOK FILM (DEFTER MANTIGI) ===\n"
        "This sheet is NOT a comic page to read with speech bubbles.\n"
        "We make a FLIPBOOK FILM: each numbered panel = ONE notebook page of the movie.\n"
        f"When pages 1..{kare_sayisi} flip fast in order, they become the short film.\n"
        f"Layout: exactly {satir} rows x {sutun} columns = {kare_sayisi} equal panels, thin black gutters.\n"
        "Order: left-to-right, then next row (1 top-left … N bottom-right).\n"
        "Small clear numbers 1..N in each panel TOP-LEFT (for our cutter to keep order). "
        "Numbers must NOT cover the face.\n"
        "After download our app will: cut panels → DELETE numbers → align character footing → "
        "upscale → play as flipbook video. So draw each panel as a FULL keyframe page "
        "(same character, different action), readable full body, headroom, feet visible, "
        "identical scale and footing baseline so the film does not slide.\n"
        "LIP FLAP (if dialogue): on talking beats alternate mouth CLOSED (dash) vs "
        "mouth OPEN (small oval) across consecutive panels — body pose stays almost same "
        "so flipping looks like speaking. Keep mouths SIMPLE (no teeth detail).\n"
    )


def manuel_prompt_metni_olustur(aciklama, karakter_yolu, stil_yolu, stil_metni=None):
    """
    Tek poz: stil METIN olarak gomulu (PixAI resim kabul etmese bile).
    """
    stil_blogu = (stil_metni or "").strip() or stil_resmini_lokal_metne_cevir(stil_yolu)
    metin = (
        f"{KANAL_STIL_DANGO}\n"
        "ONE single full-page illustration — like ONE flipbook / notebook page of a short film "
        "(NOT a multi-panel manga page, NOT a comic grid).\n\n"
        "=== ART STYLE (TEXT — must match; image upload optional) ===\n"
        f"{stil_blogu}\n\n"
        "Same heroine identity if character known: "
        f"{KANAL_KIZ_AKI} "
        "(unless the pose text says otherwise; may include REN: "
        f"{KANAL_ERKEK_REN}).\n"
        "Full body readable, head and feet not cropped, headroom above hair.\n\n"
        f"=== THIS PAGE ACTION ===\n{aciklama}\n\n"
        "=== NEGATIVE ===\n"
        f"{GORSEL_NEGATIVE_PROMPT}\n"
    )
    if karakter_yolu:
        metin += (
            f"\n(Optional: if the site allows image ref, upload '{os.path.basename(karakter_yolu)}' "
            "as CHARACTER only — style is already described in TEXT above.)"
        )
    if stil_yolu:
        metin += (
            f"\n(Style source file was '{os.path.basename(stil_yolu)}' — already converted to TEXT above; "
            "do not ignore the style block.)"
        )
    return metin


def resmi_panoya_kopyala(dosya_yolu):
    """
    Bir gorsel dosyasini WINDOWS PANOSUNA GERCEK GORSEL olarak kopyalar
    (metin/dosya yolu degil) - boylece gemini.google.com sohbet kutusuna
    dogrudan Ctrl+V ile yapistirilabilir. Bu, "Metni Kopyala" ile SADECE
    yazinin kopyalanip, referans resmin hic gonderilmemesi sorununu cozer
    (Gemini metinde 'referans resim' diye bir sey gormeden calisiyordu).

    Donus: (True, None) basarili, (False, hata_metni) basarisiz.
    Gereksinim: pywin32 (pip install pywin32) - sadece Windows'ta calisir.
    """
    try:
        import win32clipboard
    except ImportError:
        return False, ("pywin32 kutuphanesi kurulu degil. Kurulum icin komut "
                        "istemcisinde (cmd/PowerShell) sunu calistir: "
                        "pip install pywin32")

    try:
        from PIL import Image
        import io

        img = Image.open(dosya_yolu).convert("RGB")
        tampon = io.BytesIO()
        img.save(tampon, "BMP")
        # BMP dosyasinin ilk 14 baytlik dosya basligini at - Windows'un CF_DIB
        # formati bu basliksiz "cekirdek" veriyi bekler.
        dib_verisi = tampon.getvalue()[14:]
        tampon.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib_verisi)
        win32clipboard.CloseClipboard()
        return True, None
    except Exception as e:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False, str(e)


def _resmi_base64_kodla(dosya_yolu):
    import base64
    with open(dosya_yolu, "rb") as f:
        veri = f.read()
    uzanti = os.path.splitext(dosya_yolu)[1].lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(uzanti, "image/png")
    return base64.b64encode(veri).decode("ascii"), mime


# PixAI / SD / Tensor — negatif
# NOT: "bad anatomy" bilerek YOK — indie Short'ta biraz egrilik isteniyor
GORSEL_NEGATIVE_PROMPT = (
    "watermark, logo, username, extra fingers, fused fingers, "
    "extra arms, extra legs, cropped head, cropped feet, out of frame, "
    "3d, cgi, photorealistic, realistic skin pores, western cartoon, "
    "muddy colors, deformed face, glossy eyes, shiny skin, plastic skin, "
    "ai generated look, overly smooth, perfect symmetry, hyper detailed hair strands, "
    "beautiful detailed eyes, intricate shading, soft gradient lighting, bloom, glow, "
    "official art, polished digital painting, ultra detailed, oil painting, watercolor, "
    "cartoon network, multiple panels, comic grid, speech bubble, nsfw"
)

# True = defter: her kredi = 1 tam sayfa (seri video icin). Grid YOK.
FLIPBOOK_MODU = True


def _poz_satirlarini_ayikla(aciklama: str):
    """Hikaye/poz metninden defter sayfa listesi."""
    satirlar = []
    for ham in (aciklama or "").splitlines():
        s = ham.strip()
        if not s:
            continue
        if s.startswith("===") or s.startswith("---") or s.startswith("("):
            continue
        if s.lower().startswith("negative") or s.lower().startswith("art style"):
            continue
        satirlar.append(s)
    if not satirlar and (aciklama or "").strip():
        return [(aciklama or "").strip()]
    return satirlar


def _aktif_dna(kadrosu="zombie"):
    """Aktif karakter DNA + stil metni."""
    if kadrosu == "aki_ren":
        return KANAL_KIZ_AKI, KANAL_ERKEK_REN, KANAL_STIL_DANGO
    return KANAL_ZOMBIE_KIZ, "", KANAL_ZOMBIE_STIL


def _flipbook_tek_sayfa_talimati(poz_metni: str, kadrosu="zombie") -> str:
    """Defter sayfasi gibi TEK tam kare — manga ızgarasi YASAK."""
    kiz, erkek, stil = _aktif_dna(kadrosu)
    ekstra = f" If second character: {erkek}." if erkek else ""
    return (
        "ONE single full-page illustration only, NOT a comic, NOT a manga page, "
        "NOT a storyboard grid, NOT multi-panel, NO panel borders, NO gutters, NO numbers,\n"
        f"{stil}\n"
        "vertical portrait preferred (832x1216 or 768x1152).\n\n"
        f"Character lock: {kiz}.{ekstra}\n"
        "Full body readable, head and feet not cropped, headroom above hair.\n\n"
        f"THIS PAGE ACTION / SCENE:\n{poz_metni}\n\n"
        "=== NEGATIVE PROMPT ===\n"
        f"{GORSEL_NEGATIVE_PROMPT}\n"
        f"{KANAL_NEGATIVE_AI}\n"
    )


def _coklu_panel_talimat_metni(aciklama, kare_sayisi, satir, sutun, stil_metni=None):
    """Izgarada numara VAR (sira icin). Stil + defter mantigi METIN olarak."""
    stil_blogu = (stil_metni or "").strip() or (
        "clean 2D anime lineart, thick black outlines, cel shading, "
        "indie YouTube short keyframe, NOT photoreal, NOT 3D"
    )
    if FLIPBOOK_MODU:
        return (
            "FLIPBOOK MODE — SEPARATE full-page images (one notebook page = one pose).\n"
            "Do NOT draw a grid. Do NOT put multiple panels in one image.\n"
            f"You need {kare_sayisi} pages total. Flip fast in order = the film.\n\n"
            "=== ART STYLE (TEXT — must match) ===\n"
            f"{stil_blogu}\n\n"
            f"POSE LIST (page 1..{kare_sayisi}):\n{aciklama}\n\n"
            + _flipbook_tek_sayfa_talimati("[PASTE ONE POSE LINE HERE]", kadrosu="zombie")
        )
    return (
        f"{KANAL_STIL_DANGO}\n\n"
        + _defter_flipbook_aciklamasi(kare_sayisi, satir, sutun)
        + "\n=== ART STYLE (TEXT ONLY — FOLLOW THIS; NO AI POLISH) ===\n"
        f"{stil_blogu}\n"
        "Match line weight, flat colors, shaky amateur outlines EXACTLY. "
        "Do not invent a polished studio anime look.\n\n"
        "Same cast every panel (ORIGINAL OCs — do NOT draw Rias Gremory or any franchise lookalike): "
        f"{KANAL_KIZ_AKI}; {KANAL_ERKEK_REN} "
        "(unless a pose line features only one of them).\n"
        "Full body readable in every panel; headroom; feet visible; same scale + footing.\n\n"
        f"=== {kare_sayisi} DIFFERENT ACTIONS (no repeated walk-cycle copies) ===\n"
        f"{aciklama}\n\n"
        "=== NEGATIVE ===\n"
        f"{GORSEL_NEGATIVE_PROMPT}\n"
    )


def coklu_panel_prompt_metni_olustur(
    aciklama, kare_sayisi, satir, sutun, karakter_yolu, stil_yolu, stil_metni=None
):
    """
    PixAI/Gemini yapistirma metni: stil resimden TEXT'e cevrilmis + defter flipbook anlatimi.
    """
    if not (stil_metni or "").strip():
        stil_metni = stil_resmini_lokal_metne_cevir(stil_yolu)
    metin = _coklu_panel_talimat_metni(
        aciklama, kare_sayisi, satir, sutun, stil_metni=stil_metni
    )
    if karakter_yolu:
        metin += (
            f"\n(Optional character image if site allows: '{os.path.basename(karakter_yolu)}' "
            "— identity only. STYLE is already in the TEXT block above.)"
        )
    if stil_yolu:
        metin += (
            f"\n(Style came from file '{os.path.basename(stil_yolu)}' — converted to TEXT above; "
            "do not drop the ART STYLE section.)"
        )
    return metin


def flipbook_tek_sayfa_promptu(
    poz_satiri: str, karakter_yolu=None, stil_yolu=None, stil_metni=None, kadrosu="zombie", motor="tensor"
) -> str:
    """Tensor/NovelAI'ye yapistirilacak TEK defter sayfasi (1 kredi = 1 kare).
    KISA tut: uzun stil duvari modelde character sheet tetikliyor."""
    # Poz satirindan numarayi temizle
    poz = (poz_satiri or "").strip()
    if poz[:2].isdigit() and ")" in poz[:4]:
        poz = poz.split(")", 1)[-1].strip()
    if kadrosu == "zombie":
        # Kisa, sahne once — sheet riskini dusurur
        metin = (
            "1girl, solo, single character, full body in environment, "
            "amateur hand-drawn tablet sketch, uneven thin black outlines, flat matte colors only, "
            "mint pale green-gray skin zombie doll girl, messy dark bob hair ahoge, "
            "flat tired purple eyes no gloss, oversized dark purple-grey hoodie, dark shorts, barefoot, "
            "exact face as reference, NOT polished AI, NOT watercolor, "
            "FIXED CAMERA: front view simple flat night road, zebra crosswalk CLOSE TO CAMERA in foreground, "
            "character enters from RIGHT side of frame, minimal flat buildings, NO deep alley tunnel, "
            "ONE image only, NO character sheet, NO expression sheet, NO multiple heads, NO collage,\n"
            f"SCENE ACTION: {poz}"
        )
        if karakter_yolu:
            metin += f"\n(Ref upload: {os.path.basename(karakter_yolu)}, IP-Adapter 0.25)"
        return metin
    stil_blogu = (stil_metni or "").strip() or stil_resmini_lokal_metne_cevir(stil_yolu)
    _, _, stil_dna = _aktif_dna(kadrosu)
    if not stil_blogu or "clean 2D" in (stil_blogu or "")[:40]:
        stil_blogu = stil_dna
    site = "Tensor.Art + FlatIron" if motor == "tensor" else "NovelAI Precise Reference"
    metin = (
        f"=== SITE: {site} | MODEL: {CIZIM_MODEL_NOTU} ===\n"
        "Generate EXACTLY ONE image. No grid. No 4-panel. No comic page. No character sheet.\n\n"
        "=== ART STYLE (TEXT) ===\n"
        f"{stil_blogu}\n\n"
        + _flipbook_tek_sayfa_talimati(poz, kadrosu=kadrosu)
    )
    if karakter_yolu:
        metin += (
            f"\n(Upload CHARACTER ref: {os.path.basename(karakter_yolu)} — "
            "identity lock. Style is in TEXT.)"
        )
    if stil_yolu:
        metin += f"\n(Optional STYLE ref: {os.path.basename(stil_yolu)})"
    if motor == "novelai":
        metin += (
            "\n\nNovelAI: Precise Reference = Character + Style together. "
            "Tags help: flat color, lineart, tegaki."
        )
    else:
        metin += (
            "\n\nTensor: IP-Adapter 0.25-0.35, CFG 5-6, Steps 20-28, Euler."
        )
    return metin


def gemini_ile_coklu_poz_uret(api_key, karakterler, stil_referans_yolu, aciklama, kare_sayisi, satir, sutun, zaman_asimi=90):
    """
    UCRETLI API yolu: TEK Gemini gorsel istegiyle N pozi izgara olarak uretir.
    Donus: (PIL.Image, None) veya (None, hata).
    """
    try:
        from PIL import Image
        from io import BytesIO
        import base64

        parcalar = []
        for k in (karakterler or []):
            yol = k.get("yol")
            if yol and os.path.exists(yol):
                veri_b64, mime = _resmi_base64_kodla(yol)
                parcalar.append({"inline_data": {"mime_type": mime, "data": veri_b64}})
                parcalar.append({"text": f"(Above image is character reference for '{k['ad']}'.)"})

        talimat = _coklu_panel_talimat_metni(
            aciklama, kare_sayisi, satir, sutun,
            stil_metni=stil_resmini_metne_cevir(stil_referans_yolu, api_key),
        )

        if stil_referans_yolu and os.path.exists(stil_referans_yolu):
            veri_b64, mime = _resmi_base64_kodla(stil_referans_yolu)
            parcalar.append({"inline_data": {"mime_type": mime, "data": veri_b64}})
            talimat += (
                "\n\nLast image: STYLE reference only — match lineart/colors/shading, "
                "do not replace the character identity. Style is also described in TEXT above."
            )

        parcalar.append({"text": talimat})

        istek_govdesi = json.dumps({
            "contents": [{"role": "user", "parts": parcalar}],
            "generation_config": {"response_modalities": ["TEXT", "IMAGE"]},
        }).encode("utf-8")

        istek = urllib.request.Request(
            GEMINI_GORSEL_ENDPOINT, data=istek_govdesi,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )

        try:
            with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
                yanit_json = json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return None, f"Gemini Gorsel API HTTP hatasi ({e.code}): {e.read().decode('utf-8', errors='replace')[:300]}"
        except urllib.error.URLError as e:
            return None, f"Internet baglantisi/Gemini API'ye ulasilamadi: {e.reason}"

        try:
            parcalar_cevap = yanit_json["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            return None, f"Gemini'den beklenmeyen bir yanit geldi: {json.dumps(yanit_json)[:300]}"

        for parca in parcalar_cevap:
            veri_inline = parca.get("inline_data") or parca.get("inlineData")
            if veri_inline and veri_inline.get("data"):
                return Image.open(BytesIO(base64.b64decode(veri_inline["data"]))), None

        return None, "Gemini bu istekte gorsel uretmedi (sadece metin donmus olabilir)."

    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"


def gemini_ile_kare_gorseli_uret(api_key, karakterler, stil_referans_yolu, kare_aciklamasi, zaman_asimi=60):
    """Donus: (PIL.Image, None) basarili, (None, hata) basarisiz. Exception firlatmaz.

    karakterler: [{"ad": "Rias", "yol": "..."}, {"ad": "Akeno", "yol": "..."}, ...]
                 - sahnede olabilecek TUM karakterlerin referanslari. Gemini,
                 kare_aciklamasi icinde ismi GECEN karakter(ler)i bu
                 referanslardan tanimlayip ciziyor.
    stil_referans_yolu: "hangi cizim tarzina benzemesi gerektigi" (opsiyonel)
    """
    try:
        from PIL import Image
        from io import BytesIO

        parcalar = []
        karakter_isim_listesi = ", ".join(k["ad"] for k in (karakterler or []))
        talimat = (
            "Bu bir 2D anime/manga tarzi karakter animasyon karesi. Sana "
            "sirayla bazi KARAKTER REFERANS gorselleri verilecek (her biri "
            f"kimin oldugu belirtilerek): {karakter_isim_listesi or '(karakter yok)'}\n\n"
            "Asagida tarif edilen sahnede, ISMI GECEN karakter(ler)in KENDI "
            "KIMLIKLERINI/GORUNUMLERINI KORUYARAK, tarif edilen pozu/sahneyi "
            "ciz. Sahnede gecmeyen karakterleri CIZME. DUZ/BEYAZ bir zemin "
            "uzerinde, tam boy.\n\n"
            f"Istenen sahne: {kare_aciklamasi}"
        )

        for k in (karakterler or []):
            yol = k.get("yol")
            if yol and os.path.exists(yol):
                veri_b64, mime = _resmi_base64_kodla(yol)
                parcalar.append({"inline_data": {"mime_type": mime, "data": veri_b64}})
                parcalar.append({"text": f"(Yukarideki gorsel '{k['ad']}' adli karakterin referansidir.)"})

        if stil_referans_yolu and os.path.exists(stil_referans_yolu):
            veri_b64, mime = _resmi_base64_kodla(stil_referans_yolu)
            parcalar.append({"inline_data": {"mime_type": mime, "data": veri_b64}})
            talimat += "\n\nSon gorsel: SADECE CIZIM TARZI/STIL REFERANSI - karakterin kendisi degil, sanat tarzi (renklendirme, cizgi kalinligi, golgeleme tarzi) buna benzemeli."

        parcalar.append({"text": talimat})

        istek_govdesi = json.dumps({
            "contents": [{"role": "user", "parts": parcalar}],
            "generation_config": {"response_modalities": ["TEXT", "IMAGE"]},
        }).encode("utf-8")

        istek = urllib.request.Request(
            GEMINI_GORSEL_ENDPOINT, data=istek_govdesi,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )

        try:
            with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
                yanit_json = json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return None, f"Gemini Gorsel API HTTP hatasi ({e.code}): {e.read().decode('utf-8', errors='replace')[:300]}"
        except urllib.error.URLError as e:
            return None, f"Internet baglantisi/Gemini API'ye ulasilamadi: {e.reason}"

        try:
            parcalar_cevap = yanit_json["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            return None, f"Gemini'den beklenmeyen bir yanit geldi: {json.dumps(yanit_json)[:300]}"

        import base64
        for parca in parcalar_cevap:
            veri_inline = parca.get("inline_data") or parca.get("inlineData")
            if veri_inline and veri_inline.get("data"):
                return Image.open(BytesIO(base64.b64decode(veri_inline["data"]))), None

        return None, "Gemini bu kare icin gorsel uretmedi (sadece metin donmus olabilir)."

    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"


# ============================================================================
# KRITARUNNER ILE KRITA'YI ARKA PLANDA BASLATMA
# ============================================================================
def _pil_kare_kalite_buyut(src, dst, olcek=4, min_kenar=720):
    """Real-ESRGAN yokken/yedekte: LANCZOS + unsharp, min kenar garantisi."""
    from PIL import Image, ImageFilter, ImageEnhance

    with Image.open(src) as im:
        im = im.convert("RGBA")
        w, h = im.size
        hedef_olcek = max(2, min(8, int(olcek or 4)))
        nw, nh = w * hedef_olcek, h * hedef_olcek
        # Shorts icin en az ~720 kenar — bulanik kurekleri buyut
        kisa = min(nw, nh)
        if kisa < min_kenar and kisa > 0:
            ekstra = math.ceil(min_kenar / kisa)
            nw, nh = nw * ekstra, nh * ekstra
        # Iki adimli upscale daha az artifact verir
        if max(nw / w, nh / h) >= 3:
            orta = im.resize((max(w * 2, 1), max(h * 2, 1)), Image.Resampling.LANCZOS)
            im = orta.resize((nw, nh), Image.Resampling.LANCZOS)
        else:
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.8, percent=170, threshold=2))
        im = ImageEnhance.Contrast(im).enhance(1.08)
        im = ImageEnhance.Color(im).enhance(1.06)
        im = ImageEnhance.Sharpness(im).enhance(1.25)
        im.save(dst)


def kareleri_buyut(realesrgan_yolu, kaynak_klasor, hedef_klasor, olcek=4,
                    model_adi="realesrgan-x4plus-anime"):
    """
    Real-ESRGAN anime 4x + keskinlestirme. Exe yoksa PIL kalite yedegi
    (yine de video izlenebilir olsun).
    """
    try:
        from PIL import Image, ImageFilter, ImageEnhance

        os.makedirs(hedef_klasor, exist_ok=True)
        # Eski buyutulmuslari temizle — karisik boyut onlensin
        for eski in os.listdir(hedef_klasor):
            if eski.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                try:
                    os.remove(os.path.join(hedef_klasor, eski))
                except Exception:
                    pass

        olcek = max(2, min(4, int(olcek or 4)))
        son_hata = ""
        exe_ok = bool(realesrgan_yolu and os.path.exists(realesrgan_yolu))

        if exe_ok:
            modeller = [model_adi, "realesrgan-x4plus", "realesr-animevideov3"]
            for mod in modeller:
                komut = [
                    realesrgan_yolu,
                    "-i", kaynak_klasor,
                    "-o", hedef_klasor,
                    "-n", mod,
                    "-s", str(olcek),
                    "-f", "png",
                ]
                sonuc = subprocess.run(
                    komut, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=1200, **sessiz_subprocess_ayarlari()
                )
                if sonuc.returncode == 0:
                    for ad in os.listdir(hedef_klasor):
                        if not ad.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                            continue
                        yol = os.path.join(hedef_klasor, ad)
                        try:
                            with Image.open(yol) as im:
                                im = im.convert("RGBA")
                                im = im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=2))
                                im = ImageEnhance.Contrast(im).enhance(1.07)
                                im = ImageEnhance.Color(im).enhance(1.05)
                                im = ImageEnhance.Sharpness(im).enhance(1.15)
                                im.save(yol)
                        except Exception:
                            pass
                    return True, f"OK model={mod} {olcek}x + keskinlestirme"
                son_hata = sonuc.stderr or sonuc.stdout or f"kod {sonuc.returncode}"
        else:
            son_hata = "realesrgan.exe yok — PIL yedek"

        for ad in os.listdir(kaynak_klasor):
            if not ad.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            src = os.path.join(kaynak_klasor, ad)
            dst = os.path.join(hedef_klasor, os.path.splitext(ad)[0] + ".png")
            try:
                _pil_kare_kalite_buyut(src, dst, olcek=olcek, min_kenar=720)
            except Exception:
                pass
        if any(f.lower().endswith(".png") for f in os.listdir(hedef_klasor)):
            return True, f"PIL kalite {olcek}x+ ({son_hata[:100]})"
        return False, son_hata or "Buyutme basarisiz"
    except Exception as e:
        return False, str(e)


def kare_dosyalarini_video_icin_sirala(klasor):
    """krita_kare_animasyon.py'daki ile AYNI dogal siralama mantigi -
    poz_2'den sonra poz_10 gelsin, poz_1'den sonra poz_10 DEGIL."""
    import re

    def dogal_anahtar(dosya_adi):
        return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", dosya_adi)]

    if not os.path.isdir(klasor):
        return []
    dosyalar = [f for f in os.listdir(klasor) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    return sorted(dosyalar, key=dogal_anahtar)


def kareleri_dogrula(kare_klasoru, dosyalar):
    """Video olusturmadan ONCE her kare dosyasinin GERCEKTEN acilabilir bir
    gorsel olup olmadigini kontrol eder. Bozuk/yaridan kalmis dosyalar
    (onceki bir test/kesinti sirasinda olusmus olabilir) ffmpeg'in
    'mjpeg decode hatasi' gibi anlasilmaz hatalar vermesine sebep oluyor -
    bunu ONCEDEN yakalayip HANGI dosyanin bozuk oldugunu soyluyoruz."""
    from PIL import Image
    gecerli, bozuk = [], []
    for dosya_adi in dosyalar:
        tam_yol = os.path.join(kare_klasoru, dosya_adi)
        try:
            with Image.open(tam_yol) as img:
                img.verify()
            gecerli.append(dosya_adi)
        except Exception:
            bozuk.append(dosya_adi)
    return gecerli, bozuk


def ffmpeg_ile_video_olustur(ffmpeg_yolu, kare_klasoru, cikti_video_yolu, kare_basina_sure_saniye):
    """
    Madde: 'ben son VIDEOYU gormek istiyorum'. Krita'nin kendi (daha once
    TUM PROGRAMI cokerten) animasyon zaman cizelgesi API'sini HIC
    KULLANMADAN, sadece siradaki PNG karelerini dogrudan ffmpeg ile bir
    MP4 videoya birlestirir. Bu yontem Krita'dan TAMAMEN BAGIMSIZDIR, bu
    yuzden onceki Krita cokmesi riskini SIFIRLAR - ffmpeg sadece resim
    dosyalarini okuyup video yaziyor, Krita'yi hic acmiyor/kullanmiyor.

    ffmpeg_yolu: kullanicinin AYRICA indirmesi gereken, ucretsiz/acik
    kaynak "ffmpeg.exe" (ffmpeg.org/download.html, Windows 'essentials'
    build yeterli). API/kart GEREKMEZ.

    Donus: (True, cikti_video_yolu) basarili, (False, hata_mesaji) basarisiz.
    Exception firlatmaz.
    """
    try:
        dosyalar = kare_dosyalarini_video_icin_sirala(kare_klasoru)
        if not dosyalar:
            return False, f"'{kare_klasoru}' klasorunde hic kare bulunamadi."

        dosyalar, bozuk_dosyalar = kareleri_dogrula(kare_klasoru, dosyalar)
        if bozuk_dosyalar:
            return False, (
                f"Su dosyalar BOZUK/GECERSIZ gorunuyor (acilamadi): {', '.join(bozuk_dosyalar)}\n\n"
                "Bunlar muhtemelen onceki bir test sirasinda yarim kalmis. 'Kare Klasorunu Ac' "
                "butonuyla klasoru ac, bu dosyalari sil (ya da tum klasoru temizleyip kareleri "
                "yeniden uret), sonra tekrar dene."
            )
        if not dosyalar:
            return False, "Dogrulama sonrasi gecerli hic kare kalmadi."

        os.makedirs(os.path.dirname(cikti_video_yolu), exist_ok=True)

        # GUVENILIR YONTEM: ffmpeg'in "concat" demuxer'i bazi PNG'lerde
        # yanlislikla mjpeg kod cozucusu secip anlamsiz hatalar verebiliyor
        # (bilinen bir tuhaflik). Onun yerine ffmpeg'in COK DAHA STANDART/
        # SAGLAM yontemini kullaniyoruz: kareleri GECICI bir klasore
        # BOSLUKSUZ/SIRALI numaralarla kopyalayip, klasik "image2 + -r"
        # (giris hizi) yontemiyle video olusturuyoruz.
        import tempfile
        gecici_klasor = tempfile.mkdtemp(prefix="video_kareler_")
        try:
            for i, dosya_adi in enumerate(dosyalar, start=1):
                kaynak = os.path.join(kare_klasoru, dosya_adi)
                hedef = os.path.join(gecici_klasor, f"kare_{i:05d}.png")
                shutil.copy(kaynak, hedef)

            giris_fps = (1.0 / kare_basina_sure_saniye) if kare_basina_sure_saniye > 0 else STANDART_ANIMASYON_FPS
            girdi_deseni = os.path.join(gecici_klasor, "kare_%05d.png")

            komut = [
                ffmpeg_yolu, "-y",
                "-r", f"{giris_fps:.4f}",
                "-i", girdi_deseni,
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=white,"
                "unsharp=5:5:1.0:3:3:0.5",
                "-c:v", "libx264",
                "-crf", "16",
                "-preset", "medium",
                "-r", str(STANDART_ANIMASYON_FPS),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                cikti_video_yolu,
            ]
            sonuc = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=600, **sessiz_subprocess_ayarlari())

            if sonuc.returncode != 0:
                hata_metni = sonuc.stderr or sonuc.stdout or f"Bilinmeyen hata (kod {sonuc.returncode})"
                return False, hata_metni
            return True, cikti_video_yolu
        finally:
            shutil.rmtree(gecici_klasor, ignore_errors=True)
    except FileNotFoundError:
        return False, f"ffmpeg.exe bulunamadi: {ffmpeg_yolu}"
    except Exception as e:
        return False, str(e)


def kritarunner_komutunu_olustur(kritarunner_yolu, script_yolu):
    """kritarunner ile Krita'yi HIC ACMADAN (headless) script calistiran
    komutu olusturur. Gercek argüman formati Krita surumune gore
    degisebilir - resmi dokumantasyon: 'kritarunner --script <dosya>'."""
    return [kritarunner_yolu, "--script", script_yolu]


# ============================================================================
# COKLU PANEL BOLME (madde 1) - tek Gemini gorselinden N kare cikarma
# ============================================================================

# TAHMINI deger - Gemini gorsel modelinin tipik cikti karesi boyutu (piksel).
GEMINI_CIKTI_TAHMINI_PIKSEL = 1024

# Real-ESRGAN (realesrgan-x4plus-anime) pratik taban:
# - 10px → teknik olarak buyur ama YUZ/EL ERIR, ise yaramaz
# - ~128px → 4x buyutunce ~512px; anime karakter HALA okunur
# Bu tabanla 1024lik Gemini gorseline ~8x8=64 panel SIĞAR (teorik).
BUYUTME_MIN_PANEL_PIKSEL = 128

# PixAI tek gorselde guvenli panel (49 cok pahali / kotu cikar)
PIXAI_MAX_PANEL_TEK_GORSEL = 9

# Eski ad (plan yazilarinda kullanildi)
STANDART_KALITE_MIN_PANEL_PIKSEL = BUYUTME_MIN_PANEL_PIKSEL


def maksimum_kare_basina_gorsel(cikti_piksel=GEMINI_CIKTI_TAHMINI_PIKSEL,
                                 min_panel_piksel=None):
    """
    Tek PixAI/Gemini gorseline kac panel sigsin?
    Eskiden 49 idi → yanlislikla 3 parca x 49 = kredi yakimi.
    Short/defter icin tek gorselde max 9 (3x3).
    """
    return PIXAI_MAX_PANEL_TEK_GORSEL


def hikayeden_sure_ve_panel_hesapla(metin, manuel_sure=None):
    """
    Sure + keyframe. Cok panel istenirse Gemini paketlerine bolunur
    (max ~49/gorsel); kalan DEVAM ET ile gelir. Bol+RealESRGAN kaliteyi toparlar.
    Bos hikayede 3sn'ye dusmesin — Short varsayilan ~20sn / en az 9 panel.
    """
    metin = (metin or "").strip()
    kelime = len(metin.split()) if metin else 0
    # Eskiden bos → 3.0sn oluyordu (Metni Topla "3" gibi duruyordu); Short icin 20.
    tahmin = max(20.0, kelime / 2.2) if kelime else 20.0
    beat = 0
    for ch in ".!?…\n":
        beat += metin.count(ch)
    beat = max(1, beat)

    try:
        sure = float(manuel_sure) if manuel_sure is not None and float(manuel_sure) > 0 else tahmin
    except (TypeError, ValueError):
        sure = tahmin

    paket = maksimum_kare_basina_gorsel()
    # Short: akici beat; uzun surede daha fazla keyframe
    if sure <= 25:
        panel = max(9, min(paket, int(round(sure * 0.45))))  # 20sn → ~9
    else:
        panel = max(9, min(paket * 3, int(round(sure / 1.2))))
        if 2 <= beat <= paket * 3:
            panel = max(panel, min(beat, paket * 3))
    return round(sure, 1), int(panel), round(tahmin, 1)


def kare_gruplarina_bol(toplam_benzersiz_sayisi, grup_boyutu):
    """Toplam benzersiz kare sayisini, her biri en fazla grup_boyutu kadar
    olan ardisik gruplara (parcalara) boler. Her grup AYRI bir Gemini
    gorseli/istegi olacak. Ornek: 20 kare, grup_boyutu=9 -> [9, 9, 2]."""
    gruplar = []
    kalan = max(toplam_benzersiz_sayisi, 0)
    while kalan > 0:
        boyut = min(grup_boyutu, kalan)
        gruplar.append(boyut)
        kalan -= boyut
    return gruplar or [0]


def kare_sayisindan_izgara_hesapla(kare_sayisi):
    """N kareyi, mumkun oldugunca kareye/dikdortgene yakin bir satir x sutun
    izgarasina otomatik yerlestirir (orn: 5 -> 2x3, 15 -> 4x4, 20 -> 5x4).
    Boylece hem yer/limit tasarrufu (tek gorselde cok kare) hem de her
    panelin cozunurlugunun cok kucuk kalmamasi (asiri genis/uzun tek satir
    yerine) dengelenir."""
    if kare_sayisi <= 0:
        return 1, 1
    sutun = math.ceil(math.sqrt(kare_sayisi))
    satir = math.ceil(kare_sayisi / sutun)
    return satir, sutun


# Madde 5: 'rakamlar ve panelin siyah cercevesi gitmemis'. Gemini panellerin
# kosesine numara, aralarina da ayirici cizgi ciziyor (biz bunu istedik ki
# Gemini kareleri karistirmasin) - ama bu numaralar/cizgiler KARAKTERIN
# kendisine ait degil, o yuzden her paneli kestikten SONRA kenarlardan bir
# pay kirpip bunlari GORUNMEZ hale getiriyoruz.
#
# ONEMLI DUZELTME: numara SADECE SOL-UST kosede oldugu icin, kirpma da
# ASIMETRIK olmali - ust ve soldan DAHA FAZLA, alt ve sagdan SADECE ince
# ayirici cizgiyi temizleyecek kadar AZ kirpiyoruz. Eskiden TUM kenarlardan
# esit kirpiyorduk, bu da ALTTAN AYAKLARI kesiyordu - artik duzeldi.
# Eski yontem ust/soldan %11 kesiyordu → kafa/ahoge gidiyordu.
# Yeni: ince ayirici + sol-ust numarayi BOYAYARAK temizle (kirpma yok).
PANEL_UST_KIRPMA_ORANI = 0.012
PANEL_SOL_KIRPMA_ORANI = 0.012
PANEL_ALT_KIRPMA_ORANI = 0.012
PANEL_SAG_KIRPMA_ORANI = 0.012


def gorseli_izgaraya_bol(dosya_yolu, satir, sutun,
                          ust_kirpma=PANEL_UST_KIRPMA_ORANI, sol_kirpma=PANEL_SOL_KIRPMA_ORANI,
                          alt_kirpma=PANEL_ALT_KIRPMA_ORANI, sag_kirpma=PANEL_SAG_KIRPMA_ORANI):
    """Izgarayi soldan saga / yukaridan asagiya boler (= sira 1..N).
    Numara SIRALAMA icin PixAI'de istenir; burada boyanarak silinir (videoda gozukmez)."""
    from PIL import Image, ImageDraw
    img = Image.open(dosya_yolu).convert("RGBA")
    genislik, yukseklik = img.size
    parca_genislik = genislik // sutun
    parca_yukseklik = yukseklik // satir
    parcalar = []
    for r in range(satir):
        for c in range(sutun):
            sol = c * parca_genislik
            ust = r * parca_yukseklik
            sag = genislik if c == sutun - 1 else sol + parca_genislik
            alt = yukseklik if r == satir - 1 else ust + parca_yukseklik

            genislik_pay = sag - sol
            yukseklik_pay = alt - ust
            ic_sol = sol + int(genislik_pay * sol_kirpma)
            ic_ust = ust + int(yukseklik_pay * ust_kirpma)
            ic_sag = sag - int(genislik_pay * sag_kirpma)
            ic_alt = alt - int(yukseklik_pay * alt_kirpma)

            parca = img.crop((ic_sol, ic_ust, ic_sag, ic_alt)).convert("RGB")
            # Numara sil — cevre rengi (beyaz leke yok)
            w, h = parca.size
            nw, nh = max(10, int(w * 0.13)), max(10, int(h * 0.11))
            sx0, sy0 = min(w - 2, nw), min(h - 2, nh)
            patch = parca.crop((sx0, sy0, min(w, sx0 + 12), min(h, sy0 + 12)))
            pix = list(patch.getdata())
            if pix:
                fill = tuple(sum(p[i] for p in pix) // len(pix) for i in range(3))
            else:
                fill = (40, 50, 60)
            ImageDraw.Draw(parca).rectangle([0, 0, nw, nh], fill=fill)
            m = max(1, int(min(w, h) * 0.008))
            parcalar.append(parca.crop((m, m, w - m, h - m)).convert("RGBA"))
    return parcalar


def _karakter_bbox(im: "Image.Image", esik: int = 245):
    """Beyaza yakin zeminden karakter kutusunu bul."""
    from PIL import Image
    rgb = im.convert("RGB")
    w, h = rgb.size
    pix = rgb.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = pix[x, y]
            if r < esik or g < esik or b < esik:
                # cok koyu/gri de karakter olabilir; sadece saf beyaza yakin olanlari at
                if not (r > esik - 8 and g > esik - 8 and b > esik - 8):
                    xs.append(x)
                    ys.append(y)
    if not xs:
        return (0, 0, w, h)
    pad = max(2, int(min(w, h) * 0.02))
    return (
        max(0, min(xs) - pad),
        max(0, min(ys) - pad),
        min(w, max(xs) + pad),
        min(h, max(ys) + pad),
    )


def kareleri_hizala(parcalar, hedef_w: int = 768, hedef_h: int = 1280):
    """
    Kaymayi azalt: her paneldeki karakteri ayni olcek + ayni merkezde yerlestir
    (defter sayfasi flipbook icin stabil kadraj).
    """
    from PIL import Image
    if not parcalar:
        return []
    # Ortak hedef olcek: bbox'larin medyan yuksekligi
    yukseklikler = []
    bboxes = []
    for im in parcalar:
        bb = _karakter_bbox(im)
        bboxes.append(bb)
        yukseklikler.append(max(1, bb[3] - bb[1]))
    yukseklikler.sort()
    medyan_h = yukseklikler[len(yukseklikler) // 2]
    hedef_karakter_h = int(hedef_h * 0.82)

    out = []
    for im, bb in zip(parcalar, bboxes):
        x0, y0, x1, y1 = bb
        crop = im.convert("RGBA").crop((x0, y0, x1, y1))
        cw, ch = crop.size
        scale = hedef_karakter_h / max(1, ch)
        # asiri buyume siniri
        scale = min(scale, 6.0)
        nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
        resized = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (hedef_w, hedef_h), (255, 255, 255, 255))
        ox = (hedef_w - nw) // 2
        # ayaklari alta yasla (kayma azalir) — ustte kafa payi
        oy = hedef_h - nh - int(hedef_h * 0.04)
        oy = max(int(hedef_h * 0.06), oy)
        canvas.paste(resized, (ox, oy), resized if resized.mode == "RGBA" else None)
        out.append(canvas)
    return out


def guvenli_png_kaydet(im, yol: str, deneme: int = 5) -> None:
    """Windows kilit / Invalid argument icin temp+replace."""
    import tempfile
    import time
    yol = os.path.abspath(yol)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    son_hata = None
    for i in range(deneme):
        try:
            fd, tmp = tempfile.mkstemp(suffix=".png", dir=os.path.dirname(yol))
            os.close(fd)
            im.save(tmp, format="PNG")
            # kilitli eski dosyayi kaldir
            if os.path.exists(yol):
                try:
                    os.remove(yol)
                except OSError:
                    time.sleep(0.25)
                    os.remove(yol)
            os.replace(tmp, yol)
            return
        except OSError as e:
            son_hata = e
            time.sleep(0.35 * (i + 1))
            try:
                if "tmp" in locals() and os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    # son care: alternatif ad
    alt = yol.replace(".png", f"_{int(time.time())}.png")
    im.save(alt, format="PNG")
    raise OSError(f"Kayit basarisiz ({yol}): {son_hata}. Yedek: {alt}")


def gemini_uretim_planini_olustur(benzersiz_sayisi, toplam_kare_sayisi):
    """Kullaniciya ızgara (numarali) veya flipbook plani."""
    if FLIPBOOK_MODU:
        if benzersiz_sayisi <= 1:
            return (
                "FLIPBOOK: 1 defter sayfasi (tek tam gorsel).\n"
                "Tensor/NovelAI'de TEK kare uret → indir → 6) Ekle. Izgara YOK."
            )
        return (
            f"FLIPBOOK: {benzersiz_sayisi} AYRI defter sayfasi.\n"
            "Tensor/NovelAI'de her seferinde 1 sayfa (9:16). High Priority KAPALI."
        )
    maks = maksimum_kare_basina_gorsel()
    px = GEMINI_CIKTI_TAHMINI_PIKSEL // max(1, int(math.ceil(math.sqrt(min(benzersiz_sayisi, maks)))))
    if benzersiz_sayisi <= 1:
        return "Plan: 1 poz. Indir → 6) Ekle."
    if benzersiz_sayisi <= maks:
        satir, sutun = kare_sayisindan_izgara_hesapla(benzersiz_sayisi)
        return (
            f"IZGARA (kota): TEK gorsel → {satir}x{sutun} = {benzersiz_sayisi} panel, "
            f"sol-ust NUMARA 1..{benzersiz_sayisi} (sira icin).\n"
            "Her panel = 1 defter sayfasi (flipbook film). Stil promptta METIN.\n"
            "Uygulama: kes → numarayi sil → hizala → buyut → flipbook video.\n"
            f"Kesince ~{px}px/panel; buyutme kaliteyi kurtarir."
        )
    gruplar = kare_gruplarina_bol(benzersiz_sayisi, maks)
    satirlar = []
    for i, g in enumerate(gruplar, start=1):
        s, c = kare_sayisindan_izgara_hesapla(g)
        satirlar.append(f"  Parca {i}/{len(gruplar)}: {s}x{c}={g} panel")
    return (
        f"IZGARA: {benzersiz_sayisi} kare → {len(gruplar)} gorsel (max {maks}/gorsel).\n"
        "1) Metni Al → PixAI → indir → 6) Ekle\n"
        "2) DEVAM ET → tekrar...\n"
        + "\n".join(satirlar)
    )


# ============================================================================
# ANA PANEL
# ============================================================================
class KritaStudioPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan — Ana Panel (Krita)")
        self.pencere.geometry("780x720")
        self.pencere.minsize(640, 520)
        self.pencere.resizable(True, True)

        self.ayarlar = arac_yollarini_otomatik_doldur(ayarlari_yukle())
        self._karakterler = []  # [{"ad":..., "yol":...}, ...]
        self._stil_referans_yolu = None
        self._kare_plani_kuyrugu = queue.Queue()
        self._kare_uretim_kuyrugu = queue.Queue()
        self._krita_kuyrugu = queue.Queue()
        self._coklu_api_kuyrugu = queue.Queue()
        self._onay_event = threading.Event()
        self._onay_sonucu = None  # True=devam et, False=iptal
        self._tek_tus_modu = False
        self._pro_pipeline = None
        self._poz_karakter_yolu = None
        self._poz_stil_yolu = None
        self._aktif_kadrosu = "zombie"
        self._cizim_motoru = "tensor"
        self._defter_sayfalari = []
        self._defter_sayfa_i = 0

        self._arayuzu_kur()
        self._kare_plani_kuyrugunu_dinle()
        self._kare_uretim_kuyrugunu_dinle()
        self._krita_kuyrugunu_dinle()
        self._coklu_api_kuyrugunu_dinle()

        # Madde: 'her actigimda bu sayfa geliyo, kaldigim yerden devam etsin'
        if self.ayarlar.get("son_aciklama"):
            self.log_yaz("Onceki oturumdaki aciklama/sure otomatik dolduruldu - "
                         "yeni bir sey yazmak icin ustune yazabilirsin.")
        # Varsayilan: zombie kalip yollari hazir (yoksa sessizce gec)
        try:
            self._zombie_kizi_kilitle(sessiz=True)
        except Exception:
            pass

    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        """Tek ekran: kullanicinin anlattigi ANA PANEL. Eski cift bolumler yok."""
        ana = tk.Frame(self.pencere)
        ana.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(ana, text="Canavar Asistan — Ana Panel (Defter)", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(
            ana,
            text="Seri video: hikaye → tek sayfa prompt → Tensor/NovelAI (1 kredi=1 kare) → Ekle → Krita. Grid YOK.",
            font=("Segoe UI", 8), fg="#555555", wraplength=740, justify="left"
        ).pack(anchor="w", pady=(2, 4))

        motor_satir = tk.Frame(ana)
        motor_satir.pack(fill="x", pady=(0, 4))
        tk.Button(
            motor_satir, text="Zombie Kiz Kilitle", command=self._zombie_kizi_kilitle,
            bg="#2E7D32", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=5
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            motor_satir, text="Mini Short Yukle", command=self._mini_zombie_short_yukle,
            bg="#558B2F", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=5
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            motor_satir, text="Kalpli Opucuk 10syf", command=self._kalp_opucuk_short_yukle,
            bg="#C2185B", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=5
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            motor_satir, text="AKI+REN", command=self._kanal_ilk_videoyu_yukle,
            bg="#6A1B9A", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=5
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            motor_satir, text="Motor: Tensor", command=lambda: self._cizim_motor_sec("tensor"),
            bg="#1565C0", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=6, pady=5
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            motor_satir, text="Motor: NovelAI", command=lambda: self._cizim_motor_sec("novelai"),
            bg="#4527A0", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=6, pady=5
        ).pack(side="left", padx=(0, 4))
        self.motor_etiketi = tk.Label(
            motor_satir, text="Motor: Tensor + Flanime | Kadro: Zombie",
            font=("Segoe UI", 8), fg="#1565C0"
        )
        self.motor_etiketi.pack(side="left", padx=(8, 0))

        tk.Button(
            ana, text="20sn Test (eski AKI+REN)", command=self._yirmi_sn_test_hazirla,
            bg="#EF6C00", fg="white", font=("Segoe UI", 8), relief="flat", padx=8, pady=3
        ).pack(anchor="w", pady=(0, 6))

        # --- Görünen tek yuzey ---
        basit = tk.LabelFrame(
            ana, text="Senin akisin (defter sayfa sayfa)",
            font=("Segoe UI", 10, "bold"), bg="#E8F5E9", fg="#1B5E20", padx=8, pady=8
        )
        basit.pack(fill="x", pady=(0, 8))
        self._basit_cerceve = basit

        satir1 = tk.Frame(basit, bg="#E8F5E9")
        satir1.pack(fill="x", pady=(0, 4))
        self.btn_karakter = tk.Button(
            satir1, text="1) Karakter", command=self._hizli_karakter_sec,
            bg="#43A047", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=6
        )
        self.btn_karakter.pack(side="left", padx=(0, 6))
        self.hizli_karakter_etiketi = tk.Label(
            satir1, text="(secilmedi)", font=("Segoe UI", 8), bg="#E8F5E9", fg="#555"
        )
        self.hizli_karakter_etiketi.pack(side="left", padx=(0, 12))
        self.btn_stil = tk.Button(
            satir1, text="2) Stil (→metin)", command=self._hizli_stil_sec,
            bg="#AD1457", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=6
        )
        self.btn_stil.pack(side="left", padx=(0, 6))
        self.hizli_stil_etiketi = tk.Label(
            satir1, text="(kanal tarzi - opsiyonel)", font=("Segoe UI", 8), bg="#E8F5E9", fg="#555"
        )
        self.hizli_stil_etiketi.pack(side="left")

        satir_sure = tk.Frame(basit, bg="#E8F5E9")
        satir_sure.pack(fill="x", pady=(2, 4))
        tk.Label(satir_sure, text="Video suresi (sn):", font=("Segoe UI", 8, "bold"),
                 bg="#E8F5E9", fg="#1B5E20").pack(side="left")
        self.basit_sure_kutusu = tk.Entry(satir_sure, width=6, font=("Segoe UI", 9))
        self.basit_sure_kutusu.insert(0, self.ayarlar.get("son_sure") or "20")
        self.basit_sure_kutusu.pack(side="left", padx=(4, 6))
        self.basit_sure_kutusu.bind("<KeyRelease>", self._basit_sureyi_aktar)
        tk.Button(
            satir_sure, text="20sn", command=self._sureyi_20_yap,
            bg="#FFB74D", fg="#E65100", font=("Segoe UI", 8, "bold"), relief="flat", padx=6
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            satir_sure, text="Hikayeden tahmin", command=self._sureyi_hikayeden_tahmin_et,
            bg="#81C784", fg="#1B5E20", font=("Segoe UI", 8, "bold"), relief="flat", padx=6
        ).pack(side="left", padx=(0, 8))
        self.gemini_plan_etiketi = tk.Label(
            satir_sure, text="", font=("Segoe UI", 8), bg="#E8F5E9", fg="#2E7D32",
            wraplength=420, justify="left"
        )
        self.gemini_plan_etiketi.pack(side="left", fill="x", expand=True)
        # Sure kutusuna elle yazinca True olur; yoksa hikaye uzunlugu otomatik
        self._sure_manuel_mi = False

        tk.Label(
            basit, text="3) Hikaye (Enter=yeni satir, Ctrl+Enter=Metni Topla):",
            font=("Segoe UI", 8, "bold"), bg="#E8F5E9", fg="#1B5E20"
        ).pack(anchor="w", pady=(4, 2))
        self.basit_hikaye_kutusu = tk.Text(basit, height=3, wrap="word", font=("Segoe UI", 9))
        self.basit_hikaye_kutusu.pack(fill="x", pady=(0, 4))
        if self.ayarlar.get("son_aciklama"):
            self.basit_hikaye_kutusu.insert("1.0", self.ayarlar["son_aciklama"])
        # Enter artik yanlislikla ustune eklemesin — sadece Ctrl+Enter toplar
        self.basit_hikaye_kutusu.bind("<Control-Return>", self._hikaye_enter_topla)
        self.basit_hikaye_kutusu.bind("<KeyRelease>", self._basit_hikayeyi_poz_a_aktar)
        self._gemini_icin_aciklama = None

        fiksir = tk.Frame(basit, bg="#E8F5E9")
        fiksir.pack(fill="x", pady=(0, 4))
        self.btn_hikaye_uret = tk.Button(
            fiksir, text="Hikaye Bul (3 Part Short)", command=self._uc_part_hikaye_uret,
            bg="#6A1B9A", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=4
        )
        self.btn_hikaye_uret.pack(side="left", padx=(0, 4))
        self.btn_ornek_video = tk.Button(
            fiksir, text="Ornek Video", command=self._ornek_video_sec,
            bg="#00838F", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=4
        )
        self.btn_ornek_video.pack(side="left", padx=(0, 4))
        self.ornek_video_etiketi = tk.Label(
            fiksir, text="(ornek video yok)", font=("Segoe UI", 8), bg="#E8F5E9", fg="#555"
        )
        self.ornek_video_etiketi.pack(side="left")
        self._video_ornek_yolu = None
        self._video_ref_kareler = []
        self._shorts_partlar = None

        tk.Label(
            basit, text="Ornek videoya benzer ama su farklar olsun:",
            font=("Segoe UI", 8), bg="#E8F5E9", fg="#00695C"
        ).pack(anchor="w")
        self.video_fark_kutusu = tk.Text(basit, height=2, wrap="word", font=("Segoe UI", 8), bg="#E0F7FA")
        self.video_fark_kutusu.pack(fill="x", pady=(0, 4))

        metin_satir = tk.Frame(basit, bg="#E8F5E9")
        metin_satir.pack(fill="x", pady=(0, 4))
        self.btn_metin_topla = tk.Button(
            metin_satir, text="Metni Topla (ustune yaz)", command=self._hikaye_metnini_topla,
            bg="#1565C0", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=4
        )
        self.btn_metin_topla.pack(side="left", padx=(0, 4))
        self.btn_sohbet_temizle = tk.Button(
            metin_satir, text="Alt Chat Temizle", command=self._sohbeti_temizle,
            bg="#78909C", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=4
        )
        self.btn_sohbet_temizle.pack(side="left", padx=(0, 4))
        self.btn_rehber = tk.Button(
            metin_satir, text="Test Rehberi", command=self._test_rehberi_goster,
            bg="#5D4037", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", padx=8, pady=4
        )
        self.btn_rehber.pack(side="left", padx=(0, 4))
        # API pahali — bilinçli gizli/ikincil
        self.btn_programda_ciz = tk.Button(
            metin_satir, text="API (pahali)", command=self._tek_tus_videomu_yap,
            bg="#BDBDBD", fg="#424242", font=("Segoe UI", 8), relief="flat", padx=6, pady=4
        )
        self.btn_programda_ciz.pack(side="left")
        tk.Label(
            basit, text="Ana yol: Metni Al + Resimleri Al → web Gemini. Sag tik = Rias (gunluge yazmaz).",
            font=("Segoe UI", 8), bg="#E8F5E9", fg="#AD1457"
        ).pack(anchor="w", pady=(0, 4))

        self.gemini_chat_kutusu = tk.Text(basit, height=4, wrap="word", font=("Consolas", 8), bg="#F1F8E9")
        self.gemini_chat_kutusu.pack(fill="x", pady=(0, 4))

        kopya = tk.Frame(basit, bg="#E8F5E9")
        kopya.pack(fill="x", pady=(0, 4))
        self.btn_metin_al = tk.Button(
            kopya, text="4) Sayfa Prompt Al", command=self._basit_metni_kopyala,
            bg="#00897B", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6
        )
        self.btn_metin_al.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_resim_al = tk.Button(
            kopya, text="5) Ref Resimleri Al", command=self._basit_resimleri_kopyala,
            bg="#6A1B9A", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6
        )
        self.btn_resim_al.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_gemini = tk.Button(
            kopya, text="Site Ac", command=self._cizim_sitesini_ac,
            bg="#37474F", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6
        )
        self.btn_gemini.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_devam_et = tk.Button(
            kopya, text="SONRAKI SAYFA", command=self._devam_et_parcayi_kopyala,
            bg="#FF6F00", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6
        )
        self.btn_devam_et.pack(side="left", expand=True, fill="x")
        self._parca_etiketi = tk.Label(
            basit,
            text="DEFTER: her kredi = 1 tam sayfa. Metni Topla → Sayfa Prompt Al → Tensor → indir → 6) Ekle → SONRAKI SAYFA.",
            font=("Segoe UI", 8), bg="#E8F5E9", fg="#E65100", wraplength=700, justify="left"
        )
        self._parca_etiketi.pack(anchor="w", pady=(2, 4))
        self._buyutme_aktif_degiskeni = tk.BooleanVar(value=True)
        tk.Checkbutton(
            basit,
            text="Kesince Real-ESRGAN ile buyut (grid artik yok; tek sayfada da opsiyonel)",
            variable=self._buyutme_aktif_degiskeni,
            bg="#E8F5E9", fg="#1B5E20", font=("Segoe UI", 8, "bold"),
            activebackground="#E8F5E9", selectcolor="#C8E6C9"
        ).pack(anchor="w", pady=(0, 4))

        adimlar = tk.Frame(basit, bg="#E8F5E9")
        adimlar.pack(fill="x", pady=(0, 2))
        self.btn_cikti_ekle = tk.Button(
            adimlar, text="6) Indirilen Sayfayi Ekle",
            command=self._basit_cikti_ekle,
            bg="#2E7D32", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=8
        )
        self.btn_cikti_ekle.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_krita = tk.Button(
            adimlar, text="7) Krita Video",
            command=self._krita_baslat,
            bg="#00695C", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=8
        )
        self.btn_krita.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_ae = tk.Button(
            adimlar, text="8) AE Panel",
            command=self._ae_panelini_ac,
            bg="#E53935", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=8
        )
        self.btn_ae.pack(side="left", expand=True, fill="x")

        # Onizleme
        onizleme = tk.Frame(ana)
        onizleme.pack(fill="x", pady=(0, 6))
        self.onizleme_etiketi = tk.Label(onizleme, text="(henuz cikti yok)", font=("Segoe UI", 8), fg="#777777")
        self.onizleme_etiketi.pack(anchor="w")
        self._onizleme_resmi = None
        self._son_proje_adi = None
        self._son_video_yolu = None
        self.video_oynat_butonu = modern_buton(
            onizleme, "Videoyu Oynat", self._videoyu_oynat, RENK_MOR,
            font=("Segoe UI", 9, "bold"), height=1, state="disabled"
        )
        self.video_oynat_butonu.pack(anchor="w", pady=(4, 0))

        self.krita_ilerleme_cubugu = ttk.Progressbar(ana, mode="indeterminate")

        ayar = tk.Frame(ana, bg=RENK_BG_AYAR, highlightbackground="#455A64", highlightthickness=1)
        ayar.pack(fill="x", pady=(0, 6))
        modern_buton(ayar, "Gemini API", self._gemini_anahtarini_duzenle, RENK_KOYU,
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        modern_buton(ayar, "Krita Yolu", self._krita_yolunu_duzenle, RENK_KOYU,
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        modern_buton(ayar, "FFmpeg", self._ffmpeg_yolunu_duzenle, RENK_KOYU,
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        modern_buton(ayar, "Buyutme AI", self._realesrgan_yolunu_duzenle, "#1565C0",
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        modern_buton(ayar, "Kare Klasoru", lambda: self._klasoru_ac(KARE_KLASORU), RENK_KOYU,
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        modern_buton(ayar, "Cikti", lambda: self._klasoru_ac(CIKTI_KLASORU), RENK_KOYU,
                     font=("Segoe UI", 8), height=1).pack(side="left", padx=4, pady=4)
        tk.Label(ana, text="Gunluk:", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
        self.log_kutusu = scrolledtext.ScrolledText(
            ana, height=9, bg=RENK_LOG_BG, fg=RENK_LOG_FG, font=("Consolas", 9)
        )
        self.log_kutusu.pack(fill="both", expand=True)
        self.log_kutusu.configure(state="disabled")

        # --- Gizli: eski kodlarin bekledigi widget'lar (ekranda GOSTERILMEZ) ---
        gizli = tk.Frame(ana)
        # pack edilmez
        self._gizli_cerceve = gizli

        self.karakter_listesi_kutusu = tk.Listbox(gizli, height=1)
        self.stil_referans_etiketi = tk.Label(gizli, text="")
        self.hikaye_kutusu = tk.Text(gizli, height=1)
        self.uret_butonu = tk.Button(gizli, text="uret")
        self.ilerleme_cubugu = ttk.Progressbar(gizli, mode="determinate", maximum=100, value=0)
        self.coklu_api_butonu = tk.Button(gizli, text="api")
        # _buyutme_aktif_degiskeni Ana Panel checkbox'ta (varsayilan True)
        if not hasattr(self, "_buyutme_aktif_degiskeni"):
            self._buyutme_aktif_degiskeni = tk.BooleanVar(value=True)
        self.buyutme_olcek_kutusu = tk.Spinbox(gizli, values=(2, 3, 4), width=3)
        try:
            self.buyutme_olcek_kutusu.delete(0, "end")
            self.buyutme_olcek_kutusu.insert(0, "4")
        except Exception:
            pass
        self.krita_butonu = tk.Button(gizli, text="Krita'da Animasyonu Kur (arka planda)")
        self.tek_tus_butonu = tk.Button(gizli, text="API", command=self._tek_tus_videomu_yap)
        self.pro_manuel_butonu = tk.Button(gizli, text="pro", command=self._pro_manuel_devam)
        self._tam_pro_modu = tk.BooleanVar(value=False)
        self._gelismis_arayuz_degiskeni = tk.BooleanVar(value=False)
        self._gelismis_goster_degiskeni = tk.BooleanVar(value=False)
        self._gelismis_cerceve = tk.Frame(gizli)

        self.poz_aciklama_kutusu = tk.Text(gizli, height=2, wrap="word")
        if self.ayarlar.get("son_aciklama"):
            self.poz_aciklama_kutusu.insert("1.0", self.ayarlar["son_aciklama"])
        self.poz_sure_kutusu = tk.Entry(gizli, width=6)
        self.poz_sure_kutusu.insert(0, self.ayarlar.get("son_sure") or "20")
        self.poz_kare_sayisi_kutusu = tk.Spinbox(gizli, from_=1, to=2000, width=5)
        self.poz_benzersiz_kutusu = tk.Spinbox(gizli, from_=0, to=100, width=5)
        self.poz_benzersiz_kutusu.delete(0, "end")
        # Sabit 6 YOK — hikaye/sureye gore otomatik (asagida doldurulur)
        self.poz_benzersiz_kutusu.insert(0, "0")
        self.poz_tekrar_kutusu = tk.Entry(gizli, width=5)
        self.poz_hesap_etiketi = tk.Label(gizli, text="")
        self.poz_prompt_kutusu = tk.Text(gizli, height=4, wrap="word")
        self.poz_karakter_etiketi = tk.Label(gizli, text="Karakter: (secilmedi)")
        self.poz_stil_etiketi = tk.Label(gizli, text="Stil: (yok)")
        self.poz_karakter_secim_kutusu = ttk.Combobox(gizli, width=14, state="readonly", values=[])
        self.poz_animasyon_secim_kutusu = ttk.Combobox(
            gizli, width=16, state="readonly", values=ANIMASYON_TURLERI
        )
        self.poz_animasyon_secim_kutusu.current(0)

        self._gelismis_poz_otomatik_satiri = tk.Frame(gizli)
        self._gelismis_poz_dongu_satiri = tk.Frame(gizli)
        self._gelismis_poz_tekrar_satiri = tk.Frame(gizli)
        self._sira_dogrula_degiskeni = tk.BooleanVar(value=True)
        self._gelismis_sira_dogrula_kutusu = tk.Checkbutton(
            gizli, variable=self._sira_dogrula_degiskeni
        )
        self._gelismis_erken_bitir_butonu = tk.Button(gizli, command=self._poz_erken_bitir)
        self._gelismis_kutuphane_butonu = tk.Button(gizli, command=self._kutuphaneden_yukle)
        self._karakter_cercevesi = gizli
        self._stil_cercevesi = gizli
        self._poz_cercevesi = gizli
        self._gelismis_arayuz_checkbox = tk.Label(gizli)

        self._poz_karakter_yolu = getattr(self, "_poz_karakter_yolu", None)
        self._poz_stil_yolu = getattr(self, "_poz_stil_yolu", None)
        self._poz_parca_gruplari = None
        self._poz_parca_indeksi = 0
        self._poz_toplanan_benzersiz = []
        self._poz_beklenen_kare_sayisi = None
        self._poz_beklenen_benzersiz_sayisi = None
        self._son_uretilen_kare_sayisi = None
        self._son_uretilen_benzersiz_sayisi = None
        self._son_kare_basina_sure = 1.0 / STANDART_ANIMASYON_FPS

        self._rias_yardim_bagla()
        self._hikaye_sure_panel_otomatik(zorla_sure=not self._sure_manuel_mi)
        self._basit_sureyi_aktar()
        self._poz_hesaplamayi_guncelle()
        self._gemini_plan_etiketini_guncelle()
        ff = (self.ayarlar.get("ffmpeg_yolu") or "").strip()
        if ff and os.path.exists(ff):
            self.log_yaz(f"FFmpeg hazir: {ff}")
        else:
            self.log_yaz("[UYARI] FFmpeg bulunamadi — alttan FFmpeg sec.")
        kr = (self.ayarlar.get("kritarunner_yolu") or "").strip()
        if kr and os.path.exists(kr):
            self.log_yaz(f"Krita runner hazir: {kr}")

        self._maskot = None
        self._maskot_metin_alindi = False
        self._maskot_resim_alindi = False


    def log_yaz(self, mesaj):
        self.log_kutusu.configure(state="normal")
        self.log_kutusu.insert("end", mesaj + "\n")
        self.log_kutusu.see("end")
        self.log_kutusu.configure(state="disabled")

    def _klasoru_ac(self, yol):
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

    def _karakter_ekle(self):
        yol = filedialog.askopenfilename(title="Karakterin fotosunu/gorselini sec",
                                          filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")])
        if not yol:
            return
        varsayilan_isim = os.path.splitext(os.path.basename(yol))[0]
        isim = simpledialog.askstring("Karakter Adi", "Bu karakterin adi ne olsun?",
                                       initialvalue=varsayilan_isim, parent=self.pencere)
        if not isim or not isim.strip():
            return
        self._karakterler.append({"ad": isim.strip(), "yol": yol})
        self.karakter_listesi_kutusu.insert("end", f"{isim.strip()} ({os.path.basename(yol)})")
        self._poz_karakter_secim_kutusunu_guncelle()

    def _karakter_sil(self):
        secim = self.karakter_listesi_kutusu.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once listeden bir karakter sec.")
            return
        indeks = secim[0]
        self.karakter_listesi_kutusu.delete(indeks)
        del self._karakterler[indeks]
        self._poz_karakter_secim_kutusunu_guncelle()

    def _poz_hesaplamayi_guncelle(self, event=None):
        """
        Madde: 'ayni gorsel yuzlerce kez kopyalanip yer kaplamasin' + '15
        saniyede dongu cok hizli/titrek tekrarlamasin' sorunlarinin ORTAK
        cozumu. Kullanici SADECE sureyi ve (istersen) benzersiz kare sayisini
        yazar - programm SU HESABI yapar:

        - Donga YOKSA (benzersiz=0): eskisi gibi, sure*FPS kadar TAM FARKLI
          kare gerekir (kullanici zaten hepsinin farkli olmasini istemis).
        - Dongu VARSA (benzersiz>0): binlerce kopya dosya URETMEK YERINE,
          dogal bir hizda (varsayilan ~0.12sn/kare) kac kez tekrar etmesi
          gerektigini hesaplar, TOPLAM DOSYA SAYISINI KUCUK TUTAR (orn. 9x4=36,
          360 DEGIL), kalan sureyi ise 'her kare ekranda ne kadar dursun'
          (kare_basina_sure_saniye) ile doldurur - Krita/AE tarafinda bu
          deger kullanilir, boylece ayni sonuc suresi ELDE EDILIR ama disk
          sismez VE dogal/yavas gorunur.
        """
        try:
            sure = float(self.poz_sure_kutusu.get().replace(",", ".").strip())
        except ValueError:
            sure = 0
        try:
            benzersiz = int(self.poz_benzersiz_kutusu.get())
        except (ValueError, AttributeError):
            benzersiz = 0

        if benzersiz <= 0:
            # Dongu yok - eskisi gibi, her kare farkli, standart FPS'te.
            kare_sayisi = max(1, round(sure * STANDART_ANIMASYON_FPS)) if sure > 0 else 1
            self._son_kare_basina_sure = 1.0 / STANDART_ANIMASYON_FPS
            self.poz_kare_sayisi_kutusu.delete(0, "end")
            self.poz_kare_sayisi_kutusu.insert(0, str(kare_sayisi))
            if kare_sayisi <= 1:
                self.poz_hesap_etiketi.config(text="-> tek poz (kare gerekmez)", fg="#1B5E20")
            else:
                self.poz_hesap_etiketi.config(
                    text=f"-> {kare_sayisi} TAMAMEN FARKLI kare uretilecek (dongu yok, FPS "
                         f"{STANDART_ANIMASYON_FPS} standart). Cok fazlaysa 'Benzersiz' alanina "
                         "kucuk bir sayi yazip donguye gecebilirsin - yer/emek tasarrufu olur.",
                    fg="#1B5E20"
                )
            return

        # --- Dongu VAR: tekrar sayisini hesapla/oku ---
        DOGAL_KARE_TUTMA_SANIYE = 0.12  # tipik, dogal gorunen bir kare tutma suresi
        tekrar_metni = self.poz_tekrar_kutusu.get().strip()
        if tekrar_metni:
            try:
                tekrar = max(1, int(tekrar_metni))
            except ValueError:
                tekrar = None
        else:
            tekrar = None

        if tekrar is None:
            onerilen_tekrar = max(1, round(sure / (benzersiz * DOGAL_KARE_TUTMA_SANIYE))) if sure > 0 else 1
            tekrar = onerilen_tekrar
            oto_mu = True
        else:
            oto_mu = False

        toplam_gorunen_kare = benzersiz * tekrar
        kare_basina_sure = (sure / toplam_gorunen_kare) if (sure > 0 and toplam_gorunen_kare > 0) \
            else DOGAL_KARE_TUTMA_SANIYE

        self._son_kare_basina_sure = kare_basina_sure
        self.poz_kare_sayisi_kutusu.delete(0, "end")
        self.poz_kare_sayisi_kutusu.insert(0, str(toplam_gorunen_kare))

        uyari = ""
        renk = "#1B5E20"
        if kare_basina_sure < 0.05:
            uyari = " UYARI: bu cok hizli/titrek gorunebilir - 'Dongu kac kez tekrarlansin' alanina " \
                    "DAHA KUCUK bir sayi yaz (ya da sureyi kisalt)."
            renk = "#B71C1C"
        elif kare_basina_sure > 1.2:
            uyari = " UYARI: bu cok yavas/donuk gorunebilir - 'Dongu kac kez tekrarlansin' alanina " \
                    "DAHA BUYUK bir sayi yaz (ya da sureyi uzat)."
            renk = "#B71C1C"

        oto_notu = "(otomatik onerildi)" if oto_mu else "(sen belirledin)"
        self.poz_hesap_etiketi.config(
            text=(f"-> {benzersiz} benzersiz kare x {tekrar} tekrar {oto_notu} = SADECE "
                  f"{toplam_gorunen_kare} dosya uretilecek (360 degil!). Her kare ekranda "
                  f"~{kare_basina_sure:.3f} saniye kalacak, toplam ~{sure:.1f}sn eder.{uyari}"),
            fg=renk
        )
        self._gemini_plan_etiketini_guncelle()

    def _poz_aciklama_al(self):
        try:
            # Metni Topla sonrasi: Gemini'ye POZ listesi gitsin (yol hikayesi degil)
            temiz = getattr(self, "_gemini_icin_aciklama", None)
            if temiz:
                return temiz.strip()
            if hasattr(self, "basit_hikaye_kutusu"):
                basit = self.basit_hikaye_kutusu.get("1.0", "end-1c").strip()
                if basit:
                    return basit
            return self.poz_aciklama_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            return ""

    def _gemini_plan_etiketini_guncelle(self, event=None):
        try:
            try:
                sure = float(self.poz_sure_kutusu.get().replace(",", ".").strip())
            except ValueError:
                sure = 0
            kare_sayisi = int(self.poz_kare_sayisi_kutusu.get())
            benzersiz = self._benzersiz_sayisini_al(kare_sayisi)
            if hasattr(self, "gemini_plan_etiketi"):
                baslik = (
                    f"Video ~{sure:.1f}sn oynar | {benzersiz} keyframe panel "
                    f"(sabit 6 degil — hikaye/sureye gore).\n"
                )
                self.gemini_plan_etiketi.config(
                    text=baslik + gemini_uretim_planini_olustur(benzersiz, kare_sayisi)
                )
        except Exception:
            pass

    def _panel_sayisini_sureye_gore_ayarla(self):
        """Benzersiz panel = sureye oranli (60sn → ~20 panel; 6'ya kilitli degil)."""
        try:
            sure = float(self.basit_sure_kutusu.get().replace(",", ".").strip())
        except (ValueError, AttributeError):
            sure = 20.0
        hikaye = self._poz_aciklama_al()
        _, panel, _ = hikayeden_sure_ve_panel_hesapla(hikaye, manuel_sure=sure)
        try:
            self.poz_benzersiz_kutusu.delete(0, "end")
            self.poz_benzersiz_kutusu.insert(0, str(panel))
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        return panel

    def _sureyi_hikayeden_tahmin_et(self):
        """Sure kutusunu hikaye uzunlugundan doldur (manuel kilidi acar)."""
        self._sure_manuel_mi = False
        self._hikaye_sure_panel_otomatik(zorla_sure=True)
        self._maskot_soyle(
            f"Sureyi hikayeden aldım~ Video ~{self.basit_sure_kutusu.get()}sn / "
            f"{self.poz_benzersiz_kutusu.get()} panel."
        )

    def _sureyi_20_yap(self):
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "20")
        self._basit_sureyi_aktar()
        self._maskot_soyle("20 sn test suresi — ~6-7 panel.", 50)


    def _motor_etiket_guncelle(self):
        motor = "Tensor + Flanime" if getattr(self, "_cizim_motoru", "tensor") == "tensor" else "NovelAI Precise Ref"
        kadro = "Zombie" if getattr(self, "_aktif_kadrosu", "zombie") == "zombie" else "AKI+REN"
        sayfa = ""
        if getattr(self, "_defter_sayfalari", None):
            sayfa = f" | Sayfa {self._defter_sayfa_i + 1}/{len(self._defter_sayfalari)}"
        try:
            self.motor_etiketi.config(text=f"Motor: {motor} | Kadro: {kadro}{sayfa}", fg="#1565C0")
        except Exception:
            pass

    def _cizim_motor_sec(self, motor):
        self._cizim_motoru = motor if motor in ("tensor", "novelai") else "tensor"
        self._motor_etiket_guncelle()
        self.log_yaz(f"Cizim motoru: {self._cizim_motoru}")

    def _cizim_sitesini_ac(self):
        import webbrowser
        url = CIZIM_SITE_TENSOR if self._cizim_motoru == "tensor" else CIZIM_SITE_NOVELAI
        webbrowser.open(url)
        self.log_yaz(f"Site acildi: {url}")

    def _zombie_kizi_kilitle(self, sessiz=False):
        kimlik = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "ZOMBIE_KIZ", "KIMLIK", "kimlik_aktif.png")
        stil = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "ZOMBIE_KIZ", "KIMLIK", "stil_ref.png")
        if not os.path.exists(kimlik):
            kimlik = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "ZOMBIE_KIZ", "KIMLIK", "kimlik_kalip.png")
        if not os.path.exists(kimlik):
            kimlik = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "ZOMBIE_KIZ", "begendi_SOLO_eniyi_aday.png")
        if not os.path.exists(kimlik):
            kimlik = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "ZOMBIE_KIZ", "kalip_temel_tshirt_shorts.png")
        if not os.path.exists(stil):
            stil = os.path.join(BASE_DIR, "assets", "KADRO", "OLABILIR", "STIL_KILIT_3", "01_zombie_okul_flat.png")
        if not os.path.exists(kimlik):
            if not sessiz:
                messagebox.showwarning("Eksik", f"Zombie kalip yok:\n{kimlik}")
            return
        self._aktif_kadrosu = "zombie"
        self._poz_karakter_yolu = kimlik
        self._karakterler = [{"ad": "ZOMBIE_KIZ", "yol": kimlik}]
        if hasattr(self, "hizli_karakter_etiketi"):
            self.hizli_karakter_etiketi.config(text="Zombie kiz (kalip)", fg="#2E7D32")
        if os.path.exists(stil):
            self._poz_stil_yolu = stil
            self._stil_referans_yolu = stil
            self._son_stil_metni = None
            if hasattr(self, "hizli_stil_etiketi"):
                self.hizli_stil_etiketi.config(text="Stil: zombie flat kilit", fg="#AD1457")
        self.ayarlar["kanal_kadro"] = {
            "kiz": "ZOMBIE_KIZ",
            "aki_yol": kimlik,
            "stil_yol": stil if os.path.exists(stil) else "",
            "motor": getattr(self, "_cizim_motoru", "tensor"),
            "mod": "defter_flipbook",
        }
        ayarlari_kaydet(self.ayarlar)
        self._motor_etiket_guncelle()
        if not sessiz:
            self.log_yaz("Zombie kiz kilitlendi.")
            messagebox.showinfo("Zombie kilitli", "kimlik_kalip + stil_ref hazir.\nMini Short veya hikaye yaz.")

    def _mini_zombie_short_yukle(self):
        yol = os.path.join(BASE_DIR, "karakterler", "MINI_ZOMBIE_SHORT.txt")
        if not os.path.exists(yol):
            messagebox.showwarning("Eksik", yol)
            return
        self._zombie_kizi_kilitle(sessiz=True)
        with open(yol, encoding="utf-8") as f:
            ham = f.read()
        hikaye = ham
        for etiket in ("--- HİKÂYE (kısa) ---", "--- HIKAYE (kisa) ---"):
            if etiket in ham:
                parca = ham.split(etiket, 1)[-1]
                hikaye = parca.split("--- İNGİLİZCE")[0].split("--- INGILIZCE")[0].strip()
                break
        pozlar = []
        if "--- İNGİLİZCE 6 PANEL ---" in ham:
            blok = ham.split("--- İNGİLİZCE 6 PANEL ---", 1)[1]
            for sep in ("--- STİL ---", "--- STIL ---"):
                if sep in blok:
                    blok = blok.split(sep)[0]
                    break
            for line in blok.splitlines():
                s = line.strip()
                if s and s[0].isdigit():
                    pozlar.append(s)
        self.basit_hikaye_kutusu.delete("1.0", "end")
        self.basit_hikaye_kutusu.insert("1.0", hikaye.strip() or ham[:800])
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "18")
        self._basit_sureyi_aktar()
        try:
            self.poz_benzersiz_kutusu.delete(0, "end")
            self.poz_benzersiz_kutusu.insert(0, str(max(6, len(pozlar) or 6)))
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        if pozlar:
            metin = "\n".join(pozlar)
            self._gemini_icin_aciklama = metin
            try:
                self.poz_aciklama_kutusu.delete("1.0", "end")
                self.poz_aciklama_kutusu.insert("1.0", metin)
            except Exception:
                pass
            self._defter_sayfalari = pozlar
            self._defter_sayfa_i = 0
            self._poz_prompt_olustur()
            try:
                panel_prompt = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
                self.gemini_chat_kutusu.delete("1.0", "end")
                self.gemini_chat_kutusu.insert("1.0", panel_prompt)
            except Exception:
                pass
        self._motor_etiket_guncelle()
        self.log_yaz("Mini zombie short yuklendi.")
        messagebox.showinfo(
            "Mini Short",
            "6 sayfa hazir. Site Ac -> Sayfa Prompt Al -> tek kare -> Ekle -> SONRAKI SAYFA",
        )


    def _kalp_opucuk_short_yukle(self):
        """Sabit sokak + yaya gecidi + kalpli opucuk defter (10 sayfa)."""
        yol = os.path.join(BASE_DIR, "karakterler", "YAPISTIR_KALP_10SAYFA.txt")
        hikaye_yol = os.path.join(BASE_DIR, "karakterler", "DEFTER_KALP_OPUCUK.txt")
        if not os.path.exists(yol):
            messagebox.showwarning("Eksik", yol)
            return
        self._zombie_kizi_kilitle(sessiz=True)
        self._cizim_motoru = "tensor"
        with open(hikaye_yol if os.path.exists(hikaye_yol) else yol, encoding="utf-8") as f:
            ham = f.read()
        # Turkce ozet hikaye
        hikaye = (
            "Kameraya YAKIN yaya gecidi. Kiz yolun SAGINDAN gelir, "
            "gecitte kalpli opucuk atar, gecip sola kaybolur. Derin koridor sokak YOK."
        )
        # Sayfa ACTION satirlarini topla
        pozlar = []
        for line in ham.splitlines():
            s = line.strip()
            if s.startswith("ACTION:"):
                pozlar.append(s.replace("ACTION:", "", 1).strip())
        if not pozlar and os.path.exists(yol):
            with open(yol, encoding="utf-8") as f:
                yp = f.read()
            # YAPISTIR dosyasindan sayfa basliklarina gore bol
            for i in range(1, 11):
                tag = f"========== SAYFA {i}"
                if tag in yp:
                    chunk = yp.split(tag, 1)[1]
                    chunk = chunk.split("==========", 1)[0].strip()
                    # DNA satiriyla basliyorsa ACTION kismi son satirlar
                    lines = [x.strip() for x in chunk.splitlines() if x.strip() and not x.strip().startswith("(")]
                    if lines:
                        pozlar.append(lines[-1] if lines[0].startswith("1girl") or "DNA" in lines[0] else " ".join(lines[-2:]))
        if not pozlar:
            # sabit 10 action (yedek)
            pozlar = [
                "RIGHT side of road walking toward near crosswalk, approach from right",
                "closer from RIGHT walking toward near zebra crosswalk",
                "stepping onto near zebra crosswalk from the right",
                "CENTER on near crosswalk facing camera pause",
                "near crosswalk hand to mouth prepare kiss",
                "near crosswalk blowing kiss flat pink heart toward camera",
                "walk LEFT from crosswalk center heart drifts closer",
                "leave crosswalk toward LEFT side of frame",
                "smaller walking LEFT away along road",
                "exit LEFT frame edge fading silhouette lonely end",
            ]
        self.basit_hikaye_kutusu.delete("1.0", "end")
        self.basit_hikaye_kutusu.insert("1.0", hikaye)
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "14")
        self._basit_sureyi_aktar()
        try:
            self.poz_benzersiz_kutusu.delete(0, "end")
            self.poz_benzersiz_kutusu.insert(0, str(len(pozlar)))
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        metin = "\n".join(f"{i+1}) {p}" for i, p in enumerate(pozlar))
        self._gemini_icin_aciklama = metin
        try:
            self.poz_aciklama_kutusu.delete("1.0", "end")
            self.poz_aciklama_kutusu.insert("1.0", metin)
        except Exception:
            pass
        self._defter_sayfalari = [f"{i+1}) {p}" for i, p in enumerate(pozlar)]
        self._defter_sayfa_i = 0
        self._aktif_kadrosu = "zombie"
        self._poz_prompt_olustur()
        try:
            panel_prompt = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
            self.gemini_chat_kutusu.delete("1.0", "end")
            self.gemini_chat_kutusu.insert("1.0", panel_prompt)
        except Exception:
            pass
        self._motor_etiket_guncelle()
        # AE notlarini birlestir
        try:
            fx = os.path.join(BASE_DIR, "karakterler", "AE_KALP_OPUCUK_FX.txt")
            if os.path.exists(fx):
                with open(fx, encoding="utf-8") as f:
                    fx_metin = f.read()
                ae = os.path.join(BASE_DIR, "ae_edit_notes.txt")
                with open(ae, "w", encoding="utf-8") as f:
                    f.write("=== KALP OPUCUK SHORT — AE FX ===\n\n" + fx_metin)
        except Exception as e:
            self.log_yaz(f"[UYARI] AE not: {e}")
        self.log_yaz("Kalpli opucuk 10 sayfa hazir (FlatIron + sabit bg).")
        messagebox.showinfo(
            "Kalpli Opucuk",
            f"{len(pozlar)} sayfa hazir.\n\n"
            "1) Site Ac (Tensor) + FlatIron\n"
            "2) Ref: kimlik_aktif.png | IP 0.2-0.3\n"
            "3) Sayfa Prompt Al → TEK kare\n"
            "4) Indirilen Sayfayi Ekle → SONRAKI SAYFA\n\n"
            "Detay: karakterler/YAPISTIR_KALP_10SAYFA.txt\n"
            "AE FX: ae_edit_notes.txt",
        )

    def _kanal_ilk_videoyu_yukle(self):
        """AKI/REN ref + stil kilitle."""
        self._aktif_kadrosu = "aki_ren"
        aki = os.path.join(BASE_DIR, "assets", "aki_karakter_ref.png")
        ren = os.path.join(BASE_DIR, "assets", "ren_karakter_ref.png")
        stil = os.path.join(BASE_DIR, "video_stil_ref", "kanallar", "dangoheart_02.png")
        if not os.path.exists(stil):
            stil = os.path.join(BASE_DIR, "video_stil_ref", "stil_kare_01.png")
        if not os.path.exists(aki):
            messagebox.showwarning("Eksik", f"AKI ref yok:\n{aki}")
            return
        self._poz_karakter_yolu = aki
        self._karakterler = [
            {"ad": "AKI", "yol": aki},
            {"ad": "REN", "yol": ren if os.path.exists(ren) else aki},
        ]
        if hasattr(self, "hizli_karakter_etiketi"):
            self.hizli_karakter_etiketi.config(text="AKI + REN (kilitli)", fg="#6A1B9A")
        if hasattr(self, "poz_karakter_etiketi"):
            self.poz_karakter_etiketi.config(text="Karakter: AKI (+REN)")
        if hasattr(self, "karakter_listesi_kutusu"):
            try:
                self.karakter_listesi_kutusu.delete(0, "end")
                for k in self._karakterler:
                    self.karakter_listesi_kutusu.insert(
                        "end", f"{k['ad']} ({os.path.basename(k['yol'])})"
                    )
            except Exception:
                pass
        if os.path.exists(stil):
            self._poz_stil_yolu = stil
            self._stil_referans_yolu = stil
            self._son_stil_metni = None
            if hasattr(self, "hizli_stil_etiketi"):
                self.hizli_stil_etiketi.config(
                    text="Stil: Dangoheart/Ganzouomo", fg="#AD1457"
                )
        try:
            mevcut = self.basit_hikaye_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            mevcut = ""
        if not mevcut or mevcut.startswith("(Hikaye sonra"):
            self.basit_hikaye_kutusu.delete("1.0", "end")
            self.basit_hikaye_kutusu.insert("1.0", KANAL_HIKAYE_YER_TUTUCU)
        self._sure_manuel_mi = True
        if not (self.basit_sure_kutusu.get() or "").strip():
            self.basit_sure_kutusu.delete(0, "end")
            self.basit_sure_kutusu.insert(0, "22")
        self._basit_sureyi_aktar()
        try:
            bz = (self.poz_benzersiz_kutusu.get() or "").strip()
            if not bz or bz in ("0", "3"):
                self.poz_benzersiz_kutusu.delete(0, "end")
                self.poz_benzersiz_kutusu.insert(0, "9")
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        self._basit_hikayeyi_poz_a_aktar()
        self.ayarlar["kanal_kadro"] = {
            "kiz": "AKI",
            "erkek": "REN",
            "aki_yol": aki,
            "ren_yol": ren if os.path.exists(ren) else "",
            "stil_yol": stil if os.path.exists(stil) else "",
            "stil_not": "Dangoheart + Ganzouomo (+SeanWay basitlik)",
            "hikaye": "sonra",
        }
        ayarlari_kaydet(self.ayarlar)
        self._gemini_plan_etiketini_guncelle()
        self.log_yaz(
            "Kadro kilitlendi: AKI + REN (begendigin ref) + indie stil. "
            "Hikaye sonra — yazinca Metni Topla."
        )
        self._maskot_soyle("Kadro hazir~ Hikaye gelince yazariz!", 70)
        messagebox.showinfo(
            "Kadro kilitli",
            "AKI + REN begendigin halleriyle kilitlendi.\n"
            "Stil: Dangoheart / Ganzouomo.\n\n"
            "Hikaye yok — sonra yazarsin.\n"
            "Hazir olunca hikaye kutusuna yaz → Metni Topla."
        )

    def _aki_ren_20sn_test_yukle(self):
        """Kadro + 20sn detayli test hikayesi (kanal tarzi Short)."""
        self._kanal_ilk_videoyu_yukle()
        self.basit_hikaye_kutusu.delete("1.0", "end")
        self.basit_hikaye_kutusu.insert("1.0", TEST_HIKAYE_AKI_REN_20SN)
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "20")
        self._basit_sureyi_aktar()
        try:
            self.poz_benzersiz_kutusu.delete(0, "end")
            self.poz_benzersiz_kutusu.insert(0, "9")
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        self._basit_hikayeyi_poz_a_aktar()
        self.ayarlar["son_aciklama"] = TEST_HIKAYE_AKI_REN_20SN
        self.ayarlar["son_sure"] = "20"
        ayarlari_kaydet(self.ayarlar)
        self._gemini_plan_etiketini_guncelle()
        self.log_yaz("20sn AKI+REN test hikayesi yuklendi — Metni Topla otomatik basliyor...")
        self._maskot_soyle("Metin hazirlaniyor~ Biraz bekle!", 50)
        # Kullanici karismasin: dogrudan PixAI metnini uret
        self.pencere.after(200, self._hikaye_metnini_topla)

    def _yirmi_sn_test_hazirla(self):
        """Ucuz yol icin 20sn hazir paket + rehber penceresi."""
        self.basit_hikaye_kutusu.delete("1.0", "end")
        self.basit_hikaye_kutusu.insert("1.0", TEST_HIKAYE_20SN)
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "20")
        self._basit_sureyi_aktar()
        self._basit_hikayeyi_poz_a_aktar()
        try:
            with open(AE_EDIT_NOTES_YOLU, "w", encoding="utf-8") as f:
                f.write(
                    "=== 20SN TEST — AE NOTLARI ===\n"
                    "- Muzik: hafif lo-fi / anime BGM, ses dusuk tut\n"
                    "- Timing: her beat ~2.5-3sn\n"
                    "- Istersen sonunda kucuk 'like' yazisi\n"
                    "- Kirpma/sira Ana Panelde zaten yapildi; burada sarki+gecis\n"
                )
        except Exception:
            pass
        self._maskot_soyle("20sn test hazir~ Rehberi oku, karakter sec!", 60)
        self._test_rehberi_goster()

    def _test_rehberi_goster(self):
        win = tk.Toplevel(self.pencere)
        win.title("20sn Test Rehberi — kopyala-yapistir")
        win.geometry("560x520")
        win.attributes("-topmost", True)
        tk.Label(
            win, text="Simdi ne yapacaksin (ucuz yol)",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=12, pady=(10, 4))
        kutu = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 9), height=22)
        kutu.pack(fill="both", expand=True, padx=12, pady=6)
        kutu.insert("1.0", TEST_REHBERI_20SN)
        kutu.configure(state="disabled")
        tk.Button(
            win, text="Tamam — basliyorum", command=win.destroy,
            bg="#EF6C00", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=6
        ).pack(pady=(0, 12))

    def _hikaye_sure_panel_otomatik(self, zorla_sure=False):
        """Hikaye yazildikca sure + panel sayisini guncelle."""
        hikaye = self._poz_aciklama_al()
        manuel = None
        if self._sure_manuel_mi and not zorla_sure:
            try:
                manuel = float(self.basit_sure_kutusu.get().replace(",", ".").strip())
            except (ValueError, AttributeError):
                manuel = None
        sure, panel, tahmin = hikayeden_sure_ve_panel_hesapla(hikaye, manuel_sure=manuel)
        if (not self._sure_manuel_mi) or zorla_sure:
            if hasattr(self, "basit_sure_kutusu"):
                self.basit_sure_kutusu.delete(0, "end")
                self.basit_sure_kutusu.insert(0, str(sure))
            if hasattr(self, "poz_sure_kutusu"):
                self.poz_sure_kutusu.delete(0, "end")
                self.poz_sure_kutusu.insert(0, str(sure))
            self.ayarlar["son_sure"] = str(sure)
        try:
            self.poz_benzersiz_kutusu.delete(0, "end")
            self.poz_benzersiz_kutusu.insert(0, str(panel))
            # Her keyframe bir kez — sure panel tutma ile dolar (dosya sismesi yok)
            self.poz_tekrar_kutusu.delete(0, "end")
            self.poz_tekrar_kutusu.insert(0, "1")
        except Exception:
            pass
        self._poz_hesaplamayi_guncelle()
        self._gemini_plan_etiketini_guncelle()
        return sure, panel, tahmin

    def _rias_yardim_bagla(self):
        """Her ogeye sag tik → Rias ozellik + sira anlatsin (Clippy/gulp tarzi)."""
        self._rias_yardim = {
            id(self.btn_karakter): (1, 8, "Karakter",
                "Karakter fotonu sec. Gemini bu yuzu/kiyafeti koruyacak."),
            id(self.btn_stil): (2, 8, "Stil (metne cevrilir)",
                "Begendigin cizim tarzini sec. Metni Topla bunu DETAYLI yaziya cevirir — "
                "PixAI resmi kabul etmese bile stil promptta gider. Defter/flipbook da anlatilir."),
            id(self.basit_sure_kutusu): (None, None, "Video suresi",
                "Video BU kadar saniye oynar. Hikaye uzunsa burayi buyut veya 'Hikayeden tahmin'."),
            id(self.basit_hikaye_kutusu): (3, 8, "Hikaye",
                "Ne olacagini DETAYLI yaz. Enter / Metni Topla ile temizlenir."),
            id(self.btn_metin_topla): (3, 8, "Metni Topla",
                "Poz listesi + stil METNI + defter/flipbook anlatimi. Alt chat'e tek detayli prompt yazar."),
            id(self.btn_hikaye_uret): (3, 8, "Hikaye Bul",
                "3 part YouTube Short senaryosu uydurur + AE bolme notu yazar."),
            id(self.btn_ornek_video): (2, 8, "Ornek Video",
                "Begendigin videoyu okur; kare cikarir. Alta 'fakat su olsun' yaz."),
            id(self.video_fark_kutusu): (3, 8, "Fark notu",
                "Ornek videoya benzer ama degismesini istedigin seyler."),
            id(self.btn_programda_ciz): (None, None, "API (pahali)",
                "Atla. Biz ucuz kopyala-yapistir yolunu kullaniyoruz."),
            id(self.btn_rehber): (None, None, "Test Rehberi",
                "20sn ornek akisin madde madde listesi."),
            id(self.gemini_chat_kutusu): (4, 8, "Alt chat",
                "Gemini'ye yapistirilacak hazir metin burada durur."),
            id(self.btn_metin_al): (4, 8, "Metni Al",
                "Hazir promptu panoya kopyalar → Gemini'de Ctrl+V."),
            id(self.btn_resim_al): (5, 8, "Resimleri Al",
                "Once karakter, sonra stil fotonu panoya alir → Gemini'ye yapistir."),
            id(self.btn_gemini): (5, 8, "Gemini Ac",
                "gemini.google.com'u acar. Metin+resimleri oraya yapistir."),
            id(self.btn_devam_et): (None, None, "DEVAM ET",
                "Ilk gorsel geldikten sonra UNUTMA: buna bas → Gemini'ye yapistir (sonraki parca)."),
            id(self.btn_cikti_ekle): (6, 8, "Gemini Ciktisini Ekle",
                "Indirdigin coklu panel gorseli kesilir. Parca varsa sonra DEVAM ET."),
            id(self.btn_krita): (7, 8, "Krita Video",
                "Kareleri birlestirip kaba videoyu cikarir — sure kutusu kadar uzun."),
            id(self.btn_ae): (8, 8, "AE Panel",
                "Ses, timing, agiz + 3 part bolme notlari burada."),
            id(self.video_oynat_butonu): (None, None, "Videoyu Oynat",
                "Son uretilen kaba videoyu acar."),
        }
        widgets = [
            self.btn_karakter, self.btn_stil, self.basit_sure_kutusu,
            self.basit_hikaye_kutusu, self.btn_metin_topla, self.btn_rehber,
            self.btn_hikaye_uret, self.btn_ornek_video, self.video_fark_kutusu,
            self.btn_programda_ciz, self.gemini_chat_kutusu,
            self.btn_metin_al, self.btn_resim_al, self.btn_gemini, self.btn_devam_et,
            self.btn_cikti_ekle, self.btn_krita, self.btn_ae, self.video_oynat_butonu,
        ]
        for w in widgets:
            try:
                w.bind("<Button-3>", self._rias_sag_tik_event, add="+")
            except Exception:
                pass
        # plan etiketi
        try:
            self.gemini_plan_etiketi.bind("<Button-3>", self._rias_sag_tik_event, add="+")
            self._rias_yardim[id(self.gemini_plan_etiketi)] = (
                None, None, "Gemini plani",
                "Kac panel / kac gorsel lazim oldugu burada. Panel sayisi hikaye suresine gore degisir."
            )
        except Exception:
            pass

    def _rias_sag_tik_event(self, event):
        w = event.widget
        info = None
        cur = w
        for _ in range(6):
            if cur is None:
                break
            info = self._rias_yardim.get(id(cur))
            if info:
                break
            cur = getattr(cur, "master", None)
        if not info:
            self._maskot_soyle("Buna ozellik yazmadim ama akisin butonlarina sag tikla~")
            return "break"
        self._rias_anlat(*info)
        return "break"

    def _rias_anlat(self, sira, toplam, baslik, aciklama):
        if sira and toplam:
            metin = f"Adim {sira}/{toplam} — {baslik}: {aciklama}"
        else:
            metin = f"{baslik}: {aciklama}"
        # Gunluge YAZMA — sag tik spam olmasin; sadece Rias balonu
        self._maskot_soyle(metin, sure=100)

    def _maskot_soyle(self, metin, sure=80):
        if self._maskot is not None:
            try:
                self._maskot.ozellik_anlat(metin, sure=sure)
                return
            except Exception:
                pass
        # maskot kapalıysa sessiz kal (gunluk doldurma)

    def _hizli_karakter_sec(self):
        yol = filedialog.askopenfilename(
            title="Karakter fotografini sec",
            filetypes=[("Gorsel", "*.png *.jpg *.jpeg *.webp"), ("Tum", "*.*")]
        )
        if not yol:
            return
        self._poz_karakter_yolu = yol
        ad = os.path.splitext(os.path.basename(yol))[0]
        self.hizli_karakter_etiketi.config(text=f"Secildi: {os.path.basename(yol)}")
        if hasattr(self, "poz_karakter_etiketi"):
            self.poz_karakter_etiketi.config(text=f"Karakter: {os.path.basename(yol)}")
        if not any(k.get("yol") == yol for k in self._karakterler):
            self._karakterler.append({"ad": ad, "yol": yol})
            if hasattr(self, "karakter_listesi_kutusu"):
                self.karakter_listesi_kutusu.insert("end", f"{ad} ({os.path.basename(yol)})")
            self._poz_karakter_secim_kutusunu_guncelle()
        self._gemini_plan_etiketini_guncelle()
        self._maskot_adim_hatirlat()

    def _hizli_stil_sec(self):
        yol = filedialog.askopenfilename(
            title="Cizim tarzi / stil referansi (Metni Topla bunu METNE cevirir)",
            filetypes=[("Gorsel", "*.png *.jpg *.jpeg *.webp"), ("Tum", "*.*")]
        )
        if not yol:
            return
        self._poz_stil_yolu = yol
        self._stil_referans_yolu = yol
        self._son_stil_metni = None
        if hasattr(self, "hizli_stil_etiketi"):
            self.hizli_stil_etiketi.config(text=f"Stil: {os.path.basename(yol)}", fg="#AD1457")
        if hasattr(self, "poz_stil_etiketi"):
            self.poz_stil_etiketi.config(text=f"Stil: {os.path.basename(yol)}")
        if hasattr(self, "stil_referans_etiketi"):
            self.stil_referans_etiketi.config(
                text=f"Cizim tarzi benzesin: {os.path.basename(yol)}"
            )
        self.log_yaz(
            f"Stil secildi: {yol} — Metni Topla / prompt uretince bu resim "
            "DETAYLI METNE cevrilir (PixAI resmi kabul etmese bile stil yazi olarak gider)."
        )
        self._maskot_adim_hatirlat()

    def _basit_hikayeyi_poz_a_aktar(self, event=None):
        """Ust hikaye kutusunu asagidaki poz aciklamasiyla senkron tut."""
        try:
            # Kullanici hikayeyi degistirdi → eski POZ cevirisi gecersiz
            self._gemini_icin_aciklama = None
            if not hasattr(self, "basit_hikaye_kutusu") or not hasattr(self, "poz_aciklama_kutusu"):
                return
            metin = self.basit_hikaye_kutusu.get("1.0", "end-1c")
            self.poz_aciklama_kutusu.delete("1.0", "end")
            self.poz_aciklama_kutusu.insert("1.0", metin)
            self.ayarlar["son_aciklama"] = metin.strip()
            ayarlari_kaydet(self.ayarlar)
            self._hikaye_sure_panel_otomatik()
        except Exception:
            pass

    def _hikaye_enter_topla(self, event=None):
        """Ctrl+Enter: Metni Topla (ustune yazar, alta eklemez)."""
        self._hikaye_metnini_topla()
        return "break"

    def _sohbeti_temizle(self):
        if hasattr(self, "gemini_chat_kutusu"):
            self.gemini_chat_kutusu.delete("1.0", "end")
        self._gemini_icin_aciklama = None
        self._maskot_soyle("Alt chat temiz~ Yeniden Metni Topla.", 40)

    def _hikaye_metnini_topla(self):
        """Ham hikayeyi POZ listesine cevir; alt chat'i USTUNE YAZ (ekleme)."""
        # Ham hikaye kutusu (poz cevirisi degil)
        ham = ""
        try:
            ham = self.basit_hikaye_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            ham = ""
        if not ham:
            messagebox.showwarning("Eksik", "Once hikayeyi yaz veya 'Hikaye Bul' bas.")
            return
        fark = ""
        try:
            fark = self.video_fark_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            pass
        kaynak = ham
        if self._video_ornek_yolu or fark:
            ekstra = ["\n\n[REFERANS NOTU]"]
            if self._video_ornek_yolu:
                ekstra.append(
                    f"Ornek video ritmi: {os.path.basename(self._video_ornek_yolu)}."
                )
            if fark:
                ekstra.append("Farklar: " + fark)
            kaynak = ham + "\n".join(ekstra)
        self._basit_sureyi_aktar()
        try:
            panel_n = int(self.poz_benzersiz_kutusu.get())
        except Exception:
            panel_n = 4
        if panel_n <= 0:
            panel_n = 4
        api_key = self.ayarlar.get("gemini_api_anahtari", "").strip()
        self.log_yaz(
            f"Hikaye → {panel_n} FARKLI poz listesine cevriliyor "
            "(yurume kopyasi yok; opucuk varsa zorunlu)..."
        )

        def arka():
            metin, hata = gemini_ile_hikaye_temizle(api_key, kaynak, panel_sayisi=panel_n)
            self.pencere.after(0, lambda: self._hikaye_toplama_bitti(metin, hata, ham))

        threading.Thread(target=arka, daemon=True).start()

    def _uc_part_hikaye_uret(self):
        """3-part Shorts hikayesi — AE'de bol+kanca icin not yazar."""
        ipucu = self._poz_aciklama_al()
        try:
            fark = self.video_fark_kutusu.get("1.0", "end-1c").strip()
            if fark:
                ipucu = (ipucu + "\n" + fark).strip()
        except Exception:
            pass
        if not ipucu:
            ipucu = simpledialog.askstring(
                "Tema",
                "3 part short icin tema/ipucu (bos = rastgele):",
                parent=self.pencere,
            ) or ""
        api_key = self.ayarlar.get("gemini_api_anahtari", "").strip()
        self.log_yaz("3 part Shorts hikayesi uretiliyor...")
        self.btn_hikaye_uret.config(state="disabled")

        def arka():
            veri, hata = gemini_ile_uc_part_shorts_hikaye(api_key, ipucu)
            self.pencere.after(0, lambda: self._uc_part_hikaye_bitti(veri, hata))

        threading.Thread(target=arka, daemon=True).start()

    def _uc_part_hikaye_bitti(self, veri, hata):
        self.btn_hikaye_uret.config(state="normal")
        if hata and not veri:
            messagebox.showerror("Hikaye", hata)
            return
        self._shorts_partlar = veri
        birlesik = veri.get("birlesik", "")
        self.basit_hikaye_kutusu.delete("1.0", "end")
        self.basit_hikaye_kutusu.insert("1.0", birlesik)
        self._basit_hikayeyi_poz_a_aktar()
        # Sure: 3 part ~60sn hedef
        self._sure_manuel_mi = True
        self.basit_sure_kutusu.delete(0, "end")
        self.basit_sure_kutusu.insert(0, "60")
        self._basit_sureyi_aktar()
        try:
            with open(SHORTS_PARTLAR_YOLU, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
            ae_satirlar = [
                "=== 3 PART SHORTS — AE BOLME ===",
                veri.get("ae_notu", ""),
                "",
            ]
            for i, p in enumerate(veri.get("partlar") or [], start=1):
                ae_satirlar.append(f"--- {p.get('baslik', f'Part {i}')} ---")
                ae_satirlar.append(p.get("hikaye", ""))
                ae_satirlar.append(f"SON YAZI / KANCA: {p.get('kanca', '')}")
                ae_satirlar.append("")
            with open(AE_EDIT_NOTES_YOLU, "w", encoding="utf-8") as f:
                f.write("\n".join(ae_satirlar))
        except Exception as e:
            self.log_yaz(f"[UYARI] Part dosyasi yazilamadi: {e}")
        self.log_yaz("3 part hikaye hazir → shorts_3part.json + ae_edit_notes.txt")
        self._maskot_soyle("3 part hazir~ Sonunda AE'de boleriz, kancalar yazili!", 70)
        messagebox.showinfo(
            "3 Part Short",
            "Hikaye kutuya yazildi (~60sn hedef).\n"
            "AE notlari: ae_edit_notes.txt\n\n"
            "Sonraki: Metni Topla → Programda Ciz (API) veya manuel Gemini."
        )

    def _ornek_video_sec(self):
        """Begendigin short/videoyu sec — kare cikar + stil referansi."""
        yol = filedialog.askopenfilename(
            title="Ornek video (buna benzer olsun)",
            filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.avi"), ("Tum", "*.*")]
        )
        if not yol:
            return
        ffmpeg_yolu = self.ayarlar.get("ffmpeg_yolu", "").strip()
        if not ffmpeg_yolu or not os.path.exists(ffmpeg_yolu):
            messagebox.showwarning(
                "FFmpeg",
                "Ornek videodan kare almak icin alttan 'FFmpeg' yolunu sec."
            )
            return
        self.log_yaz(f"Ornek video okunuyor: {os.path.basename(yol)}")
        self.btn_ornek_video.config(state="disabled")

        def arka():
            yollar, hata = ffmpeg_videodan_kareler(ffmpeg_yolu, yol, VIDEO_REF_KLASORU, adet=4)
            self.pencere.after(0, lambda: self._ornek_video_bitti(yol, yollar, hata))

        threading.Thread(target=arka, daemon=True).start()

    def _ornek_video_bitti(self, video_yolu, kareler, hata):
        self.btn_ornek_video.config(state="normal")
        if hata or not kareler:
            messagebox.showerror("Video", hata or "Kare cikmadi")
            return
        self._video_ornek_yolu = video_yolu
        self._video_ref_kareler = kareler
        # Ortadaki kareyi stil referansi yap
        stil = kareler[len(kareler) // 2]
        self._poz_stil_yolu = stil
        self._stil_referans_yolu = stil
        if hasattr(self, "hizli_stil_etiketi"):
            self.hizli_stil_etiketi.config(
                text=f"Stil: video kare {os.path.basename(stil)}", fg="#00695C"
            )
        self.ornek_video_etiketi.config(
            text=f"{os.path.basename(video_yolu)} ({len(kareler)} kare)", fg="#00695C"
        )
        self.log_yaz(f"Ornek videodan {len(kareler)} kare → stil olarak kullanilacak.")
        self._maskot_soyle("Videoyu okudum~ Alta 'ama su olsun' yaz, sonra Metni Topla!", 70)

    def _hikaye_toplama_bitti(self, metin, hata, ham):
        if hata and not metin:
            try:
                panel_n = int(self.poz_benzersiz_kutusu.get())
            except Exception:
                panel_n = 4
            metin, _ = gemini_ile_hikaye_temizle("", ham, panel_sayisi=panel_n)
            self.log_yaz(f"[UYARI] API toparlama: {hata} — lokal poz listesi kullanildi.")
        if not metin:
            messagebox.showerror("Hata", hata or "Toparlanamadi")
            return
        # POZ listesini prompt kaynak olarak kilitle (yol hikayesini tekrar etme)
        self._gemini_icin_aciklama = metin.strip()
        self._defter_sayfalari = _poz_satirlarini_ayikla(metin)
        self._defter_sayfa_i = 0
        try:
            self.poz_aciklama_kutusu.delete("1.0", "end")
            self.poz_aciklama_kutusu.insert("1.0", metin)
        except Exception:
            pass
        self._hikaye_sure_panel_otomatik()
        self._poz_prompt_olustur()
        # TEK metin — alta ekleme / cift hikaye YOK (ustune yaz)
        panel_prompt = ""
        try:
            panel_prompt = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            pass
        if hasattr(self, "gemini_chat_kutusu"):
            self.gemini_chat_kutusu.delete("1.0", "end")
            self.gemini_chat_kutusu.insert("1.0", panel_prompt or metin)
        self.log_yaz(
            "Alt chat USTUNE YAZILDI: stil METIN + defter/flipbook anlatimi + pozlar. "
            "'Metni Al' → PixAI (resim stil zorunlu degil)."
        )
        self._parca_durumunu_guncelle()
        self._maskot_soyle("Prompt hazir~ Metni Al, sonra gerekirse DEVAM ET.", 55)
        self._maskot_adim_hatirlat()

    def _parca_durumunu_guncelle(self):
        """Parca bandini ve DEVAM ET butonunu guncelle."""
        try:
            if not hasattr(self, "_parca_etiketi"):
                return
            if self._poz_parca_gruplari:
                toplam = len(self._poz_parca_gruplari)
                no = min(self._poz_parca_indeksi + 1, toplam)
                self._parca_etiketi.config(
                    text=(
                        f"PARCA {no}/{toplam} — ilk gorsel gelince: 6) Ekle, "
                        f"SONRA turuncu DEVAM ET (unutma!)."
                    ),
                    fg="#BF360C"
                )
                self.btn_devam_et.config(bg="#FF6F00", state="normal")
            else:
                self._parca_etiketi.config(
                    text=(
                        f"Tek paket: max ~{maksimum_kare_basina_gorsel()} panel/gorsel. "
                        "Indir → 6) Ekle → (buyut aciksa) Real-ESRGAN. DEVAM gerekmez."
                    ),
                    fg="#E65100"
                )
        except Exception:
            pass

    def _devam_et_parcayi_kopyala(self):
        """Sonraki defter sayfasi veya eski grid parcasi."""
        if FLIPBOOK_MODU and getattr(self, "_defter_sayfalari", None):
            if self._defter_sayfa_i + 1 >= len(self._defter_sayfalari):
                messagebox.showinfo("Bitti", "Tum defter sayfalari bitti. Krita Video'ya gec.")
                return
            self._defter_sayfa_i += 1
            self._poz_prompt_olustur()
            metin = ""
            try:
                metin = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
            except Exception:
                pass
            if hasattr(self, "gemini_chat_kutusu"):
                self.gemini_chat_kutusu.delete("1.0", "end")
                self.gemini_chat_kutusu.insert("1.0", metin)
            self.pencere.clipboard_clear()
            self.pencere.clipboard_append(metin)
            self._motor_etiket_guncelle()
            no = self._defter_sayfa_i + 1
            toplam = len(self._defter_sayfalari)
            messagebox.showinfo(
                f"Sayfa {no}/{toplam}",
                "Panoda. Siteye yapistir -> TEK kare uret -> Indirilen Sayfayi Ekle.",
            )
            return
        if not self._poz_parca_gruplari:
            messagebox.showinfo(
                "DEVAM gerekmez",
                "Su an tek-parca is. Indirip 6) Ekle yeter.\n\n"
                "Cok parcali olursa bu buton parlar."
            )
            return
        if self._poz_parca_indeksi >= len(self._poz_parca_gruplari):
            messagebox.showinfo("Bitti", "Tum parcalar tamam — sadece kalan indirilenleri ekle.")
            return
        # Siradaki parca metnini uret + DEVAM onu ekle
        self._poz_prompt_olustur()
        govde = ""
        try:
            govde = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            pass
        if not govde:
            messagebox.showwarning("Bos", "Once Metni Topla.")
            return
        toplam = len(self._poz_parca_gruplari)
        no = self._poz_parca_indeksi + 1
        devam = (
            f"DEVAM ET — PARCA {no}/{toplam}.\n"
            "Ayni karakter, ayni stil, onceki panellerin DEVAMI.\n"
            "Onceki gorseldeki hareketin devamini ciz; tutarliligi bozma.\n\n"
        )
        metin = devam + govde
        if hasattr(self, "gemini_chat_kutusu"):
            self.gemini_chat_kutusu.delete("1.0", "end")
            self.gemini_chat_kutusu.insert("1.0", metin)
        self.pencere.clipboard_clear()
        self.pencere.clipboard_append(metin)
        self._parca_durumunu_guncelle()
        self._maskot_soyle(f"DEVAM ET hazir! Parca {no}/{toplam} → Gemini Ctrl+V", 80)
        messagebox.showinfo(
            f"DEVAM ET — Parca {no}/{toplam}",
            "Panoda.\n\n"
            "1) Gemini sohbetine Ctrl+V\n"
            "2) Gonder\n"
            "3) Gorseli indir\n"
            "4) 6) Gemini Ciktisini Ekle\n\n"
            "Kalan parca varsa yine DEVAM ET."
        )

    def _basit_metni_kopyala(self):
        metin = ""
        if hasattr(self, "gemini_chat_kutusu"):
            metin = self.gemini_chat_kutusu.get("1.0", "end-1c").strip()
        if not metin and hasattr(self, "poz_prompt_kutusu"):
            metin = self.poz_prompt_kutusu.get("1.0", "end-1c").strip()
        if not metin:
            self._hikaye_metnini_topla()
            messagebox.showinfo("Bekle", "Once 'Metni Topla' bilsin, sonra tekrar 'Metni Al'.")
            return
        self.pencere.clipboard_clear()
        self.pencere.clipboard_append(metin)
        self._maskot_metin_alindi = True
        self.log_yaz("Metin panoya kopyalandi.")
        self._maskot_adim_hatirlat()
        self._parca_durumunu_guncelle()
        if self._poz_parca_gruplari:
            toplam = len(self._poz_parca_gruplari)
            no = self._poz_parca_indeksi + 1
            messagebox.showinfo(
                f"PARCA {no}/{toplam} kopyalandi",
                "Gemini'ye Ctrl+V → gonder → gorseli INDIR → 6) Ciktisini Ekle.\n\n"
                "SONRA (unutma!): turuncu DEVAM ET butonuna bas — "
                "sonraki parca otomatik panoya gelir."
            )
            self._maskot_soyle(f"Parca {no}/{toplam} gitti~ Sonra DEVAM ET!", 70)
        else:
            messagebox.showinfo(
                "Metin panoda — Tensor/NovelAI",
                "1) Site Ac (Tensor veya NovelAI)\n"
                "2) Ref Resimleri Al (kimlik + stil)\n"
                "3) Ctrl+V ile BU sayfa promptunu yapistir\n"
                "4) TEK kare uret (grid/4-panel YASAK)\n"
                "5) Indir → 6) Indirilen Sayfayi Ekle\n"
                "6) SONRAKI SAYFA\n\n"
                "Model: Flanime Illustrious. Anti-AI negative prompt icinde."
            )

    def _basit_resimleri_kopyala(self):
        """Karakter panoya (opsiyonel). Stil artik prompt METNINDE — resim zorunlu degil."""
        if not self._poz_karakter_yolu:
            messagebox.showwarning("Eksik", "Once karakter resmi sec.")
            return
        self._gorseli_panoya_kopyala(self._poz_karakter_yolu)
        stil = self._poz_stil_yolu or getattr(self, "_stil_referans_yolu", None)
        if stil:
            messagebox.showinfo(
                "Stil metinde",
                "Karakter panoya kopyalandi (istersen yapistir).\n\n"
                "Stil artik Metni Topla / prompt icinde METIN olarak var — "
                "PixAI resmi kabul etmese bile stil gider.\n"
                "Istersen Tamam'dan sonra stil resmini de yapistirabilirsin."
            )
            self._gorseli_panoya_kopyala(stil)
            self.log_yaz("Stil panoya da alindi (opsiyonel). Asil stil prompt metninde.")
        else:
            self.log_yaz("Karakter panoya kopyalandi (stil secilmedi — prompt varsayilan stil metni).")
        self._maskot_resim_alindi = True
        self._maskot_adim_hatirlat()

    def _basit_cikti_ekle(self):
        """Gemini'den inen coklu panel gorselini kes + AI ile hikayeye gore sirala."""
        if not self._poz_aciklama_al():
            messagebox.showwarning("Eksik", "Once hikaye yaz (siralamaya yardimci olur).")
            return
        self._basit_hikayeyi_poz_a_aktar()
        if not self.poz_prompt_kutusu.get("1.0", "end-1c").strip():
            self._poz_hesaplamayi_guncelle()
            self._poz_prompt_olustur()
        self._sira_dogrula_degiskeni.set(True)
        self._tek_tus_modu = False
        self._poz_gorseli_ekle()

    def _tek_tus_videomu_yap(self):
        """Tek tus: kare uret -> kes -> video. PRO aciksa tam hat."""
        if not self._poz_karakter_yolu and not self._karakterler:
            messagebox.showwarning("Eksik", "Once ADIM 1: Karakter fotografini sec.")
            return
        if not self._poz_karakter_yolu and self._karakterler:
            self._poz_karakter_yolu = self._karakterler[0]["yol"]

        self._basit_hikayeyi_poz_a_aktar()
        aciklama = self._poz_aciklama_al()
        if not aciklama:
            messagebox.showwarning("Eksik", "ADIM 3: Hikayeyi DETAYLI yaz.")
            return

        self._poz_hesaplamayi_guncelle()
        self._poz_prompt_olustur()

        if self._tam_pro_modu.get():
            messagebox.showinfo(
                "Gelismis",
                "Tam otomasyon zinciri kaldirildi.\n\n"
                "Senin akis: Gemini ciktisi ekle → Krita Video → AE Panel."
            )
            return

        api_key = self.ayarlar.get("gemini_api_anahtari", "").strip()

        ffmpeg_yolu = self.ayarlar.get("ffmpeg_yolu", "").strip()

        if api_key:
            self._tek_tus_modu = True
            self.log_yaz("TEK TUS: API ile kareler uretiliyor, sonra otomatik video olusturulacak...")
            self._coklu_api_uretmeye_basla()
            return

        if not ffmpeg_yolu or not os.path.exists(ffmpeg_yolu):
            messagebox.showwarning(
                "FFmpeg gerekli",
                "Ucretsiz yol icin once 'FFmpeg Yolu Ayarla' butonundan ffmpeg.exe sec.\n\n"
                "Veya 'Gemini API Anahtari' girersen her sey otomatik olur."
            )
            return

        self._tek_tus_modu = True
        self._poz_prompt_kopyala()
        if self._poz_karakter_yolu:
            self._gorseli_panoya_kopyala(self._poz_karakter_yolu)
        self._gemini_web_ac()
        self._tek_tus_manuel_rehber_goster()

    def _pro_manuel_devam(self):
        """Eski PRO dugmesi — cikti ekleme ile ayni."""
        self._basit_cikti_ekle()

    def _tek_tus_manuel_rehber_goster(self):
        pencere = tk.Toplevel(self.pencere)
        pencere.title("Gemini Rehberi — Siradaki Adimlar")
        pencere.geometry("520x420")
        pencere.grab_set()

        plan = self.gemini_plan_etiketi.cget("text") if hasattr(self, "gemini_plan_etiketi") else ""
        tk.Label(pencere, text="Gemini'de yapman gerekenler:", font=("Segoe UI", 11, "bold")).pack(pady=(12, 6))
        tk.Label(pencere, text=plan, font=("Segoe UI", 9), wraplength=480, justify="left", fg="#1B5E20").pack(padx=12)

        adimlar = (
            "1) Prompt zaten panoya kopyalandi — gemini.google.com sohbetine YAPISTIR (Ctrl+V)\n"
            "2) Karakter fotografi da panoya kopyalandi — sohbete TEKRAR Ctrl+V yap\n"
            "3) Varsa stil gorselini de surukle-birak\n"
            "4) Gemini TEK GORSEL uretir (icinde kare kare paneller)\n"
            "5) Gorseli indir, asagidaki butona bas — uygulama keser ve VIDEONU yapar"
        )
        tk.Label(pencere, text=adimlar, font=("Segoe UI", 9), wraplength=480, justify="left").pack(padx=12, pady=8)

        def indirdim():
            pencere.destroy()
            self._poz_gorseli_ekle()

        tk.Button(
            pencere, text="Gemini'den Indirdim — Gorseli Ekle ve Videoyu Olustur",
            command=indirdim, bg="#FF6F00", fg="white", font=("Segoe UI", 10, "bold"), pady=8
        ).pack(fill="x", padx=12, pady=12)

    def _sadece_ffmpeg_video_olustur(self):
        """Krita/AE olmadan sadece karelerden MP4 uretir."""
        ffmpeg_yolu = self.ayarlar.get("ffmpeg_yolu", "").strip()
        if not ffmpeg_yolu or not os.path.exists(ffmpeg_yolu):
            messagebox.showwarning("FFmpeg eksik", "'FFmpeg Yolu Ayarla' ile ffmpeg.exe sec.")
            self._tek_tus_modu = False
            return

        kare_basina_sure = getattr(self, "_son_kare_basina_sure", None) or (1.0 / STANDART_ANIMASYON_FPS)
        from datetime import datetime
        proje_adi = f"tek_tus_{datetime.now():%Y%m%d_%H%M%S}"
        video_yolu = os.path.join(CIKTI_KLASORU, f"{proje_adi}.mp4")

        self.krita_ilerleme_cubugu.pack(fill="x", pady=(0, 4))
        self.krita_ilerleme_cubugu.start(12)
        self.tek_tus_butonu.config(state="disabled", text="VIDEO OLUSTURULUYOR...")
        self.ayarlar = arac_yollarini_otomatik_doldur(self.ayarlar)
        rs = self.ayarlar.get("realesrgan_yolu", "").strip()
        buyut = True
        if hasattr(self, "_buyutme_aktif_degiskeni"):
            buyut = bool(self._buyutme_aktif_degiskeni.get())
        self.log_yaz("Once kareler buyutuluyor, sonra ffmpeg video...")

        def arka_plan():
            kaynak = KARE_KLASORU
            if buyut:
                ok, _msg = kareleri_buyut(rs, KARE_KLASORU, BUYUTULMUS_KLASORU, olcek=4)
                if ok:
                    kaynak = BUYUTULMUS_KLASORU
            basarili, mesaj = ffmpeg_ile_video_olustur(
                ffmpeg_yolu, kaynak, video_yolu, kare_basina_sure
            )
            self._krita_kuyrugu.put(("TEK_TUS_VIDEO", basarili, mesaj, video_yolu))

        threading.Thread(target=arka_plan, daemon=True).start()

    def _tek_tus_video_sonucu_isle(self, basarili, mesaj, video_yolu):
        self.krita_ilerleme_cubugu.stop()
        self.krita_ilerleme_cubugu.pack_forget()
        self.tek_tus_butonu.config(state="normal", text="API ile otomatik uret (Gelismis)")
        self._tek_tus_modu = False

        if basarili:
            self._son_video_yolu = video_yolu
            self.video_oynat_butonu.config(state="normal")
            self.onizleme_etiketi.config(text=f"Video hazir: {os.path.basename(video_yolu)}")
            self.log_yaz(f"TEK TUS TAMAM: {video_yolu}")

            messagebox.showinfo("Video Hazir!", f"Videon olusturuldu:\n{video_yolu}\n\nSimdi '8) AE Panel' ile devam edebilirsin.")
        else:
            self.log_yaz(f"[HATA] Video olusturulamadi:\n{mesaj}")
            messagebox.showerror("Video Olusturulamadi", mesaj)

    def _basit_sureyi_aktar(self, event=None):
        try:
            if hasattr(self, "basit_sure_kutusu") and hasattr(self, "poz_sure_kutusu"):
                if event is not None:
                    self._sure_manuel_mi = True
                v = self.basit_sure_kutusu.get().strip()
                if v:
                    self.poz_sure_kutusu.delete(0, "end")
                    self.poz_sure_kutusu.insert(0, v)
                    self.ayarlar["son_sure"] = v
                    ayarlari_kaydet(self.ayarlar)
                    self._panel_sayisini_sureye_gore_ayarla()
                    self._poz_hesaplamayi_guncelle()
                    self._gemini_plan_etiketini_guncelle()
        except Exception:
            pass

    def _maskot_baslat(self):
        return

    def _maskot_toggle(self):
        return

    def _maskot_adim_hatirlat(self):
        return

    def _ae_panelini_ac(self):
        """AE Studio panelini ayri pencerede acar (ayni klasorden)."""
        script = os.path.join(BASE_DIR, "ae_studio_paneli.py")
        if not os.path.exists(script):
            messagebox.showerror("Bulunamadi", f"ae_studio_paneli.py yok:\n{script}")
            return
        try:
            subprocess.Popen([sys.executable, script], cwd=BASE_DIR)
            self.log_yaz("AE Studio paneli acildi.")
        except Exception as e:
            messagebox.showerror("Acilamadi", str(e))

    def _basit_gelismis_mod_guncelle(self):
        """Eski cift UI kaldirildi — bos birakildi (uyumluluk)."""
        return

    def _gelismis_bolumu_guncelle(self):
        """Eski ucretli bolum UI'da yok."""
        return

    def _poz_karakter_secildi(self, event=None):
        """Karakter acilir kutusundan bir isim secilince, o karakterin
        referans gorselini OTOMATIK olarak baglar - ayrica 'Karakter Gorseli
        Sec' butonuna basmaya gerek kalmaz (madde: manuel olmasin)."""
        ad = self.poz_karakter_secim_kutusu.get().strip()
        for k in self._karakterler:
            if k["ad"] == ad:
                self._poz_karakter_yolu = k["yol"]
                self.poz_karakter_etiketi.config(text=f"Karakter: {os.path.basename(k['yol'])} ({ad})")
                break

    def _poz_karakter_secim_kutusunu_guncelle(self):
        """Poz/Kare Uret bolumundeki 'Karakter' acilir kutusunu, Sahnedeki
        Karakterler listesiyle senkron tutar (madde: manuel yazim yerine
        secim ile otomatik doldurma)."""
        isimler = [k["ad"] for k in self._karakterler]
        self.poz_karakter_secim_kutusu["values"] = isimler
        if isimler and not self.poz_karakter_secim_kutusu.get():
            self.poz_karakter_secim_kutusu.current(0)

    def _poz_aciklamayi_otomatik_doldur(self):
        """Madde: 'ne cizilsin' alanini MANUEL yazmak yerine, secili karakter +
        animasyon turunden OTOMATIK olarak (ae_studio_paneli.py ile ayni
        kelime dagarcigiyla) uretir."""
        karakter_adi = self.poz_karakter_secim_kutusu.get().strip()
        if not karakter_adi:
            messagebox.showwarning("Eksik", "Once yukarida 'Sahnedeki Karakterler' bolumunden en az bir "
                                             "karakter ekle, sonra buradan sec.")
            return
        animasyon_turu = self.poz_animasyon_secim_kutusu.get().strip() or ANIMASYON_TURLERI[0]
        aciklama = animasyon_aciklamasi_olustur(karakter_adi, animasyon_turu)
        self.poz_aciklama_kutusu.delete("1.0", "end")
        self.poz_aciklama_kutusu.insert("1.0", aciklama)
        self.log_yaz(f"Aciklama otomatik dolduruldu: '{aciklama}' (karakter: {karakter_adi}, "
                     f"animasyon: {animasyon_turu})")

    def _stil_referans_sec(self):
        yol = filedialog.askopenfilename(title="Benzetmek istedigin cizim tarzinin gorselini sec",
                                          filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")])
        if yol:
            self._stil_referans_yolu = yol
            self.stil_referans_etiketi.config(text=f"Cizim tarzi benzesin: {os.path.basename(yol)}")

    # ------------------------------------------------------------
    # MANUEL PROMPT HAZIRLAMA (ucretsiz yol - API/kart gerektirmez)
    # ------------------------------------------------------------
    def _gorseli_panoya_kopyala(self, dosya_yolu):
        if not dosya_yolu:
            messagebox.showwarning("Eksik", "Once bir gorsel sec (Karakter/Stil Gorseli Sec butonuyla).")
            return
        basarili, hata = resmi_panoya_kopyala(dosya_yolu)
        if basarili:
            self.log_yaz(f"'{os.path.basename(dosya_yolu)}' panoya GORSEL olarak kopyalandi - "
                          "simdi gemini.google.com sohbet kutusuna Ctrl+V yap.")
        else:
            self.log_yaz(f"[HATA] Gorsel panoya kopyalanamadi: {hata}")
            messagebox.showerror(
                "Kopyalanamadi",
                f"{hata}\n\nAlternatif: dosyayi Dosya Gezgini'nden acip gemini.google.com "
                "sohbet kutusuna elle surukle-birak yapabilirsin."
            )

    def _kare_klasorunu_temizle_arsivle(self):
        """Madde: 'her yeni video icin Kare Klasorunu elle bosaltmak sacma' -
        tek tikla, hicbir sey SILMEDEN, eski kareleri tarih-damgali bir
        arsive tasir - Kare Klasoru yeni video icin BOMBOS kalir."""
        onay = messagebox.askyesno(
            "Yeni Video Icin Temizle",
            "Kare Klasoru'ndeki mevcut kareler SILINMEYECEK, tarih-damgali bir "
            "arsiv klasorune TASINACAK. Kare Klasoru yeni video icin bombos "
            "kalacak.\n\nDevam edilsin mi?"
        )
        if not onay:
            return
        basarili, sonuc = kare_klasorunu_arsivle()
        if basarili:
            if sonuc == 0:
                self.log_yaz("Kare Klasoru zaten bostu, arsivlenecek bir sey yoktu.")
            else:
                self.log_yaz(f"{sonuc} eski kare arsivlendi ({KARE_ARSIVI_KLASORU}). "
                             "Kare Klasoru simdi bombos - yeni video icin hazir.")
            messagebox.showinfo("Tamamlandi", "Kare Klasoru temizlendi (eskiler arsivde duruyor).")
        else:
            self.log_yaz(f"[HATA] Arsivleme basarisiz: {sonuc}")
            messagebox.showerror("Hata", f"Arsivleme basarisiz:\n{sonuc}")

    def _poz_karakter_sec(self):
        yol = filedialog.askopenfilename(title="Karakter gorselini sec",
                                          filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")])
        if yol:
            self._poz_karakter_yolu = yol
            self.poz_karakter_etiketi.config(text=f"Karakter: {os.path.basename(yol)}")

    def _poz_stil_sec(self):
        yol = filedialog.askopenfilename(title="Stil gorselini sec",
                                          filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")])
        if yol:
            self._poz_stil_yolu = yol
            self.poz_stil_etiketi.config(text=f"Stil: {os.path.basename(yol)}")

    def _benzersiz_sayisini_al(self, toplam_kare_sayisi):
        """Dongusel/tekrarlayan animasyonlar icin: kullanici 'benzersiz kare'
        alanina bir sey yazmadiysa (0 veya toplamdan buyuk/esit) DONGU YOK
        demektir - tum kareler farkli uretilir (eski davranis). Kucuk bir
        sayi yazdiysa (orn. 20 karelik yuruyus icin 4), SADECE o kadar
        benzersiz kare uretilir, gerisi TEKRARLANARAK doldurulur - ekstra
        gorsel uretilmez, ucretsiz/hizli olur."""
        try:
            benzersiz = int(self.poz_benzersiz_kutusu.get())
        except (ValueError, AttributeError):
            benzersiz = 0
        if benzersiz <= 0 or benzersiz >= toplam_kare_sayisi:
            return toplam_kare_sayisi
        return benzersiz

    def _poz_prompt_olustur(self):
        """Kac kare istendigine gore OTOMATIK olarak tek poz mu, tek gorselde
        coklu panel mi, yoksa (standart kaliteyi korumak icin tek gorsele
        sigmayacak kadar cok kare istenmisse) COK PARCALI uretim mi
        yapilacagina karar verir. Kullanici hicbir zaman izgara duzenini
        veya kac gorsele bolunecegini kendisi ayarlamaz - hepsi otomatik."""
        aciklama = self._poz_aciklama_al()
        if not aciklama:
            messagebox.showwarning("Eksik", "Once ne cizilecegini yaz.")
            return

        # Madde: 'her actigimda bu sayfa geliyo, kaldigim yerden devam etsin'
        # - son yazilan aciklama/sureyi kaydet, panel yeniden acildiginda
        # otomatik doldurulsun.
        self.ayarlar["son_aciklama"] = self._poz_aciklama_al()
        self.ayarlar["son_sure"] = self.poz_sure_kutusu.get().strip()
        ayarlari_kaydet(self.ayarlar)

        try:
            kare_sayisi = int(self.poz_kare_sayisi_kutusu.get())
        except ValueError:
            messagebox.showwarning("Hatali sayi", "Kare sayisi gecerli bir tam sayi olmali.")
            return

        # PixAI promptu = KEYFRAME panel sayisi (benzersiz). Video FPS karesi (480 vs) DEGIL.
        try:
            panel_hedef = int(self.poz_benzersiz_kutusu.get())
        except (ValueError, AttributeError):
            panel_hedef = 0
        if panel_hedef <= 0:
            # Eski bug: 0 → tum FPS kareleri → 49x3 parca. Short'ta asla.
            panel_hedef = 9
            try:
                self.poz_benzersiz_kutusu.delete(0, "end")
                self.poz_benzersiz_kutusu.insert(0, "9")
            except Exception:
                pass
        benzersiz_sayisi = panel_hedef  # keyframe panel (9 = 3x3 tek gorsel)
        maks_kare_basina_gorsel = maksimum_kare_basina_gorsel()

        stil_yolu = self._poz_stil_yolu or getattr(self, "_stil_referans_yolu", None)
        api_key = self.ayarlar.get("gemini_api_anahtari", "").strip()
        # Stil resmi → METIN (PixAI resmi kabul etmese bile promptta stil var)
        if stil_yolu and os.path.exists(stil_yolu):
            self.log_yaz(f"Stil resmi metne cevriliyor: {os.path.basename(stil_yolu)}")
            stil_metni = stil_resmini_metne_cevir(stil_yolu, api_key)
            self._son_stil_metni = stil_metni
        else:
            stil_metni = stil_resmini_lokal_metne_cevir(None)
            self._son_stil_metni = stil_metni
            self.log_yaz("Stil resmi yok — varsayilan anime stil metni kullanildi (2) Stil secerek iyilestir).")

        # DEFTER MODU: her kredi = 1 tam sayfa (Tensor/NovelAI)
        if FLIPBOOK_MODU:
            sayfalar = _poz_satirlarini_ayikla(aciklama)
            mevcut = getattr(self, '_defter_sayfalari', None) or []
            if (not mevcut) or (len(sayfalar) != len(mevcut)):
                self._defter_sayfalari = sayfalar or [aciklama.strip()]
                self._defter_sayfa_i = 0
            if self._defter_sayfa_i >= len(self._defter_sayfalari):
                self._defter_sayfa_i = 0
            poz = self._defter_sayfalari[self._defter_sayfa_i]
            self._poz_parca_gruplari = None
            self._son_uretilen_kare_sayisi = 1
            self._son_uretilen_benzersiz_sayisi = 1
            prompt = flipbook_tek_sayfa_promptu(
                poz,
                self._poz_karakter_yolu,
                stil_yolu,
                stil_metni=stil_metni,
                kadrosu=getattr(self, '_aktif_kadrosu', 'zombie'),
                motor=getattr(self, '_cizim_motoru', 'tensor'),
            )
            prompt = (
                f'=== DEFTER SAYFA {self._defter_sayfa_i + 1}/{len(self._defter_sayfalari)} ===\n'
                + prompt
            )
            self.poz_prompt_kutusu.delete('1.0', 'end')
            self.poz_prompt_kutusu.insert('1.0', prompt)
            try:
                self._motor_etiket_guncelle()
            except Exception:
                pass
            self.log_yaz(
                f'Defter sayfa {self._defter_sayfa_i + 1}/{len(self._defter_sayfalari)} prompt hazir.'
            )
            return

        if benzersiz_sayisi <= 1:
            self._poz_parca_gruplari = None  # tek poz - parcalama yok
            self._son_uretilen_kare_sayisi = kare_sayisi
            self._son_uretilen_benzersiz_sayisi = 1
            prompt = manuel_prompt_metni_olustur(
                aciklama, self._poz_karakter_yolu, stil_yolu, stil_metni=stil_metni
            )
            self.log_yaz(
                "Prompt hazir (tek defter sayfasi). Stil METIN olarak gomulu. "
                "Metni Al → PixAI'ye yapistir."
            )

        elif benzersiz_sayisi <= maks_kare_basina_gorsel:
            # Standart kaliteyi bozmadan TEK gorsele sigar - parcalama gerekmez.
            self._poz_parca_gruplari = None
            self._son_uretilen_kare_sayisi = kare_sayisi
            self._son_uretilen_benzersiz_sayisi = benzersiz_sayisi
            satir, sutun = kare_sayisindan_izgara_hesapla(benzersiz_sayisi)
            prompt = coklu_panel_prompt_metni_olustur(
                aciklama, benzersiz_sayisi, satir, sutun,
                self._poz_karakter_yolu, stil_yolu, stil_metni=stil_metni,
            )
            if benzersiz_sayisi < kare_sayisi:
                prompt += (
                    f"\n\nONEMLI: Bu, toplam {kare_sayisi} karelik DONGUSEL/tekrarlayan bir animasyonun "
                    f"sadece {benzersiz_sayisi} BENZERSIZ temel karesi - geri kalani bu kareler sirayla "
                    "TEKRARLANARAK elde edilecek. Bu yuzden ilk kare ile son kare, dongu baglandiginda "
                    "(son kareden ilk kareye gecince) akici gorunecek sekilde uyumlu olsun."
                )
                self.log_yaz(
                    f"Prompt metni olusturuldu ({benzersiz_sayisi} BENZERSIZ kare, toplamda {kare_sayisi} "
                    f"kareye dongu ile tamamlanacak - {kare_sayisi - benzersiz_sayisi} ekstra gorsel "
                    "URETILMEYECEK, ayni kareler tekrar kullanilacak). Sira: 1) 'Metni Kopyala' -> "
                    "gemini.google.com'a yapistir -> 2) 'Karakter Gorselini Panoya Kopyala' -> sohbet "
                    "kutusuna TEKRAR Ctrl+V yap -> 3) gonder -> gelen TEK gorseli indir -> 'Indirdigim "
                    "Gorseli Ekle' ile ekle (otomatik bolunur VE dongu ile cogaltilir)."
                )
            else:
                self.log_yaz(
                    f"Prompt metni olusturuldu ({kare_sayisi} kare, duzen otomatik hesaplandi, standart "
                    f"kalitede tek gorsele sigiyor - maks {maks_kare_basina_gorsel} kare/gorsel). "
                    "Sira: 1) 'Metni Kopyala' -> gemini.google.com'a yapistir -> 2) 'Karakter Gorselini "
                    "Panoya Kopyala' -> sohbet kutusuna TEKRAR Ctrl+V yap -> 3) gonder -> gelen TEK gorseli "
                    "indir -> 'Indirdigim Gorseli Ekle' ile ekle (otomatik bolunur)."
                )

        else:
            # Standart kaliteyi korumak icin TEK gorsele sigmiyor - OTOMATIK
            # olarak birden fazla parcaya (ayri Gemini gorseli) bolunuyor.
            # Kullanici bunu HIC ayarlamiyor, sadece parca parca gonderiyor.
            if not self._poz_parca_gruplari or self._poz_beklenen_benzersiz_sayisi != benzersiz_sayisi \
                    or self._poz_beklenen_kare_sayisi != kare_sayisi:
                # Yeni bir uretim baslangici (once yapilmamis veya ayarlar degismis)
                self._poz_parca_gruplari = kare_gruplarina_bol(benzersiz_sayisi, maks_kare_basina_gorsel)
                self._poz_parca_indeksi = 0
                self._poz_toplanan_benzersiz = []
                self._poz_beklenen_kare_sayisi = kare_sayisi
                self._poz_beklenen_benzersiz_sayisi = benzersiz_sayisi

            toplam_parca = len(self._poz_parca_gruplari)
            bu_parca_boyutu = self._poz_parca_gruplari[self._poz_parca_indeksi]
            satir, sutun = kare_sayisindan_izgara_hesapla(bu_parca_boyutu)
            prompt = coklu_panel_prompt_metni_olustur(
                aciklama, bu_parca_boyutu, satir, sutun,
                self._poz_karakter_yolu, stil_yolu, stil_metni=stil_metni,
            )
            prompt += (
                f"\n\nONEMLI: Bu, standart kaliteyi korumak icin {toplam_parca} PARCAYA bolunmus buyuk bir "
                f"animasyonun {self._poz_parca_indeksi + 1}. PARCASI (bu parcada {bu_parca_boyutu} kare var). "
                "Ayni karakteri, ayni tutarlilikta ciz - bu parca, oncekilerin/sonrakilerin DEVAMI niteliginde."
            )
            self.log_yaz(
                f"Prompt metni olusturuldu - PARCA {self._poz_parca_indeksi + 1}/{toplam_parca} "
                f"({bu_parca_boyutu} kare). Standart kalite icin tek gorsele en fazla "
                f"{maks_kare_basina_gorsel} kare sigdiriliyor, bu yuzden {kare_sayisi} kare "
                f"{toplam_parca} ayri gorsele bolundu. Sira: 1) 'Metni Kopyala' -> gemini.google.com'a "
                "yapistir -> 2) 'Karakter Gorselini Panoya Kopyala' -> sohbet kutusuna TEKRAR Ctrl+V yap "
                "-> 3) gonder -> gelen gorseli indir -> 'Indirdigim Gorseli Ekle' ile ekle -> bu parca "
                "kaydedilince bu buton OTOMATIK olarak siradaki parcanin metnini hazirlayacak."
            )

        self.poz_prompt_kutusu.delete("1.0", "end")
        self.poz_prompt_kutusu.insert("1.0", prompt)

    def _poz_prompt_kopyala(self):
        metin = self.poz_prompt_kutusu.get("1.0", "end-1c")
        if not metin.strip():
            messagebox.showinfo("Bos", "Once 'Prompt Metnini Olustur' butonuna bas.")
            return
        self.pencere.clipboard_clear()
        self.pencere.clipboard_append(metin)
        self.log_yaz("Prompt metni panoya kopyalandi - simdi gemini.google.com'a yapistirabilirsin.")

    def _gemini_web_ac(self):
        import webbrowser
        webbrowser.open("https://gemini.google.com/app")
        self.log_yaz("gemini.google.com tarayicida acildi.")

    def _poz_gorseli_ekle(self):
        """Indirilen gorseli ekler. Kac kare istendiyse (spinbox) ona gore
        OTOMATIK olarak: 1 ise tek poz olarak kutuphaneye kaydeder, birden
        fazla ise izgarayi (yine otomatik hesaplanan duzenle) boler.

        COK PARCALI uretim aktifse (standart kaliteyi korumak icin tek
        gorsele sigmayan buyuk kare sayilari), bu gorsel sadece O PARCANIN
        kareleri olarak toplanir; TUM parcalar tamamlanana kadar Kare
        Klasorune/kutuphaneye HENUZ YAZILMAZ. Son parca eklenince tum
        kareler birlesip (dongu varsa tekrarla) kaydedilir."""
        yol = filedialog.askopenfilename(title="Tensor/NovelAI'dan indirdigin TEK sayfayi sec",
                                          filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")])
        if not yol:
            return

        # DEFTER: tek tam sayfa → dogrudan Kare Klasoru (grid bolme YOK)
        if FLIPBOOK_MODU and getattr(self, "_defter_sayfalari", None):
            try:
                from PIL import Image
                gorsel = Image.open(yol).convert("RGBA")
                mevcut = len([f for f in os.listdir(KARE_KLASORU) if f.lower().endswith(".png")])
                hedef = os.path.join(KARE_KLASORU, f"poz_{mevcut + 1}.png")
                guvenli_png_kaydet(gorsel, hedef)
                no = self._defter_sayfa_i + 1
                toplam = len(self._defter_sayfalari)
                self.log_yaz(f"Defter sayfa {no}/{toplam} eklendi → {os.path.basename(hedef)}")
                if no < toplam:
                    messagebox.showinfo(
                        f"Sayfa {no}/{toplam} eklendi",
                        "Simdi SONRAKI SAYFA bas → yeni prompt → tekrar uret.",
                    )
                    self._devam_et_parcayi_kopyala()
                else:
                    messagebox.showinfo("Defter bitti", "Tum sayfalar eklendi. 7) Krita Video.")
            except Exception as e:
                messagebox.showerror("Hata", str(e))
            return

        # --- COK PARCALI (batch) uretim aktifse: bu gorsel sadece bir parca ---
        if self._poz_parca_gruplari:
            bu_parca_boyutu = self._poz_parca_gruplari[self._poz_parca_indeksi]
            satir, sutun = kare_sayisindan_izgara_hesapla(bu_parca_boyutu)
            onay = messagebox.askyesno(
                "Kontrol Et",
                f"Bu gorseli {satir} satir x {sutun} sutun = {bu_parca_boyutu} PARCAYA bolecegim.\n\n"
                "Secilen gorselde GERCEKTEN bu kadar panel var mi?\n\n"
                "EVET: Dogru, devam et.\nHAYIR: Iptal et."
            )
            if not onay:
                self.log_yaz("Bu parca icin iptal edildi.")
                return
            try:
                parcalar = gorseli_izgaraya_bol(yol, satir, sutun)[:bu_parca_boyutu]
                self._poz_toplanan_benzersiz.extend(parcalar)
                self._poz_parca_indeksi += 1
            except Exception as e:
                self.log_yaz(f"[HATA] Parca gorseli bolunemedi: {e}")
                messagebox.showerror("Hata", f"Gorsel bolunemedi:\n{e}")
                return

            toplam_parca = len(self._poz_parca_gruplari)
            if self._poz_parca_indeksi < toplam_parca:
                kalan = toplam_parca - self._poz_parca_indeksi
                self.log_yaz(
                    f"Parca {self._poz_parca_indeksi}/{toplam_parca} eklendi ({len(parcalar)} kare). "
                    f"{kalan} kaldi — simdi DEVAM ET bas (unutma!)."
                )
                self._parca_durumunu_guncelle()
                # Otomatik panoya koy — kullanici unutmasin
                self._devam_et_parcayi_kopyala()
                return

            # --- Son parca da geldi: toplananlari birlestirip kaydet ---
            kare_sayisi = self._poz_beklenen_kare_sayisi
            benzersiz_sayisi = self._poz_beklenen_benzersiz_sayisi
            tum_benzersiz_parcalar = self._poz_toplanan_benzersiz
            # Durumu sifirla (bir sonraki uretim icin temiz baslasin)
            self._poz_parca_gruplari = None
            self._poz_parca_indeksi = 0
            self._poz_toplanan_benzersiz = []
            self._poz_beklenen_kare_sayisi = None
            self._poz_beklenen_benzersiz_sayisi = None

            self.log_yaz(f"Tum parcalar tamamlandi - {len(tum_benzersiz_parcalar)} benzersiz kare "
                         "birlestiriliyor.")
            self._poz_parcalari_kaydet(tum_benzersiz_parcalar, kare_sayisi, benzersiz_sayisi)
            return

        # --- TEK gorsellik (parcasiz) yol ---
        # Madde: 'panel sayisini ben girmeyeyim, uygulama hatirlasin' - eger bu
        # oturumda bir prompt uretildiyse, O ANKI widget degerleri yerine
        # NE ISTENDIYSE onu kullan (kullanici arada kutulari degistirmis/
        # unutmus olsa bile tutarlilik bozulmaz).
        if self._son_uretilen_kare_sayisi is not None:
            kare_sayisi = self._son_uretilen_kare_sayisi
            benzersiz_sayisi = self._son_uretilen_benzersiz_sayisi
        else:
            try:
                kare_sayisi = int(self.poz_kare_sayisi_kutusu.get())
            except ValueError:
                kare_sayisi = 1
            benzersiz_sayisi = self._benzersiz_sayisini_al(kare_sayisi)

        if benzersiz_sayisi <= 1:
            isim = simpledialog.askstring("Karakter Adi", "Bu hangi karaktere ait? (orn: Rias)", parent=self.pencere)
            if not isim or not isim.strip():
                return
            poz_adi = simpledialog.askstring("Poz Adi", "Bu poza kisa bir isim ver (orn: 'el_sallar'):", parent=self.pencere)
            if not poz_adi or not poz_adi.strip():
                return
            try:
                from PIL import Image
                gorsel = Image.open(yol).convert("RGBA")
                kutuphane_klasoru = karakterin_kutuphane_klasoru(isim.strip())
                hedef_yol = os.path.join(kutuphane_klasoru, poz_dosya_adini_temizle(poz_adi) + ".png")
                gorsel.save(hedef_yol)
                self.log_yaz(f"Kutuphaneye eklendi: {isim.strip()}/{poz_dosya_adini_temizle(poz_adi)} (ucretsiz)")
                messagebox.showinfo("Eklendi", f"'{poz_adi}' kutuphaneye eklendi.")
            except Exception as e:
                self.log_yaz(f"[HATA] Gorsel kutuphaneye eklenemedi: {e}")
                messagebox.showerror("Hata", f"Gorsel eklenemedi:\n{e}")
            return

        satir, sutun = kare_sayisindan_izgara_hesapla(benzersiz_sayisi)

        # Madde: 'benzersiz sayisi yanlis girilince yanlis izgarayla bolunuyor,
        # video bozuluyor' - bolmeden ONCE kullaniciya ne yapacagimizi ACIKCA
        # sor, boylece resimdeki gercek panel sayisiyla uyusmuyorsa hemen
        # fark edilsin (iptal edip 'Prompt Metnini Olustur'u tekrar calistirabilsin).
        kaynak_notu = ("(Prompt Metnini Olustur'da hatirlanan sayi)" if self._son_uretilen_kare_sayisi is not None
                       else "('Bunlardan kaci BENZERSIZ' kutusundaki sayi)")
        if not self._tek_tus_modu:
            onay = messagebox.askyesno(
                "Kontrol Et",
                f"Bu gorseli {satir} satir x {sutun} sutun = {benzersiz_sayisi} PARCAYA bolecegim "
                f"{kaynak_notu}.\n\n"
                "Secilen gorselde GERCEKTEN bu kadar panel var mi? Yoksa YANLIS bolunecek "
                "(kareler karisir, video bozuk cikar). Farkli bir gorsel eklemek istiyorsan (orn. "
                "kutuphaneden eski bir gorsel), 'Bunlardan kaci BENZERSIZ' kutusunu guncelleyip "
                "'Prompt Metnini Olustur'a tekrar basarak bu hatirlanan sayiyi degistirebilirsin.\n\n"
                "EVET: Dogru, devam et.\nHAYIR: Iptal et."
            )
            if not onay:
                self.log_yaz("Iptal edildi.")
                return
        try:
            parcalar = gorseli_izgaraya_bol(yol, satir, sutun)[:benzersiz_sayisi]
        except Exception as e:
            self.log_yaz(f"[HATA] Gorsel bolunemedi: {e}")
            messagebox.showerror("Hata", f"Gorsel bolunemedi:\n{e}")
            return

        # Madde: 'AI ile sirayi dogrula' - opsiyonel, isaretliyse Gemini'nin
        # METIN modeline (gorsel URETMEZ, sadece analiz eder - ucuz/genelde
        # ucretsiz) sorup dogru oynatma sirasini aliyoruz.
        if self._sira_dogrula_degiskeni.get():
            api_anahtari = self.ayarlar.get("gemini_api_anahtari", "").strip()
            if not api_anahtari:
                messagebox.showwarning("Eksik", "Sira dogrulama icin 'Gemini API Anahtari' gerekiyor.")
            else:
                aciklama = self._poz_aciklama_al() or "(aciklama yok)"
                self.log_yaz("AI ile sira dogrulanıyor (gorsel uretilmiyor, sadece analiz)...")
                sira_listesi, hata = gemini_ile_sira_dogrula(api_anahtari, yol, benzersiz_sayisi, aciklama)
                if sira_listesi is None:
                    self.log_yaz(f"[UYARI] Sira dogrulanamadi, orijinal sira kullanilacak: {hata}")
                else:
                    if sira_listesi == list(range(1, benzersiz_sayisi + 1)):
                        self.log_yaz("AI: siralama zaten dogru, degisiklik yok.")
                    else:
                        parcalar = [parcalar[i - 1] for i in sira_listesi]
                        self.log_yaz(f"AI siralamayi degistirdi, yeni sira: {sira_listesi}")

        self._poz_parcalari_kaydet(parcalar, kare_sayisi, benzersiz_sayisi)

    def _poz_parcalari_kaydet(self, benzersiz_parcalar, kare_sayisi, benzersiz_sayisi):
        """Ortak kaydetme adimi: hem TEK gorsellik hem COK PARCALI uretimin
        SONUNDA cagrilir. benzersiz_parcalar = toplanan tum PIL.Image
        kareleri (benzersiz_sayisi kadar). kare_sayisi = TOPLAM (dongu ile
        tamamlanacak) kare sayisi."""
        isim = simpledialog.askstring("Karakter Adi", "Bu kareler hangi karaktere ait? (orn: Rias)", parent=self.pencere)
        if not isim or not isim.strip():
            if self._tek_tus_modu:
                isim = "karakter"
            else:
                return

        if self._tek_tus_modu:
            hedef_kare_klasoru = True
        else:
            hedef_kare_klasoru = messagebox.askyesno(
                "Nereye kaydedilsin?",
                "EVET: Dogrudan animasyon sirasina ekle (Kare Klasoru - Krita adimi icin hazir olur).\n\n"
                "HAYIR: Poz Kutuphanesine ekle (ileride tekrar kullanmak icin, taban isim + numara ile)."
            )
        try:
            if hedef_kare_klasoru:
                # Hizala — kaymayi azalt (ayni olcek/merkez)
                hizali = kareleri_hizala(list(benzersiz_parcalar))
                if len(hizali) == len(benzersiz_parcalar):
                    benzersiz_parcalar = hizali
                    self.log_yaz("Kareler hizalandi (kayma azaltma).")
                mevcut_sayisi = len([f for f in os.listdir(KARE_KLASORU) if f.lower().endswith(".png")])
                for j in range(kare_sayisi):
                    parca = benzersiz_parcalar[j % len(benzersiz_parcalar)]  # DONGU: bastan tekrarla
                    hedef_yol = os.path.join(KARE_KLASORU, f"poz_{mevcut_sayisi + j + 1}.png")
                    guvenli_png_kaydet(parca.convert("RGBA"), hedef_yol)
                if benzersiz_sayisi < kare_sayisi:
                    self.log_yaz(
                        f"{kare_sayisi} karelik dizi olusturuldu ({benzersiz_sayisi} benzersiz gorsel, "
                        f"dongu ile {kare_sayisi} kareye tamamlandi - {kare_sayisi - benzersiz_sayisi} "
                        "ekstra gorsel URETILMEDI, ayni dosyalar tekrar kullanildi, ucretsiz)."
                    )
                else:
                    self.log_yaz(
                        f"{len(benzersiz_parcalar)} kare Kare Klasorune eklendi "
                        f"(poz_{mevcut_sayisi + 1}..poz_{mevcut_sayisi + kare_sayisi}.png) - ucretsiz."
                    )
                if self._tek_tus_modu:
                    self.log_yaz(f"TEK TUS: {kare_sayisi} kare hazir — video olusturuluyor...")
                    self._sadece_ffmpeg_video_olustur()
                    return
                messagebox.showinfo(
                    "Bitti",
                    f"{kare_sayisi} kare Kare Klasorune eklendi (gerekirse dongu ile tekrar dahil).\n"
                    "Simdi 'Krita'da Animasyonu Kur' butonuna basabilirsin."
                )
            else:
                taban_adi = simpledialog.askstring(
                    "Taban Poz Adi", "Pozlara verilecek taban isim (orn: 'yuruyor'):", parent=self.pencere
                )
                if not taban_adi or not taban_adi.strip():
                    return
                kutuphane_klasoru = karakterin_kutuphane_klasoru(isim.strip())
                for j, parca in enumerate(benzersiz_parcalar, start=1):
                    dosya_adi = poz_dosya_adini_temizle(f"{taban_adi}_{j}") + ".png"
                    parca.convert("RGBA").save(os.path.join(kutuphane_klasoru, dosya_adi))
                self.log_yaz(
                    f"{len(benzersiz_parcalar)} BENZERSIZ kare '{isim.strip()}' kutuphanesine eklendi "
                    f"({taban_adi}_1..{taban_adi}_{len(benzersiz_parcalar)}) - ucretsiz."
                )
                messagebox.showinfo("Bitti", f"{len(benzersiz_parcalar)} benzersiz kare kutuphaneye eklendi.")
        except Exception as e:
            self.log_yaz(f"[HATA] Kareler kaydedilemedi: {e}")
            messagebox.showerror("Hata", f"Kareler kaydedilemedi:\n{e}")

    def _coklu_api_uretmeye_basla(self):
        """Ucretli yol: 'Poz/Kare Uret' bolumundeki ayni girdileri kullanarak,
        standart kaliteyi korumak icin gereken kadar API cagrisini (1 veya
        birden fazla, otomatik) ARKA PLANDA sirayla yapar, tum benzersiz
        kareleri toplar, dongu varsa TEKRARLAYARAK toplam sayiya tamamlar.
        Kullanici hicbir sey beklemeden tek butona basar, kalan hersey
        arka planda otomatik olur (API yolunda bekleme sorunu yok, manuel
        yoldaki gibi parca parca kopyala-yapistir GEREKMEZ)."""
        api_anahtari = self.ayarlar.get("gemini_api_anahtari", "").strip()
        if not api_anahtari:
            messagebox.showwarning("Eksik", "Once 'Gemini API Anahtari' gir.")
            return
        aciklama = self._poz_aciklama_al()
        if not aciklama:
            messagebox.showwarning("Eksik", "Once yukaridaki 'Poz/Kare Uret' bolumune "
                                             "ne cizilecegini yaz.")
            return
        try:
            kare_sayisi = int(self.poz_kare_sayisi_kutusu.get())
        except ValueError:
            messagebox.showwarning("Hatali sayi", "Kare sayisi gecerli bir tam sayi olmali.")
            return
        kare_sayisi = max(kare_sayisi, 1)
        benzersiz_sayisi = self._benzersiz_sayisini_al(kare_sayisi)
        maks_kare_basina_gorsel = maksimum_kare_basina_gorsel()
        gruplar = kare_gruplarina_bol(benzersiz_sayisi, maks_kare_basina_gorsel)

        karakterler = list(self._karakterler)
        if self._poz_karakter_yolu and not karakterler:
            karakterler = [{"ad": "karakter", "yol": self._poz_karakter_yolu}]
        stil_referans_yolu = self._poz_stil_yolu or self._stil_referans_yolu

        self.coklu_api_butonu.config(state="disabled", text=f"URETILIYOR (0/{len(gruplar)} parca)...")
        if len(gruplar) > 1:
            self.log_yaz(f"Standart kaliteyi korumak icin {benzersiz_sayisi} benzersiz kare "
                         f"{len(gruplar)} ayri API cagrisina bolundu (her biri en fazla "
                         f"{maks_kare_basina_gorsel} kare) - hepsi arka planda otomatik yapiliyor...")
        elif benzersiz_sayisi < kare_sayisi:
            self.log_yaz(f"API'ye TEK cagri gonderiliyor ({benzersiz_sayisi} BENZERSIZ kare, toplamda "
                         f"{kare_sayisi} kareye dongu ile tamamlanacak)...")
        else:
            self.log_yaz(f"API'ye TEK cagri gonderiliyor ({kare_sayisi} kare)...")

        def arka_plan():
            toplanan = []
            for i, grup_boyutu in enumerate(gruplar, start=1):
                satir, sutun = kare_sayisindan_izgara_hesapla(grup_boyutu)
                gorsel, hata = gemini_ile_coklu_poz_uret(
                    api_anahtari, karakterler, stil_referans_yolu, aciklama, grup_boyutu, satir, sutun
                )
                if gorsel is None:
                    self._coklu_api_kuyrugu.put(("HATA", hata, i, len(gruplar)))
                    return
                self._coklu_api_kuyrugu.put(("PARCA_BITTI", i, len(gruplar), None))
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as gecici:
                        gecici_yol = gecici.name
                    gorsel.convert("RGBA").save(gecici_yol)
                    parcalar = gorseli_izgaraya_bol(gecici_yol, satir, sutun)[:grup_boyutu]
                    os.remove(gecici_yol)
                    toplanan.extend(parcalar)
                except Exception as e:
                    self._coklu_api_kuyrugu.put(("HATA", str(e), i, len(gruplar)))
                    return
            self._coklu_api_kuyrugu.put(("TAMAMLANDI", toplanan, kare_sayisi, benzersiz_sayisi))

        threading.Thread(target=arka_plan, daemon=True).start()

    def _coklu_api_kuyrugunu_dinle(self):
        try:
            while True:
                paket = self._coklu_api_kuyrugu.get_nowait()
                tur = paket[0]

                if tur == "HATA":
                    _, hata, i, toplam_parca = paket
                    self.coklu_api_butonu.config(state="normal", text="API ile Coklu Poz Uret (TEK cagri - kota tasarruflu)")
                    self.log_yaz(f"[HATA] Parca {i}/{toplam_parca} uretilemedi: {hata}")
                    if "429" in str(hata):
                        messagebox.showerror(
                            "Kota Asildi",
                            "Gemini gorsel modelinin kotasi asildi (429 hatasi).\n\n"
                            "Bir sure bekleyip tekrar dene."
                        )
                    else:
                        messagebox.showerror("Hata", f"Parca {i}/{toplam_parca} uretilemedi:\n{hata}")
                    continue

                if tur == "PARCA_BITTI":
                    _, i, toplam_parca, _ = paket
                    self.coklu_api_butonu.config(text=f"URETILIYOR ({i}/{toplam_parca} parca)...")
                    if toplam_parca > 1:
                        self.log_yaz(f"Parca {i}/{toplam_parca} API'den geldi, devam ediliyor...")
                    continue

                # tur == "TAMAMLANDI"
                _, toplanan_pozlar, kare_sayisi, benzersiz_sayisi = paket
                self.coklu_api_butonu.config(state="normal", text="API ile Coklu Poz Uret (TEK cagri - kota tasarruflu)")
                try:
                    mevcut_sayisi = len([f for f in os.listdir(KARE_KLASORU) if f.lower().endswith(".png")])
                    for j in range(kare_sayisi):
                        parca = toplanan_pozlar[j % len(toplanan_pozlar)]  # DONGU: bastan tekrarla
                        hedef_yol = os.path.join(KARE_KLASORU, f"poz_{mevcut_sayisi + j + 1}.png")
                        parca.convert("RGBA").save(hedef_yol)

                    if benzersiz_sayisi < kare_sayisi:
                        self.log_yaz(
                            f"API ile {benzersiz_sayisi} BENZERSIZ kare uretildi, dongu ile "
                            f"{kare_sayisi} kareye tamamlandi ve Kare Klasorune eklendi "
                            f"({kare_sayisi - benzersiz_sayisi} ekstra API cagrisi YAPILMADI)."
                        )
                    else:
                        self.log_yaz(
                            f"API ile {len(toplanan_pozlar)} kare uretildi ve Kare Klasorune eklendi "
                            f"(poz_{mevcut_sayisi + 1}..poz_{mevcut_sayisi + kare_sayisi}.png)."
                        )
                    if self._tek_tus_modu:
                        self.log_yaz("TEK TUS: Kareler hazir — ffmpeg ile video olusturuluyor...")
                        self._sadece_ffmpeg_video_olustur()
                    else:
                        messagebox.showinfo(
                            "Bitti",
                            f"{kare_sayisi} kare API ile uretildi/tamamlandi ve eklendi.\n"
                            "Simdi 'Krita'da Animasyonu Kur' butonuna basabilirsin."
                        )
                except Exception as e:
                    self.log_yaz(f"[HATA] Uretilen kareler kaydedilemedi: {e}")
                    messagebox.showerror("Hata", f"Kareler kaydedilemedi:\n{e}")
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._coklu_api_kuyrugunu_dinle)

    def _kutuphaneden_yukle(self):
        """Madde 5: 'bir yerde yuruyen Rias lazim oldu, nasil geri
        kullanacagim' - kutuphanede daha once kaydedilmis kareleri, YENIDEN
        URETMEDEN, dogrudan Kare Klasorune (sirali) kopyalar."""
        dosyalar = filedialog.askopenfilenames(
            title="Kutuphaneden kareleri sec (SIRAYLA eklenecek, dogru sirada sec)",
            initialdir=POZ_KUTUPHANESI_KLASORU,
            filetypes=[("Resimler", "*.png")]
        )
        if not dosyalar:
            return
        try:
            mevcut_sayisi = len([f for f in os.listdir(KARE_KLASORU) if f.lower().endswith(".png")])
            for j, yol in enumerate(dosyalar, start=1):
                hedef = os.path.join(KARE_KLASORU, f"poz_{mevcut_sayisi + j}.png")
                shutil.copy(yol, hedef)
            self.log_yaz(f"{len(dosyalar)} kare kutuphaneden Kare Klasorune kopyalandi "
                         "(yeniden URETILMEDI, tamamen ucretsiz).")
            messagebox.showinfo(
                "Eklendi",
                f"{len(dosyalar)} kare kutuphaneden eklendi.\nSimdi 'Krita'da Animasyonu Kur' "
                "butonuna basabilirsin."
            )
        except Exception as e:
            self.log_yaz(f"[HATA] Kutuphaneden kopyalanamadi: {e}")
            messagebox.showerror("Hata", f"Kopyalanamadi:\n{e}")

    def _poz_erken_bitir(self):
        """Hizli test icin: cok parcali uretim ortasindaysan (bazi parcalar
        henuz eklenmediyse), kalanlari BEKLEMEDEN, su ana kadar toplanan
        kareleri dongu ile tekrarlayip hemen kaydeder. Kalite dusebilir
        (daha az benzersiz poz) ama akisi hizlica ucdan uca test etmek icin
        idealdir."""
        if not self._poz_parca_gruplari or not self._poz_toplanan_benzersiz:
            messagebox.showinfo(
                "Parcalama Aktif Degil",
                "Su an devam eden cok parcali bir uretim yok - bu buton sadece "
                "3 parcadan 1-2'sini ekleyip kalanini atlamak istedigin durumlar icin."
            )
            return

        toplanan = self._poz_toplanan_benzersiz
        kare_sayisi = self._poz_beklenen_kare_sayisi
        tamamlanan_parca = self._poz_parca_indeksi
        toplam_parca = len(self._poz_parca_gruplari)

        # Durumu sifirla
        self._poz_parca_gruplari = None
        self._poz_parca_indeksi = 0
        self._poz_toplanan_benzersiz = []
        self._poz_beklenen_kare_sayisi = None
        self._poz_beklenen_benzersiz_sayisi = None

        self.log_yaz(f"Erken bitirildi: {tamamlanan_parca}/{toplam_parca} parca ({len(toplanan)} benzersiz "
                     f"kare) ile devam ediliyor, kalan parcalar atlandi.")
        self._poz_parcalari_kaydet(toplanan, kare_sayisi, len(toplanan))

    def _gemini_anahtarini_duzenle(self):
        mevcut = self.ayarlar.get("gemini_api_anahtari", "")
        yeni = simpledialog.askstring("Gemini API Anahtari", "API anahtarini yapistir:",
                                       initialvalue=mevcut, parent=self.pencere)
        if yeni is not None:
            self.ayarlar["gemini_api_anahtari"] = yeni.strip()
            ayarlari_kaydet(self.ayarlar)
            self.log_yaz("Gemini API anahtari kaydedildi.")

    def _realesrgan_yolunu_duzenle(self):
        yol = filedialog.askopenfilename(
            title="realesrgan-ncnn-vulkan.exe dosyasini sec (ucretsiz, ayrica indirilir: "
                  "github.com/xinntao/Real-ESRGAN-ncnn-vulkan)",
            filetypes=[("Uygulama", "*.exe"), ("Tumu", "*.*")]
        )
        if yol:
            self.ayarlar["realesrgan_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
            self.log_yaz(f"realesrgan yolu kaydedildi: {yol}")

    def _ffmpeg_yolunu_duzenle(self):
        yol = filedialog.askopenfilename(
            title="ffmpeg.exe dosyasini sec (ucretsiz, ayrica indirilir: ffmpeg.org/download.html "
                  "- Windows icin 'essentials' build yeterli)",
            filetypes=[("Uygulama", "*.exe"), ("Tumu", "*.*")]
        )
        if yol:
            self.ayarlar["ffmpeg_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
            self.log_yaz(f"ffmpeg yolu kaydedildi: {yol}")

    def _krita_yolunu_duzenle(self):
        yol = filedialog.askopenfilename(title="kritarunner.exe dosyasini sec",
                                          filetypes=[("Uygulama", "*.exe"), ("Tumu", "*.*")])
        if yol:
            self.ayarlar["kritarunner_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
            self.log_yaz(f"kritarunner yolu kaydedildi: {yol}")

    # ------------------------------------------------------------
    # 1) AI ILE KARELERI URETME (metin plani + her kare icin gorsel)
    # ------------------------------------------------------------
    def _kareleri_uretmeye_basla(self):
        api_anahtari = self.ayarlar.get("gemini_api_anahtari", "").strip()
        if not api_anahtari:
            messagebox.showwarning("Eksik", "Once 'Gemini API Anahtari' gir.")
            return
        hikaye = self.hikaye_kutusu.get("1.0", "end-1c").strip()
        if not hikaye:
            messagebox.showwarning("Eksik", "Once ne tur bir animasyon istedigini yaz.")
            return

        self.uret_butonu.config(state="disabled", text="PLANLANIYOR...")
        self.ilerleme_cubugu["value"] = 0
        self.log_yaz("")
        self.log_yaz("Gemini'den kare plani isteniyor...")

        karakterler = list(self._karakterler)  # kopya al, thread'e guvenli tasi
        stil_referans_yolu = self._stil_referans_yolu
        karakterler_ve_pozlari = [
            {"ad": k["ad"], "mevcut_pozlar": karakterin_mevcut_pozlari(k["ad"])}
            for k in karakterler
        ]

        def arka_plan():
            kare_listesi, hata = gemini_ile_kare_plani_uret(api_anahtari, hikaye, karakterler_ve_pozlari)
            self._kare_plani_kuyrugu.put((kare_listesi, hata, api_anahtari, karakterler, stil_referans_yolu))

        threading.Thread(target=arka_plan, daemon=True).start()

    def _kare_plani_kuyrugunu_dinle(self):
        try:
            while True:
                kare_listesi, hata, api_anahtari, karakterler, stil_referans_yolu = self._kare_plani_kuyrugu.get_nowait()
                self._kare_plani_sonucunu_isle(kare_listesi, hata, api_anahtari, karakterler, stil_referans_yolu)
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._kare_plani_kuyrugunu_dinle)

    def _kare_plani_sonucunu_isle(self, kare_listesi, hata, api_anahtari, karakterler, stil_referans_yolu):
        if kare_listesi is None:
            self.log_yaz(f"[HATA] Kare plani uretilemedi: {hata}")
            messagebox.showerror("Hata", f"Kare plani uretilemedi:\n{hata}")
            self.uret_butonu.config(state="normal", text="AI ile Kareleri Uret (metin plani + API gorsel)")
            return

        self.log_yaz(f"{len(kare_listesi)} kare planlandi:")
        for k in kare_listesi:
            self.log_yaz(f"  Kare {k.get('kare_no')}: {k.get('aciklama')}")

        self.uret_butonu.config(text="KARELER CIZILIYOR...")
        threading.Thread(
            target=self._karelerin_gorsellerini_uret_arka_plan,
            args=(kare_listesi, api_anahtari, karakterler, stil_referans_yolu), daemon=True
        ).start()

    def _karelerin_gorsellerini_uret_arka_plan(self, kare_listesi, api_anahtari, karakterler, stil_referans_yolu):
        toplam = len(kare_listesi)
        basarili_sayisi = 0

        for i, kare in enumerate(kare_listesi, start=1):
            tekrar_kullan_adi = kare.get("tekrar_kullan")

            if tekrar_kullan_adi:
                # ============================================================
                # TEKRAR KULLANIM: AI, bu pozun DAHA ONCE cizildigini
                # belirtti - GEMINI'YE HIC ISTEK ATMADAN, kutuphaneden
                # dogrudan kopyaliyoruz (tamamen ucretsiz, aninda).
                # ============================================================
                bulunan_yol = None
                for k in karakterler:
                    aday_yol = os.path.join(karakterin_kutuphane_klasoru(k["ad"]),
                                             poz_dosya_adini_temizle(tekrar_kullan_adi) + ".png")
                    if os.path.exists(aday_yol):
                        bulunan_yol = aday_yol
                        break

                if bulunan_yol:
                    hedef_yol = os.path.join(KARE_KLASORU, f"poz_{i}.png")
                    shutil.copyfile(bulunan_yol, hedef_yol)
                    basarili_sayisi += 1
                    self._kare_uretim_kuyrugu.put((
                        "ilerleme", i, toplam,
                        f"Kare {i}/{toplam}: '{tekrar_kullan_adi}' kutuphaneden TEKRAR KULLANILDI (API cagrisi YOK, ucretsiz)."
                    ))
                    continue
                else:
                    self._kare_uretim_kuyrugu.put((
                        "ilerleme", i, toplam,
                        f"UYARI: '{tekrar_kullan_adi}' kutuphanede bulunamadi, yeni cizilecek."
                    ))
                    # bulunamadi - asagida normal (yeni) uretime devam eder

            gorsel, hata = gemini_ile_kare_gorseli_uret(api_anahtari, karakterler, stil_referans_yolu, kare.get("aciklama", ""))

            if gorsel is None:
                self._kare_uretim_kuyrugu.put(("ilerleme", i, toplam, f"[HATA] Kare {i} olusturulamadi: {hata}"))

                # ============================================================
                # DUZELTME: Once, ilk kare BASARISIZ olsa bile kod sessizce
                # KALAN TUM kareleri de denemeye devam ediyordu - bu, orn.
                # kota asimi (429) gibi bir hata durumunda TUM kareler icin
                # bosuna basarisiz istek atilmasina (kota israfina) sebep
                # oluyordu. Artik: (a) 429/kota hatasi görülürse HEMEN dur,
                # (b) ilk kare basarisiz olursa da devam etmeden dur.
                # ============================================================
                if "429" in str(hata) or i == 1:
                    self._kare_uretim_kuyrugu.put(("iptal_edildi_hata", basarili_sayisi, toplam, hata))
                    return
                continue

            hedef_yol = os.path.join(KARE_KLASORU, f"poz_{i}.png")
            gorsel.convert("RGBA").save(hedef_yol)
            basarili_sayisi += 1
            self._kare_uretim_kuyrugu.put(("ilerleme", i, toplam, f"Kare {i}/{toplam} olusturuldu: poz_{i}.png"))

            # ================================================================
            # YENI POZU KUTUPHANEYE KAYDET: Boylece bir DAHAKI SEFERE ayni
            # poz tekrar gerektiginde, Gemini'ye TEKRAR PARA/KOTA HARCAMADAN
            # bu dosya dogrudan kullanilabilir. Sahnede tek karakter varsa
            # onun kutuphanesine, birden fazla varsa ILK karakterin
            # kutuphanesine kaydedilir (basit/ongorulur davranis icin).
            # ================================================================
            yeni_poz_adi = kare.get("yeni_poz_adi")
            if yeni_poz_adi and karakterler:
                try:
                    kutuphane_klasoru = karakterin_kutuphane_klasoru(karakterler[0]["ad"])
                    kutuphane_yolu = os.path.join(kutuphane_klasoru, poz_dosya_adini_temizle(yeni_poz_adi) + ".png")
                    shutil.copyfile(hedef_yol, kutuphane_yolu)
                    self._kare_uretim_kuyrugu.put(("ilerleme", i, toplam, f"  -> Kutuphaneye kaydedildi: {karakterler[0]['ad']}/{yeni_poz_adi} (ileride ucretsiz tekrar kullanilabilir)"))
                except Exception as e:
                    self._kare_uretim_kuyrugu.put(("ilerleme", i, toplam, f"  UYARI: Kutuphaneye kaydedilemedi: {e}"))

            # ================================================================
            # ILK KAREDEN SONRA DUR VE ONAY ISTE: Kalan tum kareleri (ve
            # Gemini API kotasini) bosa harcamadan once, kullaniciya SADECE
            # ILK karenin tarzini/kalitesini onaylat. Onay gelene kadar
            # thread burada BEKLER (threading.Event ile).
            # ================================================================
            if i == 1:
                self._onay_event.clear()
                self._onay_sonucu = None
                self._kare_uretim_kuyrugu.put(("onay_bekleniyor", hedef_yol, None, None))
                self._onay_event.wait()  # ana thread karar verene kadar bekle

                if not self._onay_sonucu:
                    self._kare_uretim_kuyrugu.put(("iptal_edildi", basarili_sayisi, toplam, None))
                    return

        self._kare_uretim_kuyrugu.put(("bitti", basarili_sayisi, toplam, None))

    def _kare_uretim_kuyrugunu_dinle(self):
        try:
            while True:
                tur, a, b, mesaj = self._kare_uretim_kuyrugu.get_nowait()
                if tur == "ilerleme":
                    self.log_yaz(mesaj)
                    self.ilerleme_cubugu["value"] = (a / b) * 100
                elif tur == "onay_bekleniyor":
                    self._onay_penceresini_goster(a)  # a = ilk karenin dosya yolu
                elif tur == "iptal_edildi":
                    self.log_yaz(f"Kullanici iptal etti. {a}/{b} kare olusturulmustu (sadece ilk kare).")
                    self.uret_butonu.config(state="normal", text="AI ile Kareleri Uret (metin plani + API gorsel)")
                elif tur == "iptal_edildi_hata":
                    self.log_yaz("[HATA] Islem durduruldu - kalan kareler icin bosuna istek atilmadi.")
                    self.uret_butonu.config(state="normal", text="AI ile Kareleri Uret (metin plani + API gorsel)")
                    if "429" in str(mesaj):
                        messagebox.showerror(
                            "Kota Asildi",
                            "Gemini gorsel modelinin ucretsiz kotasi asildi (429 hatasi).\n\n"
                            "Bir sure (birkac dakika - birkac saat arasi) bekleyip tekrar dene, "
                            "veya faturalandirma acip ucretli katmana gec."
                        )
                elif tur == "bitti":
                    self.log_yaz(f"BITTI: {a}/{b} kare basariyla olusturuldu. Klasor: {KARE_KLASORU}")
                    self.uret_butonu.config(state="normal", text="AI ile Kareleri Uret (metin plani + API gorsel)")
                    if a > 0:
                        self.log_yaz("Kareler hazir - Krita otomatik olarak baslatiliyor (tek akis)...")
                        self.pencere.after(500, self._krita_baslat)  # otomatik 2. adima gec
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._kare_uretim_kuyrugunu_dinle)

    def _onay_penceresini_goster(self, ilk_kare_yolu):
        """Ilk karenin onizlemesini gosterir, kullanicidan 'Devam Et' veya
        'Iptal' ister. Arka plan thread'i bu karar verilene kadar BEKLIYOR
        (threading.Event ile) - boylece geri kalan kareler icin gereksiz
        API cagrisi/kota harcanmiyor eger kullanici tarzi begenmezse."""
        from PIL import Image, ImageTk

        pencere = tk.Toplevel(self.pencere)
        pencere.title("Ilk Kare Onayi")
        pencere.grab_set()

        tk.Label(
            pencere, text="Ilk kare boyle uretildi. Tarz/kalite uygun mu?\n"
                          "'Devam Et' dersen kalan kareler de bu tarzda uretilecek.",
            font=("Segoe UI", 10), justify="center"
        ).pack(padx=15, pady=(15, 10))

        try:
            onizleme_img = Image.open(ilk_kare_yolu)
            onizleme_img.thumbnail((300, 500))
            self._onay_foto_referansi = ImageTk.PhotoImage(onizleme_img)  # referans tutulmali (GC)
            tk.Label(pencere, image=self._onay_foto_referansi).pack(padx=15, pady=(0, 15))
        except Exception as e:
            tk.Label(pencere, text=f"(Onizleme gosterilemedi: {e})", fg="red").pack(padx=15, pady=10)

        def devam_et():
            self._onay_sonucu = True
            self._onay_event.set()
            pencere.destroy()

        def iptal_et():
            self._onay_sonucu = False
            self._onay_event.set()
            pencere.destroy()

        buton_satiri = tk.Frame(pencere)
        buton_satiri.pack(fill="x", padx=15, pady=(0, 15))
        tk.Button(buton_satiri, text="Devam Et (kalan kareleri de uret)", bg=RENK_YESIL, fg=RENK_BEYAZ,
                  command=devam_et).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(buton_satiri, text="Iptal (tarz uygun degil)", bg="#c0392b", fg=RENK_BEYAZ,
                  command=iptal_et).pack(side="left", expand=True, fill="x")

        pencere.protocol("WM_DELETE_WINDOW", iptal_et)  # pencere X ile kapatilirsa da iptal say

    # ------------------------------------------------------------
    # 2) KRITA'YI ARKA PLANDA BASLATMA
    # ------------------------------------------------------------
    def _krita_baslat(self):
        kritarunner_yolu = self.ayarlar.get("kritarunner_yolu", "").strip()
        if not kritarunner_yolu or not os.path.exists(kritarunner_yolu):
            messagebox.showwarning("Eksik", "Once 'Krita Yolu Ayarlari' ile kritarunner.exe dosyasini sec.")
            return

        kare_dosyalari = [f for f in os.listdir(KARE_KLASORU) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not kare_dosyalari:
            messagebox.showwarning("Eksik", f"'{KARE_KLASORU}' klasorunde hic kare yok. Once 1. adimi calistir.")
            return

        # Madde: 'bekleniyor gibi bir yazi/donen bir yuvarlak' - islem
        # basladigi andan itibaren surekli hareket eden bir cubuk goster.
        self.krita_ilerleme_cubugu.pack(fill="x", pady=(0, 4))
        self.krita_ilerleme_cubugu.start(12)
        self.video_oynat_butonu.config(state="disabled")

        # ================================================================
        # Madde 3: istege bagli AI buyutme adimi. Checkbox isaretliyse,
        # Krita'ya HAM kareler yerine BUYUTULMUS kareler gonderilir -
        # bicubic yerine Real-ESRGAN (anime modeli) kullanildigi icin
        # kalite kaybi cok daha az olur.
        # ================================================================
        if self._buyutme_aktif_degiskeni.get():
            self.ayarlar = arac_yollarini_otomatik_doldur(self.ayarlar)
            realesrgan_yolu = self.ayarlar.get("realesrgan_yolu", "").strip()
            try:
                olcek = int(self.buyutme_olcek_kutusu.get())
            except ValueError:
                olcek = 4
            if olcek < 4:
                olcek = 4

            self.krita_butonu.config(state="disabled", text="KARELER BUYUTULUYOR...")
            if realesrgan_yolu and os.path.exists(realesrgan_yolu):
                self.log_yaz(
                    f"Kareler Real-ESRGAN ANIME {olcek}x + keskinlestirme "
                    f"(canli video kalitesi)..."
                )
            else:
                self.log_yaz(
                    f"Real-ESRGAN yok — PIL {olcek}x kalite buyutme "
                    f"(yine de 1080p video). Istersen sonra exe ekle."
                )

            def buyutme_arka_plan():
                basarili, mesaj = kareleri_buyut(
                    realesrgan_yolu, KARE_KLASORU, BUYUTULMUS_KLASORU,
                    olcek=olcek, model_adi="realesrgan-x4plus-anime",
                )
                self._krita_kuyrugu.put(("BUYUTME_SONUCU", basarili, mesaj, None))

            threading.Thread(target=buyutme_arka_plan, daemon=True).start()
            return  # buyutme bitince kuyruk dinleyici devam edecek (_devam_krita_kur cagirir)

        self._devam_krita_kur(KARE_KLASORU)

    def _devam_krita_kur(self, kaynak_kare_klasoru):
        """Buyutme yapildiysa BUYUTULMUS_KLASORU, yapilmadiysa KARE_KLASORU ile
        Krita adimina devam eder."""
        kritarunner_yolu = self.ayarlar.get("kritarunner_yolu", "").strip()

        # Madde: 'Poz/Kare Uret' bolumunde hesaplanan (dongu ile dogal hiz
        # icin) kare_basina_sure degerini KULLAN - boylece video, gercekte
        # kac dosya uretildiginden BAGIMSIZ olarak dogru surede oynar.
        kare_basina_sure = getattr(self, "_son_kare_basina_sure", None) or (1.0 / STANDART_ANIMASYON_FPS)

        # Madde: 'beğenmediğimi ben silerim, üzerine yazma, yanina koy' -
        # her calistirmada FARKLI (zaman damgali) bir proje adi kullan,
        # boylece onceki .kra/.png/.mp4 SILINMEZ/UZERINE YAZILMAZ - Cikti
        # Klasoru'nde birikirler, begenmedigini SEN silersin.
        from datetime import datetime
        proje_adi = f"kare_animasyon_{datetime.now():%Y%m%d_%H%M%S}"
        self._son_proje_adi = proje_adi

        krita_ayarlari = {
            "kare_klasoru": kaynak_kare_klasoru,
            "cikti_klasoru": CIKTI_KLASORU,
            "proje_genislik": 1080,
            "proje_yukseklik": 1920,
            "proje_fps": 24,
            "kare_basina_sure_saniye": kare_basina_sure,
            "proje_adi": proje_adi,
        }
        with open(KRITA_AYAR_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(krita_ayarlari, f, ensure_ascii=False, indent=2)
        self.log_yaz(f"krita_ayarlar.json yazildi (kaynak: {kaynak_kare_klasoru}, "
                     f"kare basina sure: {kare_basina_sure:.3f}sn, proje adi: {proje_adi}).")

        self.krita_butonu.config(state="disabled", text="KRITA CALISIYOR...")
        self.log_yaz("Krita arka planda (kritarunner ile) baslatiliyor...")

        def arka_plan():
            komut = kritarunner_komutunu_olustur(kritarunner_yolu, KRITA_SCRIPT_YOLU)
            try:
                sonuc = subprocess.run(komut, cwd=BASE_DIR, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=300,
                                        **sessiz_subprocess_ayarlari())
                self._krita_kuyrugu.put((sonuc.returncode, sonuc.stdout, sonuc.stderr, None))

                if sonuc.returncode == 0:
                    # Madde: 'ben son VIDEOYU gormek istiyorum' - Krita basariyla
                    # bittiginde, kareleri Krita'dan BAGIMSIZ olarak ffmpeg ile
                    # gercek bir MP4'e cevir (crash riski yok, Krita'ya hic
                    # dokunmuyoruz, sadece PNG dosyalarini okuyoruz).
                    ffmpeg_yolu = self.ayarlar.get("ffmpeg_yolu", "").strip()
                    if ffmpeg_yolu and os.path.exists(ffmpeg_yolu):
                        video_yolu = os.path.join(CIKTI_KLASORU, f"{proje_adi}.mp4")
                        basarili, mesaj = ffmpeg_ile_video_olustur(
                            ffmpeg_yolu, kaynak_kare_klasoru, video_yolu, kare_basina_sure
                        )
                        self._krita_kuyrugu.put(("VIDEO_SONUCU", basarili, mesaj, video_yolu))
                    else:
                        self._krita_kuyrugu.put((
                            "VIDEO_SONUCU", False,
                            "ffmpeg yolu ayarlanmamis - 'FFmpeg Yolu Ayarla' butonuyla ffmpeg.exe sec "
                            "(ucretsiz, ffmpeg.org/download.html).",
                            None
                        ))
            except Exception as e:
                self._krita_kuyrugu.put((None, "", "", str(e)))

        threading.Thread(target=arka_plan, daemon=True).start()

    def _krita_kuyrugunu_dinle(self):
        try:
            while True:
                donus_kodu, cikti, hata_ciktisi, istisna = self._krita_kuyrugu.get_nowait()

                if donus_kodu == "TEK_TUS_VIDEO":
                    self._tek_tus_video_sonucu_isle(cikti, hata_ciktisi, istisna)
                    continue

                if donus_kodu == "BUYUTME_SONUCU":
                    basarili, mesaj = cikti, hata_ciktisi
                    if not basarili:
                        self._ilerlemeyi_durdur()
                        self.krita_butonu.config(state="normal", text="Krita'da Animasyonu Kur (arka planda)")
                        self.log_yaz(f"[HATA] Kareler buyutulemedi: {mesaj}")
                        messagebox.showerror("Hata", f"Kareler buyutulemedi:\n{mesaj}\n\n"
                                                       "Buyutme yapilmadan devam etmek istersen checkbox'i "
                                                       "kapatip tekrar dene.")
                    else:
                        self.log_yaz(f"Kareler basariyla buyutuldu: {BUYUTULMUS_KLASORU}")
                        self._devam_krita_kur(BUYUTULMUS_KLASORU)
                    continue

                if donus_kodu == "VIDEO_SONUCU":
                    self._ilerlemeyi_durdur()
                    basarili, mesaj, video_yolu = cikti, hata_ciktisi, istisna
                    if basarili:
                        self.log_yaz(f"VIDEO olusturuldu: {video_yolu}")
                        self._son_video_yolu = video_yolu
                        self.video_oynat_butonu.config(state="normal")
                        self.onizleme_etiketi.config(text=f"Video hazir: {os.path.basename(video_yolu)}")
                        messagebox.showinfo("Video Hazir", f"Video basariyla olusturuldu:\n{video_yolu}")
                    else:
                        self.log_yaz(f"[HATA] Video olusturulamadi - tam detay:\n{mesaj}")
                        if "ffmpeg yolu ayarlanmamis" in str(mesaj):
                            messagebox.showwarning(
                                "FFmpeg Ayarlanmamis",
                                "Video icin ffmpeg.exe yolunu ayarlaman lazim ('FFmpeg Yolu Ayarla' "
                                "butonu). ffmpeg ucretsizdir: ffmpeg.org/download.html adresinden "
                                "'essentials' build indirilebilir (kart/API gerekmez)."
                            )
                        else:
                            # ffmpeg ciktisinin cogu (x264 istatistikleri) normal - asil hatayi
                            # bulmak icin 'error'/'invalid'/'no such' gecen satirlari one cikar.
                            onemli_satirlar = [
                                s for s in str(mesaj).splitlines()
                                if any(k in s.lower() for k in ("error", "invalid", "no such", "not found",
                                                                  "permission denied", "could not"))
                            ]
                            ozet = "\n".join(onemli_satirlar[-6:]) if onemli_satirlar else \
                                "(belirgin bir 'error' satiri bulunamadi, tam detay Gunluk'te)"
                            messagebox.showerror(
                                "Video Olusturulamadi",
                                f"Olasi sebep:\n{ozet}\n\nTam detay icin asagidaki Gunluk kutusuna bak."
                            )
                    continue

                self.krita_butonu.config(state="normal", text="Krita'da Animasyonu Kur (arka planda)")
                if istisna:
                    self._ilerlemeyi_durdur()
                    self.log_yaz(f"[HATA] kritarunner baslatilamadi: {istisna}")
                    messagebox.showerror("Hata", f"kritarunner baslatilamadi:\n{istisna}")
                else:
                    if cikti:
                        self.log_yaz(cikti)
                    if hata_ciktisi:
                        self.log_yaz(f"[HATA] {hata_ciktisi}")
                    if donus_kodu == 0:
                        self.log_yaz(f"Krita adimi bitti (.kra + PNG). Cikti klasoru: {CIKTI_KLASORU}")
                        self._onizlemeyi_guncelle()
                        if self.ayarlar.get("ffmpeg_yolu", "").strip():
                            self.log_yaz("Video simdi ffmpeg ile olusturuluyor, birazdan ayri bir "
                                         "bildirim gelecek...")
                            # NOT: ilerleme cubugu HENUZ durmuyor - video adimi devam ediyor.
                        else:
                            self._ilerlemeyi_durdur()
                            messagebox.showinfo(
                                "Tamamlandi (video HARIC)",
                                f".kra proje dosyasi ve PNG olusturuldu.\nCikti: {CIKTI_KLASORU}\n\n"
                                "Gercek VIDEO icin 'FFmpeg Yolu Ayarla' butonuyla ffmpeg.exe sec, "
                                "sonra bu adimi tekrar calistir - video otomatik da olusturulur."
                            )
                    else:
                        self._ilerlemeyi_durdur()
                        self.log_yaz(f"[HATA] kritarunner {donus_kodu} kodu ile bitti.")
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._krita_kuyrugunu_dinle)

    def _ilerlemeyi_durdur(self):
        """Islem (Krita/video) bittiginde donen ilerleme cubugunu durdurur/gizler."""
        try:
            self.krita_ilerleme_cubugu.stop()
            self.krita_ilerleme_cubugu.pack_forget()
        except Exception:
            pass

    def _videoyu_oynat(self):
        """Madde: 'panelden izleyebileyim' - Tkinter icinde gercek bir video
        oynatici gomulu degil (bu, ekstra agir kutuphaneler gerektirir),
        bunun yerine tek tikla bilgisayarin VARSAYILAN video programiyla
        ANINDA acar - klasore gitmene gerek kalmaz."""
        if not self._son_video_yolu or not os.path.exists(self._son_video_yolu):
            messagebox.showinfo("Video Yok", "Henuz oynatilacak bir video yok.")
            return
        try:
            os.startfile(self._son_video_yolu)
        except Exception as e:
            self.log_yaz(f"[HATA] Video oynatilamadi: {e}")
            messagebox.showerror("Hata", f"Video oynatilamadi:\n{e}")

    def _onizlemeyi_guncelle(self):
        """Madde: 'panelden direkt son yaptigimiza bakabilelim' - Dosya
        Gezgini'ne gitmeden son PNG ciktisini panelin icinde gosterir."""
        try:
            from PIL import Image, ImageTk
            proje_adi = getattr(self, "_son_proje_adi", None) or "kare_animasyon"
            png_yolu = os.path.join(CIKTI_KLASORU, f"{proje_adi}.png")
            if not os.path.exists(png_yolu):
                self.onizleme_etiketi.config(text="(cikti PNG bulunamadi)")
                return
            gorsel = Image.open(png_yolu)
            gorsel.thumbnail((220, 220))
            self._onizleme_resmi = ImageTk.PhotoImage(gorsel)  # referansi sakla, GC'ye kaptirma
            self.onizleme_etiketi.config(image=self._onizleme_resmi, text="", compound="top")
        except Exception as e:
            self.onizleme_etiketi.config(text=f"(onizleme yuklenemedi: {e})")


if __name__ == "__main__":
    pencere = ctk.CTk() if _CTK_VAR else tk.Tk()
    uygulama = KritaStudioPaneli(pencere)
    pencere.mainloop()