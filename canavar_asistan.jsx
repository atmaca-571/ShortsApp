/*
================================================================================
Manga Animasyon Otomasyon Asistani - After Effects ExtendScript (.jsx)
================================================================================
Kullanim: After Effects -> File -> Scripts -> Run Script File... -> bu dosyayi sec.
Ya da Window menusune panel olarak sabitlemek icin bu dosyayi AE'nin
"Scripts/ScriptUI Panels" klasorune atip AE'yi yeniden baslat.

Bu script:
  1) script.txt (Python motorunun formatinda) dosyasini okur
  2) 1080x1920 / 30fps bir Composition olusturur
  3) Her sahne icin arka plan + karakter katmanlarini yerlestirir
  4) Kamera zoom, wiggle (ruzgar), zipla/titre/sabit efektlerini keyframe
     ve expression olarak uygular
  5) Patlayan (pop-up) altyazi metin katmanlarini ekler

NOT: Bir dosya (arka plan/karakter) bulunamazsa script DURMAZ; $.writeln() ile
konsola hata yazar, yerine placeholder bir solid katman koyup devam eder.
================================================================================
*/

(function (thisObj) {

    // ============================================================
    // GENEL SABITLER
    // ============================================================
    var COMP_GENISLIK = 1080;
    var COMP_YUKSEKLIK = 1920;
    var COMP_FPS = 30;

    var POZISYON_X = { "sol": 216, "merkez": 540, "sag": 864 };

    // Kullanicinin sectigi dosya/klasor yollari (global durum)
    var secilenScriptDosyasi = null;
    var secilenArkaplanKlasoru = null;
    var secilenKarakterKlasoru = null;

    // ============================================================
    // YARDIMCI: HATA YONETIMI (crash yerine konsola yaz + devam et)
    // ============================================================
    function hataBildir(mesaj) {
        try {
            $.writeln("HATA: " + mesaj);
        } catch (e) {
            // $.writeln bulunamazsa (cok nadir) sessizce gec
        }
    }

    function placeholderKatmanOlustur(comp, isim, sure, baslangicZamani) {
        var renk = [0.05, 0.05, 0.05];
        var solid = comp.layers.addSolid(renk, "PLACEHOLDER_" + isim, COMP_GENISLIK, COMP_YUKSEKLIK, 1, sure);
        solid.startTime = baslangicZamani;
        solid.outPoint = baslangicZamani + sure;
        return solid;
    }

    // ============================================================
    // BOLUM 1: SCRIPT.TXT AYRISTIRICI
    // ============================================================
    function scriptDosyasiniOku(dosyaYolu) {
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
            // bastaki/sondaki bosluklari ve \r karakterini temizle
            satir = satir.replace(/^\s+|\s+$/g, "").replace(/\r/g, "");
            if (satir === "" || satir.charAt(0) === "#") continue;

            var sahne = satiriAyristir(satir, i + 1);
            if (sahne) sahneler.push(sahne);
        }
        return sahneler;
    }

    function satiriAyristir(satir, satirNo) {
        var parcalar = satir.split("|");
        if (parcalar.length !== 4) {
            hataBildir("Satir " + satirNo + " atlandi (4 bolum bekleniyor): " + satir);
            return null;
        }

        for (var i = 0; i < parcalar.length; i++) {
            parcalar[i] = parcalar[i].replace(/^\s+|\s+$/g, "");
        }

        var sure = parseFloat(parcalar[0]);
        if (isNaN(sure)) {
            hataBildir("Satir " + satirNo + " atlandi (sure sayi degil): " + parcalar[0]);
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
    }

    // ============================================================
    // DOSYA BULMA YARDIMCILARI
    // ============================================================
    function dosyaBul(klasorYolu, dosyaAdi) {
        var tamYol = klasorYolu + "/" + dosyaAdi;
        var dosya = new File(tamYol);
        return dosya.exists ? dosya : null;
    }

    function karakterDosyasiBul(klasorYolu, karakterAdi) {
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
    }

    // ============================================================
    // GOREV: FOOTAGE IMPORT ETME (tekrar import etmemek icin onbellek)
    // ============================================================
    var _importOnbellek = {};

    function footageImportEt(dosya) {
        var anahtar = dosya.fsName;
        if (_importOnbellek[anahtar]) return _importOnbellek[anahtar];

        var ioSec = new ImportOptions(dosya);
        var oge = app.project.importFile(ioSec);
        _importOnbellek[anahtar] = oge;
        return oge;
    }

    // ============================================================
    // BOLUM 2: ARKA PLAN KATMANI (zoom + wiggle ruzgar)
    // ============================================================
    function arkaplanKatmaniEkle(comp, sahne, baslangicZamani) {
        var katman;

        if (secilenArkaplanKlasoru) {
            var dosya = dosyaBul(secilenArkaplanKlasoru, sahne.arkaplan);
            if (dosya) {
                var oge = footageImportEt(dosya);
                katman = comp.layers.add(oge);
            } else {
                hataBildir("Arka plan bulunamadi: '" + sahne.arkaplan + "' -> placeholder olusturuldu.");
                katman = placeholderKatmanOlustur(comp, "arkaplan", sahne.sure, baslangicZamani);
                return katman;
            }
        } else {
            hataBildir("Arka plan klasoru secilmedi -> placeholder olusturuldu.");
            katman = placeholderKatmanOlustur(comp, "arkaplan", sahne.sure, baslangicZamani);
            return katman;
        }

        katman.startTime = baslangicZamani;
        katman.outPoint = baslangicZamani + sahne.sure;

        // Dikey formata sigacak sekilde olcekle (letterbox mantigi: kisa kenari doldur)
        try {
            var kaynakGenislik = katman.source.width;
            var kaynakYukseklik = katman.source.height;
            var olcekYuzde = Math.max(COMP_GENISLIK / kaynakGenislik, COMP_YUKSEKLIK / kaynakYukseklik) * 100;
            katman.property("Transform").property("Scale").setValue([olcekYuzde, olcekYuzde]);
            katman.property("Transform").property("Position").setValue([COMP_GENISLIK / 2, COMP_YUKSEKLIK / 2]);
        } catch (e) {
            hataBildir("Arka plan olcekleme hatasi: " + e.toString());
        }

        // Sinematik kamera zoom: sahne basinda %100 (goreceli), sonunda +%4
        try {
            var scaleProp = katman.property("Transform").property("Scale");
            var baslangicOlcek = scaleProp.value; // mevcut (sigdirma sonrasi) olcek
            var bitisOlcek = [baslangicOlcek[0] * 1.04, baslangicOlcek[1] * 1.04];
            scaleProp.setValueAtTime(0, baslangicOlcek);
            scaleProp.setValueAtTime(sahne.sure, bitisOlcek);
        } catch (e) {
            hataBildir("Kamera zoom keyframe hatasi: " + e.toString());
        }

        // Ruzgar/cevre simulasyonu: hafif wiggle
        try {
            katman.property("Transform").property("Position").expression = "wiggle(0.5, 15);";
        } catch (e) {
            hataBildir("Wiggle expression hatasi: " + e.toString());
        }

        return katman;
    }

    // ============================================================
    // BOLUM 3: KARAKTER KATMANI (pozisyon + keyframe efektler)
    // ============================================================
    function easyEaseUygula(prop, keyIndex) {
        try {
            var kolayGecis = new KeyframeEase(0, 33);
            prop.setTemporalEaseAtKey(keyIndex, [kolayGecis], [kolayGecis]);
        } catch (e) {
            hataBildir("Easy ease uygulanamadi: " + e.toString());
        }
    }

    function karakterKatmaniEkle(comp, karakterTanimi, sahneSuresi, baslangicZamani) {
        if (!secilenKarakterKlasoru) {
            hataBildir("Karakter klasoru secilmedi, '" + karakterTanimi.ad + "' atlandi.");
            return null;
        }

        var dosya = karakterDosyasiBul(secilenKarakterKlasoru, karakterTanimi.ad);
        if (!dosya) {
            hataBildir("Karakter bulunamadi: '" + karakterTanimi.ad + "' -> placeholder olusturuldu.");
            placeholderKatmanOlustur(comp, "karakter_" + karakterTanimi.ad, sahneSuresi, baslangicZamani);
            return null;
        }

        var oge = footageImportEt(dosya);
        var katman = comp.layers.add(oge);
        katman.startTime = baslangicZamani;
        katman.outPoint = baslangicZamani + sahneSuresi;

        // Anchor point'i karakterin ALT-ORTA noktasina tasi (taban cizgisi sabitlemesi)
        var genislik = katman.source.width;
        var yukseklik = katman.source.height;
        katman.property("Transform").property("Anchor Point").setValue([genislik / 2, yukseklik]);

        var xKoordinati = POZISYON_X[karakterTanimi.pozisyon];
        if (xKoordinati === undefined) xKoordinati = POZISYON_X["merkez"];

        // Taban Y=1920'ye sabitlenir (anchor zaten alt-ortada oldugu icin Position=Y hedefi budur)
        katman.property("Transform").property("Position").setValue([xKoordinati, COMP_YUKSEKLIK]);

        var efekt = karakterTanimi.efekt;

        if (efekt === "zipla") {
            try {
                var posProp = katman.property("Transform").property("Position");
                var tabanY = COMP_YUKSEKLIK;
                var zipiralamaYuksekligi = 40;
                var adim = 0.5; // her 0.5 saniyede bir zipla
                var t = 0;
                var keyIndexler = [];

                while (t < sahneSuresi) {
                    // inis (taban) keyframe'i
                    posProp.setValueAtTime(t, [xKoordinati, tabanY]);
                    // ziplama (tepe) keyframe'i - 0.25 saniye sonra
                    var tepeZaman = Math.min(t + adim / 2, sahneSuresi);
                    posProp.setValueAtTime(tepeZaman, [xKoordinati, tabanY - zipiralamaYuksekligi]);
                    t += adim;
                }

                // Tum keyframe'lere Easy Ease uygula (pürüzsüz zıplama/düşme)
                for (var ki = 1; ki <= posProp.numKeys; ki++) {
                    easyEaseUygula(posProp, ki);
                }
            } catch (e) {
                hataBildir("Zipla efekti uygulanamadi: " + e.toString());
            }
        } else if (efekt === "titre") {
            try {
                katman.property("Transform").property("Position").expression = "wiggle(15, 30);";
            } catch (e) {
                hataBildir("Titre expression hatasi: " + e.toString());
            }
        } else {
            // 'sabit' (veya taninmayan efekt) -> hafif nefes alma hissi
            try {
                katman.property("Transform").property("Scale").expression =
                    "var taban = 100;\nvar genlik = 1;\nvar s = taban + Math.sin(time * 3) * genlik;\n[s, s];";
            } catch (e) {
                hataBildir("Sabit/nefes expression hatasi: " + e.toString());
            }
        }

        return katman;
    }

    // ============================================================
    // BOLUM 4: POP-UP ALTYAZI METIN KATMANI
    // ============================================================
    function altyaziKatmaniEkle(comp, metin, sahneSuresi, baslangicZamani) {
        if (!metin || metin === "") return null;

        var textLayer = comp.layers.addText(metin);
        textLayer.startTime = baslangicZamani;
        textLayer.outPoint = baslangicZamani + sahneSuresi;

        try {
            var textProp = textLayer.property("Source Text");
            var textDoc = textProp.value;

            // Font: Impact varsa onu kullan, yoksa Arial-BoldMT'ye dus
            try {
                textDoc.font = "Impact";
            } catch (fontHata) {
                textDoc.font = "Arial-BoldMT";
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
        } catch (e) {
            hataBildir("Altyazi tipografi ayari hatasi: " + e.toString());
        }

        // Konum: alt-orta (Y=1550), yatayda ortalanmis
        textLayer.property("Transform").property("Position").setValue([COMP_GENISLIK / 2, 1550]);
        textLayer.property("Transform").property("Anchor Point").setValue([0, 0]);

        // Pop-up animasyonu: 0 -> 0.15 saniyede Scale %0 -> %100, ease in/out ile
        try {
            var scaleProp = textLayer.property("Transform").property("Scale");
            scaleProp.setValueAtTime(0, [0, 0]);
            scaleProp.setValueAtTime(0.15, [100, 100]);

            var easeIn = new KeyframeEase(0, 75);
            var easeOut = new KeyframeEase(0, 20);
            scaleProp.setTemporalEaseAtKey(1, [easeIn], [easeIn]);
            scaleProp.setTemporalEaseAtKey(2, [easeOut], [easeOut]);
        } catch (e) {
            hataBildir("Pop-up animasyon hatasi: " + e.toString());
        }

        return textLayer;
    }

    // ============================================================
    // ANA PIPELINE: KOMPOZISYON OLUSTURMA
    // ============================================================
    function animasyonuBaslat() {
        if (!secilenScriptDosyasi) {
            alert("Lütfen önce 'Script Dosyasını Seç' ile script.txt dosyasını seçin.");
            return;
        }

        var sahneler = scriptDosyasiniOku(secilenScriptDosyasi.fsName);
        if (sahneler.length === 0) {
            alert("script.txt içinde geçerli hiçbir sahne bulunamadı. Konsolu (Window > Console veya ExtendScript Toolkit) kontrol edin.");
            return;
        }

        var toplamSure = 0;
        for (var i = 0; i < sahneler.length; i++) toplamSure += sahneler[i].sure;

        app.beginUndoGroup("Manga Animasyon Otomasyonu");

        try {
            var comp = app.project.items.addComp(
                "Manga_Shorts_Otomatik",
                COMP_GENISLIK,
                COMP_YUKSEKLIK,
                1,
                toplamSure,
                COMP_FPS
            );

            var baslangicZamani = 0;
            for (var s = 0; s < sahneler.length; s++) {
                var sahne = sahneler[s];

                arkaplanKatmaniEkle(comp, sahne, baslangicZamani);

                for (var k = 0; k < sahne.karakterler.length; k++) {
                    karakterKatmaniEkle(comp, sahne.karakterler[k], sahne.sure, baslangicZamani);
                }

                altyaziKatmaniEkle(comp, sahne.metin, sahne.sure, baslangicZamani);

                baslangicZamani += sahne.sure;
            }

            comp.openInViewer();
            alert("Animasyon oluşturuldu! Toplam süre: " + toplamSure.toFixed(2) + " saniye.\n" +
                  "Hata/uyarı olduysa Window > Console'dan kontrol edebilirsin.");
        } catch (genelHata) {
            alert("Beklenmeyen bir hata oluştu: " + genelHata.toString());
            hataBildir("GENEL HATA: " + genelHata.toString());
        } finally {
            app.endUndoGroup();
        }
    }

    // ============================================================
    // BOLUM 1 (devam): SCRIPTUI PANELI
    // ============================================================
    function buildUI(thisObj) {
        var panel = (thisObj instanceof Panel)
            ? thisObj
            : new Window("palette", "Manga Animasyon Otomasyonu", undefined, { resizeable: true });

        panel.orientation = "column";
        panel.alignChildren = ["fill", "top"];
        panel.spacing = 10;
        panel.margins = 16;

        var baslikGrubu = panel.add("group");
        baslikGrubu.add("statictext", undefined, "🎬 Manga Shorts -> AE Otomasyonu");

        // --- Script dosyasi secimi ---
        var scriptGrubu = panel.add("group");
        scriptGrubu.orientation = "row";
        var scriptButonu = scriptGrubu.add("button", undefined, "Script Dosyasını Seç");
        var scriptEtiketi = scriptGrubu.add("statictext", undefined, "(seçilmedi)");
        scriptEtiketi.characters = 24;

        scriptButonu.onClick = function () {
            var dosya = File.openDialog("script.txt dosyasını seç", "*.txt");
            if (dosya) {
                secilenScriptDosyasi = dosya;
                scriptEtiketi.text = dosya.name;
            }
        };

        // --- Arka plan klasoru secimi ---
        var arkaplanGrubu = panel.add("group");
        arkaplanGrubu.orientation = "row";
        var arkaplanButonu = arkaplanGrubu.add("button", undefined, "Arka Plan Klasörü Seç");
        var arkaplanEtiketi = arkaplanGrubu.add("statictext", undefined, "(seçilmedi)");
        arkaplanEtiketi.characters = 24;

        arkaplanButonu.onClick = function () {
            var klasor = Folder.selectDialog("Arka plan resimlerinin bulunduğu klasörü seç");
            if (klasor) {
                secilenArkaplanKlasoru = klasor.fsName;
                arkaplanEtiketi.text = klasor.name;
            }
        };

        // --- Karakter klasoru secimi ---
        var karakterGrubu = panel.add("group");
        karakterGrubu.orientation = "row";
        var karakterButonu = karakterGrubu.add("button", undefined, "Karakter Klasörü Seç");
        var karakterEtiketi = karakterGrubu.add("statictext", undefined, "(seçilmedi)");
        karakterEtiketi.characters = 24;

        karakterButonu.onClick = function () {
            var klasor = Folder.selectDialog("Transparan karakter PNG'lerinin bulunduğu klasörü seç");
            if (klasor) {
                secilenKarakterKlasoru = klasor.fsName;
                karakterEtiketi.text = klasor.name;
            }
        };

        panel.add("panel", undefined, "").minimumSize = [0, 1]; // ince ayirici cizgi

        // --- ANA BUTON ---
        var baslatButonu = panel.add("button", undefined, "🚀 ANİMASYONU BAŞLAT");
        baslatButonu.graphics.font = ScriptUI.newFont("dialog", "BOLD", 14);

        baslatButonu.onClick = function () {
            animasyonuBaslat();
        };

        panel.layout.layout(true);
        return panel;
    }

    var myPanel = buildUI(thisObj);
    if (myPanel instanceof Window) {
        myPanel.center();
        myPanel.show();
    }

})(this);