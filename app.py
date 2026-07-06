"""
app.py
------
Python Kaba Kurgu Motoru (Katmanli Animasyon Sistemi)

Saf Python backend - arayuz yok. Calistirmak icin:
    python app.py

Klasorler (otomatik olusur):
    input_backgrounds/  -> sahne arka plan gorselleri (jpg/png)
    input_characters/   -> karakterlerin transparan (alpha) PNG'leri
    input_audio/         -> arka plan muzigi (mp3/wav)
    output_shorts/       -> uretilen dikey mp4 videolari

script.txt (ana klasorde, yoksa otomatik ornek olusturulur):
    FORMAT: [SAHNE_SURESI] | [ARKA_PLAN_RESMI] | [KARAKTER:POZISYON:EFEKT , ...] | ["EKRAN_YAZISI"]
    ORNEK:
    3.0 | okul.jpg | rias:sol:sabit , issei:sag:zipla | "Rias-senpai! Sonunda buldum seni!"
"""

import os
import math
import random
import time as zaman_modulu
import sys

# Windows konsolunun eski kod sayfasi (cp1252 gibi) yuzunden Turkce karakterlerde
# veya herhangi bir ozel karakterde UnicodeEncodeError almamak icin, stdout/stderr'i
# acikca UTF-8'e zorluyoruz. Bu satirlar sorun cikarirsa sessizce yoksayilir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


from moviepy import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.audio.fx import AudioLoop
from PIL import Image

# ============================================================================
# BOLUM 1: KATMANLI KLASOR MIMARISI
# ============================================================================
TEMEL_KLASOR = os.path.dirname(os.path.abspath(__file__))
ARKAPLAN_KLASORU = os.path.join(TEMEL_KLASOR, "input_backgrounds")
KARAKTER_KLASORU = os.path.join(TEMEL_KLASOR, "input_characters")
SES_KLASORU = os.path.join(TEMEL_KLASOR, "input_audio")
CIKTI_KLASORU = os.path.join(TEMEL_KLASOR, "output_shorts")
SCRIPT_DOSYASI = os.path.join(TEMEL_KLASOR, "script.txt")

for klasor in (ARKAPLAN_KLASORU, KARAKTER_KLASORU, SES_KLASORU, CIKTI_KLASORU):
    os.makedirs(klasor, exist_ok=True)

HEDEF_GENISLIK = 1080
HEDEF_YUKSEKLIK = 1920

# Pozisyon -> X koordinati (spesifikasyona gore sabit)
POZISYON_X = {
    "sol": 216,
    "merkez": 540,
    "sag": 864,
}

ORNEK_SCRIPT_ICERIGI = (
    '3.0 | okul.jpg | rias:sol:sabit , issei:sag:zipla | "Rias-senpai! Sonunda buldum seni!"\n'
    '4.5 | savas.jpg | rias:merkez:titre | "Bu güç... İmkansız!"\n'
)


def script_yoksa_ornek_olustur():
    if not os.path.exists(SCRIPT_DOSYASI):
        with open(SCRIPT_DOSYASI, "w", encoding="utf-8") as f:
            f.write(ORNEK_SCRIPT_ICERIGI)
        print(f"'script.txt' bulunamadı, örnek bir şablon oluşturuldu: {SCRIPT_DOSYASI}")
        print("Lütfen bu dosyayı kendi sahnelerinle düzenleyip tekrar çalıştır.\n")
        return True  # yeni olusturuldu, kullanicinin duzenlemesi beklenmeli
    return False


# ============================================================================
# DOSYA BULMA YARDIMCILARI
# ============================================================================
def arkaplan_dosyasi_bul(dosya_adi):
    tam_yol = os.path.join(ARKAPLAN_KLASORU, dosya_adi)
    if os.path.exists(tam_yol):
        return tam_yol
    return None


