"""
app.py
------
Dinamik Manga/Chibi Animasyon Motoru - Enterprise Refactor

Mimari ozeti:
- Regex tabanli, hataya dayanikli script.txt parser
- URL indirme (requests) + URI sanitization (urlparse + mimetypes)
- Cift katmanli fallback: eksik karakter -> default_char.png,
  eksik arka plan -> bellek-ici (in-memory) siyah canvas (disk'e hic yazmadan)
- Her render sonrasi, After Effects'in okuyabilecegi bir JSON metadata dosyasi
  (sahne/karakter/animasyon verileri) uretilir
- Tum hata yonetimi 'try-except + logging', sys.exit YOK (her zaman bir
  sonraki satira/sahneye devam eder)

NOT (bu surumde script.txt formati DEGISTI):
  ESKI:   rias:sol:sabit
  YENI:   rias:pozisyon=sol animasyon=sabit
  (Elemanlar artik key=value ciftleri seklinde, bosluklarla ayrilmis.)
"""

import os
import sys
import re
import json
import logging
import mimetypes
import time as zaman_modulu
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image
from moviepy import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
    vfx,
)
from moviepy.audio.fx import AudioLoop

# ============================================================================
# UTF-8 GUVENLIGI (Windows konsolunda UnicodeEncodeError almamak icin)
# ============================================================================
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================================
# LOGGING (sys.exit YOK; her hata loglanip devam edilir)
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("manga_engine")

# ============================================================================
# KLASOR MIMARISI
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARKAPLAN_KLASORU = os.path.join(BASE_DIR, "input_backgrounds")
KARAKTER_KLASORU = os.path.join(BASE_DIR, "input_characters")
SES_KLASORU = os.path.join(BASE_DIR, "input_audio")
CIKTI_KLASORU = os.path.join(BASE_DIR, "output_shorts")
SCRIPT_DOSYASI = os.path.join(BASE_DIR, "script.txt")
VARSAYILAN_KARAKTER = os.path.join(KARAKTER_KLASORU, "default_char.png")

for klasor in (ARKAPLAN_KLASORU, KARAKTER_KLASORU, SES_KLASORU, CIKTI_KLASORU):
    os.makedirs(klasor, exist_ok=True)

HEDEF_GENISLIK = 1080
HEDEF_YUKSEKLIK = 1920
HEDEF_FPS = 30

POZISYON_X = {"sol": 216, "merkez": 540, "sag": 864}

# animasyon adi -> After Effects tarafinin anlayacagi enum ismi
ANIMASYON_ENUM = {
    "zipla": "bounce_expression",
    "titre": "wiggle_expression",
    "sabit": "static_expression",
}

# ============================================================================
# REGEX MOTORU
# ============================================================================
# duration | scene | elements (| caption) -- caption opsiyonel bir 4. alan
# olarak eklendi (orijinal 3 grubu BIREBIR koruyarak).
SATIR_REGEX = re.compile(
    r"^\s*(?P<duration>\d+(?:\.\d+)?)\s*\|\s*(?P<scene>\S+)\s*\|\s*"
    r"(?P<elements>[^|]*)(?:\|\s*(?P<caption>.*))?$"
)
ELEMENT_REGEX = re.compile(r"^(?P<name>\S+):(?P<kv_pairs>.*)$")


def _varsayilan_karakteri_olustur_eger_yoksa():
    """default_char.png hicbir zaman eksik olmasin diye, yoksa basit bir
    seffaf placeholder siluet otomatik olusturulur (dis kaynak gerekmez)."""
    if os.path.exists(VARSAYILAN_KARAKTER):
        return
    try:
        img = Image.new("RGBA", (300, 600), (0, 0, 0, 0))
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        d.ellipse([90, 30, 210, 150], fill=(150, 150, 160, 255))
        d.rectangle([100, 150, 200, 480], fill=(120, 120, 135, 255))
        img.save(VARSAYILAN_KARAKTER)
        log.info("default_char.png bulunamadigi icin otomatik olusturuldu.")
    except Exception as e:
        log.error(f"default_char.png olusturulamadi: {e}")


