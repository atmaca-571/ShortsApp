"""
yardimci_maskot.py — Sexy pixel Rias yardimci (kanatsiz)
30+ animasyon: yurume, konusma, soru, opucuk, jiggle fizik.
"""

from __future__ import annotations

import math
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_YOLU = os.path.join(BASE_DIR, "assets", "yardimci_rias_pixel.png")
SPRITE_ALT = os.path.join(BASE_DIR, "assets", "yardimci_rias_alt.png")
SEFFAF = "#010101"

ADIM_METINLERI = {
    1: "Adim 1: Karakter fotonu sec~ Yardim ister misin?",
    2: "Adim 2: Stil resmi (opsiyonel). Sorun var mi?",
    3: "Adim 3: Hikayeyi yaz. Takildin mi, anlatayim mi?",
    4: "Adim 4: Metni Al → Gemini'ye Ctrl+V. Yardim edeyim mi?",
    5: "Adim 5: Resimleri Al. Karakteri unutma!",
    6: "Adim 6: Gemini ciktisini Ekle. Indirdin mi?",
    7: "Adim 7: Krita Video. Hazirsan tikla~",
    8: "Adim 8: AE Panel — sarki/timing orada!",
    0: "Bitti gibi~ Videonu oynatmak ister misin?",
}

# En az 30 hareket
ANIMASYONLAR = (
    "idle", "idle_sway", "idle_hip", "breath",
    "walk", "walk_fast", "strut", "skip",
    "wave", "wave_both", "point", "come_here",
    "look_left", "look_right", "look_up", "nod",
    "talk", "talk_fast", "ask", "think",
    "kiss", "blow_kiss", "wink", "blush",
    "jump", "bounce", "dance", "hip_sway",
    "celebrate", "surprised", "shy", "stretch",
    "squash", "spin", "bow", "sleep",
)

SORU_METINLERI = [
    "Takildin mi? Sor, cevaplayayim~",
    "Yardim edeyim mi? Sag tikla butona, anlatirim!",
    "Hangi adımdasın emin degilsen sor bana~",
    "Metni Topla'yi denedin mi? Istersen birlikte bakalom.",
    "Gemini tek gorsel verdiyse normal — icinde paneller var.",
    "DEVAM ET lazim mi? Kontrol edeyim mi?",
    "Karakter secili mi? Bakayim yardim edeyim~",
    "Sikildin mi? Ben yuruyeyim, sen hikaye yaz~",
    "Buyutme acik kalsin — kalite artsin. Anlatayim mi?",
    "20sn test ister misin? Turuncu butona bak~",
    "Videoyu gordun mu? 'Videoyu Oynat' yesil olsun.",
    "Opucuk atayim mi yoksa once adimi bitirelim? Hehe~",
    "Krita Video oncesi paneller eklendi mi?",
    "Gemini'ye karakteri de ekledin mi? Unutma~",
    "Sorun var mi? Buradayim, sor!",
]


