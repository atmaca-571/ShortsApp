"""
ae_studio_paneli.py
--------------------
Canavar Asistan - AE Studio Paneli (Basitlestirilmis, Tamamen AE-Odakli Surum)

BU SURUMDE ESKI PYTHON VIDEO MOTORU (app.py / moviepy render) TAMAMEN
KALDIRILDI. Bu program artik video RENDER ETMIYOR - sadece:

  1) Sana gorsel secip, surukleyip, sahne sahne DIZMENI saglayan bir
     arayuz sunuyor (script.txt'yi ELLE YAZMANA gerek KALMIYOR),
  2) Karakter gorsellerinin arka planini (varsa duz/beyaz zeminliyse)
     OTOMATIK temizliyor (bu bir 'video motoru' degil, sadece resim
     hazirlama adimi - saniyeler icinde biter, video render etmez),
  3) script.txt dosyasini SENIN ICIN otomatik yaziyor,
  4) After Effects'i, 'canavar_asistan.jsx' ile birlikte baslatiyor.

Butun gercek animasyon/render isi artik TAMAMEN After Effects'te oluyor.

Calistirmak icin:
    python ae_studio_paneli.py
"""

import os
import sys
import json
import subprocess
import threading
import queue
import shutil
import urllib.request
import urllib.error
from collections import deque

import numpy as np
from PIL import Image

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, scrolledtext, ttk

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================================
# HATA LOG DOSYASI (pythonw.exe ile calisirken konsol GORUNMEZ - yani
# normalde bir hata olursa HICBIR IZ kalmaz, program sessizce kapanir.
# Bu yuzden acilista TUM beklenmeyen hatalari bir log dosyasina yazan bir
# guvenlik agi kuruyoruz. Program acilmiyorsa, bu dosyaya bak.)
# ============================================================================
import logging
import traceback

_HATA_LOG_YOLU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ae_studio_hata_log.txt")
logging.basicConfig(
    filename=_HATA_LOG_YOLU, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8"
)