def kv_ciftlerini_ayristir(kv_pairs):
    """
    'pozisyon=sol animasyon=zipla' -> {'pozisyon': 'sol', 'animasyon': 'zipla'}
    NOT: Istekte verilen orijinal dict comprehension'da 'v' degiskeni hic
    tanimlanmamisti (calisirsa NameError verirdi) - burada ayni niyeti
    (bosluk ayrilmis key=value ciftlerini dict'e cevirmek) DOGRU sekilde
    uyguluyoruz.
    """
    sonuc = {}
    for pair in kv_pairs.split():
        if "=" in pair:
            k, v = pair.split("=", 1)
            sonuc[k.strip()] = v.strip()
        else:
            log.error(f"Row parsing failed: gecersiz key=value ciftii atlandi: '{pair}'")
    return sonuc


def satiri_parse_et(satir, satir_no):
    """Regex tabanli, hataya dayanikli tekil satir parser'i. Hata durumunda
    None doner, logging.error ile loglanir, 'continue' mantigiyla ust
    fonksiyonda bir sonraki satira gecilir (islem asla durmaz)."""
    try:
        eslesme = SATIR_REGEX.match(satir)
        if not eslesme:
            if "|" not in satir:
                # Kullanici muhtemelen eski/yanlis formatta yaziyor
                # (orn: 'sahne: link, sure: 4' gibi) -> ozel, anlasilir uyari
                logging.error(
                    "[HATA] Lutfen guncel 'sure | arka_plan | karakter' formatini kullanin!"
                )
            else:
                logging.error(f"Row parsing failed: satir {satir_no} formatla eslesmedi: '{satir}'")
            return None

        sure = float(eslesme.group("duration"))
        sahne_gorseli = eslesme.group("scene")
        elements_ham = eslesme.group("elements") or ""
        caption = (eslesme.group("caption") or "").strip().strip('"')

        elementler = []
        for parca in elements_ham.split(","):
            parca = parca.strip()
            if not parca:
                continue
            element_eslesme = ELEMENT_REGEX.match(parca)
            if not element_eslesme:
                logging.error(f"Row parsing failed: element eslesmedi, atlandi: '{parca}'")
                continue
            ad = element_eslesme.group("name")
            kv = kv_ciftlerini_ayristir(element_eslesme.group("kv_pairs"))
            elementler.append({
                "ad": ad,
                "pozisyon": kv.get("pozisyon", "merkez").lower(),
                "animasyon": kv.get("animasyon", "sabit").lower(),
            })

        return {"sure": sure, "arkaplan": sahne_gorseli, "karakterler": elementler, "metin": caption}

    except Exception as e:
        logging.error(f"Row parsing failed: satir {satir_no} beklenmeyen hata: {e}")
        return None


def scripti_oku():
    if not os.path.exists(SCRIPT_DOSYASI):
        log.warning("script.txt bulunamadi.")
        return []

    try:
        with open(SCRIPT_DOSYASI, "r", encoding="utf-8") as f:
            satirlar = f.read().splitlines()
    except Exception as e:
        logging.error(f"script.txt okunamadi: {e}")
        return []

    sahneler = []
    for i, satir in enumerate(satirlar, start=1):
        satir = satir.strip()
        if not satir or satir.startswith("#"):
            continue
        sahne = satiri_parse_et(satir, i)
        if sahne:
            sahneler.append(sahne)
    return sahneler


# ============================================================================
# URI SANITIZATION + INDIRME (requests tabanli)
# ============================================================================
_GECERLI_MIME_ONEKI = "image/"


def url_gecerli_mi(deger):
    try:
        ayristirilmis = urlparse(deger)
        return ayristirilmis.scheme in ("http", "https") and bool(ayristirilmis.netloc)
    except Exception:
        return False