def _chroma_yesil_magenta(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    pix = im.load()
    w, h = im.size
    for yy in range(h):
        for xx in range(w):
            r, g, b, a = pix[xx, yy]
            if a < 8:
                continue
            # magenta / yesil chroma
            if (r > 160 and g < 120 and b > 160) or (r < 50 and g > 180 and b < 50):
                pix[xx, yy] = (0, 0, 0, 0)
            elif r > 180 and b > 180 and g < 140 and abs(r - b) < 40:
                pix[xx, yy] = (0, 0, 0, 0)
            # siyahi / koyu gri export bg
            elif a > 0 and r < 8 and g < 8 and b < 8:
                pix[xx, yy] = (0, 0, 0, 0)
    return im


def _kirp_ve_sigdir(im: Image.Image, size: int) -> Image.Image:
    """Alpha bbox kirp, oran bozmadan kareye yerlestir (bos padding)."""
    im = im.convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        pad = 2
        im = im.crop((
            max(0, x0 - pad), max(0, y0 - pad),
            min(im.size[0], x1 + pad), min(im.size[1], y1 + pad),
        ))
    w, h = im.size
    if w < 1 or h < 1:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = min(size / w, size / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    method = Image.NEAREST if max(w, h) <= 320 else Image.LANCZOS
    resized = im.resize((nw, nh), method)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
    return out


def _jiggle_varyant(im: Image.Image, miktar: float) -> Image.Image:
    """Gogus bolgesini hafif kaydir — oran bozmadan (scale yok)."""
    w, h = im.size
    out = im.copy()
    y0 = int(h * 0.36)
    y1 = int(h * 0.52)
    mid = im.crop((0, y0, w, y1))
    dx = int(round(miktar * 1.5))
    dy = int(round(-miktar * 2))
    # once orta seridi temizle, sonra kaydirilmis yapistir
    clear = Image.new("RGBA", (w, y1 - y0), (0, 0, 0, 0))
    out.paste(clear, (0, y0))
    out.paste(mid, (dx, y0 + dy), mid)
    return out


def _agiz_varyant(im: Image.Image, acik: bool) -> Image.Image:
    """Konusma icin agiza kucuk piksel (yuz ortasi)."""
    out = im.copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    mx, my = int(w * 0.50), int(h * 0.28)
    if acik:
        d.ellipse([mx - 2, my, mx + 2, my + 3], fill=(90, 30, 50, 220))
    else:
        d.line([(mx - 2, my + 1), (mx + 2, my + 1)], fill=(90, 30, 50, 200), width=1)
    return out


def _balon_png(metin: str, max_w: int = 248) -> Image.Image:
    uzun = len(metin) > 70
    punto = 11 if uzun else 13
    try:
        font = ImageFont.truetype("segoeui.ttf", punto)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", punto)
        except Exception:
            font = ImageFont.load_default()
    pad_x, pad_y = 12, 8
    kelimeler = metin.split()
    satirlar, satir = [], ""
    for k in kelimeler:
        deneme = (satir + " " + k).strip()
        bbox = font.getbbox(deneme)
        if bbox[2] - bbox[0] > max_w - pad_x * 2 and satir:
            satirlar.append(satir)
            satir = k
        else:
            satir = deneme
    if satir:
        satirlar.append(satir)
    if not satirlar:
        satirlar = [metin]
    satir_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1] + 3
    ic_h = pad_y * 2 + satir_h * len(satirlar)
    ic_w = pad_x * 2
    for s in satirlar:
        bb = font.getbbox(s)
        ic_w = max(ic_w, bb[2] - bb[0] + pad_x * 2)
    ic_w = min(max(ic_w, 80), max_w)
    kuyruk = 10
    W, H = ic_w + 4, ic_h + kuyruk + 4
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill, edge = (255, 240, 245, 255), (140, 40, 70, 255)
    d.rectangle([1, 1, ic_w + 2, ic_h + 1], fill=fill, outline=edge, width=2)
    mid = W // 2
    d.polygon([(mid - 8, ic_h - 2), (mid + 8, ic_h - 2), (mid, ic_h + kuyruk)], fill=fill)
    d.line([(mid - 8, ic_h - 1), (mid, ic_h + kuyruk), (mid + 8, ic_h - 1)], fill=edge, width=2)
    y = pad_y + 2
    for s in satirlar:
        d.text((pad_x + 2, y), s, fill=(70, 20, 40, 255), font=font)
        y += satir_h
    return im


class YardimciMaskot:
    W, H, BODY = 320, 300, 156

    def __init__(self, root: tk.Tk, panel):
        self.root = root
        self.panel = panel
        self.aktif = True
        self.adim = 1
        self.frame_i = 0
        self.x = self.tx = 140.0
        self.y = self.ty = 200.0
        self.vx = self.vy = 0.0
        self.t = 0.0
        self._yon = 1
        self._durum = "idle"
        self._durum_tick = 0
        self._anim = "idle"
        self._anim_tick = 0
        self._anim_sure = 40
        self._burun = 0.0
        self._goz_kirp = 0
        self._emote_sira = 0
        self._ozel_metin = None
        self._ozel_metin_tick = 0
        self._grab_ox = self._grab_oy = 0
        self._throw_hist = []
        self._partikuller = []
        self._stil_onerme_yapildi = False
        self._mx = self._my = 0
        self._idle_baslangic = time.time()
        self._balon_gorunur = False
        self._balon_tick = 0
        self._balon_foto = None
        self._soru_sayac = 0
        self._jiggle = 0.0
        self._jiggle_v = 0.0
        self._konusuyor = False
        self._son_x = self.x
        self._son_y = self.y

        self.win = tk.Toplevel(root)
        self.win.title("Yardimci")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", False)
        try:
            self.win.wm_attributes("-transparentcolor", SEFFAF)
        except tk.TclError:
            pass
        self.win.configure(bg=SEFFAF)
        self.win.geometry(f"{self.W}x{self.H}+200+200")
        self.root.bind("<FocusIn>", self._panel_odak, add="+")
        self.root.bind("<FocusOut>", self._panel_odak_kaybi, add="+")

        self.canvas = tk.Canvas(
            self.win, width=self.W, height=self.H, bg=SEFFAF, highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        self._sprite_yukle()

        self.balon_id = self.canvas.create_image(self.W // 2, 36, state="hidden")
        self.sprite_id = self.canvas.create_image(self.W // 2, 178, image=self._foto)
        self.agiz_id = self.canvas.create_oval(
            0, 0, 0, 0, fill="#9E3050", outline="", state="hidden"
        )
        self.kalp_id = self.canvas.create_text(
            0, 0, text="<3", fill="#FF4081", font=("Segoe UI", 14, "bold"), state="hidden"
        )

        self.canvas.bind("<ButtonPress-1>", self._basildi)
        self.canvas.bind("<B1-Motion>", self._surukleniyor)
        self.canvas.bind("<ButtonRelease-1>", self._birakildi)
        self.canvas.bind("<Button-3>", self._sag_tik)
        self.canvas.bind("<Double-Button-1>", self._cift_tik)
        self.canvas.bind("<Button-2>", lambda e: self.toggle())

        try:
            self._mx = self.root.winfo_pointerx()
            self._my = self.root.winfo_pointery()
        except Exception:
            pass

        self._anim_degistir("wave")
        self._tick()
        self.root.after(500, self.adimi_guncelle)
        self.root.after(700, lambda: self._soyle(
            "Selam~ Ben Rias. Yuruyorum, soruyorum, opucuk atiyorum~ Sag tik=hareket!", 80
        ))
        self.root.after(10000, self._rastgele_soru_dongusu)

    # ------------------------------------------------------------------ asset
    def _sprite_yukle(self):
        try:
            # Once temiz pixel alt (168), yoksa ana sprite
            adaylar = []
            if os.path.exists(SPRITE_ALT):
                adaylar.append(SPRITE_ALT)
            if os.path.exists(SPRITE_YOLU):
                adaylar.append(SPRITE_YOLU)
            im = None
            for yol in adaylar:
                raw = _chroma_yesil_magenta(Image.open(yol))
                if raw.getbbox():
                    im = _kirp_ve_sigdir(raw, self.BODY)
                    break
            if im is None:
                im = self._ciz_yedek_pixel()
        except Exception:
            im = self._ciz_yedek_pixel()
        self._base_im = im
        self._varyasyonlari_uret(im)

    def _varyasyonlari_uret(self, im: Image.Image):
        self._imgs = {}
        for yon, mirror in ((1, False), (-1, True)):
            base = im.transpose(Image.FLIP_LEFT_RIGHT) if mirror else im
            key = "n" if yon > 0 else "m"
            self._imgs[key] = ImageTk.PhotoImage(base)
            self._imgs[f"{key}_sq"] = ImageTk.PhotoImage(
                base.resize((int(self.BODY * 1.08), int(self.BODY * 0.88)), Image.NEAREST)
            )
            self._imgs[f"{key}_st"] = ImageTk.PhotoImage(
                base.resize((int(self.BODY * 0.90), int(self.BODY * 1.10)), Image.NEAREST)
            )
            self._imgs[f"{key}_l"] = ImageTk.PhotoImage(
                base.rotate(8, expand=True, fillcolor=(0, 0, 0, 0))
            )
            self._imgs[f"{key}_r"] = ImageTk.PhotoImage(
                base.rotate(-8, expand=True, fillcolor=(0, 0, 0, 0))
            )
            self._imgs[f"{key}_ll"] = ImageTk.PhotoImage(
                base.rotate(16, expand=True, fillcolor=(0, 0, 0, 0))
            )
            self._imgs[f"{key}_rr"] = ImageTk.PhotoImage(
                base.rotate(-16, expand=True, fillcolor=(0, 0, 0, 0))
            )
            # jiggle frame'leri
            for i, m in enumerate((-0.9, -0.4, 0.4, 0.9, 1.2)):
                j = _jiggle_varyant(base, m)
                self._imgs[f"{key}_j{i}"] = ImageTk.PhotoImage(j)
            # konusma agiz
            self._imgs[f"{key}_talk0"] = ImageTk.PhotoImage(_agiz_varyant(base, False))
            self._imgs[f"{key}_talk1"] = ImageTk.PhotoImage(_agiz_varyant(base, True))
            # kiss puckerslight squash + blush shift
            kiss = _jiggle_varyant(base, 0.5)
            d = ImageDraw.Draw(kiss)
            ww, hh = kiss.size
            d.ellipse([int(ww * 0.42), int(hh * 0.28), int(ww * 0.48), int(hh * 0.33)],
                      fill=(255, 120, 150, 160))
            d.ellipse([int(ww * 0.52), int(hh * 0.28), int(ww * 0.58), int(hh * 0.33)],
                      fill=(255, 120, 150, 160))
            self._imgs[f"{key}_kiss"] = ImageTk.PhotoImage(kiss)
        self._foto = self._imgs["n"]

    def _ciz_yedek_pixel(self) -> Image.Image:
        im = Image.new("RGBA", (self.BODY, self.BODY), (0, 0, 0, 0))
        p = im.load()
        K, S, R, G, SK = (
            (20, 20, 20, 255), (255, 210, 180, 255), (190, 30, 55, 255),
            (240, 70, 100, 255), (120, 70, 150, 255),
        )

        def blok(x0, y0, x1, y1, renk):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if 0 <= x < self.BODY and 0 <= y < self.BODY:
                        p[x, y] = renk

        b = self.BODY
        blok(int(b * 0.25), int(b * 0.05), int(b * 0.75), int(b * 0.35), R)
        blok(int(b * 0.35), int(b * 0.22), int(b * 0.65), int(b * 0.42), S)
        blok(int(b * 0.38), int(b * 0.30), int(b * 0.42), int(b * 0.34), K)
        blok(int(b * 0.55), int(b * 0.30), int(b * 0.59), int(b * 0.34), K)
        blok(int(b * 0.32), int(b * 0.40), int(b * 0.68), int(b * 0.62), SK)
        blok(int(b * 0.30), int(b * 0.50), int(b * 0.70), int(b * 0.58), (255, 200, 210, 255))
        blok(int(b * 0.34), int(b * 0.62), int(b * 0.66), int(b * 0.72), G)
        blok(int(b * 0.36), int(b * 0.72), int(b * 0.46), int(b * 0.92), (80, 50, 40, 255))
        blok(int(b * 0.54), int(b * 0.72), int(b * 0.64), int(b * 0.92), (80, 50, 40, 255))
        return im

    # ------------------------------------------------------------------ soz / anim
    def _soyle(self, metin: str, sure: int = 70):
        self._ozel_metin = metin
        self._ozel_metin_tick = sure
        self._konusuyor = True
        if self._anim not in ("kiss", "blow_kiss", "sleep"):
            self._anim_degistir(random.choice(["talk", "talk_fast", "ask"]), sure=min(sure, 50))
        self._balon_goster(metin, sure)

    def _balon_goster(self, metin: str, sure: int = 70):
        try:
            im = _balon_png(metin)
            self._balon_foto = ImageTk.PhotoImage(im)
            self.canvas.itemconfigure(self.balon_id, image=self._balon_foto, state="normal")
            self.canvas.coords(self.balon_id, self.W // 2, 8 + im.size[1] // 2)
            self._balon_gorunur = True
            self._balon_tick = sure
            self.canvas.tag_raise(self.balon_id)
        except Exception:
            pass

    def _balon_gizle(self):
        self._balon_gorunur = False
        self._balon_tick = 0
        self._ozel_metin = None
        self._ozel_metin_tick = 0
        self._konusuyor = False
        try:
            self.canvas.itemconfigure(self.balon_id, state="hidden")
        except Exception:
            pass

    def ozellik_anlat(self, metin: str, sure: int = 100):
        if not self.aktif:
            self.toggle()
        self._burun = 1.5
        self._anim_degistir("ask")
        self._durum = "emote"
        self._durum_tick = 0
        try:
            self.tx, self.ty = self._panel_kutusuna_sikistir(
                self.root.winfo_pointerx() - self.W * 0.4,
                self.root.winfo_pointery() - self.H * 0.7,
            )
        except Exception:
            pass
        self._parca_ekle("?", "#AD1457")
        self._soyle(metin, sure)

    def _anim_degistir(self, ad: str, sure: int | None = None):
        if ad not in ANIMASYONLAR:
            ad = "idle"
        self._anim = ad
        self._anim_tick = 0
        varsayilan = {
            "idle": 45, "idle_sway": 40, "idle_hip": 42, "breath": 50,
            "walk": 48, "walk_fast": 36, "strut": 50, "skip": 40,
            "wave": 36, "wave_both": 40, "point": 38, "come_here": 40,
            "look_left": 30, "look_right": 30, "look_up": 28, "nod": 32,
            "talk": 44, "talk_fast": 36, "ask": 55, "think": 48,
            "kiss": 38, "blow_kiss": 42, "wink": 28, "blush": 40,
            "jump": 30, "bounce": 36, "dance": 52, "hip_sway": 44,
            "celebrate": 42, "surprised": 28, "shy": 40, "stretch": 34,
            "squash": 22, "spin": 32, "bow": 34, "sleep": 70,
        }
        self._anim_sure = sure or varsayilan.get(ad, 40)
        # jiggle impulse
        if ad in ("walk", "walk_fast", "strut", "skip", "jump", "bounce", "dance", "hip_sway", "celebrate"):
            self._jiggle_v += 0.9
        if ad in ("kiss", "blow_kiss"):
            self._jiggle_v += 0.5

    def _rastgele_soru_dongusu(self):
        if not self.aktif:
            self.root.after(15000, self._rastgele_soru_dongusu)
            return
        self._soru_sayac += 1
        if self._durum == "idle" and not self._balon_gorunur:
            sec = random.choice(["ask", "talk", "wave", "blow_kiss", "think", "wink"])
            self._anim_degistir(sec)
            if sec in ("kiss", "blow_kiss"):
                self._soyle(random.choice(["Mwah~", "Opucuk!", "Hehe~ <3", "Senin icin~"]), 45)
                self._parca_ekle("<3", "#FF4081")
            else:
                self._soyle(random.choice(SORU_METINLERI), 70)
        self.root.after(12000 + random.randint(0, 9000), self._rastgele_soru_dongusu)

    def _idle_anim_sec(self):
        if self._anim_tick < self._anim_sure:
            return
        # yurume firsati
        if random.random() < 0.35:
            self._anim_degistir(random.choice(["walk", "strut", "skip", "walk_fast"]))
            self._hedef_konumuna_git()
            return
        if random.random() < 0.2:
            self._anim_degistir(random.choice(["blow_kiss", "kiss", "wink", "blush"]))
            if self._anim in ("kiss", "blow_kiss"):
                self._soyle(random.choice(["Mwah~", "Opucuk sana~", "<3"]), 40)
                self._parca_ekle("<3", "#FF4081")
            return
        self._anim_degistir(random.choice(ANIMASYONLAR))

    # ------------------------------------------------------------------ etkilesim
    def _basildi(self, event):
        self._durum = "grab"
        self._durum_tick = 0
        self._anim_degistir("squash")
        self.vx = self.vy = 0.0
        self._grab_ox, self._grab_oy = event.x, event.y
        self._throw_hist = [(event.x_root, event.y_root)]
        self._jiggle_v += 1.2
        self._idle_baslangic = time.time()
        self._soyle(random.choice(["Hey~ dikkatli!", "Hmm?", "Tasiyor~", "Alindim!"]), 30)

    def _surukleniyor(self, event):
        if self._durum != "grab":
            return
        self.x = float(event.x_root - self._grab_ox)
        self.y = float(event.y_root - self._grab_oy)
        self.tx, self.ty = self.x, self.y
        self._throw_hist.append((event.x_root, event.y_root))
        if len(self._throw_hist) > 5:
            self._throw_hist.pop(0)
        self._jiggle_v += 0.15
        self._anim_degistir("stretch", 20)

    def _birakildi(self, _event):
        if self._durum != "grab":
            return
        if len(self._throw_hist) >= 2:
            x0, y0 = self._throw_hist[0]
            x1, y1 = self._throw_hist[-1]
            olcek = self.BODY / 100.0
            self.vx = (x1 - x0) * 0.28 * olcek
            self.vy = (y1 - y0) * 0.28 * olcek
        else:
            self.vx = self.vy = 0
        hiz = math.hypot(self.vx, self.vy)
        esik = self.BODY * 0.12
        self._jiggle_v += min(2.5, hiz * 0.08)
        if hiz > esik:
            self._durum = "throw"
            self._durum_tick = 0
            self._anim_degistir("spin" if hiz > esik * 1.8 else "bounce")
            self._soyle(random.choice(["Oww~!", "Heyy!!", "Yumusak firlat~", "Wah!"]), 40)
        else:
            self._durum = "idle"
            self.vx = self.vy = 0
            self._hedef_isaretle()

    def _sag_tik(self, _event=None):
        self._emote_sira = (self._emote_sira + 1) % len(ANIMASYONLAR)
        anim = ANIMASYONLAR[self._emote_sira]
        self._anim_degistir(anim)
        self._durum = "emote"
        self._durum_tick = 0
        if anim in ("kiss", "blow_kiss"):
            self._soyle(random.choice(["Mwah~", "Opucuk!", "Senin icin <3", "Hehe~"]), 45)
            self._parca_ekle("<3", "#FF4081")
            self._parca_ekle("<3", "#F48FB1")
        elif anim in ("ask", "talk", "talk_fast"):
            self.adimi_guncelle()
            self._soyle(ADIM_METINLERI.get(self.adim, "Buraya bak!") + " Yardim edeyim mi?", 70)
            self._hedef_isaretle()
        elif anim in ("walk", "walk_fast", "strut", "skip"):
            self._soyle("Yuruyorum~ Takip et!", 40)
            self._hedef_konumuna_git()
        else:
            self._soyle(random.choice(SORU_METINLERI + [
                f"Hareket: {anim}", "Sag tik = yeni animasyon~", "Sorun var mi?",
            ]), 50)

    def _cift_tik(self, _event=None):
        self._durum = "emote"
        self._durum_tick = 0
        self._anim_degistir("blow_kiss")
        self._jiggle_v += 1.4
        self._soyle("Cift tik! Opucuk + dans~ Yardim ister misin?", 55)
        for _ in range(7):
            self._parca_ekle("<3", "#FF4081")

    def _hedef_isaretle(self):
        self.adimi_guncelle()
        hedef = self._hedef_widget()
        if hedef is None:
            return
        try:
            hedef.focus_set()
            if "bg" in hedef.keys():
                eski = hedef.cget("bg")
                hedef.configure(bg="#FFEB3B")
                self.root.after(350, lambda: hedef.configure(bg=eski))
            self._anim_degistir("point")
            self._soyle(ADIM_METINLERI.get(self.adim, "Buraya!") + " Tikla~", 55)
        except Exception:
            pass

    def _parca_ekle(self, ch: str, renk: str):
        self._partikuller.append({
            "ch": ch, "renk": renk,
            "x": self.W // 2 + random.uniform(-20, 20),
            "y": 130 + random.uniform(-10, 10),
            "vy": random.uniform(-2.0, -0.9),
            "life": 26, "id": None,
        })

    def toggle(self):
        self.aktif = not self.aktif
        if self.aktif:
            self.win.deiconify()
            try:
                self.win.attributes("-topmost", True)
                self.root.after(80, lambda: self.win.attributes("-topmost", False))
            except Exception:
                pass
            self.adimi_guncelle()
            self._anim_degistir("wave")
            self._soyle("Geri geldim~ Orta tik=gizle. Sor!", 45)
        else:
            self.win.withdraw()

    def _panel_odak(self, _event=None):
        if self.aktif:
            try:
                self.win.deiconify()
            except Exception:
                pass

    def _panel_odak_kaybi(self, _event=None):
        try:
            if self.root.focus_displayof() is not None:
                return
            self.win.withdraw()
        except Exception:
            pass

    def kapat(self):
        try:
            self.aktif = False
            self.win.destroy()
        except Exception:
            pass

    def _panel_durumu(self) -> int:
        p = self.panel
        if not getattr(p, "_poz_karakter_yolu", None):
            return 1
        if (
            not getattr(p, "_poz_stil_yolu", None)
            and not getattr(p, "_stil_referans_yolu", None)
            and not self._stil_onerme_yapildi
        ):
            self._stil_onerme_yapildi = True
            return 2
        hikaye = ""
        try:
            hikaye = p.basit_hikaye_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            pass
        if not hikaye:
            return 3
        chat = ""
        try:
            chat = p.gemini_chat_kutusu.get("1.0", "end-1c").strip()
        except Exception:
            pass
        if not chat:
            return 3
        if not getattr(p, "_maskot_metin_alindi", False):
            return 4
        if not getattr(p, "_maskot_resim_alindi", False):
            return 5
        if not getattr(p, "_son_video_yolu", None):
            try:
                kare = os.path.join(BASE_DIR, "input_karakter_kareleri")
                pngler = (
                    [f for f in os.listdir(kare) if f.lower().endswith(".png")]
                    if os.path.isdir(kare) else []
                )
                return 6 if not pngler else 7
            except Exception:
                return 6
        return 8

    def _hedef_widget(self):
        p = self.panel
        return {
            1: getattr(p, "btn_karakter", None),
            2: getattr(p, "btn_stil", None),
            3: getattr(p, "basit_hikaye_kutusu", None),
            4: getattr(p, "btn_metin_al", None),
            5: getattr(p, "btn_resim_al", None),
            6: getattr(p, "btn_cikti_ekle", None),
            7: getattr(p, "btn_krita", None),
            8: getattr(p, "btn_ae", None),
            0: getattr(p, "video_oynat_butonu", None),
        }.get(self.adim)

    def adimi_guncelle(self):
        if not self.aktif:
            return
        self.adim = self._panel_durumu()
        if self._durum == "idle" and not self._balon_gorunur:
            self._hedef_konumuna_git()

    def _hedef_konumuna_git(self):
        w = self._hedef_widget()
        try:
            if w is None:
                self.tx = self.root.winfo_rootx() + 60
                self.ty = self.root.winfo_rooty() + 100
                return
            self.root.update_idletasks()
            hx = w.winfo_rootx() + max(w.winfo_width() // 2, 20)
            hy = w.winfo_rooty() + max(w.winfo_height(), 10)
            self.tx, self.ty = self._panel_kutusuna_sikistir(
                hx - self.BODY * 0.55, hy + self.BODY * 0.08
            )
        except Exception:
            pass

    def _panel_kutusuna_sikistir(self, px, py):
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            px = max(rx - 40, min(px, rx + rw - self.W + 20))
            py = max(ry - 20, min(py, ry + rh - 40))
        except Exception:
            pass
        return px, py

    def _fare_idle_kontrol(self):
        try:
            mx, my = self.root.winfo_pointerx(), self.root.winfo_pointery()
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
        except Exception:
            return
        if not (rx - 8 <= mx <= rx + rw + 8 and ry - 8 <= my <= ry + rh + 8):
            self._idle_baslangic = time.time()
            return
        if math.hypot(mx - self._mx, my - self._my) > 6:
            self._mx, self._my = mx, my
            self._idle_baslangic = time.time()
            return
        if self._durum != "idle":
            return
        if time.time() - self._idle_baslangic >= 1.8 and not self._balon_gorunur:
            self.tx, self.ty = self._panel_kutusuna_sikistir(
                mx - self.W * 0.45, my - self.H * 0.75
            )
            self._anim_degistir("ask")
            self._soyle(
                ADIM_METINLERI.get(self.adim, "Buraya bak!") + " Yardim edeyim mi?",
                70,
            )
            self._idle_baslangic = time.time() + 5

    def _peri_hedef_yumusat(self):
        if self._durum != "idle":
            return
        self.tx, self.ty = self._panel_kutusuna_sikistir(self.tx, self.ty)
        dx, dy = self.tx - self.x, self.ty - self.y
        dist = math.hypot(dx, dy)
        if dist < 2:
            return
        # yurume animasyonunda daha hizli
        carp = 1.35 if self._anim in ("walk", "walk_fast", "strut", "skip") else 1.0
        hiz = min(self.BODY * 0.09 * carp, dist * 0.07 + self.BODY * 0.012)
        self.x += dx / dist * hiz
        self.y += dy / dist * hiz
        self.x, self.y = self._panel_kutusuna_sikistir(self.x, self.y)
        if self._anim not in ("walk", "walk_fast", "strut", "skip", "talk", "talk_fast", "ask"):
            if dist > 25:
                self._anim_degistir(random.choice(["walk", "strut"]))

    def _jiggle_guncelle(self):
        # hareket ivmesi → salinim
        dx = self.x - self._son_x
        dy = self.y - self._son_y
        hiz = math.hypot(dx, dy)
        self._son_x, self._son_y = self.x, self.y
        self._jiggle_v += hiz * 0.045
        if self._anim in ("walk", "walk_fast", "strut", "skip", "bounce", "dance", "hip_sway"):
            self._jiggle_v += 0.08 + abs(math.sin(self.t * 3)) * 0.06
        # yay-mass damper
        self._jiggle_v += -self._jiggle * 0.22
        self._jiggle_v *= 0.86
        self._jiggle += self._jiggle_v
        self._jiggle = max(-1.6, min(1.6, self._jiggle))

    # ------------------------------------------------------------------ cizim
    def _anim_sprite_key(self) -> str:
        k = "n" if self._yon >= 0 else "m"
        a, ti = self._anim, self._anim_tick

        if a in ("squash",) or self._durum == "grab":
            return f"{k}_sq"
        if a == "stretch":
            return f"{k}_st"
        if a in ("look_left", "bow", "shy"):
            return f"{k}_l"
        if a in ("look_right", "point", "come_here", "wink"):
            return f"{k}_r"
        if a in ("spin", "dance"):
            return f"{k}_ll" if (ti // 3) % 2 == 0 else f"{k}_rr"
        if a in ("kiss", "blow_kiss"):
            return f"{k}_kiss"
        if a in ("talk", "talk_fast", "ask") or self._konusuyor:
            return f"{k}_talk{1 if (ti // (2 if a == 'talk_fast' else 3)) % 2 else 0}"
        if a == "jump" and ti < 12:
            return f"{k}_st"
        # jiggle frame sec
        ji = int((self._jiggle + 1.6) / 3.2 * 4)
        ji = max(0, min(4, ji))
        if a in ("walk", "walk_fast", "strut", "skip", "bounce", "hip_sway", "idle_hip", "celebrate") or abs(self._jiggle) > 0.35:
            return f"{k}_j{ji}"
        return f"{k}"

    def _anim_offset(self):
        a, ti, ph = self._anim, self._anim_tick, self.t
        ox = oy = 0.0
        if a in ("idle", "breath", "idle_sway"):
            oy = math.sin(ph) * 2.5
            ox = math.sin(ph * 0.7) * 1.5 if a == "idle_sway" else 0
        elif a == "idle_hip":
            ox = math.sin(ph * 1.3) * 5
            oy = abs(math.sin(ph * 1.3)) * 2
        elif a == "wave" or a == "wave_both":
            ox = math.sin(ti * 0.55) * 5
        elif a == "jump":
            oy = -abs(math.sin(ti * 0.4)) * 16
        elif a in ("walk", "walk_fast", "strut"):
            phase = ti * (0.55 if a == "walk_fast" else 0.4)
            oy = abs(math.sin(phase)) * (6 if a != "strut" else 4)
            ox = math.sin(phase * 0.5) * 3
        elif a == "skip":
            oy = -abs(math.sin(ti * 0.5)) * 10
            ox = math.sin(ti * 0.25) * 4
        elif a == "dance":
            ox = math.sin(ti * 0.65) * 10
            oy = abs(math.sin(ti * 0.9)) * 7
        elif a == "hip_sway":
            ox = math.sin(ti * 0.45) * 9
        elif a == "celebrate":
            oy = -abs(math.sin(ti * 0.55)) * 12
        elif a == "bounce":
            oy = -abs(math.sin(ti * 0.6)) * 11
        elif a == "surprised":
            oy = -7 if ti < 8 else 0
        elif a == "sleep":
            oy = math.sin(ph * 0.4) * 1.2
        elif a in ("kiss", "blow_kiss"):
            ox = 2
            oy = -2 + math.sin(ti * 0.3) * 2
        elif a in ("talk", "talk_fast", "ask"):
            oy = math.sin(ti * 0.4) * 1.5
        elif a == "nod":
            oy = math.sin(ti * 0.7) * 4
        elif a == "look_up":
            oy = -3
        # jiggle offset ekstra
        oy += self._jiggle * 2.2
        ox += self._jiggle * 0.8
        return ox, oy

    def _partikulleri_ciz(self):
        kalan = []
        for p in self._partikuller:
            p["life"] -= 1
            p["y"] += p["vy"]
            if p["id"] is None:
                p["id"] = self.canvas.create_text(
                    p["x"], p["y"], text=p["ch"], fill=p["renk"], font=("Segoe UI", 11, "bold")
                )
            else:
                try:
                    self.canvas.coords(p["id"], p["x"], p["y"])
                except Exception:
                    pass
            if p["life"] > 0:
                kalan.append(p)
            else:
                try:
                    self.canvas.delete(p["id"])
                except Exception:
                    pass
        self._partikuller = kalan

    def _tick(self):
        if not self.aktif:
            self.root.after(80, self._tick)
            return
        try:
            if not self.win.winfo_exists():
                return
        except Exception:
            return

        self.t += 0.1
        self.frame_i = (self.frame_i + 1) % 60
        self._durum_tick += 1
        self._anim_tick += 1
        if self._anim_tick >= self._anim_sure and self._durum == "idle":
            self._idle_anim_sec()

        if self._balon_tick > 0:
            self._balon_tick -= 1
            if self._balon_tick <= 0:
                self._balon_gizle()
        if self._ozel_metin_tick > 0:
            self._ozel_metin_tick -= 1

        if self._goz_kirp > 0:
            self._goz_kirp -= 1
        elif random.random() < 0.018:
            self._goz_kirp = 3

        if self._burun > 0:
            self._burun = max(0.0, self._burun - 0.05)

        self._fare_idle_kontrol()
        self._jiggle_guncelle()

        if self._durum == "grab":
            pass
        elif self._durum == "throw":
            max_v = self.BODY * 0.35
            self.vx = max(-max_v, min(max_v, self.vx))
            self.vy = max(-max_v, min(max_v, self.vy))
            self.x += self.vx
            self.y += self.vy
            self.vx *= 0.94
            self.vy += 0.38
            self.tx, self.ty = self.x, self.y
            try:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            except Exception:
                sw, sh = 1920, 1080
            if self.x < 0 or self.x > sw - self.W:
                self.vx *= -0.5
                self.x = max(0, min(self.x, sw - self.W))
            if self.y > sh - self.H - 40:
                self.y = sh - self.H - 40
                self.vy *= -0.35
                self._jiggle_v += 1.5
                if abs(self.vy) < 1.5:
                    self._durum = "idle"
                    self.vx = self.vy = 0
                    self._anim_degistir("squash")
            if self._durum == "throw" and self._durum_tick > 80:
                self._durum = "idle"
                self.vx = self.vy = 0
        elif self._durum == "emote":
            if self._durum_tick > 48:
                self._durum = "idle"
            self._peri_hedef_yumusat()
        else:
            self._peri_hedef_yumusat()

        if abs(self.tx - self.x) > 3:
            self._yon = 1 if self.tx > self.x else -1

        hop = math.sin(self.t) * (self.BODY * 0.025)
        aox, aoy = self._anim_offset()
        cx = self.W // 2 + aox
        cy = 165 + aoy + math.sin(self.t * 1.4) * 1.0

        try:
            self.win.geometry(f"{self.W}x{self.H}+{int(self.x)}+{int(self.y + hop)}")
            key = self._anim_sprite_key()
            if self._goz_kirp > 0 and key.endswith(("n", "m")):
                key = key + "_sq"
            img = self._imgs.get(key) or self._imgs["n"]
            self.canvas.itemconfigure(self.sprite_id, image=img)
            self.canvas.coords(self.sprite_id, cx, cy)

            # konusma agiz noktasi (ek)
            if self._konusuyor or self._anim in ("talk", "talk_fast", "ask"):
                aw = 2 + (self._anim_tick % 4)
                ax = cx + self._yon * 2
                ay = cy - self.BODY * 0.18
                self.canvas.itemconfigure(self.agiz_id, state="normal")
                self.canvas.coords(self.agiz_id, ax - aw, ay, ax + aw, ay + aw + 1)
            else:
                self.canvas.itemconfigure(self.agiz_id, state="hidden")

            if self._anim in ("kiss", "blow_kiss") and self._anim_tick < 30:
                self.canvas.itemconfigure(self.kalp_id, state="normal")
                self.canvas.coords(
                    self.kalp_id,
                    cx + self._yon * (20 + self._anim_tick),
                    cy - 40 - self._anim_tick * 1.2,
                )
            else:
                self.canvas.itemconfigure(self.kalp_id, state="hidden")

            self._partikulleri_ciz()
            if self._balon_gorunur:
                self.canvas.tag_raise(self.balon_id)
        except Exception:
            pass

        if self.frame_i == 0 and self._durum == "idle":
            self.adimi_guncelle()

        self.root.after(40, self._tick)