# pythonw.exe altinda sys.stdout/sys.stderr None olabilir - buna yazan
# herhangi bir kod (beklenmedik sekilde) cokmesin diye guvenli hale getir.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def _beklenmeyen_hata_yakala(exc_type, exc_value, exc_tb):
    logging.error("YAKALANMAMIS HATA:\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    try:
        messagebox.showerror(
            "Beklenmeyen Hata",
            f"Program beklenmedik bir hatayla karsilasti.\n\nDetaylar icin:\n{_HATA_LOG_YOLU}"
        )
    except Exception:
        pass  # Tkinter bile baslamamis olabilir, sessizce gec


sys.excepthook = _beklenmeyen_hata_yakala

# ============================================================================
# YOLLAR
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARKAPLAN_KLASORU = os.path.join(BASE_DIR, "input_backgrounds")
KARAKTER_KLASORU = os.path.join(BASE_DIR, "input_characters")
VIDEO_KLASORU = os.path.join(BASE_DIR, "input_videos")
SCRIPT_TXT_YOLU = os.path.join(BASE_DIR, "script.txt")
PANEL_CONFIG_YOLU = os.path.join(BASE_DIR, "panel_config.json")
SAHNE_LISTESI_YOLU = os.path.join(BASE_DIR, "sahne_listesi.json")

for _klasor in (ARKAPLAN_KLASORU, KARAKTER_KLASORU, VIDEO_KLASORU):
    os.makedirs(_klasor, exist_ok=True)

POZISYONLAR = ["sol", "merkez", "sag"]
# NOT: 'yuru_*' animasyonlari BURADA YOK. Onlar sadece eski Python video
# motorunda vardi; canavar_asistan.jsx (AE scripti) SU AN sadece asagidaki
# ucunu destekliyor. Ileride JSX'e yurume eklenirse buraya da eklenecek.
ANIMASYONLAR = ["sabit", "zipla", "titre", "yuru_sagdan_sola", "yuru_soldan_saga"]

# Karakterin sahne icinde NASIL belirip NASIL kaybolacagi (Position hareketinden
# BAGIMSIZ, Opacity ile calisir - hepsiyle birlikte kullanilabilir)
GIRIS_CIKIS_SECENEKLERI = {"Yok (aninda)": "yok", "Solarak (yumusak)": "solma"}

# Sahneler arasi gecis tipi
SAHNE_GECIS_SECENEKLERI = {"Otomatik (yumusak gecis)": "oto", "Kes (sert kesme)": "kes"}

# Arka plan hareket tipleri: goruntulenen isim -> script.txt'ye yazilacak kod
ARKAPLAN_HAREKETLERI = {
    "Yakinlasma (varsayilan)": "zoom",
    "Sagdan Sola Kaydir (tren/arac gibi)": "kaydir_sagdan_sola",
    "Soldan Saga Kaydir": "kaydir_soldan_saga",
}

RENK_KURGU_BG = "#673AB7"
RENK_AE_BG = "#E53935"
RENK_KLASOR_BG = "#37474F"
RENK_KAYDET_BG = "#2E7D32"
RENK_BEYAZ = "#FFFFFF"
RENK_LOG_BG = "#000000"
RENK_LOG_FG = "#00FF00"


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


def sahneleri_yukle():
    if os.path.exists(SAHNE_LISTESI_YOLU):
        try:
            with open(SAHNE_LISTESI_YOLU, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def sahneleri_kaydet(sahneler):
    try:
        with open(SAHNE_LISTESI_YOLU, "w", encoding="utf-8") as f:
            json.dump(sahneler, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================================
# GORSEL HAZIRLAMA (video motoru DEGIL - sadece anlik resim temizleme)
# ============================================================================
def beyaz_arkaplani_seffaflastir(pil_img, esik=225):
    """Kenarlardan iceri dogru beyaza-yakin alani seffaflastirir (flood-fill).
    Karakterin ICINDEKI beyaz detaylara (goz, dis vb.) dokunmaz."""
    img = pil_img.convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]

    yakin_beyaz = (arr[:, :, 0] >= esik) & (arr[:, :, 1] >= esik) & (arr[:, :, 2] >= esik)
    ziyaret_edildi = np.zeros((h, w), dtype=bool)
    kuyruk = deque()

    for x in range(w):
        for y in (0, h - 1):
            if yakin_beyaz[y, x] and not ziyaret_edildi[y, x]:
                kuyruk.append((y, x))
                ziyaret_edildi[y, x] = True
    for y in range(h):
        for x in (0, w - 1):
            if yakin_beyaz[y, x] and not ziyaret_edildi[y, x]:
                kuyruk.append((y, x))
                ziyaret_edildi[y, x] = True

    while kuyruk:
        cy, cx = kuyruk.popleft()
        arr[cy, cx, 3] = 0
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and not ziyaret_edildi[ny, nx] and yakin_beyaz[ny, nx]:
                ziyaret_edildi[ny, nx] = True
                kuyruk.append((ny, nx))

    return Image.fromarray(arr)


def karakter_gorselini_hazirla(kaynak_yolu, hedef_yolu):
    """Karakter gorselini ac, RGBA'ya cevir, zaten seffafligi yoksa
    otomatik beyaz-silme uygula, PNG olarak hedefe kaydet."""
    img = Image.open(kaynak_yolu).convert("RGBA")
    alfa = np.array(img)[:, :, 3]
    zaten_seffaf_var = alfa.min() < 250
    if not zaten_seffaf_var:
        try:
            img = beyaz_arkaplani_seffaflastir(img)
        except Exception:
            pass
    img.save(hedef_yolu)


def benzersiz_dosya_adi(klasor, taban_ad, uzanti):
    taban_ad = "".join(c for c in taban_ad if c.isalnum() or c in ("_", "-")).lower() or "gorsel"
    aday = f"{taban_ad}{uzanti}"
    sayac = 2
    while os.path.exists(os.path.join(klasor, aday)):
        aday = f"{taban_ad}_{sayac}{uzanti}"
        sayac += 1
    return aday


def kutuphanedeki_karakterler():
    """input_characters klasorundeki (daha once islenmis) tum PNG'lerin
    listesini doner - boylece kullanici ayni karakteri her sahnede
    yeniden secip yeniden islemek zorunda kalmaz, tek tikla tekrar kullanir."""
    if not os.path.isdir(KARAKTER_KLASORU):
        return []
    return sorted(f for f in os.listdir(KARAKTER_KLASORU) if f.lower().endswith(".png"))


# ============================================================================
# GEMINI AI ENTEGRASYONU - "Hikayeni Anlat" ozelligi
# ============================================================================
# NOT: gemini-2.0-flash modeli 1 Haziran 2026'da KAPATILDI. Guncel, dogru
# model adi gemini-3.5-flash (Temmuz 2026 itibariyle resmi Google
# dokumantasyonundaki ornek model budur).
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

GEMINI_IZINLI_POZISYONLAR = {"sol", "merkez", "sag"}
GEMINI_IZINLI_ANIMASYONLAR = {"sabit", "zipla", "titre", "yuru_sagdan_sola", "yuru_soldan_saga"}
GEMINI_IZINLI_GIRIS_CIKIS = {"yok", "solma"}
GEMINI_IZINLI_SAHNE_GECISI = {"oto", "kes"}
GEMINI_IZINLI_ARKAPLAN_HAREKETI = {"zoom", "kaydir_sagdan_sola", "kaydir_soldan_saga"}


def gemini_sistem_talimati_uret(mevcut_arkaplanlar, mevcut_karakterler):
    return (
        "Sen bir video sahne planlayicisisin. Kullanicinin anlattigi hikayeyi/istegi, "
        "ASAGIDAKI KURALLARA HARFIYEN uyarak bir JSON sahne listesine cevir.\n\n"
        f"KULLANILABILIR ARKA PLAN DOSYALARI (SADECE bunlari kullan, baska isim UYDURMA, "
        f"eger uygun bir tanesi yoksa listedeki en yakinini kullan): {mevcut_arkaplanlar}\n\n"
        f"KULLANILABILIR KARAKTER ISIMLERI (SADECE bunlari kullan, baska isim UYDURMA): "
        f"{mevcut_karakterler}\n\n"
        "Her sahne icin izin verilen degerler (BASKA HICBIR DEGER KULLANMA):\n"
        "- pozisyon: \"sol\", \"merkez\", \"sag\"\n"
        "- animasyon: \"sabit\", \"zipla\", \"titre\", \"yuru_sagdan_sola\", \"yuru_soldan_saga\"\n"
        "- giris / cikis: \"yok\", \"solma\"\n"
        "- sahne_gecisi: \"oto\" (yumusak), \"kes\" (sert kesme)\n"
        "- arkaplan_hareketi: \"zoom\", \"kaydir_sagdan_sola\", \"kaydir_soldan_saga\"\n\n"
        "SADECE gecerli bir JSON dizisi don, baska HICBIR aciklama/metin ekleme, "
        "kod bloku (```) da ekleme. Tam olarak su formatta:\n"
        "[\n"
        "  {\"sure\": 3.0, \"arkaplan\": \"dosya_adi\", \"arkaplan_hareketi\": \"zoom\", "
        "\"sahne_gecisi\": \"oto\",\n"
        "   \"karakterler\": [{\"ad\": \"...\", \"pozisyon\": \"...\", \"animasyon\": \"...\", "
        "\"giris\": \"...\", \"cikis\": \"...\"}],\n"
        "   \"metin\": \"...\"}\n"
        "]"
    )


def gemini_ile_sahne_uret(api_anahtari, hikaye_metni, mevcut_arkaplanlar, mevcut_karakterler, zaman_asimi=30):
    """
    Gemini API'sine hikaye metnini gonderir, JSON sahne listesi ister.
    Basarili olursa (sahneler_listesi, None) doner.
    Basarisiz olursa (None, hata_mesaji) doner - HICBIR ZAMAN exception firlatmaz.
    """
    sistem_talimati = gemini_sistem_talimati_uret(mevcut_arkaplanlar, mevcut_karakterler)

    istek_govdesi = {
        "contents": [
            {"role": "user", "parts": [{"text": sistem_talimati + "\n\nHIKAYE/ISTEK:\n" + hikaye_metni}]}
        ]
    }

    try:
        istek = urllib.request.Request(
            GEMINI_ENDPOINT,
            data=json.dumps(istek_govdesi).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_anahtari},
            method="POST",
        )
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
            yanit_verisi = json.loads(yanit.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            hata_govdesi = e.read().decode("utf-8")
        except Exception:
            hata_govdesi = ""
        return None, f"Gemini API hatasi ({e.code}): {hata_govdesi[:300]}"
    except urllib.error.URLError as e:
        return None, f"Internet baglantisi/Gemini'ye ulasilamadi: {e.reason}"
    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"

    try:
        metin_cevap = yanit_verisi["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return None, f"Gemini'den beklenmeyen bir cevap formati geldi: {json.dumps(yanit_verisi)[:300]}"

    # Bazen model, istenmemesine ragmen ```json ... ``` bloguyla sarabiliyor - temizle
    metin_cevap = metin_cevap.strip()
    if metin_cevap.startswith("```"):
        metin_cevap = metin_cevap.strip("`")
        if metin_cevap.lower().startswith("json"):
            metin_cevap = metin_cevap[4:]
        metin_cevap = metin_cevap.strip()

    try:
        ham_sahneler = json.loads(metin_cevap)
    except json.JSONDecodeError as e:
        return None, f"Gemini'nin cevabi gecerli JSON degildi: {e}\n\nCevap: {metin_cevap[:300]}"

    if not isinstance(ham_sahneler, list):
        return None, "Gemini'nin cevabi bir liste (JSON array) degildi."

    dogrulanmis_sahneler, uyarilar = gemini_sahneleri_dogrula(ham_sahneler, mevcut_arkaplanlar, mevcut_karakterler)

    if not dogrulanmis_sahneler:
        return None, "Gemini gecerli hicbir sahne uretemedi.\n" + "\n".join(uyarilar)

    return dogrulanmis_sahneler, ("\n".join(uyarilar) if uyarilar else None)


def gemini_sahneleri_dogrula(ham_sahneler, mevcut_arkaplanlar, mevcut_karakterler):
    """
    Gemini'nin urettigi HAM JSON'u, bizim GERCEKTEN desteklediklerimizle
    karsilastirip DOGRULAR. Gemini'nin uydurdugu / hallucinate ettigi
    gecersiz bir deger varsa, o alani GUVENLI bir varsayilana ceker,
    ASLA oldugu gibi (kontrolsuz) kullanmaz.
    """
    sonuc = []
    uyarilar = []

    for i, ham in enumerate(ham_sahneler):
        if not isinstance(ham, dict):
            uyarilar.append(f"Sahne {i+1}: gecersiz format (dict degil), atlandi.")
            continue

        try:
            sure = float(ham.get("sure", 3.0))
            if sure <= 0:
                sure = 3.0
        except (TypeError, ValueError):
            sure = 3.0
            uyarilar.append(f"Sahne {i+1}: gecersiz sure, 3.0sn varsayildi.")

        arkaplan = ham.get("arkaplan", "")
        if arkaplan not in mevcut_arkaplanlar:
            uyarilar.append(f"Sahne {i+1}: Gemini olmayan bir arka plan uydurdu ('{arkaplan}'), "
                             f"kutuphanedeki ilk dosyayla degistirildi.")
            arkaplan = mevcut_arkaplanlar[0] if mevcut_arkaplanlar else "eksik_arkaplan.jpg"

        arkaplan_hareketi = str(ham.get("arkaplan_hareketi", "zoom")).lower()
        if arkaplan_hareketi not in GEMINI_IZINLI_ARKAPLAN_HAREKETI:
            arkaplan_hareketi = "zoom"

        sahne_gecisi = str(ham.get("sahne_gecisi", "oto")).lower()
        if sahne_gecisi not in GEMINI_IZINLI_SAHNE_GECISI:
            sahne_gecisi = "oto"

        if arkaplan_hareketi != "zoom":
            arkaplan_dosya = f"{arkaplan}:{arkaplan_hareketi}" + (f":{sahne_gecisi}" if sahne_gecisi != "oto" else "")
        elif sahne_gecisi != "oto":
            arkaplan_dosya = f"{arkaplan}:zoom:{sahne_gecisi}"
        else:
            arkaplan_dosya = arkaplan

        karakterler = []
        for k in ham.get("karakterler", []):
            if not isinstance(k, dict):
                continue
            ad = k.get("ad", "")
            if ad not in mevcut_karakterler and os.path.splitext(ad)[0] not in [
                os.path.splitext(m)[0] for m in mevcut_karakterler
            ]:
                uyarilar.append(f"Sahne {i+1}: Gemini olmayan bir karakter uydurdu ('{ad}'), bu karakter atlandi.")
                continue

            pozisyon = str(k.get("pozisyon", "merkez")).lower()
            if pozisyon not in GEMINI_IZINLI_POZISYONLAR:
                pozisyon = "merkez"

            animasyon = str(k.get("animasyon", "sabit")).lower()
            if animasyon not in GEMINI_IZINLI_ANIMASYONLAR:
                animasyon = "sabit"

            giris = str(k.get("giris", "yok")).lower()
            if giris not in GEMINI_IZINLI_GIRIS_CIKIS:
                giris = "yok"

            cikis = str(k.get("cikis", "yok")).lower()
            if cikis not in GEMINI_IZINLI_GIRIS_CIKIS:
                cikis = "yok"

            karakterler.append({
                "ad": os.path.splitext(ad)[0], "pozisyon": pozisyon, "animasyon": animasyon,
                "giris": giris, "cikis": cikis,
            })

        metin = str(ham.get("metin", ""))[:200]  # asiri uzun metinleri kirp

        sonuc.append({
            "sure": sure, "arkaplan_dosya": arkaplan_dosya,
            "karakterler": karakterler, "metin": metin,
        })

    return sonuc, uyarilar


def kutuphanedeki_arkaplanlar():
    """input_backgrounds VE input_videos klasorlerindeki tum gorsel/video
    dosyalarinin listesini doner (video dosyalari da arka plan olarak
    kullanilabilir - gercek video klip eklemek icin)."""
    sonuc = []
    if os.path.isdir(ARKAPLAN_KLASORU):
        sonuc += sorted(f for f in os.listdir(ARKAPLAN_KLASORU) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    if os.path.isdir(VIDEO_KLASORU):
        sonuc += sorted(f for f in os.listdir(VIDEO_KLASORU) if f.lower().endswith((".mp4", ".mov", ".avi", ".webm", ".m4v")))
    return sonuc


def dosya_video_mu(dosya_adi):
    return dosya_adi.lower().endswith((".mp4", ".mov", ".avi", ".webm", ".m4v"))


# ============================================================================
# GEMINI API ENTEGRASYONU (serbest metinle hikaye anlatip AI'nin bizim
# script.txt semamiza uygun sahneler uretmesi icin)
# ============================================================================
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _gemini_sistem_talimati_olustur(mevcut_arkaplanlar, mevcut_karakterler):
    return (
        "Sen bir video sahne planlayicisin. Kullanicinin serbest metinle anlattigi "
        "hikayeyi, ASAGIDAKI KESIN JSON semasina uygun bir sahne listesine cevireceksin.\n\n"
        "COK ONEMLI KURAL: Sadece asagida listelenen MEVCUT dosya isimlerini "
        "kullanabilirsin. YENI bir dosya adi UYDURAMAZSIN (o dosya diskte yok, "
        "hata verir). Hikayede olmayan bir karakter/arka plan gerekiyorsa, en "
        "yakin mevcut olani kullan.\n\n"
        f"Mevcut arka plan/video dosyalari: {', '.join(mevcut_arkaplanlar) or '(hic yok)'}\n"
        f"Mevcut karakter dosyalari (uzantisiz kullan): "
        f"{', '.join(os.path.splitext(k)[0] for k in mevcut_karakterler) or '(hic yok)'}\n\n"
        "Izin verilen pozisyon degerleri: sol, merkez, sag\n"
        "Izin verilen animasyon degerleri: sabit, zipla, titre, yuru_sagdan_sola, yuru_soldan_saga\n"
        "Izin verilen giris/cikis degerleri: yok, solma\n"
        "Izin verilen arkaplan_hareketi: zoom, kaydir_sagdan_sola, kaydir_soldan_saga\n"
        "Izin verilen sahne_gecisi: oto, kes\n\n"
        "SADECE gecerli JSON don (dizi/array), markdown code fence KULLANMA, "
        "baska hicbir aciklama ekleme. Tam format:\n"
        '[{"sure": 3.0, "arkaplan_dosya": "ev.jpg", "arkaplan_hareketi": "zoom", '
        '"sahne_gecisi": "oto", "karakterler": [{"ad": "rias", "pozisyon": "sol", '
        '"animasyon": "zipla", "giris": "solma", "cikis": "yok"}], '
        '"metin": "Altyazi metni"}]'
    )


def gemini_ile_sahne_uret(api_key, hikaye_metni, mevcut_arkaplanlar, mevcut_karakterler):
    """
    Kullanicinin serbest metinle anlattigi hikayeyi Gemini API'ye gonderir,
    donen JSON'u kendi ic sahne formatimiza cevirir.

    Donus: (sahneler, uyari_metni) basarili olursa (uyari_metni bos olabilir),
           (None, hata_metni) basarisiz olursa. HICBIR ZAMAN exception
           firlatmaz - arka plan thread'inde guvenle cagirilabilir.
    """
    try:
        sistem_talimati = _gemini_sistem_talimati_olustur(mevcut_arkaplanlar, mevcut_karakterler)

        istek_govdesi = json.dumps({
            "system_instruction": {"parts": [{"text": sistem_talimati}]},
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
            gövde = e.read().decode("utf-8", errors="replace")
            return None, f"Gemini API HTTP hatasi ({e.code}): {gövde[:300]}"
        except urllib.error.URLError as e:
            return None, f"Internet baglantisi/Gemini API'ye ulasilamadi: {e.reason}"

        try:
            metin = yanit_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return None, f"Gemini'den beklenmeyen bir yanit geldi: {json.dumps(yanit_json)[:300]}"

        # Gemini bazen "SADECE JSON don" desek bile ```json ... ``` ile
        # sarmalayabilir - onu temizleyelim.
        metin_temiz = metin.strip()
        if metin_temiz.startswith("```"):
            metin_temiz = metin_temiz.split("\n", 1)[1] if "\n" in metin_temiz else metin_temiz
            if metin_temiz.rstrip().endswith("```"):
                metin_temiz = metin_temiz.rstrip()[:-3]
            metin_temiz = metin_temiz.replace("```json", "").replace("```", "").strip()

        try:
            ham_sahneler = json.loads(metin_temiz)
        except json.JSONDecodeError as e:
            return None, f"AI'nin cevabi gecerli JSON degildi: {e}\n\nHam cevap: {metin_temiz[:300]}"

        gecerli_arkaplanlar = set(mevcut_arkaplanlar)
        gecerli_karakterler = set(os.path.splitext(k)[0] for k in mevcut_karakterler)
        uyarilar = []

        sahneler = []
        for hs in ham_sahneler:
            arkaplan_adi = hs.get("arkaplan_dosya", "")
            if arkaplan_adi not in gecerli_arkaplanlar:
                uyarilar.append(f"'{arkaplan_adi}' kutuphanede yok, AI hatali bir dosya adi uretmis olabilir.")

            arkaplan_dosya_alani = arkaplan_alanini_kodla(
                arkaplan_adi,
                hs.get("arkaplan_hareketi", "zoom"),
                hs.get("sahne_gecisi", "oto"),
            )
            karakterler = []
            for k in hs.get("karakterler", []):
                ad = k.get("ad", "")
                if ad not in gecerli_karakterler:
                    uyarilar.append(f"Karakter '{ad}' kutuphanede yok, AI hatali bir isim uretmis olabilir.")
                karakterler.append({
                    "ad": ad,
                    "pozisyon": k.get("pozisyon", "merkez"),
                    "animasyon": k.get("animasyon", "sabit"),
                    "giris": k.get("giris", "yok"),
                    "cikis": k.get("cikis", "yok"),
                })
            sahneler.append({
                "sure": float(hs.get("sure", 3.0)),
                "arkaplan_dosya": arkaplan_dosya_alani,
                "karakterler": karakterler,
                "metin": hs.get("metin", ""),
            })

        return sahneler, ("\n".join(uyarilar) if uyarilar else "")

    except Exception as e:
        return None, f"Beklenmeyen hata: {e}"


# ============================================================================
# OS YARDIMCILAR
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


# ============================================================================
# SCRIPT.TXT URETICI (kullanici ELLE YAZMIYOR, bu fonksiyon otomatik uretiyor)
# ============================================================================
def arkaplan_alanini_kodla(dosya_adi, hareket="zoom", gecis="oto"):
    """
    script.txt'deki arkaplan alanini kodlar: 'dosya' / 'dosya:hareket' /
    'dosya:hareket:gecis' - hem manuel GUI'den hem AI'dan gelen sahnelerde
    AYNI mantik kullanilsin diye tek bir yerde toplandi.
    """
    if gecis != "oto":
        return f"{dosya_adi}:{hareket}:{gecis}"
    elif hareket != "zoom":
        return f"{dosya_adi}:{hareket}"
    return dosya_adi


def script_txt_uret(sahneler):
    satirlar = []
    for sahne in sahneler:
        karakter_parcalari = []
        for k in sahne["karakterler"]:
            giris = k.get("giris", "yok")
            cikis = k.get("cikis", "yok")
            if giris != "yok" or cikis != "yok":
                karakter_parcalari.append(f"{k['ad']}:{k['pozisyon']}:{k['animasyon']}:{giris}:{cikis}")
            else:
                karakter_parcalari.append(f"{k['ad']}:{k['pozisyon']}:{k['animasyon']}")
        karakter_str = " , ".join(karakter_parcalari)
        metin = sahne.get("metin", "").replace('"', "'")
        satir = f'{sahne["sure"]} | {sahne["arkaplan_dosya"]} | {karakter_str} | "{metin}"'
        satirlar.append(satir)

    icerik = "\n".join(satirlar) + "\n"
    with open(SCRIPT_TXT_YOLU, "w", encoding="utf-8") as f:
        f.write(icerik)
    return icerik


# ============================================================================
# ANA PANEL
# ============================================================================
class AEStudioPaneli:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("Canavar Asistan - AE Studio Paneli")
        self.pencere.geometry("820x680")
        self.pencere.minsize(650, 550)
        self.pencere.resizable(True, True)

        self.ayarlar = ayarlari_yukle()
        self.sahneler = sahneleri_yukle()
        self._ai_sonuc_kuyrugu = queue.Queue()

        self._arayuzu_kur()
        self._sahne_listesini_guncelle()
        self.log_yaz(f"{len(self.sahneler)} sahne yuklendi (onceki oturumdan).")
        self._ai_kuyrugunu_dinle()

    def _ai_kuyrugunu_dinle(self):
        """
        AI (Gemini) sonucunu ARKA PLAN thread'inden GUVENLI sekilde ana
        thread'e tasir. NOT: arka plan thread'inden dogrudan
        self.pencere.after(...) cagirmak guvenilir DEGIL (Tkinter'in
        ana thread disi cagrilarda tutarsiz davranabilmesi nedeniyle -
        'main thread is not in main loop' hatasi verebilir). Bu yuzden
        thread sonucu bir queue.Queue'ya koyar, BU fonksiyon (ana thread'de,
        periyodik olarak) kuyrugu kontrol edip isler.
        """
        try:
            while True:
                sahneler, hata_veya_uyari = self._ai_sonuc_kuyrugu.get_nowait()
                self._ai_sonucunu_isle(sahneler, hata_veya_uyari)
        except queue.Empty:
            pass
        finally:
            self.pencere.after(150, self._ai_kuyrugunu_dinle)

    # ------------------------------------------------------------
    def _arayuzu_kur(self):
        ana = tk.Frame(self.pencere)
        ana.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(ana, text="Canavar Asistan - AE Studio", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(
            ana, text="Gorselleri surukle-birak yerine 'Yeni Sahne Ekle' ile tek tek sahne olarak diz. "
                      "script.txt ELLE YAZILMAZ, otomatik uretilir. Video render YOK - her sey AE'de olur.",
            font=("Segoe UI", 8), fg="#555555", wraplength=780, justify="left"
        ).pack(anchor="w", pady=(2, 10))

        ust_buton_cercevesi = tk.Frame(ana)
        ust_buton_cercevesi.pack(fill="x", pady=(0, 6))

        tk.Button(
            ust_buton_cercevesi, text="+ Yeni Sahne Ekle", command=self.sahne_ekle_penceresi,
            bg=RENK_KURGU_BG, fg=RENK_BEYAZ, font=("Segoe UI", 11, "bold"), height=2
        ).pack(fill="x")

        # --- Hikayeni Anlat (Gemini AI) ---
        ai_cercevesi = tk.LabelFrame(ana, text="Hikayeni Anlat (AI ile Otomatik Sahne Uret)", font=("Segoe UI", 9, "bold"))
        ai_cercevesi.pack(fill="x", pady=(8, 4))

        self.hikaye_kutusu = tk.Text(ai_cercevesi, height=4, wrap="word", font=("Segoe UI", 9))
        self.hikaye_kutusu.pack(fill="x", padx=8, pady=(6, 4))
        self.hikaye_kutusu.insert(
            "1.0", "Ornek: Rias eve girer, sasirir. Akeno sagdan gelir, ona sert bakar. "
                   "Gerilim artar, sahne sertçe kesilir."
        )

        ai_buton_satiri = tk.Frame(ai_cercevesi)
        ai_buton_satiri.pack(fill="x", padx=8, pady=(0, 8))
        self.ai_uret_butonu = tk.Button(
            ai_buton_satiri, text="AI ile Sahneleri Uret", command=self.ai_ile_sahne_uret,
            bg="#7B1FA2", fg=RENK_BEYAZ, font=("Segoe UI", 10, "bold")
        )
        self.ai_uret_butonu.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(
            ai_buton_satiri, text="Gemini API Anahtari", font=("Segoe UI", 8),
            command=self.gemini_anahtarini_duzenle
        ).pack(side="left")

        # --- Sahne listesi ---
        tk.Label(ana, text="Sahne Sirasi:", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 2))

        liste_cercevesi = tk.Frame(ana)
        liste_cercevesi.pack(fill="both", expand=True)

        self.sahne_listesi = tk.Listbox(liste_cercevesi, font=("Consolas", 9))
        self.sahne_listesi.pack(side="left", fill="both", expand=True)
        kaydirma = ttk.Scrollbar(liste_cercevesi, orient="vertical", command=self.sahne_listesi.yview)
        kaydirma.pack(side="left", fill="y")
        self.sahne_listesi.configure(yscrollcommand=kaydirma.set)

        yan_butonlar = tk.Frame(liste_cercevesi)
        yan_butonlar.pack(side="left", fill="y", padx=(6, 0))
        tk.Button(yan_butonlar, text="Yukari", width=10, command=self.sahneyi_yukari_tasi).pack(pady=2)
        tk.Button(yan_butonlar, text="Asagi", width=10, command=self.sahneyi_asagi_tasi).pack(pady=2)
        tk.Button(yan_butonlar, text="Sil", width=10, bg="#e74c3c", fg="white",
                  command=self.sahneyi_sil).pack(pady=2)

        # --- Alt butonlar ---
        alt_cerceve = tk.Frame(ana)
        alt_cerceve.pack(fill="x", pady=(10, 4))

        tk.Button(
            alt_cerceve, text="script.txt Olustur ve Kaydet", command=self.script_olustur,
            bg=RENK_KAYDET_BG, fg=RENK_BEYAZ, font=("Segoe UI", 10, "bold")
        ).pack(fill="x", pady=2)

        tk.Button(
            alt_cerceve, text="AFTER EFFECTS'I BASLAT", command=self.ae_baslat,
            bg=RENK_AE_BG, fg=RENK_BEYAZ, font=("Segoe UI", 11, "bold"), height=2
        ).pack(fill="x", pady=2)

        klasor_satiri = tk.Frame(alt_cerceve)
        klasor_satiri.pack(fill="x", pady=(6, 0))
        tk.Button(klasor_satiri, text="Arka Planlar Klasoru", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  command=lambda: klasoru_ac(ARKAPLAN_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(klasor_satiri, text="Karakterler Klasoru", bg=RENK_KLASOR_BG, fg=RENK_BEYAZ,
                  command=lambda: klasoru_ac(KARAKTER_KLASORU)).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(klasor_satiri, text="AE Yolu Ayarlari", font=("Segoe UI", 8),
                  command=self.ayarlari_duzenle).pack(side="left", expand=True, fill="x", padx=2)

        # --- Log ---
        tk.Label(ana, text="Gunluk:", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 2))
        self.log_kutusu = scrolledtext.ScrolledText(
            ana, height=6, bg=RENK_LOG_BG, fg=RENK_LOG_FG, font=("Consolas", 9)
        )
        self.log_kutusu.pack(fill="both", expand=False)
        self.log_kutusu.configure(state="disabled")

    def log_yaz(self, mesaj):
        self.log_kutusu.configure(state="normal")
        self.log_kutusu.insert("end", mesaj + "\n")
        self.log_kutusu.see("end")
        self.log_kutusu.configure(state="disabled")

    # ------------------------------------------------------------
    # SAHNE LISTESI GORUNTULEME
    # ------------------------------------------------------------
    def _sahne_listesini_guncelle(self):
        self.sahne_listesi.delete(0, "end")
        for i, sahne in enumerate(self.sahneler, start=1):
            karakter_ozet = ", ".join(k["ad"] for k in sahne["karakterler"]) or "(karaktersiz)"
            metin_ozet = sahne.get("metin", "")
            if len(metin_ozet) > 30:
                metin_ozet = metin_ozet[:30] + "..."
            self.sahne_listesi.insert(
                "end",
                f"Sahne {i}: {sahne['sure']}sn | {sahne['arkaplan_dosya']} | {karakter_ozet} | \"{metin_ozet}\""
            )
        sahneleri_kaydet(self.sahneler)

    def sahneyi_yukari_tasi(self):
        secim = self.sahne_listesi.curselection()
        if not secim or secim[0] == 0:
            return
        i = secim[0]
        self.sahneler[i - 1], self.sahneler[i] = self.sahneler[i], self.sahneler[i - 1]
        self._sahne_listesini_guncelle()
        self.sahne_listesi.selection_set(i - 1)

    def sahneyi_asagi_tasi(self):
        secim = self.sahne_listesi.curselection()
        if not secim or secim[0] == len(self.sahneler) - 1:
            return
        i = secim[0]
        self.sahneler[i + 1], self.sahneler[i] = self.sahneler[i], self.sahneler[i + 1]
        self._sahne_listesini_guncelle()
        self.sahne_listesi.selection_set(i + 1)

    def sahneyi_sil(self):
        secim = self.sahne_listesi.curselection()
        if not secim:
            messagebox.showinfo("Secim yok", "Once bir sahne sec.")
            return
        if messagebox.askyesno("Emin misin?", "Bu sahne listeden silinsin mi?"):
            del self.sahneler[secim[0]]
            self._sahne_listesini_guncelle()
            self.log_yaz("Sahne silindi.")

    # ------------------------------------------------------------
    # YENI SAHNE EKLEME PENCERESI
    # ------------------------------------------------------------
    def sahne_ekle_penceresi(self):
        pencere = tk.Toplevel(self.pencere)
        pencere.title("Yeni Sahne Ekle")
        pencere.geometry("480x520")
        pencere.grab_set()

        veri = {"arkaplan_yolu": None, "arkaplan_hazir_dosya": None, "karakterler": []}

        tk.Label(pencere, text="Sahne suresi (saniye):", font=("Segoe UI", 10)).pack(pady=(12, 2), padx=15, anchor="w")
        sure_kutusu = tk.Entry(pencere)
        sure_kutusu.insert(0, "3.0")
        sure_kutusu.pack(fill="x", padx=15)

        tk.Label(pencere, text="Arka plan:", font=("Segoe UI", 10)).pack(pady=(12, 2), padx=15, anchor="w")
        arkaplan_satiri = tk.Frame(pencere)
        arkaplan_satiri.pack(fill="x", padx=15)
        arkaplan_etiketi = tk.Label(arkaplan_satiri, text="(secilmedi)", fg="#555555")
        arkaplan_etiketi.pack(side="left", padx=(0, 8))

        def arkaplan_sec():
            yol = filedialog.askopenfilename(
                title="Arka plan resmi VEYA video klibi sec",
                filetypes=[("Resim/Video", "*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.avi *.webm *.m4v")]
            )
            if yol:
                veri["arkaplan_yolu"] = yol
                veri["arkaplan_hazir_dosya"] = None
                etiket_notu = " (video, yeni)" if dosya_video_mu(yol) else " (yeni)"
                arkaplan_etiketi.config(text=os.path.basename(yol) + etiket_notu)
                genislik_uyarisini_kontrol_et()

        def arkaplan_kutuphaneden_sec():
            mevcutlar = kutuphanedeki_arkaplanlar()
            if not mevcutlar:
                messagebox.showinfo("Kutuphane bos", "Henuz kutuphanede hic arka plan yok. Once 'Yeni Dosya Sec' ile bir tane ekle.", parent=pencere)
                return
            secim_penceresi = tk.Toplevel(pencere)
            secim_penceresi.title("Kutuphaneden Arka Plan Sec")
            secim_penceresi.geometry("320x360")
            secim_penceresi.grab_set()
            liste = tk.Listbox(secim_penceresi)
            liste.pack(fill="both", expand=True, padx=10, pady=10)
            for ad in mevcutlar:
                liste.insert("end", ad)

            def secildi():
                secim = liste.curselection()
                if not secim:
                    return
                secilen_ad = mevcutlar[secim[0]]
                veri["arkaplan_yolu"] = None
                veri["arkaplan_hazir_dosya"] = secilen_ad
                arkaplan_etiketi.config(text=secilen_ad + " (kutuphaneden)")
                secim_penceresi.destroy()
                genislik_uyarisini_kontrol_et()

            tk.Button(secim_penceresi, text="Sec", command=secildi, bg=RENK_KURGU_BG, fg=RENK_BEYAZ).pack(pady=(0, 10), padx=10, fill="x")

        arkaplan_buton_satiri = tk.Frame(arkaplan_satiri)
        arkaplan_buton_satiri.pack(side="left")
        tk.Button(arkaplan_buton_satiri, text="Yeni Dosya Sec", command=arkaplan_sec).pack(side="left", padx=(0, 4))
        tk.Button(arkaplan_buton_satiri, text="Kutuphaneden Sec", command=arkaplan_kutuphaneden_sec).pack(side="left")

        tk.Label(pencere, text="Arka plan hareketi:", font=("Segoe UI", 10)).pack(pady=(10, 2), padx=15, anchor="w")
        arkaplan_hareket_secimi = ttk.Combobox(pencere, values=list(ARKAPLAN_HAREKETLERI.keys()), state="readonly")
        arkaplan_hareket_secimi.current(0)
        arkaplan_hareket_secimi.pack(fill="x", padx=15)

        genislik_uyari_etiketi = tk.Label(pencere, text="", fg="#c0392b", font=("Segoe UI", 8), wraplength=440, justify="left")
        genislik_uyari_etiketi.pack(fill="x", padx=15)

        tk.Label(pencere, text="Bu sahneye giris (onceki sahneden):", font=("Segoe UI", 10)).pack(pady=(10, 2), padx=15, anchor="w")
        sahne_gecis_secimi = ttk.Combobox(pencere, values=list(SAHNE_GECIS_SECENEKLERI.keys()), state="readonly")
        sahne_gecis_secimi.current(0)
        sahne_gecis_secimi.pack(fill="x", padx=15)

        def genislik_uyarisini_kontrol_et(event=None):
            secilen_hareket = ARKAPLAN_HAREKETLERI.get(arkaplan_hareket_secimi.get(), "zoom")
            if secilen_hareket == "zoom":
                genislik_uyari_etiketi.config(text="")
                return
            yol = veri["arkaplan_yolu"]
            if not yol and veri.get("arkaplan_hazir_dosya"):
                aday1 = os.path.join(ARKAPLAN_KLASORU, veri["arkaplan_hazir_dosya"])
                aday2 = os.path.join(VIDEO_KLASORU, veri["arkaplan_hazir_dosya"])
                yol = aday1 if os.path.exists(aday1) else (aday2 if os.path.exists(aday2) else None)
            if not yol or not os.path.exists(yol) or dosya_video_mu(yol):
                genislik_uyari_etiketi.config(text="")
                return
            try:
                img = Image.open(yol)
                olceklenmis_genislik = img.width * (1920 / img.height)
                if olceklenmis_genislik < 1080 * 1.5:
                    genislik_uyari_etiketi.config(
                        text=f"UYARI: Bu resim kaydirma icin muhtemelen yeterince genis degil "
                             f"(yukseklige oturunca ~{int(olceklenmis_genislik)}px genislik olur, "
                             f"iyi bir kayma icin en az ~1620px+ onerilir). Yine de denenebilir ama "
                             f"hareket cok az/hic olmayabilir."
                    )
                else:
                    genislik_uyari_etiketi.config(text="")
            except Exception:
                pass

        arkaplan_hareket_secimi.bind("<<ComboboxSelected>>", genislik_uyarisini_kontrol_et)

        tk.Label(pencere, text="Karakterler:", font=("Segoe UI", 10)).pack(pady=(12, 2), padx=15, anchor="w")
        karakter_listesi = tk.Listbox(pencere, height=5)
        karakter_listesi.pack(fill="x", padx=15)

        def karakter_ekle_penceresi():
            alt = tk.Toplevel(pencere)
            alt.title("Karakter Ekle")
            alt.geometry("360x320")
            alt.grab_set()

            alt_veri = {"yol": None, "hazir_dosya": None}

            tk.Label(alt, text="Karakter gorseli:", font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            gorsel_satiri = tk.Frame(alt)
            gorsel_satiri.pack(fill="x", padx=15)
            gorsel_etiketi = tk.Label(gorsel_satiri, text="(secilmedi)", fg="#555555")
            gorsel_etiketi.pack(side="top", anchor="w", pady=(0, 4))

            def gorsel_sec():
                yol = filedialog.askopenfilename(
                    title="Karakter gorselini sec",
                    filetypes=[("Resimler", "*.jpg *.jpeg *.png *.webp")]
                )
                if yol:
                    alt_veri["yol"] = yol
                    alt_veri["hazir_dosya"] = None
                    gorsel_etiketi.config(text=os.path.basename(yol) + " (yeni, otomatik islenecek)")

            def gorsel_kutuphaneden_sec():
                mevcutlar = kutuphanedeki_karakterler()
                if not mevcutlar:
                    messagebox.showinfo("Kutuphane bos", "Henuz kutuphanede hic karakter yok. Once 'Yeni Dosya Sec' ile bir tane ekle.", parent=alt)
                    return
                secim_penceresi = tk.Toplevel(alt)
                secim_penceresi.title("Kutuphaneden Karakter Sec")
                secim_penceresi.geometry("320x360")
                secim_penceresi.grab_set()
                liste = tk.Listbox(secim_penceresi)
                liste.pack(fill="both", expand=True, padx=10, pady=10)
                for ad in mevcutlar:
                    liste.insert("end", ad)

                def secildi():
                    secim = liste.curselection()
                    if not secim:
                        return
                    secilen_ad = mevcutlar[secim[0]]
                    alt_veri["yol"] = None
                    alt_veri["hazir_dosya"] = secilen_ad
                    gorsel_etiketi.config(text=secilen_ad + " (kutuphaneden, tekrar islenmeyecek)")
                    if not isim_kutusu.get().strip():
                        isim_kutusu.insert(0, os.path.splitext(secilen_ad)[0])
                    secim_penceresi.destroy()

                tk.Button(secim_penceresi, text="Sec", command=secildi, bg=RENK_KURGU_BG, fg=RENK_BEYAZ).pack(pady=(0, 10), padx=10, fill="x")

            gorsel_buton_satiri = tk.Frame(gorsel_satiri)
            gorsel_buton_satiri.pack(side="top", anchor="w")
            tk.Button(gorsel_buton_satiri, text="Yeni Dosya Sec", command=gorsel_sec).pack(side="left", padx=(0, 4))
            tk.Button(gorsel_buton_satiri, text="Kutuphaneden Sec", command=gorsel_kutuphaneden_sec).pack(side="left")

            tk.Label(alt, text="Karakter adi (bos birakirsan otomatik verilir):",
                     font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            isim_kutusu = tk.Entry(alt)
            isim_kutusu.pack(fill="x", padx=15)

            tk.Label(alt, text="Pozisyon:", font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            pozisyon_secimi = ttk.Combobox(alt, values=POZISYONLAR, state="readonly")
            pozisyon_secimi.current(1)
            pozisyon_secimi.pack(fill="x", padx=15)

            tk.Label(alt, text="Animasyon:", font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            animasyon_secimi = ttk.Combobox(alt, values=ANIMASYONLAR, state="readonly")
            animasyon_secimi.current(0)
            animasyon_secimi.pack(fill="x", padx=15)

            tk.Label(alt, text="Giris efekti:", font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            giris_secimi = ttk.Combobox(alt, values=list(GIRIS_CIKIS_SECENEKLERI.keys()), state="readonly")
            giris_secimi.current(0)
            giris_secimi.pack(fill="x", padx=15)

            tk.Label(alt, text="Cikis efekti:", font=("Segoe UI", 9)).pack(pady=(12, 2), padx=15, anchor="w")
            cikis_secimi = ttk.Combobox(alt, values=list(GIRIS_CIKIS_SECENEKLERI.keys()), state="readonly")
            cikis_secimi.current(0)
            cikis_secimi.pack(fill="x", padx=15)

            def karakteri_listeye_ekle():
                if not alt_veri["yol"] and not alt_veri["hazir_dosya"]:
                    messagebox.showwarning("Eksik", "Once bir gorsel sec (yeni dosya ya da kutuphaneden).", parent=alt)
                    return
                varsayilan_isim = (
                    os.path.splitext(alt_veri["hazir_dosya"])[0] if alt_veri["hazir_dosya"]
                    else f"karakter{len(veri['karakterler']) + 1}"
                )
                isim = isim_kutusu.get().strip() or varsayilan_isim
                veri["karakterler"].append({
                    "yol": alt_veri["yol"],
                    "hazir_dosya": alt_veri["hazir_dosya"],
                    "isim": isim,
                    "pozisyon": pozisyon_secimi.get(),
                    "animasyon": animasyon_secimi.get(),
                    "giris": GIRIS_CIKIS_SECENEKLERI.get(giris_secimi.get(), "yok"),
                    "cikis": GIRIS_CIKIS_SECENEKLERI.get(cikis_secimi.get(), "yok"),
                })
                karakter_listesi.insert("end", f"{isim} ({pozisyon_secimi.get()}, {animasyon_secimi.get()})")
                alt.destroy()

            tk.Button(alt, text="Karakteri Ekle", bg=RENK_KURGU_BG, fg=RENK_BEYAZ,
                      command=karakteri_listeye_ekle).pack(pady=15, padx=15, fill="x")

        tk.Button(pencere, text="+ Karakter Ekle", command=karakter_ekle_penceresi).pack(padx=15, pady=(4, 0), anchor="w")

        tk.Label(pencere, text="Altyazi metni (konusma):", font=("Segoe UI", 10)).pack(pady=(12, 2), padx=15, anchor="w")
        metin_kutusu = tk.Entry(pencere)
        metin_kutusu.pack(fill="x", padx=15)

        def sahneyi_kaydet():
            try:
                sure = float(sure_kutusu.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Hatali sure", "Sure gecerli bir sayi olmali (orn: 3.0).", parent=pencere)
                return
            if not veri["arkaplan_yolu"] and not veri.get("arkaplan_hazir_dosya"):
                messagebox.showwarning("Eksik", "Once bir arka plan sec (yeni dosya ya da kutuphaneden).", parent=pencere)
                return

            try:
                if veri.get("arkaplan_hazir_dosya"):
                    # Kutuphaneden secildi -> zaten islenmis, TEKRAR ISLENMEZ, dogrudan kullanilir
                    arkaplan_hedef_ad = veri["arkaplan_hazir_dosya"]
                else:
                    arkaplan_uzanti = os.path.splitext(veri["arkaplan_yolu"])[1].lower() or ".jpg"

                    if dosya_video_mu(veri["arkaplan_yolu"]):
                        # Video dosyasi: PIL ile ACILMAZ (resim degil), oldugu
                        # gibi (yeniden kodlamadan) VIDEO_KLASORU'ne kopyalanir.
                        arkaplan_hedef_ad = benzersiz_dosya_adi(
                            VIDEO_KLASORU, os.path.splitext(os.path.basename(veri["arkaplan_yolu"]))[0], arkaplan_uzanti
                        )
                        arkaplan_hedef_yol = os.path.join(VIDEO_KLASORU, arkaplan_hedef_ad)
                        shutil.copyfile(veri["arkaplan_yolu"], arkaplan_hedef_yol)
                    else:
                        arkaplan_hedef_ad = benzersiz_dosya_adi(
                            ARKAPLAN_KLASORU, os.path.splitext(os.path.basename(veri["arkaplan_yolu"]))[0], arkaplan_uzanti
                        )
                        arkaplan_hedef_yol = os.path.join(ARKAPLAN_KLASORU, arkaplan_hedef_ad)
                        Image.open(veri["arkaplan_yolu"]).convert("RGB").save(arkaplan_hedef_yol)

                arkaplan_dosya_alani = arkaplan_alanini_kodla(
                    arkaplan_hedef_ad,
                    ARKAPLAN_HAREKETLERI.get(arkaplan_hareket_secimi.get(), "zoom"),
                    SAHNE_GECIS_SECENEKLERI.get(sahne_gecis_secimi.get(), "oto"),
                )

                karakterler_islenmis = []
                for k in veri["karakterler"]:
                    if k.get("hazir_dosya"):
                        # Kutuphaneden secildi -> zaten islenmis (seffaflastirma dahil), TEKRAR ISLENMEZ
                        ad = os.path.splitext(k["hazir_dosya"])[0]
                    else:
                        hedef_ad = benzersiz_dosya_adi(KARAKTER_KLASORU, k["isim"], ".png")
                        hedef_yol = os.path.join(KARAKTER_KLASORU, hedef_ad)
                        karakter_gorselini_hazirla(k["yol"], hedef_yol)
                        ad = os.path.splitext(hedef_ad)[0]
                    karakterler_islenmis.append({
                        "ad": ad,
                        "pozisyon": k["pozisyon"],
                        "animasyon": k["animasyon"],
                        "giris": k.get("giris", "yok"),
                        "cikis": k.get("cikis", "yok"),
                    })

                self.sahneler.append({
                    "sure": sure,
                    "arkaplan_dosya": arkaplan_dosya_alani,
                    "karakterler": karakterler_islenmis,
                    "metin": metin_kutusu.get().strip(),
                })
                self._sahne_listesini_guncelle()
                self.log_yaz(f"Yeni sahne eklendi ({sure}sn, {len(karakterler_islenmis)} karakter).")
                pencere.destroy()
            except Exception as e:
                messagebox.showerror("Hata", f"Sahne eklenirken hata olustu:\n{e}", parent=pencere)

        tk.Button(
            pencere, text="Sahneyi Listeye Ekle", command=sahneyi_kaydet,
            bg=RENK_KAYDET_BG, fg=RENK_BEYAZ, font=("Segoe UI", 10, "bold")
        ).pack(pady=15, padx=15, fill="x")

    # ------------------------------------------------------------
    # SCRIPT.TXT URETME
    # ------------------------------------------------------------
    def script_olustur(self):
        if not self.sahneler:
            messagebox.showwarning("Bos liste", "Once en az bir sahne eklemelisin.")
            return
        try:
            icerik = script_txt_uret(self.sahneler)
            self.log_yaz(f"script.txt olusturuldu ({len(self.sahneler)} sahne).")
            self.log_yaz(icerik)
        except Exception as e:
            self.log_yaz(f"[HATA] script.txt olusturulamadi: {e}")
            messagebox.showerror("Hata", f"script.txt olusturulamadi:\n{e}")

    # ------------------------------------------------------------
    # AFTER EFFECTS BASLATMA
    # ------------------------------------------------------------
    def ae_baslat(self):
        if self.sahneler:
            try:
                script_txt_uret(self.sahneler)
                self.log_yaz("script.txt guncellendi (AE baslatilmadan once otomatik).")
            except Exception as e:
                self.log_yaz(f"[HATA] script.txt guncellenemedi: {e}")

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

        self.log_yaz(f"After Effects baslatiliyor: {ae_yolu}")
        try:
            subprocess.Popen([ae_yolu, "-r", jsx_yolu])
            self.log_yaz("After Effects komutu gonderildi.")
        except Exception as e:
            self.log_yaz(f"[HATA] After Effects baslatilamadi: {e}")
            messagebox.showerror("Baslatilamadi", f"After Effects baslatilamadi:\n{e}")

    def _ae_yolunu_sor(self):
        messagebox.showinfo(
            "AfterFX.exe konumu",
            r"AfterFX.exe dosyasini sec. Genelde: "
            r"C:\Program Files\Adobe\Adobe After Effects <surum>\Support Files\AfterFX.exe"
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
        yol = filedialog.askopenfilename(title="canavar_asistan.jsx sec", filetypes=[("JSX", "*.jsx")])
        if yol:
            self.ayarlar["jsx_yolu"] = yol
            ayarlari_kaydet(self.ayarlar)
        return yol or None

    def gemini_anahtarini_duzenle(self):
        mevcut = self.ayarlar.get("gemini_api_anahtari", "")
        yeni = simpledialog.askstring(
            "Gemini API Anahtari",
            "Google AI Studio'dan aldigin ucretsiz API anahtarini yapistir:",
            initialvalue=mevcut, parent=self.pencere, show="*"
        )
        if yeni is not None and yeni.strip():
            self.ayarlar["gemini_api_anahtari"] = yeni.strip()
            ayarlari_kaydet(self.ayarlar)
            self.log_yaz("Gemini API anahtari kaydedildi.")

    def ai_ile_sahne_uret(self):
        api_anahtari = self.ayarlar.get("gemini_api_anahtari", "").strip()
        if not api_anahtari:
            messagebox.showwarning(
                "API Anahtari Eksik",
                "Once 'Gemini API Anahtari' butonundan ucretsiz API anahtarini girmen lazim."
            )
            return

        hikaye_metni = self.hikaye_kutusu.get("1.0", "end-1c").strip()
        if not hikaye_metni:
            messagebox.showwarning("Bos Hikaye", "Once yukaridaki kutuya bir hikaye/istek yaz.")
            return

        mevcut_arkaplanlar = kutuphanedeki_arkaplanlar()
        mevcut_karakterler = kutuphanedeki_karakterler()

        if not mevcut_arkaplanlar or not mevcut_karakterler:
            messagebox.showwarning(
                "Kutuphane Bos",
                "AI'nin sahne uretebilmesi icin once en az bir arka plan ve bir karakteri "
                "'Yeni Sahne Ekle' penceresinden kutuphaneye eklemis olman lazim."
            )
            return

        self.ai_uret_butonu.config(state="disabled", text="AI DUSUNUYOR...")
        self.log_yaz("")
        self.log_yaz("Gemini'ye hikaye gonderiliyor, bekleniyor...")

        def arka_plan_gorevi():
            sahneler, hata_veya_uyari = gemini_ile_sahne_uret(
                api_anahtari, hikaye_metni, mevcut_arkaplanlar, mevcut_karakterler
            )
            self._ai_sonuc_kuyrugu.put((sahneler, hata_veya_uyari))

        threading.Thread(target=arka_plan_gorevi, daemon=True).start()

    def _ai_sonucunu_isle(self, sahneler, hata_veya_uyari):
        self.ai_uret_butonu.config(state="normal", text="AI ile Sahneleri Uret")

        if sahneler is None:
            self.log_yaz(f"[HATA] AI sahne uretemedi: {hata_veya_uyari}")
            messagebox.showerror("AI Hatasi", f"Gemini sahne uretemedi:\n\n{hata_veya_uyari}")
            return

        for sahne in sahneler:
            self.sahneler.append(sahne)
        self._sahne_listesini_guncelle()

        self.log_yaz(f"AI {len(sahneler)} sahne uretti ve listeye eklendi.")
        if hata_veya_uyari:
            self.log_yaz("AI uyarilari (bazi degerler duzeltildi):\n" + hata_veya_uyari)
        messagebox.showinfo(
            "Sahneler Uretildi",
            f"AI {len(sahneler)} yeni sahne uretti. Listeyi kontrol et, istersen duzenle, "
            "sonra 'script.txt Olustur' ve 'AFTER EFFECTS'I BASLAT' ile devam et."
        )

    def ayarlari_duzenle(self):
        pencere = tk.Toplevel(self.pencere)
        pencere.title("Ayarlar")
        pencere.geometry("480x220")

        tk.Label(pencere, text="AfterFX.exe yolu:", font=("Segoe UI", 10)).pack(pady=(15, 5), padx=15, anchor="w")
        ae_etiketi = tk.Label(pencere, text=self.ayarlar.get("ae_yolu", "(secilmedi)"),
                                font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w")
        ae_etiketi.pack(fill="x", padx=15)

        def ae_sec():
            yol = self._ae_yolunu_sor()
            if yol:
                ae_etiketi.config(text=yol)

        tk.Button(pencere, text="AfterFX.exe Sec", command=ae_sec).pack(pady=(5, 15), padx=15, anchor="w")

        tk.Label(pencere, text="canavar_asistan.jsx yolu:", font=("Segoe UI", 10)).pack(pady=(0, 5), padx=15, anchor="w")
        jsx_etiketi = tk.Label(pencere, text=self.ayarlar.get("jsx_yolu", "(secilmedi)"),
                                 font=("Segoe UI", 8), wraplength=440, justify="left", anchor="w")
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
    uygulama = AEStudioPaneli(pencere)
    pencere.mainloop()