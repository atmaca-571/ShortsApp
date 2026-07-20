"""
PixAI 3x3 sheet -> temiz paneller -> hikaye sirali 9:16 video.
Calistir: python pixai_sheet_video.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

BASE = Path(__file__).resolve().parent
SHEET_DIR = BASE / "gemini_indirilenler" / "pixai_batch"
KARE = BASE / "input_karakter_kareleri"
CIKTI = BASE / "krita_ciktilari"
KAR = BASE / "input_characters"
SEQ = BASE / "_tmp_seq"


def _ff() -> str:
    cfg = BASE / "krita_studio_config.json"
    if cfg.exists():
        yol = (json.loads(cfg.read_text(encoding="utf-8")).get("ffmpeg_yolu") or "").strip()
        if yol and os.path.exists(yol):
            return yol
    return r"C:\Users\rias\Desktop\kodlama\ffmpeg-8.1.2-essentials_build\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"


def _numara_sil(crop: Image.Image) -> Image.Image:
    """Sol-ust numarayi cevre renkleriyle kapat (beyaz leke birakma)."""
    im = crop.convert("RGB")
    w, h = im.size
    nw, nh = max(10, int(w * 0.12)), max(10, int(h * 0.10))
    # ornek bolge: numaranin sag-altindan
    sx0, sy0 = min(w - 1, nw), min(h - 1, nh)
    sx1, sy1 = min(w, nw + max(8, w // 20)), min(h, nh + max(8, h // 20))
    patch = im.crop((sx0, sy0, sx1, sy1))
    # ortalama renk
    pixels = list(patch.getdata())
    if not pixels:
        fill = (30, 40, 55)
    else:
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        fill = (r, g, b)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, nw, nh], fill=fill)
    # ince kenar ayirici (gri cizgi) temizligi
    m = max(1, int(min(w, h) * 0.008))
    return im.crop((m, m, w - m, h - m))


def sheet_bol(yol: Path, satir: int = 3, sutun: int = 3) -> list[Image.Image]:
    img = Image.open(yol).convert("RGB")
    W, H = img.size
    pw, ph = W // sutun, H // satir
    out = []
    for r in range(satir):
        for c in range(sutun):
            sol, ust = c * pw, r * ph
            sag = W if c == sutun - 1 else sol + pw
            alt = H if r == satir - 1 else ust + ph
            out.append(_numara_sil(img.crop((sol, ust, sag, alt))))
    return out


def sahne_916(src: Image.Image, out_w: int = 1080, out_h: int = 1920) -> Image.Image:
    """Karakteri dikey short frame'e yerlestir; ustte kafa payi."""
    im = src.convert("RGB")
    # hafif keskinlik
    im = ImageEnhance.Sharpness(im).enhance(1.25)
    im = ImageEnhance.Contrast(im).enhance(1.05)

    # letterbox: paneli genisligin %92'sine sigdir, dikey ortala ama ust pay fazla
    margin_x = int(out_w * 0.04)
    top = int(out_h * 0.08)
    bot = int(out_h * 0.06)
    avail_w = out_w - margin_x * 2
    avail_h = out_h - top - bot
    iw, ih = im.size
    scale = min(avail_w / iw, avail_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im2 = im.resize((nw, nh), Image.LANCZOS)

    # arka plan: panel kenar ortalama (plaj/gece uyumlu)
    border = list(im.resize((8, 8), Image.BILINEAR).getdata())
    br = sum(p[0] for p in border) // len(border)
    bg = sum(p[1] for p in border) // len(border)
    bb = sum(p[2] for p in border) // len(border)
    canvas = Image.new("RGB", (out_w, out_h), (br, bg, bb))
    # hafif vignette hissi icin ust/alt koyulastirma yok — sade
    ox = (out_w - nw) // 2
    oy = top + (avail_h - nh) // 3  # biraz uste
    canvas.paste(im2, (ox, oy))
    return canvas


def main():
    sheets = sorted(SHEET_DIR.glob("sheet_*.png"))
    if not sheets:
        raise SystemExit(f"Sheet yok: {SHEET_DIR}")

    # tum panelleri cikar
    bank: dict[str, Image.Image] = {}
    for sh in sheets:
        paneller = sheet_bol(sh)
        for i, p in enumerate(paneller):
            key = f"{sh.stem}_p{i}"
            bank[key] = p

    # En iyi hikaye karisimi (elle secim — tutarli film ritmi)
    # sheet_6 = gece su + savas iyi; sheet_4 = climax enerji iyi; sheet_5/2 yedek
    # Dosya adlari kopya sirasina gore: sheet_1..6
    # Tercih: sheet_6 (gece acilis) + sheet_4 (savas) karisimi
    sira_keys = [
        "sheet_6_p0",  # gece sudan cikis
        "sheet_4_p1",  # plaj yuruyus
        "sheet_6_p2",  # dusman / kararli
        "sheet_4_p3",  # saldiri baslangic
        "sheet_6_p5",  # hizli dash
        "sheet_4_p6",  # enerji yukleme
        "sheet_4_p7",  # climax slash
        "sheet_6_p7",  # yumruk/patlama
        "sheet_4_p8",  # gunisigi final
    ]
    # eksik anahtar varsa ayni indeksten sheet_6
    fallback = [f"sheet_6_p{i}" for i in range(9)]
    secilen: list[Image.Image] = []
    for i, k in enumerate(sira_keys):
        if k in bank:
            secilen.append(bank[k])
        elif fallback[i] in bank:
            secilen.append(bank[fallback[i]])
        else:
            # herhangi bir sheet'ten
            any_key = f"sheet_1_p{i}"
            secilen.append(bank.get(any_key) or next(iter(bank.values())))

    # klasorleri hazirla
    KARE.mkdir(parents=True, exist_ok=True)
    CIKTI.mkdir(parents=True, exist_ok=True)
    KAR.mkdir(parents=True, exist_ok=True)
    for f in list(KARE.glob("*.png")) + list(KARE.glob("*.jpg")):
        f.unlink()

    for i, im in enumerate(secilen, 1):
        yol = KARE / f"poz_{i}.png"
        im.save(yol, quality=95)
        im.save(KAR / f"rias_pixai_{i}.png", quality=95)
        print("kayit", yol, im.size)

    # video kareleri — tempo: acilis biraz yavas, savas hizli, final orta
    sureler = [0.85, 0.70, 0.65, 0.55, 0.45, 0.50, 0.70, 0.55, 0.90]  # ~6.0sn
    if SEQ.exists():
        shutil.rmtree(SEQ)
    SEQ.mkdir()

    # fps=24 icin her sahneyi tekrarlayan kare yaz (duzgun sure)
    frame_i = 1
    for im, sure in zip(secilen, sureler):
        fr = sahne_916(im)
        n = max(1, int(round(sure * 24)))
        for _ in range(n):
            fr.save(SEQ / f"kare_{frame_i:05d}.png")
            frame_i += 1
    print("toplam frame", frame_i - 1)

    ff = _ff()
    video = CIKTI / "rias_pixai_film_v1.mp4"
    cmd = [
        ff, "-y",
        "-framerate", "24",
        "-i", str(SEQ / "kare_%05d.png"),
        "-c:v", "libx264", "-crf", "14", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("ffmpeg", r.returncode, video, video.stat().st_size if video.exists() else 0)
    if r.returncode != 0:
        print(r.stderr[-1200:])
        raise SystemExit(1)

    shutil.copy2(video, CIKTI / "son_video.mp4")
    # onizleme contact sheet
    thumbs = [sahne_916(im).resize((180, 320), Image.LANCZOS) for im in secilen]
    contact = Image.new("RGB", (180 * 3 + 8, 320 * 3 + 8), (20, 20, 24))
    for i, t in enumerate(thumbs):
        contact.paste(t, (4 + (i % 3) * 180, 4 + (i // 3) * 320))
    contact.save(CIKTI / "_qa_pixai_film_contact.png")

    notes = """=== PIXAI FILM V1 — AE NOTLARI ===
Video: krita_ciktilari/rias_pixai_film_v1.mp4 (~6sn)
Kareler: input_karakter_kareleri/poz_1..9.png

SIRALAMA:
1 sudan cikis (gece)
2 plaj yuruyus
3 tehdit / karar
4 saldiri
5 dash
6 enerji yukleme
7 climax slash
8 patlama/yumruk
9 gunisigi final

MUZIK: hizli beat, 0:00-0:02 build, 0:02-0:05 drop, 0:05-0:06 resolve
GECIS: hard cut (zaten aksiyon)
BILINEN EKSIKLER (PixAI kaynagi):
- panel numaralari bozuktu — biz sildik + hikayeyi elle siraladik
- geometri (gogus) abarti / AI kokusu var
- gece-gunduz isik sifti var — AE'de color grade birlestir
Sonraki PixAI: ayni seed/stil, 'consistent lighting dusk beach', daha az fanservice prompt
"""
    (BASE / "ae_edit_notes.txt").write_text(notes, encoding="utf-8")
    shutil.rmtree(SEQ, ignore_errors=True)
    print("DONE", video)


if __name__ == "__main__":
    main()