def karakter_dosyasi_bul(karakter_adi):
    """Karakter ismiyle baslayan bir .png dosyasi arar (buyuk/kucuk harf duyarsiz)."""
    karakter_adi = karakter_adi.strip().lower()
    if not os.path.isdir(KARAKTER_KLASORU):
        return None
    for dosya in os.listdir(KARAKTER_KLASORU):
        if dosya.lower().startswith(karakter_adi) and dosya.lower().endswith(".png"):
            return os.path.join(KARAKTER_KLASORU, dosya)
    return None


# ============================================================================
# BOLUM 2.1: ARKA PLAN KATMANI (letterbox/crop + Ken Burns %3 zoom)
# ============================================================================
def arka_plani_hazirla(resim_yolu, gecici_yol):
    """Arka plani 1080x1920'ye ortalayarak sigdirir (letterbox), bozmadan."""
    resim = Image.open(resim_yolu).convert("RGB")
    oran = min(HEDEF_GENISLIK / resim.width, HEDEF_YUKSEKLIK / resim.height)
    yeni_genislik = max(1, int(resim.width * oran))
    yeni_yukseklik = max(1, int(resim.height * oran))
    resim = resim.resize((yeni_genislik, yeni_yukseklik))

    zemin = Image.new("RGB", (HEDEF_GENISLIK, HEDEF_YUKSEKLIK), (0, 0, 0))
    x = (HEDEF_GENISLIK - yeni_genislik) // 2
    y = (HEDEF_YUKSEKLIK - yeni_yukseklik) // 2
    zemin.paste(resim, (x, y))
    zemin.save(gecici_yol)
    return gecici_yol


def arkaplan_klibi_olustur(resim_yolu, sahne_suresi):
    """Ken Burns: sahne suresi boyunca %3 icine dogru akici zoom."""
    klip = ImageClip(resim_yolu).with_duration(sahne_suresi)
    klip = klip.resized(lambda t: 1.0 + 0.03 * (t / sahne_suresi))
    klip = klip.with_position(("center", "center"))
    return klip


# ============================================================================
# BOLUM 2.2: KARAKTER KATMANI (pozisyon + animasyon matematigi)
# ============================================================================
def karakter_klibi_olustur(karakter_png_yolu, pozisyon, efekt, sahne_suresi):
    """
    Transparan karakter PNG'sini, verilen pozisyon ve efekte gore
    hareket eden bir klip haline getirir.
    """
    karakter_klip = ImageClip(karakter_png_yolu).with_duration(sahne_suresi)

    x_pos = POZISYON_X.get(pozisyon, POZISYON_X["merkez"])
    # Karakterin ALTI ekran tabanina (y=1920) sifirlanir:
    karakter_yuksekligi = karakter_klip.h
    y_base = HEDEF_YUKSEKLIK - karakter_yuksekligi

    # x_pos, karakterin yatayda ortalanacagi merkez X koordinati kabul edilir.
    # Klip pozisyonu (moviepy) sol-ust kosedir, bu yuzden genislik/2 kadar kaydiriyoruz.
    karakter_genisligi = karakter_klip.w
    x_sol_kenar = x_pos - (karakter_genisligi / 2)

    if efekt == "zipla":
        def konum(t):
            return (x_sol_kenar, y_base - abs(math.sin(t * math.pi * 2) * 30))
    elif efekt == "titre":
        def konum(t):
            return (x_sol_kenar + random.randint(-6, 6), y_base + random.randint(-6, 6))
    else:  # 'sabit' veya taninmayan efekt -> sabit dur
        def konum(t):
            return (x_sol_kenar, y_base)

    karakter_klip = karakter_klip.with_position(konum)
    return karakter_klip


# ============================================================================
# BOLUM 3.2: POP-UP ALTYAZI (sahne basina bir kere, %10 buyume ile patlama)
# ============================================================================
ALTYAZI_FONT_ADAYLARI = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\Impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _altyazi_fontu_bul():
    for aday in ALTYAZI_FONT_ADAYLARI:
        if os.path.exists(aday):
            return aday
    return None


