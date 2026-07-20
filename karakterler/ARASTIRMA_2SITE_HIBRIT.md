# Araştırma — Çizim kilidi + defter (2026-07-20 güncelleme)

Hedef: taslak bozulmasın, flat/mat el çizimi, **tek kare sayfa** (grid değil), zombie kız kimliği sabit.

## Net karar (birleştirme OK)

Tek site sihirli çözüm değil. Bizim iş için **2 site + kendi panel**:

| Rol | Site | Ne yapar |
|-----|------|----------|
| **A — ÇİZİM / STİL** | [Tensor.Art](https://tensor.art) | Flanime / FlatIron → flat matte, model seçimi serbest |
| **B — KİMLİK KİLİDİ** | [NovelAI](https://novelai.net) Precise Reference | Character + Style ref aynı anda; LoRA eğitmeden tutarlılık |
| **Bizim panel** | Krita studio / yeni “defter paneli” | Metin → kare listesi → prompt kopyala → PNG klasöre |

Yedek B: [Dashtoon Studio](https://www.dashtoon.com) — free ~100 img/gün + LoRA (tutarlılık güçlü; stil webtoon’a kayabilir → sadece LoRA/karakter için dene, ana stil Tensor’da kalsın).

**Kullanma (şimdilik ana hat):** Anifusion Generate Page (GPT Image + 4 panel), PixAI 9’lu sheet — taslağı ezer, defter değil.

---

## Neden bu ikili?

1. Comic siteleri (Anifusion, COMICPAD, Dashtoon comic mode) **multi-panel** zorluyor → senin defter mantığına ters.
2. Flat stil için **açık SD hub** lazım (Flanime) → Tensor / SeaArt.
3. Karakter+stil ref’i kolay kilitlemek için 2026’da en temiz web özelliği: **NovelAI Precise Reference** (Character + Style aynı anda).
4. Sıra: NovelAI veya Tensor’da **tek kare** → indir → Krita flipbook. Video için sonra keyframe→I2V (ayrı konu).

SeaArt ≈ Tensor (aynı ekosistem). Birini seç yeter; ikisini birden tutma.

---

## Akış (günlük short)

1. Ref sabit: `ZOMBIE_KIZ/KIMLIK/kimlik_kalip.png` + `stil_ref.png`
2. Hikâye → 6–12 tek kare prompt (`MINI_ZOMBIE_SHORT.txt`)
3. Her kareyi **A veya B**’de ayrı üret (grid YOK)
4. Beğenilenleri `poz_1…n.png` → panel / Krita
5. Konuşma: ağız açık / kapalı alternatif 2 kare

Panel fikri (yapılabilir):
- Sol: kare planı (Türkçe beat)
- Orta: İngilizce prompt + negative (otomatik DNA bloğu)
- Sağ: “Tensor / NovelAI için kopyala” + indirme klasörü yolu
- İleride: Tensor API varsa otomatik kuyruk

---

## Diğer siteler (kısa skor — bizim hedefe)

| Site | Skor | Not |
|------|------|-----|
| Tensor.Art | 9 | Flat model + tek kare; ana çizim |
| NovelAI Precise Ref | 8.5 | Kimlik+stil kilidi en kolay web |
| SeaArt | 8 | Tensor yedeği |
| Dashtoon | 7 | LoRA tutarlılık; stil riski |
| Katalist / Atlabs | 6 | Storyboard/video; flat indie garanti değil |
| Anifusion | 5 | Manga grid + GPT Image = bizde çöktü |
| Komiko | 5 | Kolay ama stil “güzel comic” |
| PixAI | 2 | Parlak sheet — bırakıldı |

Kaynak notları: COMICPAD accuracy ranking (Jul 2026) Dashtoon #1 LoRA; NovelAI docs Precise Reference; Katalist/Atlabs script→board (stil farklı).

---

## Bu hafta dene (sırayla)

1. Tensor + Flanime + kimlik_kalip → 1 kare hoodie sokak  
2. Aynı promptu NovelAI Precise Ref ile → hangisi flat’e yakın seç  
3. Kazananı “ana motor” yap; diğerini sadece drift olunca yedek  
4. Beğenirsek paneli 2-site kopyala butonuyla bağlarız
