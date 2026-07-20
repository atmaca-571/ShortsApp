"""
panel_film_uret.py
------------------
PixAI manga-ızgara sheet → kes → numara sil → hizala → buyut → flipbook video.

Numara SIRALAMA icin PixAI'de kalir; uygulamada kesilince silinir.
Kayma: karakter ayak hizasi + merkez sabitlenir.
Kalite: Real-ESRGAN (varsa) + istege bagli Topaz Video AI (final mp4).

Calistir:
  python panel_film_uret.py
  python panel_film_uret.py --sheet yol.png --satir 3 --sutun 3
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from krita_studio_paneli import (  # noqa: E402
    BUYUTULMUS_KLASORU,
    CIKTI_KLASORU,
    KARE_KLASORU,
    ayarlari_yukle,
    ffmpeg_ile_video_olustur,
    gorseli_izgaraya_bol,
    guvenli_png_kaydet,
    kareleri_buyut,
    kareleri_hizala,
)


def _ff(ayarlar: dict) -> str:
    yol = (ayarlar.get("ffmpeg_yolu") or "").strip()
    if yol and os.path.exists(yol):
        return yol
    return r"C:\Users\rias\Desktop\kodlama\ffmpeg-8.1.2-essentials_build\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"


def _topaz_var_mi() -> str | None:
    adaylar = [
        r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\ffmpeg.exe",
        r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\Topaz Video AI.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Topaz Labs LLC\Topaz Video AI\ffmpeg.exe"),
    ]
    for a in adaylar:
        if os.path.exists(a):
            return a
    return None


def _sheetleri_bul() -> list[Path]:
    d = BASE / "gemini_indirilenler" / "pixai_batch"
    if d.is_dir():
        return sorted(d.glob("sheet_*.png"))
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="Tek sheet PNG")
    ap.add_argument("--satir", type=int, default=3)
    ap.add_argument("--sutun", type=int, default=3)
    ap.add_argument("--sure", type=float, default=6.0, help="Toplam video suresi (sn)")
    args = ap.parse_args()

    sheets: list[Path] = []
    if args.sheet:
        sheets = [Path(args.sheet)]
    else:
        sheets = _sheetleri_bul()
    if not sheets:
        print("Sheet yok. --sheet yol.png ver veya gemini_indirilenler/pixai_batch/sheet_*.png koy.")
        return 1

    ayarlar = ayarlari_yukle()
    os.makedirs(KARE_KLASORU, exist_ok=True)
    os.makedirs(CIKTI_KLASORU, exist_ok=True)

    # eski kareleri temizle (guvenli)
    for f in Path(KARE_KLASORU).glob("poz_*.png"):
        try:
            f.unlink()
        except OSError:
            pass

    tum = []
    for sh in sheets:
        print("bol:", sh.name)
        tum.extend(gorseli_izgaraya_bol(str(sh), args.satir, args.sutun))

    # tek sheet kullan (ilk) — cok sheet varsa ilk 9
    if len(sheets) == 1:
        parcalar = tum[: args.satir * args.sutun]
    else:
        # karisik sheet'lerden ilk 9 hucre (sheet1)
        parcalar = tum[:9]

    print(f"{len(parcalar)} panel → hizala")
    hizali = kareleri_hizala(parcalar, hedef_w=768, hedef_h=1280)

    for i, im in enumerate(hizali, 1):
        yol = os.path.join(KARE_KLASORU, f"poz_{i}.png")
        guvenli_png_kaydet(im, yol)
        print("  kayit", yol)

    # buyut
    rs = (ayarlar.get("realesrgan_yolu") or "").strip()
    print("buyutme...", rs or "PIL")
    ok, msg = kareleri_buyut(rs, KARE_KLASORU, BUYUTULMUS_KLASORU, olcek=4)
    print("buyutme:", ok, msg)
    kaynak = BUYUTULMUS_KLASORU if ok and os.path.isdir(BUYUTULMUS_KLASORU) and any(
        f.endswith(".png") for f in os.listdir(BUYUTULMUS_KLASORU)
    ) else KARE_KLASORU

    n = len(hizali)
    kare_basina = args.sure / max(1, n)
    video = os.path.join(CIKTI_KLASORU, "rias_panel_flipbook.mp4")
    ff = _ff(ayarlar)
    okv, msgv = ffmpeg_ile_video_olustur(ff, kaynak, video, kare_basina)
    print("video:", okv, msgv)

    topaz = _topaz_var_mi()
    if topaz and okv:
        out2 = os.path.join(CIKTI_KLASORU, "rias_panel_flipbook_topaz.mp4")
        print("Topaz bulundu:", topaz)
        print(
            "Topaz Video AI GUI'den acip su dosyayi Proteus/Iris ile 2x isle:\n ",
            video,
            "\n(CLI model adi surume gore degisir; otomatik cagri atlandi.)",
        )
        # Not dosyasi
        Path(CIKTI_KLASORU, "TOPAZ_TALIMAT.txt").write_text(
            "1) Topaz Video AI ac\n"
            f"2) Input: {video}\n"
            "3) Model: Proteus veya Artemis / Iris (anime icin deneme)\n"
            "4) Scale 2x, export → rias_panel_flipbook_topaz.mp4\n",
            encoding="utf-8",
        )
    else:
        Path(CIKTI_KLASORU, "TOPAZ_TALIMAT.txt").write_text(
            "Topaz Video AI bu PC'de bulunamadi.\n"
            "Kurarsan: final mp4'u Topaz'a at → 2x upscale = en iyi kalite kurtarma.\n"
            "Simdilik Real-ESRGAN/PIL kare buyutmesi kullanildi.\n"
            f"Video: {video}\n",
            encoding="utf-8",
        )

    if okv and os.path.exists(video):
        shutil.copy2(video, os.path.join(CIKTI_KLASORU, "son_video.mp4"))
        print("DONE", video)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