def _pop_olcek_fonksiyonu(sahne_suresi):
    pop_suresi = min(0.1, sahne_suresi / 2)

    def olcek(t):
        if t < pop_suresi:
            return 0.9 + 0.1 * (t / pop_suresi)
        return 1.0

    return olcek


def altyazi_klibi_olustur(metin, sahne_suresi):
    if not metin:
        return None
    font_yolu = _altyazi_fontu_bul()
    try:
        klip = TextClip(
            text=metin,
            font=font_yolu,
            font_size=75,
            color="white",
            stroke_color="black",
            stroke_width=5,
            method="label",
        )
    except Exception as hata:
        print(f"  (Altyazı uyarısı: metin oluşturulamadı, atlanıyor: {hata})")
        return None

    klip = klip.with_duration(sahne_suresi)
    klip = klip.resized(_pop_olcek_fonksiyonu(sahne_suresi))
    # y=1500 alt-orta konum; x eksenini ortalamak icin 'center' kullaniyoruz
    klip = klip.with_position(("center", 1500))
    return klip


# ============================================================================
# SCRIPT.TXT AYRISTIRICI
# ============================================================================
def script_satirini_ayristir(satir, satir_no):
    """
    '3.0 | okul.jpg | rias:sol:sabit , issei:sag:zipla | "metin"' satirini
    ayristirir. Hatali/eksik satirlarda None doner ve uyari basar (crash yok).
    """
    parcalar = [p.strip() for p in satir.split("|")]
    if len(parcalar) != 4:
        print(f"  UYARI: Satır {satir_no} atlandı (4 bölüm bekleniyor, {len(parcalar)} bulundu): {satir}")
        return None

    try:
        sahne_suresi = float(parcalar[0])
    except ValueError:
        print(f"  UYARI: Satır {satir_no} atlandı (süre sayı değil): {parcalar[0]}")
        return None

    arkaplan_adi = parcalar[1]
    karakter_tanimlari = parcalar[2]
    metin_ham = parcalar[3].strip().strip('"')

    karakterler = []
    if karakter_tanimlari:
        for tanim in karakter_tanimlari.split(","):
            tanim = tanim.strip()
            if not tanim:
                continue
            alt_parcalar = tanim.split(":")
            if len(alt_parcalar) != 3:
                print(f"  UYARI: Satır {satir_no}: karakter tanımı hatalı, atlandı: '{tanim}'")
                continue
            ad, pozisyon, efekt = [p.strip().lower() for p in alt_parcalar]
            karakterler.append((ad, pozisyon, efekt))

    return {
        "sure": sahne_suresi,
        "arkaplan": arkaplan_adi,
        "karakterler": karakterler,
        "metin": metin_ham,
    }


def scripti_oku():
    with open(SCRIPT_DOSYASI, "r", encoding="utf-8") as f:
        satirlar = [s for s in f.read().splitlines() if s.strip() and not s.strip().startswith("#")]

    sahneler = []
    for i, satir in enumerate(satirlar, start=1):
        sahne = script_satirini_ayristir(satir, i)
        if sahne:
            sahneler.append(sahne)
    return sahneler


# ============================================================================
# BOLUM 3.1 + 4: SES ENTEGRASYONU + RENDER
# ============================================================================
def muzik_dosyasi_bul():
    if not os.path.isdir(SES_KLASORU):
        return None
    for dosya in sorted(os.listdir(SES_KLASORU)):
        if dosya.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
            return os.path.join(SES_KLASORU, dosya)
    return None


def muzigi_hazirla(toplam_sure):
    """Muzigi bulur, gerekirse dongusel tekrarlar, tam toplam_sure'ye kirpar."""
    muzik_yolu = muzik_dosyasi_bul()
    if not muzik_yolu:
        print("UYARI: 'input_audio' klasöründe müzik bulunamadı, video sessiz olacak.")
        return None

    ses = AudioFileClip(muzik_yolu)
    if ses.duration < toplam_sure:
        ses = ses.with_effects([AudioLoop(duration=toplam_sure)])
    else:
        ses = ses.subclipped(0, toplam_sure)
    return ses