def uzantiyi_dogrula(url):
    """Query string'leri bypass ederek (?width=100 vb.) saf uzantiyi cikarir,
    mimetypes ile dogrular. Gecersiz/bilinmeyen ise .jpg varsayilan doner."""
    yol_kismi = urlparse(url).path
    uzanti = os.path.splitext(yol_kismi)[1].lower()

    mime_turu, _ = mimetypes.guess_type("dosya" + uzanti)
    if mime_turu and mime_turu.startswith(_GECERLI_MIME_ONEKI):
        return uzanti
    return ".jpg"


def gorseli_indir(url, hedef_klasor):
    """requests ile indirir (stream=True), URI sanitization uygular.
    Basarisiz olursa (RequestException) None doner, cagiran taraf
    kendi fallback mekanizmasini (default_char / siyah canvas) kullanir."""
    try:
        if not url_gecerli_mi(url):
            logging.error(f"Gecersiz URL, indirilmedi: {url}")
            return None

        uzanti = uzantiyi_dogrula(url)
        import hashlib
        dosya_adi = hashlib.md5(url.encode("utf-8")).hexdigest() + uzanti
        hedef_yol = os.path.join(hedef_klasor, dosya_adi)

        if os.path.exists(hedef_yol):
            log.info(f"Zaten indirilmis, tekrar indirilmiyor: {dosya_adi}")
            return hedef_yol

        log.info(f"Indiriliyor: {url}")
        yanit = requests.get(url, timeout=10, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        yanit.raise_for_status()

        with open(hedef_yol, "wb") as f:
            for parca in yanit.iter_content(chunk_size=8192):
                f.write(parca)

        log.info(f"Indirildi: {dosya_adi}")
        return hedef_yol

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP indirme hatasi ({url}): {e}")
        return None
    except Exception as e:
        logging.error(f"Beklenmeyen indirme hatasi ({url}): {e}")
        return None


def yerel_dosya_bul(klasor, ad):
    tam_yol = os.path.join(klasor, ad)
    return tam_yol if os.path.exists(tam_yol) else None


def yerel_karakter_bul(klasor, ad):
    ad_kucuk = ad.strip().lower()
    if not os.path.isdir(klasor):
        return None
    for dosya in os.listdir(klasor):
        if dosya.lower().startswith(ad_kucuk) and dosya.lower().endswith(".png"):
            return os.path.join(klasor, dosya)
    return None


def arkaplan_yolunu_coz(deger):
    """URL ise indirir; degilse yerelde arar. Ikisi de basarisiz olursa
    None doner (cagiran taraf bellek-ici siyah canvas kullanir)."""
    if url_gecerli_mi(deger):
        return gorseli_indir(deger, ARKAPLAN_KLASORU)
    return yerel_dosya_bul(ARKAPLAN_KLASORU, deger)


def karakter_yolunu_coz(ad):
    """URL ise indirir; degilse yerelde arar. Ikisi de basarisiz olursa
    default_char.png yoluna fallback yapilir (HICBIR ZAMAN None donmez)."""
    yol = gorseli_indir(ad, KARAKTER_KLASORU) if url_gecerli_mi(ad) else yerel_karakter_bul(KARAKTER_KLASORU, ad)
    if yol:
        return yol
    logging.error(f"Karakter bulunamadi/indirilemedi: '{ad}' -> default_char.png kullaniliyor")
    _varsayilan_karakteri_olustur_eger_yoksa()
    return VARSAYILAN_KARAKTER if os.path.exists(VARSAYILAN_KARAKTER) else None


# ============================================================================
# GORUNTU ISLEME (letterbox + In-Memory fallback canvas)
# ============================================================================
def dikey_formata_getir(resim_yolu_veya_None, gecici_yol):
    """
    resim_yolu_veya_None gecerliyse dosyayi 1080x1920'ye sigdirir.
    None ise (arka plan bulunamadiysa) DISKE HIC YAZMADAN, bellek-ici
    (numpy) siyah bir canvas uretip onu kullanir (spesifikasyondaki
    np.zeros((1920,1080,3)) mantigi).
    """
    if resim_yolu_veya_None is None:
        logging.error("Arka plan bulunamadi -> bellek-ici (in-memory) siyah canvas kullaniliyor.")
        return np.zeros((HEDEF_YUKSEKLIK, HEDEF_GENISLIK, 3), dtype=np.uint8)

    try:
        resim = Image.open(resim_yolu_veya_None).convert("RGB")
        oran = min(HEDEF_GENISLIK / resim.width, HEDEF_YUKSEKLIK / resim.height)
        yeni_genislik = max(1, int(resim.width * oran))
        yeni_yukseklik = max(1, int(resim.height * oran))
        resim = resim.resize((yeni_genislik, yeni_yukseklik))

        zemin = Image.new("RGB", (HEDEF_GENISLIK, HEDEF_YUKSEKLIK), (0, 0, 0))
        x = (HEDEF_GENISLIK - yeni_genislik) // 2
        y = (HEDEF_YUKSEKLIK - yeni_yukseklik) // 2
        zemin.paste(resim, (x, y))
        return np.array(zemin)
    except Exception as e:
        logging.error(f"Arka plan islenemedi ({resim_yolu_veya_None}): {e} -> siyah canvas kullaniliyor.")
        return np.zeros((HEDEF_YUKSEKLIK, HEDEF_GENISLIK, 3), dtype=np.uint8)


# ============================================================================
# SINEMATIK KAMERA + KARAKTER KATMANLARI
# ============================================================================
def arkaplan_klibi_olustur(numpy_dizisi, sure, zoom_orani=0.03):
    klip = ImageClip(numpy_dizisi).with_duration(sure)
    klip = klip.resized(lambda t: 1.0 + zoom_orani * (t / sure))
    klip = klip.with_position(("center", "center"))
    return CompositeVideoClip([klip], size=(HEDEF_GENISLIK, HEDEF_YUKSEKLIK)).with_duration(sure)


def karakter_gorselini_rgba_yukle(karakter_yolu):
    """
    Karakter gorselini PIL ile acip ACIKCA RGBA'ya cevirir, sonra numpy
    dizisi olarak dondurur. Bu, indirilen bazi PNG'lerin (ozellikle
    palet-modlu / P-mode transparency kullananlarin) MoviePy tarafindan
    dogrudan dosya yolundan yuklenince alfa/seffaflik bilgisini
    KAYBETMESINI engeller (aksi halde karakterin arkasinda siyah/beyaz
    dikdortgen kutular olusur).
    """
    img = Image.open(karakter_yolu).convert("RGBA")
    return np.array(img)


def karakter_klibi_olustur(karakter_yolu, pozisyon, animasyon, sure):
    try:
        karakter_dizisi = karakter_gorselini_rgba_yukle(karakter_yolu)
        klip = ImageClip(karakter_dizisi).with_duration(sure)
    except Exception as e:
        logging.error(f"Karakter goruntusu yuklenemedi ({karakter_yolu}): {e}")
        return None

    genislik, yukseklik = klip.w, klip.h
    klip = klip.with_anchor((genislik / 2, yukseklik)) if hasattr(klip, "with_anchor") else klip

    x_pos = POZISYON_X.get(pozisyon, POZISYON_X["merkez"])
    y_base = HEDEF_YUKSEKLIK - yukseklik

    try:
        if animasyon == "zipla":
            def konum(t):
                return (x_pos - genislik / 2, y_base - abs(np.sin(t * np.pi * 2)) * 30)
            klip = klip.with_position(konum)
        elif animasyon == "titre":
            import random as _rastgele
            def konum(t):
                return (x_pos - genislik / 2 + _rastgele.randint(-6, 6),
                        y_base + _rastgele.randint(-6, 6))
            klip = klip.with_position(konum)
        else:  # sabit
            klip = klip.with_position((x_pos - genislik / 2, y_base))
    except Exception as e:
        logging.error(f"Karakter animasyonu uygulanamadi ({animasyon}): {e}")
        klip = klip.with_position((x_pos - genislik / 2, y_base))

    return CompositeVideoClip([klip], size=(HEDEF_GENISLIK, HEDEF_YUKSEKLIK)).with_duration(sure)


ALTYAZI_FONT_ADAYLARI = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font_bul():
    for aday in ALTYAZI_FONT_ADAYLARI:
        if os.path.exists(aday):
            return aday
    return None


def altyazi_klibi_olustur(metin, sure):
    if not metin:
        return None
    try:
        klip = TextClip(
            text=metin, font=_font_bul(), font_size=70, color="white",
            stroke_color="black", stroke_width=4, method="label",
        ).with_duration(sure).with_position(("center", int(HEDEF_YUKSEKLIK * 0.75)))
        return klip
    except Exception as e:
        logging.error(f"Altyazi olusturulamadi: {e}")
        return None


def gecisli_birlestir(klipler, gecis_suresi=0.25):
    if gecis_suresi <= 0 or len(klipler) < 2:
        return concatenate_videoclips(klipler)
    sonuc = [klipler[0]]
    baslangic = klipler[0].duration - gecis_suresi
    for klip in klipler[1:]:
        gs = min(gecis_suresi, klip.duration / 2, klipler[0].duration)
        klip_fade = klip.with_effects([vfx.CrossFadeIn(gs)]).with_start(max(baslangic, 0))
        sonuc.append(klip_fade)
        baslangic += klip.duration - gs
    return CompositeVideoClip(sonuc, size=(HEDEF_GENISLIK, HEDEF_YUKSEKLIK)).with_duration(baslangic + gecis_suresi)


# ============================================================================
# MUZIK
# ============================================================================
def muzik_dosyasi_bul():
    if not os.path.isdir(SES_KLASORU):
        return None
    for dosya in sorted(os.listdir(SES_KLASORU)):
        if dosya.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
            return os.path.join(SES_KLASORU, dosya)
    return None


def muzigi_hazirla(toplam_sure):
    yol = muzik_dosyasi_bul()
    if not yol:
        log.warning("input_audio klasorunde muzik bulunamadi, video sessiz olacak.")
        return None
    try:
        ses = AudioFileClip(yol)
        if ses.duration < toplam_sure:
            ses = ses.with_effects([AudioLoop(duration=toplam_sure)])
        else:
            ses = ses.subclipped(0, toplam_sure)
        return ses
    except Exception as e:
        logging.error(f"Muzik yuklenemedi: {e}")
        return None


# ============================================================================
# JSON METADATA ENGINE (After Effects icin)
# ============================================================================
def metadata_json_yaz(cikti_video_yolu, sahneler):
    json_yolu = os.path.splitext(cikti_video_yolu)[0] + ".json"
    baslangic = 0.0
    sahne_meta = []

    for sahne in sahneler:
        karakter_meta = []
        for k in sahne["karakterler"]:
            x = POZISYON_X.get(k["pozisyon"], POZISYON_X["merkez"])
            karakter_meta.append({
                "ad": k["ad"],
                "pozisyon": k["pozisyon"],
                "x": x,
                "y": HEDEF_YUKSEKLIK,
                "animasyon": k["animasyon"],
                "animasyon_enum": ANIMASYON_ENUM.get(k["animasyon"], "static_expression"),
            })

        sahne_meta.append({
            "baslangic_zamani": round(baslangic, 3),
            "sure": sahne["sure"],
            "arkaplan": sahne["arkaplan"],
            "karakterler": karakter_meta,
            "metin": sahne["metin"],
        })
        baslangic += sahne["sure"]

    metadata = {
        "video_dosyasi": os.path.basename(cikti_video_yolu),
        "genislik": HEDEF_GENISLIK,
        "yukseklik": HEDEF_YUKSEKLIK,
        "fps": HEDEF_FPS,
        "toplam_sure": round(baslangic, 3),
        "sahneler": sahne_meta,
    }

    try:
        with open(json_yolu, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        log.info(f"Metadata JSON yazildi: {json_yolu}")
    except Exception as e:
        logging.error(f"Metadata JSON yazilamadi: {e}")

    return json_yolu


# ============================================================================
# ANA PIPELINE
# ============================================================================
def sahneyi_isle(sahne, sahne_no):
    log.info(f"Sahne {sahne_no}: sure={sahne['sure']}sn, arkaplan='{sahne['arkaplan']}', "
             f"{len(sahne['karakterler'])} karakter")

    arkaplan_yolu = arkaplan_yolunu_coz(sahne["arkaplan"])
    arkaplan_dizisi = dikey_formata_getir(arkaplan_yolu, None)
    katmanlar = [arkaplan_klibi_olustur(arkaplan_dizisi, sahne["sure"])]

    for k in sahne["karakterler"]:
        karakter_yolu = karakter_yolunu_coz(k["ad"])
        if karakter_yolu:
            karakter_klip = karakter_klibi_olustur(karakter_yolu, k["pozisyon"], k["animasyon"], sahne["sure"])
            if karakter_klip:
                katmanlar.append(karakter_klip)

    altyazi = altyazi_klibi_olustur(sahne["metin"], sahne["sure"])
    if altyazi:
        katmanlar.append(altyazi)

    return CompositeVideoClip(katmanlar, size=(HEDEF_GENISLIK, HEDEF_YUKSEKLIK)).with_duration(sahne["sure"])


def video_uret():
    _varsayilan_karakteri_olustur_eger_yoksa()

    sahneler = scripti_oku()
    if not sahneler:
        log.warning("script.txt icinde gecerli hicbir sahne bulunamadi.")
        return None

    log.info(f"{len(sahneler)} sahne bulundu. Islem basliyor.")

    sahne_klipleri = []
    for i, sahne in enumerate(sahneler, start=1):
        try:
            sahne_klipleri.append(sahneyi_isle(sahne, i))
        except Exception as e:
            logging.error(f"Sahne {i} islenemedi, atlaniyor: {e}")
            continue

    if not sahne_klipleri:
        log.warning("Hicbir sahne basariyla islenemedi, video uretilemedi.")
        return None

    video = gecisli_birlestir(sahne_klipleri, gecis_suresi=0.25)
    toplam_sure = video.duration
    log.info(f"Toplam video suresi: {toplam_sure:.2f} sn")

    muzik = muzigi_hazirla(toplam_sure)
    if muzik:
        video = video.with_audio(muzik)

    cikti_adi = f"kaba_kurgu_{int(zaman_modulu.time())}.mp4"
    cikti_yolu = os.path.join(CIKTI_KLASORU, cikti_adi)

    log.info(f"Render basliyor -> {cikti_yolu}")
    try:
        video.write_videofile(
            cikti_yolu, fps=HEDEF_FPS, codec="libx264", audio_codec="aac",
            threads=8, preset="ultrafast", logger=None,
        )
    except Exception as e:
        logging.error(f"Render basarisiz: {e}")
        return None

    metadata_json_yaz(cikti_yolu, sahneler)

    log.info(f"BITTI! Kaba kurgu hazir: {cikti_yolu}")
    # kontrol_paneli.py bu satiri arayip son video yolunu yakalayacak:
    print(f"RENDER_COMPLETE:{cikti_yolu}")
    return cikti_yolu


if __name__ == "__main__":
    video_uret()
