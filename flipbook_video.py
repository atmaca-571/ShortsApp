"""
flipbook_video.py
-----------------
Defter sayfasi / flipbook film:
- Her gorsel = TAM SAYFA (manga ızgarasi degil)
- Hizli cevirme hissi (klasik defter animasyonu)
- Mevcut poz_*.png veya tek tek full-page PNG'lerden video

Calistir:
  python flipbook_video.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

BASE = Path(__file__).resolve().parent
KARE = BASE / "input_karakter_kareleri"
CIKTI = BASE / "krita_ciktilari"
SEQ = BASE / "_tmp_flip"


def _ff() -> str:
    cfg = BASE / "krita_studio_config.json"
    if cfg.exists():
        yol = (json.loads(cfg.read_text(encoding="utf-8")).get("ffmpeg_yolu") or "").strip()
        if yol and Path(yol).exists():
            return yol
    return r"C:\Users\rias\Desktop\kodlama\ffmpeg-8.1.2-essentials_build\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"


def _sirali_kareler() -> list[Path]:
    dosyalar = sorted(
        [p for p in KARE.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}],
        key=lambda p: p.name,
    )
    # poz_1, poz_2 ... tercih
    pozlar = [p for p in dosyalar if p.stem.lower().startswith("poz_")]
    if pozlar:
        def key(p: Path):
            try:
                return int("".join(ch for ch in p.stem if ch.isdigit()) or "0")
            except ValueError:
                return 0
        return sorted(pozlar, key=key)
    return dosyalar


def sayfa_yap(src: Image.Image, out_w: int = 1080, out_h: int = 1920) -> Image.Image:
    """
    Flipbook sayfasi: canvas'i TAM DOLDUR (manga hucresi / letterbox hissi yok).
    Kucuk kaynagi agresif buyut + keskinlestir.
    """
    im = src.convert("RGB")
    # kucuk panel ise once 4x
    if max(im.size) < 700:
        im = im.resize((im.size[0] * 4, im.size[1] * 4), Image.LANCZOS)
    elif max(im.size) < 1100:
        im = im.resize((im.size[0] * 2, im.size[1] * 2), Image.LANCZOS)

    im = ImageEnhance.Sharpness(im).enhance(1.55)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))

    # cover: kenarlari doldur (defter sayfasi gibi edge-to-edge)
    iw, ih = im.size
    scale = max(out_w / iw, out_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im2 = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - out_w) // 2
    top = max(0, (nh - out_h) // 2 - int(out_h * 0.02))  # hafif uste (kafa)
    if top + out_h > nh:
        top = nh - out_h
    return im2.crop((left, top, left + out_w, top + out_h))


def main():
    kareler = _sirali_kareler()
    if not kareler:
        raise SystemExit(f"Kare yok: {KARE}")

    CIKTI.mkdir(parents=True, exist_ok=True)
    if SEQ.exists():
        shutil.rmtree(SEQ)
    SEQ.mkdir()

    # Flipbook hissi: ~10-12 fps klasik defter cevirme (her sayfa ~2-3 frame @24fps)
    # Daha "ceviriyorum" hissi icin sayfa basina ~0.18-0.22 sn
    SAYFA_SURE = 0.20
    FPS = 24
    tekrar = max(2, int(round(SAYFA_SURE * FPS)))

    frame_i = 1
    for yol in kareler:
        sayfa = sayfa_yap(Image.open(yol))
        for _ in range(tekrar):
            sayfa.save(SEQ / f"kare_{frame_i:05d}.png")
            frame_i += 1
        print(yol.name, "->", tekrar, "frame")

    video = CIKTI / "rias_flipbook_v1.mp4"
    ff = _ff()
    cmd = [
        ff, "-y",
        "-framerate", str(FPS),
        "-i", str(SEQ / "kare_%05d.png"),
        "-c:v", "libx264", "-crf", "12", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("ffmpeg", r.returncode, video, video.stat().st_size if video.exists() else 0)
    if r.returncode != 0:
        print(r.stderr[-1000:])
        raise SystemExit(1)

    shutil.copy2(video, CIKTI / "son_video.mp4")
    shutil.rmtree(SEQ, ignore_errors=True)

    (BASE / "ae_edit_notes.txt").write_text(
        "=== FLIPBOOK V1 ===\n"
        "Defter sayfasi mantigi: her kare TAM SAYFA, hizli cevirme.\n"
        f"Video: {video.name}\n"
        "Manga ızgarasi YOK. Sonraki PixAI uretimleri TEK SAYFA (9:16) olmali.\n",
        encoding="utf-8",
    )
    print("DONE", video)


if __name__ == "__main__":
    main()
