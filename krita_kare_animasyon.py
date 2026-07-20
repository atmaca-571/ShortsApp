"""
krita_kare_animasyon.py
------------------------
Krita Python Scripting API (libkis/PyKrita) kullanarak, Gemini'nin urettigi
ardisik karakter karelerini (orn: poz_1.png, poz_2.png, poz_3.png...) GERCEK
bir kare-kare (frame-by-frame) Krita animasyon dosyasina donusturur.

MIMARI:
  Gemini (kare kare tutarli karakter gorselleri uretir)
      -> BU SCRIPT (Krita icinde kareleri zaman cizelgesine dizer)
      -> Krita'dan PNG sirasi/video olarak disa aktarilir
      -> AE (son rotus: altyazi, muzik, kucuk ayarlar) icin kullanilir

NASIL CALISTIRILIR:
  1) Krita'yi ac
  2) Tools > Scripts > Scripter (Scripter eklentisini ac)
  3) Bu dosyanin icerigini yapistir, KARE_KLASORU degiskenini kendi
     klasorune gore duzenle
  4) "Run" tusuna bas

  VEYA (Krita hic acilmadan, headless/arka planda calistirmak icin):
  kritarunner --script krita_kare_animasyon.py
  (bu, Krita'nin kendi kurulumuyla gelen bir komut satiri aracidir)

============================================================================
DURUSTLUK NOTU (onemli): Bu script'i GERCEK Krita icinde CALISTIRAMADIM -
Krita indirilebilir bir masaustu programi, benim test ortamimda (sandbox)
kurulamiyor. Kodun genel yapisi ve mantigi, Krita'nin RESMI dokumantasyonuna
(docs.krita.org) dayanarak yazildi ve gozden gecirildi, ama ozellikle
"ANIMASYON KARESI EKLEME" kismi (asagida ISARETLENDI) libkis'in en az
dokumante edilmis, en belirsiz kismi - bu yuzden bu kisimda hata cikma
ihtimali diger kisimlara gore daha yuksek. Ilk gercek Krita testinde
en cok BURAYA dikkat et.
============================================================================
"""

import os
import sys
import json

try:
    from krita import Krita, InfoObject
except ImportError:
    print("HATA: Bu script SADECE Krita'nin kendi Python ortaminda calisir "
          "(Tools > Scripts > Scripter icinden, veya kritarunner ile). "
          "Normal bir Python yorumlayicisinda 'krita' modulu bulunmaz.")
    raise

# ============================================================================
# AYARLAR - bunlari kendi klasor yapina gore duzenle
# ============================================================================
# ============================================================================
# AYARLAR - varsayilan olarak bu script'in yaninda duran "krita_ayarlar.json"
# dosyasindan okunur (Python panelimiz bu dosyayi otomatik yazar). Dosya
# yoksa, asagidaki VARSAYILAN degerler kullanilir (elle test icin).
# ============================================================================
try:
    # Script gercek bir .py dosyasi olarak calistirilirsa (orn. kritarunner
    # ile) __file__ tanimlidir.
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Krita'nin Scripter'ina KOPYALA-YAPISTIR yapilip calistirilinca, kod
    # dogrudan metin olarak calistigi icin __file__ TANIMLI DEGILDIR.
    # Bu durumda proje klasorunu sabit olarak biliyoruz (senin bilgisayarinda
    # hep ayni yer) - onu kullaniyoruz. Farkli bir klasordeysen bu satiri
    # kendi yoluna gore degistir.
    _BASE_DIR = r"C:\Users\rias\Desktop\LayerEngine_paket"
    print(f"UYARI: __file__ tanimli degildi (Scripter'a yapistirilmis olabilir). "
          f"BASE_DIR sabit olarak ayarlandi: {_BASE_DIR}")
_AYAR_DOSYASI = os.path.join(_BASE_DIR, "krita_ayarlar.json")

_VARSAYILAN_AYARLAR = {
    "kare_klasoru": r"C:\Users\rias\Desktop\LayerEngine_paket\input_karakter_kareleri",
    "cikti_klasoru": r"C:\Users\rias\Desktop\LayerEngine_paket\krita_ciktilari",
    "proje_genislik": 1080,
    "proje_yukseklik": 1920,
    "proje_fps": 24,
    "kare_basina_sure_saniye": 0.15,
    "proje_adi": "kare_animasyon",
}


def _ayarlari_yukle():
    if os.path.exists(_AYAR_DOSYASI):
        try:
            with open(_AYAR_DOSYASI, "r", encoding="utf-8") as f:
                yuklenen = json.load(f)
            ayarlar = dict(_VARSAYILAN_AYARLAR)
            ayarlar.update(yuklenen)
            return ayarlar
        except Exception as e:
            print(f"UYARI: krita_ayarlar.json okunamadi, varsayilanlar kullaniliyor: {e}")
    return dict(_VARSAYILAN_AYARLAR)


