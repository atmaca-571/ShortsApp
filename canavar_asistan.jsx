/*
================================================================================
Canavar Asistan - Manga Animasyon Otomasyonu - After Effects ExtendScript (.jsx)
================================================================================
Kullanim: After Effects -> File -> Scripts -> Run Script File... -> bu dosyayi sec.

DUZELTMELER (bu surumde):
  - setTemporalEaseAtKey artik ozelligin GERCEK boyut sayisina gore (2 veya 3
    elemanli) dinamik dizi olusturuyor -> "Value array does not have 3
    elements" hatasi kokten cozuldu.
  - TUM fonksiyonlar try-catch ile sarildi; hicbir null/undefined durumu
    After Effects'i cokertmez, sadece $.writeln() ile loglanir.
  - Her calistirmada YENI ve TEMIZ bir kompozisyon acilir (Manga_Shorts_
    Otomatik_v1, v2, v3... seklinde otomatik numaralanir), eskilerin
    ustune binmez.
  - Arka planlar orantili "cover" (tasma yok, bosluk yok) ile, karakterler
    de orantili "sigdirma" ile, kaynak boyutu ne olursa olsun otomatik
    olceklenir.
================================================================================
*/

(function (thisObj) {

    // ============================================================
    // GENEL SABITLER
    // ============================================================
    var COMP_GENISLIK = 1080;
    var COMP_YUKSEKLIK = 1920;
    var COMP_FPS = 30;
    var KOMPOZISYON_TEMEL_ADI = "Manga_Shorts_Otomatik";
    var KARAKTER_HEDEF_YUKSEKLIK_ORANI = 0.62; // karakter, ekran yuksekliginin ne kadarini kaplasin

    var POZISYON_X = { "sol": 216, "merkez": 540, "sag": 864 };

    var secilenScriptDosyasi = null;
    var secilenArkaplanKlasoru = null;
    var secilenKarakterKlasoru = null;

    // ============================================================
    // YARDIMCI: HATA YONETIMI
    // ============================================================
    function hataBildir(mesaj) {
        try {
            $.writeln("HATA: " + mesaj);
        } catch (e) {
            // konsol bile yoksa sessizce gec, uygulamayi asla cokertme
        }
    }

    function guvenliCagir(fonksiyon, hataAciklamasi, geriDonusDeger) {
        try {
            return fonksiyon();
        } catch (e) {
            hataBildir(hataAciklamasi + " -> " + e.toString());
            return geriDonusDeger !== undefined ? geriDonusDeger : null;
        }
    }

    // ============================================================
    // YARDIMCI: DINAMIK EASE DIZISI (asil hata duzeltmesi burada)
    // ============================================================
    function easeDizisiOlustur(prop, easeNesnesi) {
        var boyutSayisi = 3; // AE 2020+ pek cok durumda 3 bekliyor, guvenli varsayilan
        try {
            if (prop && prop.value && typeof prop.value.length === "number") {
                boyutSayisi = prop.value.length;
            }
        } catch (e) {
            hataBildir("Ease dizisi boyutu okunamadi, varsayilan 3 kullaniliyor: " + e.toString());
        }
        var dizi = [];
        for (var i = 0; i < boyutSayisi; i++) dizi.push(easeNesnesi);
        return dizi;
    }

    function easyEaseUygula(prop, keyIndex, hiz, etki) {
        try {
            if (!prop || keyIndex < 1 || keyIndex > prop.numKeys) return;
            var kolayGecis = new KeyframeEase(hiz || 0, etki || 33);
            var dizi = easeDizisiOlustur(prop, kolayGecis);
            prop.setTemporalEaseAtKey(keyIndex, dizi, dizi);
        } catch (e) {
            hataBildir("Easy ease uygulanamadi (key " + keyIndex + "): " + e.toString());
        }
    }

    // ============================================================
    // YARDIMCI: PLACEHOLDER KATMAN (dosya bulunamazsa)
    // ============================================================
    function placeholderKatmanOlustur(comp, isim, sure, baslangicZamani) {
        return guvenliCagir(function () {
            var renk = [0.05, 0.05, 0.05];
            var solid = comp.layers.addSolid(renk, "PLACEHOLDER_" + isim, COMP_GENISLIK, COMP_YUKSEKLIK, 1, sure);
            solid.startTime = baslangicZamani;
            solid.outPoint = baslangicZamani + sure;
            return solid;
        }, "Placeholder katman olusturulamadi (" + isim + ")", null);
    }

    // ============================================================
    // BOLUM 1: SCRIPT.TXT AYRISTIRICI
    // ============================================================
    function scriptDosyasiniOku(dosyaYolu) {
        return guvenliCagir(function () {
            var dosya = new File(dosyaYolu);
            if (!dosya.exists) {
                hataBildir("script.txt bulunamadi: " + dosyaYolu);
                return [];
            }

            dosya.open("r");
            var icerik = dosya.read();
            dosya.close();

            var satirlar = icerik.split("\n");
            var sahneler = [];

            for (var i = 0; i < satirlar.length; i++) {
                var satir = satirlar[i];
                satir = satir.replace(/^\s+|\s+$/g, "").replace(/\r/g, "");
                if (satir === "" || satir.charAt(0) === "#") continue;

                var sahne = satiriAyristir(satir, i + 1);
                if (sahne) sahneler.push(sahne);
            }
            return sahneler;
        }, "script.txt okunamadi", []);
    }

    function satiriAyristir(satir, satirNo) {
        return guvenliCagir(function () {
            var parcalar = satir.split("|");
            if (parcalar.length !== 4) {
                hataBildir("Satir " + satirNo + " atlandi (4 bolum bekleniyor): " + satir);
                return null;
            }

            for (var i = 0; i < parcalar.length; i++) {
                parcalar[i] = parcalar[i].replace(/^\s+|\s+$/g, "");
            }

            var sure = parseFloat(parcalar[0]);
            if (isNaN(sure) || sure <= 0) {
                hataBildir("Satir " + satirNo + " atlandi (sure gecersiz): " + parcalar[0]);
                return null;
            }

            var arkaplanAdi = parcalar[1];
            var karakterTanimlari = parcalar[2];
            var metinHam = parcalar[3].replace(/^"+|"+$/g, "");

            var karakterler = [];
            if (karakterTanimlari !== "") {
                var tanimlar = karakterTanimlari.split(",");
                for (var k = 0; k < tanimlar.length; k++) {
                    var tanim = tanimlar[k].replace(/^\s+|\s+$/g, "");
                    if (tanim === "") continue;
                    var altParcalar = tanim.split(":");
                    if (altParcalar.length !== 3) {
                        hataBildir("Satir " + satirNo + ": karakter tanimi hatali, atlandi: " + tanim);
                        continue;
                    }
                    karakterler.push({
                        ad: altParcalar[0].replace(/^\s+|\s+$/g, "").toLowerCase(),
                        pozisyon: altParcalar[1].replace(/^\s+|\s+$/g, "").toLowerCase(),
                        efekt: altParcalar[2].replace(/^\s+|\s+$/g, "").toLowerCase()
                    });
                }
            }

            return { sure: sure, arkaplan: arkaplanAdi, karakterler: karakterler, metin: metinHam };
        }, "Satir " + satirNo + " ayristirilamadi", null);
    }

    // ============================================================
    // DOSYA BULMA YARDIMCILARI
    // ============================================================
    function dosyaBul(klasorYolu, dosyaAdi) {
        return guvenliCagir(function () {
            var tamYol = klasorYolu + "/" + dosyaAdi;
            var dosya = new File(tamYol);
            return dosya.exists ? dosya : null;
        }, "Dosya aranirken hata (" + dosyaAdi + ")", null);
    }

    function karakterDosyasiBul(klasorYolu, karakterAdi) {
        return guvenliCagir(function () {
            var klasor = new Folder(klasorYolu);
            if (!klasor.exists) return null;
            var dosyalar = klasor.getFiles("*.png");
            for (var i = 0; i < dosyalar.length; i++) {
                var ad = dosyalar[i].name.toLowerCase();
                if (ad.indexOf(karakterAdi.toLowerCase()) === 0) {
                    return dosyalar[i];
                }
            }
            return null;
        }, "Karakter aranirken hata (" + karakterAdi + ")", null);
    }

    // ============================================================
    // FOOTAGE IMPORT (onbellekli, guvenli)
    // ============================================================
    var _importOnbellek = {};

    function footageImportEt(dosya) {
        return guvenliCagir(function () {
            var anahtar = dosya.fsName;
            if (_importOnbellek[anahtar]) return _importOnbellek[anahtar];

            var ioSec = new ImportOptions(dosya);
            var oge = app.project.importFile(ioSec);
            _importOnbellek[anahtar] = oge;
            return oge;
        }, "Dosya import edilemedi (" + (dosya ? dosya.fsName : "bilinmiyor") + ")", null);
    }

    // ============================================================
    // BOLUM 2: ARKA PLAN KATMANI (orantili cover + zoom + wiggle)
    // ============================================================
    function arkaplanKatmaniEkle(comp, sahne, baslangicZamani) {
        return guvenliCagir(function () {
            var katman = null;

            if (secilenArkaplanKlasoru) {
                var dosya = dosyaBul(secilenArkaplanKlasoru, sahne.arkaplan);
                if (dosya) {
                    var oge = footageImportEt(dosya);
                    if (oge) {
                        katman = comp.layers.add(oge);
                    }
                }
            }

            if (!katman) {
                hataBildir("Arka plan bulunamadi/eklenemedi: '" + sahne.arkaplan + "' -> placeholder olusturuldu.");
                return placeholderKatmanOlustur(comp, "arkaplan", sahne.sure, baslangicZamani);
            }

            katman.startTime = baslangicZamani;
            katman.outPoint = baslangicZamani + sahne.sure;

            guvenliCagir(function () {
                var kaynakGenislik = katman.source.width;
                var kaynakYukseklik = katman.source.height;
                var olcekOrani = Math.max(COMP_GENISLIK / kaynakGenislik, COMP_YUKSEKLIK / kaynakYukseklik);
                var olcekYuzde = olcekOrani * 100;
                katman.property("Transform").property("Scale").setValue([olcekYuzde, olcekYuzde]);
                katman.property("Transform").property("Position").setValue([COMP_GENISLIK / 2, COMP_YUKSEKLIK / 2]);
            }, "Arka plan orantili olcekleme hatasi", null);

            guvenliCagir(function () {
                var scaleProp = katman.property("Transform").property("Scale");
                var baslangicOlcek = scaleProp.value;
                var bitisOlcek = [baslangicOlcek[0] * 1.04, baslangicOlcek[1] * 1.04];
                scaleProp.setValueAtTime(0, baslangicOlcek);
                scaleProp.setValueAtTime(sahne.sure, bitisOlcek);
                easyEaseUygula(scaleProp, 1, 0, 50);
                easyEaseUygula(scaleProp, 2, 0, 50);
            }, "Kamera zoom keyframe hatasi", null);

            guvenliCagir(function () {
                katman.property("Transform").property("Position").expression = "wiggle(0.5, 15);";
            }, "Wiggle expression hatasi", null);

            return katman;
        }, "Arka plan katmani genel hatasi", null);
    }

    // ============================================================
    // BOLUM 3: KARAKTER KATMANI (orantili sigdirma + pozisyon + efekt)
    // ============================================================
    function karakterKatmaniEkle(comp, karakterTanimi, sahneSuresi, baslangicZamani) {
        return guvenliCagir(function () {
            if (!secilenKarakterKlasoru) {
                hataBildir("Karakter klasoru secilmedi, '" + karakterTanimi.ad + "' atlandi.");
                placeholderKatmanOlustur(comp, "karakter_" + karakterTanimi.ad, sahneSuresi, baslangicZamani);
                return null;
            }

            var dosya = karakterDosyasiBul(secilenKarakterKlasoru, karakterTanimi.ad);
            if (!dosya) {
                hataBildir("Karakter bulunamadi: '" + karakterTanimi.ad + "' -> placeholder olusturuldu.");
                placeholderKatmanOlustur(comp, "karakter_" + karakterTanimi.ad, sahneSuresi, baslangicZamani);
                return null;
            }

            var oge = footageImportEt(dosya);
            if (!oge) {
                placeholderKatmanOlustur(comp, "karakter_" + karakterTanimi.ad, sahneSuresi, baslangicZamani);
                return null;
            }

            var katman = comp.layers.add(oge);
            katman.startTime = baslangicZamani;
            katman.outPoint = baslangicZamani + sahneSuresi;

            var genislik = 100, yukseklik = 100;
            guvenliCagir(function () {
                genislik = katman.source.width;
                yukseklik = katman.source.height;
                katman.property("Transform").property("Anchor Point").setValue([genislik / 2, yukseklik]);
            }, "Anchor point ayarlanamadi (" + karakterTanimi.ad + ")", null);

            guvenliCagir(function () {
                var hedefYukseklik = COMP_YUKSEKLIK * KARAKTER_HEDEF_YUKSEKLIK_ORANI;
                var olcekYuzde = (hedefYukseklik / yukseklik) * 100;
                katman.property("Transform").property("Scale").setValue([olcekYuzde, olcekYuzde]);
            }, "Karakter orantili olcekleme hatasi (" + karakterTanimi.ad + ")", null);

            var xKoordinati = POZISYON_X[karakterTanimi.pozisyon];
            if (xKoordinati === undefined) xKoordinati = POZISYON_X["merkez"];

            guvenliCagir(function () {
                katman.property("Transform").property("Position").setValue([xKoordinati, COMP_YUKSEKLIK]);
            }, "Pozisyon ayarlanamadi (" + karakterTanimi.ad + ")", null);

            var efekt = karakterTanimi.efekt;

            if (efekt === "zipla") {
                guvenliCagir(function () {
                    var posProp = katman.property("Transform").property("Position");
                    var tabanY = COMP_YUKSEKLIK;
                    var zipiralamaYuksekligi = 40;
                    var adim = 0.5;
                    var t = 0;

                    while (t < sahneSuresi) {
                        posProp.setValueAtTime(t, [xKoordinati, tabanY]);
                        var tepeZaman = Math.min(t + adim / 2, sahneSuresi);
                        posProp.setValueAtTime(tepeZaman, [xKoordinati, tabanY - zipiralamaYuksekligi]);
                        t += adim;
                    }

                    for (var ki = 1; ki <= posProp.numKeys; ki++) {
                        easyEaseUygula(posProp, ki, 0, 33);
                    }
                }, "Zipla efekti uygulanamadi (" + karakterTanimi.ad + ")", null);
            } else if (efekt === "titre") {
                guvenliCagir(function () {
                    katman.property("Transform").property("Position").expression = "wiggle(15, 30);";
                }, "Titre expression hatasi (" + karakterTanimi.ad + ")", null);
            } else {
                guvenliCagir(function () {
                    katman.property("Transform").property("Scale").expression =
                        "var olcekTabani = thisComp.layer(index).transform.scale.valueAtTime(0)[0];\n" +
                        "var s = olcekTabani + Math.sin(time * 3) * 1;\n[s, s];";
                }, "Sabit/nefes expression hatasi (" + karakterTanimi.ad + ")", null);
            }

            return katman;
        }, "Karakter katmani genel hatasi (" + (karakterTanimi ? karakterTanimi.ad : "?") + ")", null);
    }

    // ============================================================
    // BOLUM 4: POP-UP ALTYAZI METIN KATMANI
    // ============================================================
    function altyaziKatmaniEkle(comp, metin, sahneSuresi, baslangicZamani) {
        return guvenliCagir(function () {
            if (!metin || metin === "") return null;

            var textLayer = comp.layers.addText(metin);
            textLayer.startTime = baslangicZamani;
            textLayer.outPoint = baslangicZamani + sahneSuresi;

            guvenliCagir(function () {
                var textProp = textLayer.property("Source Text");
                var textDoc = textProp.value;

                try {
                    textDoc.font = "Impact";
                } catch (fontHata) {
                    guvenliCagir(function () { textDoc.font = "Arial-BoldMT"; }, "Yedek font ayarlanamadi", null);
                }

                textDoc.fontSize = 75;
                textDoc.fillColor = [1, 1, 1];
                textDoc.strokeColor = [0, 0, 0];
                textDoc.strokeWidth = 5;
                textDoc.applyStroke = true;
                textDoc.applyFill = true;
                textDoc.strokeOverFill = true;
                textDoc.justification = ParagraphJustification.CENTER_JUSTIFY;

                textProp.setValue(textDoc);
            }, "Altyazi tipografi ayari hatasi", null);

            guvenliCagir(function () {
                textLayer.property("Transform").property("Anchor Point").setValue([0, 0]);
                textLayer.property("Transform").property("Position").setValue([COMP_GENISLIK / 2, 1550]);
            }, "Altyazi konumlandirma hatasi", null);

            guvenliCagir(function () {
                var scaleProp = textLayer.property("Transform").property("Scale");
                scaleProp.setValueAtTime(0, [0, 0]);
                scaleProp.setValueAtTime(0.15, [100, 100]);
                easyEaseUygula(scaleProp, 1, 0, 75);
                easyEaseUygula(scaleProp, 2, 0, 20);
            }, "Pop-up animasyon hatasi", null);

            return textLayer;
        }, "Altyazi katmani genel hatasi", null);
    }

    // ============================================================
    // AKILLI KOMPOZISYON ISIMLENDIRME (eskilerin ustune binmez)
    // ============================================================
    function benzersizKompozisyonAdiUret() {
        return guvenliCagir(function () {
            var maxVersiyon = 0;
            for (var i = 1; i <= app.project.items.length; i++) {
                var oge = app.project.items[i];
                if (oge instanceof CompItem && oge.name.indexOf(KOMPOZISYON_TEMEL_ADI) === 0) {
                    var eslesme = oge.name.match(/_v(\d+)$/);
                    if (eslesme) {
                        var versiyon = parseInt(eslesme[1], 10);
                        if (!isNaN(versiyon) && versiyon > maxVersiyon) maxVersiyon = versiyon;
                    }
                }
            }
            return KOMPOZISYON_TEMEL_ADI + "_v" + (maxVersiyon + 1);
        }, "Kompozisyon adi uretilemedi, zaman damgasi kullanilacak", KOMPOZISYON_TEMEL_ADI + "_" + new Date().getTime());
    }

    // ============================================================
    // ANA PIPELINE
    // ============================================================
    function animasyonuBaslat() {
        if (!secilenScriptDosyasi) {
            alert("Lütfen önce 'Script Dosyasını Seç' ile script.txt dosyasını seçin.");
            return;
        }

        var sahneler = scriptDosyasiniOku(secilenScriptDosyasi.fsName);
        if (!sahneler || sahneler.length === 0) {
            alert("script.txt içinde geçerli hiçbir sahne bulunamadı. Konsolu kontrol edin ($.writeln çıktıları).");
            return;
        }

        var toplamSure = 0;
        for (var i = 0; i < sahneler.length; i++) toplamSure += sahneler[i].sure;

        if (toplamSure <= 0) {
            alert("Toplam sahne süresi geçersiz (0 veya negatif). script.txt dosyasını kontrol edin.");
            return;
        }

        app.beginUndoGroup("Canavar Asistan - Manga Animasyon Otomasyonu");

        try {
            var kompozisyonAdi = benzersizKompozisyonAdiUret();

            var comp = app.project.items.addComp(
                kompozisyonAdi,
                COMP_GENISLIK,
                COMP_YUKSEKLIK,
                1,
                toplamSure,
                COMP_FPS
            );

            var baslangicZamani = 0;
            for (var s = 0; s < sahneler.length; s++) {
                var sahne = sahneler[s];
                if (!sahne) continue;

                arkaplanKatmaniEkle(comp, sahne, baslangicZamani);

                for (var k = 0; k < sahne.karakterler.length; k++) {
                    karakterKatmaniEkle(comp, sahne.karakterler[k], sahne.sure, baslangicZamani);
                }

                altyaziKatmaniEkle(comp, sahne.metin, sahne.sure, baslangicZamani);

                baslangicZamani += sahne.sure;
            }

            guvenliCagir(function () { comp.openInViewer(); }, "Kompozisyon viewer'da acilamadi", null);

            alert("Animasyon oluşturuldu: '" + kompozisyonAdi + "'\nToplam süre: " + toplamSure.toFixed(2) +
                  " saniye.\nUyarılar için Window > Console kontrol edilebilir.");
        } catch (genelHata) {
            alert("Beklenmeyen bir hata oluştu: " + genelHata.toString());
            hataBildir("GENEL HATA (animasyonuBaslat): " + genelHata.toString());
        } finally {
            app.endUndoGroup();
        }
    }

    // ============================================================
    // SCRIPTUI PANELI
    // ============================================================
    function buildUI(thisObj) {
        return guvenliCagir(function () {
            var panel = (thisObj instanceof Panel)
                ? thisObj
                : new Window("palette", "Canavar Asistan - Manga Animasyonu", undefined, { resizeable: true });

            panel.orientation = "column";
            panel.alignChildren = ["fill", "top"];
            panel.spacing = 10;
            panel.margins = 16;

            var baslikGrubu = panel.add("group");
            baslikGrubu.add("statictext", undefined, "🎬 Manga Shorts -> AE Otomasyonu");

            var scriptGrubu = panel.add("group");
            scriptGrubu.orientation = "row";
            var scriptButonu = scriptGrubu.add("button", undefined, "Script Dosyasını Seç");
            var scriptEtiketi = scriptGrubu.add("statictext", undefined, "(seçilmedi)");
            scriptEtiketi.characters = 24;

            scriptButonu.onClick = function () {
                guvenliCagir(function () {
                    var dosya = File.openDialog("script.txt dosyasını seç", "*.txt");
                    if (dosya) {
                        secilenScriptDosyasi = dosya;
                        scriptEtiketi.text = dosya.name;
                    }
                }, "Script dosyasi secilemedi", null);
            };

            var arkaplanGrubu = panel.add("group");
            arkaplanGrubu.orientation = "row";
            var arkaplanButonu = arkaplanGrubu.add("button", undefined, "Arka Plan Klasörü Seç");
            var arkaplanEtiketi = arkaplanGrubu.add("statictext", undefined, "(seçilmedi)");
            arkaplanEtiketi.characters = 24;

            arkaplanButonu.onClick = function () {
                guvenliCagir(function () {
                    var klasor = Folder.selectDialog("Arka plan resimlerinin bulunduğu klasörü seç");
                    if (klasor) {
                        secilenArkaplanKlasoru = klasor.fsName;
                        arkaplanEtiketi.text = klasor.name;
                    }
                }, "Arka plan klasoru secilemedi", null);
            };

            var karakterGrubu = panel.add("group");
            karakterGrubu.orientation = "row";
            var karakterButonu = karakterGrubu.add("button", undefined, "Karakter Klasörü Seç");
            var karakterEtiketi = karakterGrubu.add("statictext", undefined, "(seçilmedi)");
            karakterEtiketi.characters = 24;

            karakterButonu.onClick = function () {
                guvenliCagir(function () {
                    var klasor = Folder.selectDialog("Transparan karakter PNG'lerinin bulunduğu klasörü seç");
                    if (klasor) {
                        secilenKarakterKlasoru = klasor.fsName;
                        karakterEtiketi.text = klasor.name;
                    }
                }, "Karakter klasoru secilemedi", null);
            };

            panel.add("panel", undefined, "").minimumSize = [0, 1];

            var baslatButonu = panel.add("button", undefined, "🚀 ANİMASYONU BAŞLAT");
            guvenliCagir(function () {
                baslatButonu.graphics.font = ScriptUI.newFont("dialog", "BOLD", 14);
            }, "Font ayarlanamadi (kritik degil)", null);

            baslatButonu.onClick = function () {
                guvenliCagir(function () { animasyonuBaslat(); }, "Animasyon baslatilirken hata", null);
            };

            panel.layout.layout(true);
            return panel;
        }, "Panel olusturulamadi", null);
    }

    var myPanel = buildUI(thisObj);
    if (myPanel instanceof Window) {
        myPanel.center();
        myPanel.show();
    }

})(this);