# ============================================================================
# ANA PIPELINE
# ============================================================================
def sahneyi_isle(sahne, sahne_no, gecici_klasor):
    print(f"  Sahne {sahne_no}: süre={sahne['sure']}sn, arkaplan='{sahne['arkaplan']}', "
          f"{len(sahne['karakterler'])} karakter")

    arkaplan_yolu = arkaplan_dosyasi_bul(sahne["arkaplan"])
    if not arkaplan_yolu:
        print(f"    UYARI: Arka plan bulunamadı: '{sahne['arkaplan']}' -> düz siyah zeminle devam ediliyor.")
        gecici_arkaplan = os.path.join(gecici_klasor, f"siyah_{sahne_no}.jpg")
        Image.new("RGB", (HEDEF_GENISLIK, HEDEF_YUKSEKLIK), (0, 0, 0)).save(gecici_arkaplan)
        arkaplan_yolu = gecici_arkaplan
    else:
        islenmis_arkaplan = os.path.join(gecici_klasor, f"arkaplan_{sahne_no}.jpg")
        arka_plani_hazirla(arkaplan_yolu, islenmis_arkaplan)
        arkaplan_yolu = islenmis_arkaplan

    katmanlar = [arkaplan_klibi_olustur(arkaplan_yolu, sahne["sure"])]

    for ad, pozisyon, efekt in sahne["karakterler"]:
        karakter_yolu = karakter_dosyasi_bul(ad)
        if not karakter_yolu:
            print(f"    UYARI: Karakter bulunamadı: '{ad}' (input_characters içine '{ad}.png' at) -> atlandı.")
            continue
        katmanlar.append(karakter_klibi_olustur(karakter_yolu, pozisyon, efekt, sahne["sure"]))

    altyazi = altyazi_klibi_olustur(sahne["metin"], sahne["sure"])
    if altyazi:
        katmanlar.append(altyazi)

    sahne_klibi = CompositeVideoClip(katmanlar, size=(HEDEF_GENISLIK, HEDEF_YUKSEKLIK))
    sahne_klibi = sahne_klibi.with_duration(sahne["sure"])
    return sahne_klibi


def video_uret():
    yeni_olusturuldu = script_yoksa_ornek_olustur()
    if yeni_olusturuldu:
        return None

    sahneler = scripti_oku()
    if not sahneler:
        print("UYARI: 'script.txt' içinde geçerli hiçbir sahne bulunamadı. Lütfen dosyayı kontrol et.")
        return None

    print(f"{len(sahneler)} sahne bulundu. İşlem başlıyor...\n")

    gecici_klasor = os.path.join(TEMEL_KLASOR, "_gecici")
    os.makedirs(gecici_klasor, exist_ok=True)

    sahne_klipleri = []
    for i, sahne in enumerate(sahneler, start=1):
        sahne_klipleri.append(sahneyi_isle(sahne, i, gecici_klasor))

    print("\nSahneler diziliyor (kaba kurgu birleştiriliyor)...")
    video = concatenate_videoclips(sahne_klipleri, method="compose")

    toplam_sure = video.duration
    print(f"Toplam video süresi: {toplam_sure:.2f} sn")

    muzik = muzigi_hazirla(toplam_sure)
    if muzik:
        video = video.with_audio(muzik)

    cikti_adi = f"kaba_kurgu_{int(zaman_modulu.time())}.mp4"
    cikti_yolu = os.path.join(CIKTI_KLASORU, cikti_adi)

    print(f"\nRender başlıyor -> {cikti_yolu}")
    video.write_videofile(
        cikti_yolu,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=8,
        preset="ultrafast",
        logger=None,
    )

    print(f"\nBİTTİ! Kaba kurgu hazır: {cikti_yolu}")
    return cikti_yolu


if __name__ == "__main__":
    video_uret()