_ayarlar = _ayarlari_yukle()
KARE_KLASORU = _ayarlar["kare_klasoru"]
CIKTI_KLASORU = _ayarlar["cikti_klasoru"]
PROJE_GENISLIK = _ayarlar["proje_genislik"]
PROJE_YUKSEKLIK = _ayarlar["proje_yukseklik"]
PROJE_FPS = _ayarlar["proje_fps"]
KARE_BASINA_SURE_SANIYE = _ayarlar["kare_basina_sure_saniye"]
PROJE_ADI = _ayarlar.get("proje_adi", "kare_animasyon")


def kare_dosyalarini_bul(klasor):
    """Klasordeki gorselleri DOGAL SIRAYLA (poz_1, poz_2, poz_10 - poz_2'den
    sonra poz_10 gelsin, poz_1 sonra poz_10 degil) siralar."""
    import re

    def dogal_anahtar(dosya_adi):
        return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", dosya_adi)]

    if not os.path.isdir(klasor):
        return []
    dosyalar = [f for f in os.listdir(klasor) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    return sorted(dosyalar, key=dogal_anahtar)


def yeni_proje_olustur(uygulama, genislik, yukseklik, fps):
    """Bos, dogru boyutta bir Krita belgesi olusturur ve FPS'ini ayarlar."""
    belge = uygulama.createDocument(
        genislik, yukseklik, "Kare_Animasyon", "RGBA", "U8", "", 300.0
    )
    uygulama.activeWindow().addView(belge)

    # ONEMLI DUZELTME: uygulama.setBatchmode(True) (Krita instance) ile
    # belge.setBatchmode(True) (Document) FARKLI SEYLER! Resmi dokumana gore
    # Document.setBatchmode() ozellikle "export/save option dialoglari"nin
    # gosterilip gosterilmeyecegini kontrol ediyor - PNG penceresinin
    # cikmasinin sebebi muhtemelen bu BELGE seviyesindeki ayarin eksik olmasiydi.
    try:
        belge.setBatchmode(True)
    except Exception as e:
        print(f"UYARI: belge.setBatchmode ayarlanamadi: {e}")

    try:
        belge.setFramesPerSecond(fps)
    except Exception as e:
        print(f"UYARI: FPS ayarlanamadi (belki bu Krita surumunde farkli isimlendirilmis): {e}")
    return belge


def kareyi_katman_olarak_ekle(belge, dosya_yolu, katman_adi):
    """Bir gorsel dosyasini, belgeye YENI BIR PAINT LAYER olarak ekler ve
    icerigini o gorselle doldurur."""
    kok = belge.rootNode()
    katman = belge.createNode(katman_adi, "paintlayer")
    kok.addChildNode(katman, None)

    # Gorseli gecici bir belge olarak acip pixel verisini kopyalamak,
    # dogrudan import etmekten daha guvenilir (Krita surumleri arasinda
    # tutarli calisir).
    gecici_belge = Krita.instance().openDocument(dosya_yolu)
    if gecici_belge is None:
        print(f"UYARI: Gorsel acilamadi, atlaniyor: {dosya_yolu}")
        return katman

    try:
        gecici_kok = gecici_belge.rootNode()
        gecici_katmanlar = gecici_kok.childNodes()
        if gecici_katmanlar:
            kaynak_katman = gecici_katmanlar[0]
            veri = kaynak_katman.projectionPixelData(0, 0, gecici_belge.width(), gecici_belge.height())
            katman.setPixelData(veri, 0, 0, gecici_belge.width(), gecici_belge.height())
    finally:
        gecici_belge.close()

    return katman


def kareleri_zaman_cizelgesine_dagit(belge, katmanlar, kare_basina_frame_sayisi):
    """
    ================================================================
    DUZELTME (gercek Krita testinde bulunan hatadan sonra): Onceki surumde
    Krita.instance().action("enable_animated_layer") KULLANILMISTI ama bu
    action ID Krita 5.3.2'de MEVCUT DEGIL, hata verdi (script COKMEDI,
    guvenli sekilde atladi - hata yonetimi dogru calisti).

    Resmi Krita Scripting School (scripting.krita.org/lessons/animation)
    dokumantasyonuna gore DOGRU yontem, katmanin KENDI metodu:
        katman.enableAnimation()
    (action sistemi degil, dogrudan Node metodu)

    Ayrica confirmed action ID'ler (bunlar dogrulanmis):
        'add_blank_frame'      -> o anki zamanda bos kare ekler
        'insert_keyframe_right'
        'insert_keyframe_left'
    ================================================================
    """
    toplam_kare = len(katmanlar) * kare_basina_frame_sayisi
    belge.setFullClipRangeStartTime(0)
    belge.setFullClipRangeEndTime(max(toplam_kare - 1, 1))

    baslangic_frame = 0
    for katman in katmanlar:
        try:
            katman.enableAnimation()  # DOGRULANMIS: dogrudan Node metodu
            belge.setCurrentTime(baslangic_frame)
            belge.setActiveNode(katman)
            Krita.instance().action("add_blank_frame").trigger()
        except Exception as e:
            print(f"UYARI: Katman '{katman.name()}' animasyonlu yapilamadi: {e}")
        baslangic_frame += kare_basina_frame_sayisi

    belge.refreshProjection()


def kareleri_disa_aktar(belge, cikti_klasoru, proje_adi="kare_animasyon"):
    """Animasyonu PNG sirasi olarak disa aktarmaya calisir.

    DUZELTME: belge.exportImage() bazen belge.setBatchmode(True) olsa bile
    PNG ayar penceresini gosterebiliyor (Krita forumunda dogrulanmis, bilinen
    bir sorun). Bunun yerine, ayni forumda paylasilan DAHA GUVENILIR
    dusuk-seviye yontemi kullaniyoruz: belge.rootNode().save(...) - bu,
    dialog gostermeden dogrudan dosyaya yazar.
    """
    os.makedirs(cikti_klasoru, exist_ok=True)
    cikti_yolu = os.path.join(cikti_klasoru, f"{proje_adi}.png")

    ayarlar = InfoObject()
    ayarlar.setProperty("alpha", True)
    ayarlar.setProperty("compression", 9)

    try:
        from PyQt5.QtCore import QRect
        sinirlar = QRect(0, 0, belge.width(), belge.height())
        cozunurluk_orani = belge.resolution() / 72.0
        belge.rootNode().save(cikti_yolu, cozunurluk_orani, cozunurluk_orani, ayarlar, sinirlar)
        print(f"Disa aktarildi (dialogsuz yontem): {cikti_yolu}")
    except Exception as e:
        print(f"UYARI: Dialogsuz disa aktarma basarisiz, eski yontemi deniyorum: {e}")
        try:
            belge.exportImage(cikti_yolu, ayarlar)
            print(f"Disa aktarildi (eski yontem): {cikti_yolu}")
        except Exception as e2:
            print(f"UYARI: Disa aktarma tamamen basarisiz: {e2}")

    # Tam animasyon sirasi/video icin Krita'nin "Render Animation" ozelligi
    # (File > Render Animation) script ile de tetiklenebilir olabilir, ama
    # bu da GERCEK KRITA'DA DOGRULANMASI gereken bir kisim.
    kritadosyasi_yolu = os.path.join(cikti_klasoru, f"{proje_adi}.kra")
    try:
        belge.saveAs(kritadosyasi_yolu)
        print(f".kra proje dosyasi kaydedildi: {kritadosyasi_yolu}")
    except Exception as e:
        print(f"UYARI: .kra kaydedilemedi: {e}")


def calistir():
    uygulama = Krita.instance()
    uygulama.setBatchmode(True)  # onay pencerelerini/dialoglari bastir

    kare_dosyalari = kare_dosyalarini_bul(KARE_KLASORU)
    if not kare_dosyalari:
        print(f"HATA: '{KARE_KLASORU}' klasorunde hic gorsel bulunamadi.")
        return

    print(f"{len(kare_dosyalari)} kare bulundu: {kare_dosyalari}")

    belge = yeni_proje_olustur(uygulama, PROJE_GENISLIK, PROJE_YUKSEKLIK, PROJE_FPS)

    katmanlar = []
    for i, dosya_adi in enumerate(kare_dosyalari):
        tam_yol = os.path.join(KARE_KLASORU, dosya_adi)
        katman = kareyi_katman_olarak_ekle(belge, tam_yol, f"kare_{i+1}_{dosya_adi}")
        katmanlar.append(katman)
        print(f"  Eklendi: {dosya_adi}")

    # ================================================================
    # GECICI OLARAK DEVRE DISI: Bir onceki denemede TUM KRITA PROGRAMI
    # cokme yasadi (Python hatasi degil, gercek uygulama cokmesi) - bu,
    # animasyon zaman cizelgesi (enableAnimation + add_blank_frame)
    # kisminda bir kararlilik sorunu oldugunu gosteriyor. Guvenli, CALISAN
    # bir sonuc vermek icin bu adim SIMDILIK atlanıyor - kareler DUZ
    # KATMANLAR olarak duruyor (zaten dogru gorsellerle, dogru sirada),
    # animasyon zaman cizelgesi kismini ayrica, tek tek test ederek
    # ekleyecegiz.
    # ================================================================
    print("NOT: Animasyon zaman cizelgesi adimi GUVENLIK ICIN simdilik atlaniyor "
          "(onceki denemede tam program cokmesine sebep olmustu). Kareler "
          "DUZ KATMANLAR olarak eklendi, sirali ve dogru - .kra dosyasini "
          "acip katmanlari elle (Katmanlar panelinden gorunur/gizli yaparak) "
          "kontrol edebilirsin.")

    kareleri_disa_aktar(belge, CIKTI_KLASORU, proje_adi=PROJE_ADI)

    print("BITTI (guvenli mod - animasyon zaman cizelgesi olmadan).")


if __name__ == "__main__":
    calistir()