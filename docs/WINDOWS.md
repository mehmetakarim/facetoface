# Windows test sürümü kurulumu

Bu paket Windows x64 içindir. Python motoru ve FFmpeg paket içindedir; ayrıca Python, Node.js veya Rust kurmanız gerekmez. ONNX modelleri ayrı sağlanır. Windows ARM64 yerel sürümü yoktur.

1. Release sayfasından `Yuz-Atolyesi-Windows-x64.zip` dosyasını indirin ve tamamını yazılabilir bir klasöre çıkarın. Uygulamayı ZIP içinden çalıştırmayın.
2. macOS'ta kullandığınız mevcut modelleri aşağıdaki konumlara kopyalayın:

   - Projedeki `models/inswapper_128.onnx` → `models/inswapper_128.onnx`
   - Ev klasöründeki `.insightface/models/buffalo_l/det_10g.onnx` → `models/buffalo_l/det_10g.onnx`
   - Ev klasöründeki `.insightface/models/buffalo_l/w600k_r50.onnx` → `models/buffalo_l/w600k_r50.onnx`
   - İsteğe bağlı: `xseg.onnx` → `models/xseg.onnx`. Yüzün önündeki eli ve gerçek saç çizgisini korur. Kaynak: https://huggingface.co/hacksider/deep-live-cam/blob/main/xseg.onnx

3. `Yuz-Atolyesi.exe` dosyasını açın. `engine-worker` klasörünü uygulamanın yanında bırakın.
4. WebView2 çalışma zamanı bulunmuyorsa Microsoft'un resmî WebView2 Evergreen Runtime paketini kurun: https://developer.microsoft.com/microsoft-edge/webview2/
5. Ayarlardaki kurulum kontrolünü çalıştırın. Önce standart işlem (CPU), ardından ekran kartı hızlandırmasıyla küçük bir fotoğraf deneyin; ardından kısa video ve kamera testlerine geçin. Apple hızlandırması Windows'ta kullanılamaz.

Paket henüz kod imzalı değildir. Windows bilinmeyen yayıncı uyarısı gösterebilir. Yalnızca bu deponun Releases sayfasından indirdiğiniz paketi kullanın; SHA256SUMS.txt ile bütünlüğünü kontrol edebilirsiniz.

Modeller eksikse işlem başlayamaz. İlk model yüklemesi düşük kaynaklı cihazlarda uzun sürebilir. Gelişmiş ayarlardaki "Ekran kartı hızlandırması · DirectML" seçeneği yüz değiştirmeyi ekran kartında çalıştırır; ayrı bir CUDA kurulumu gerekmez ve NVIDIA, AMD ve Intel kartlarda çalışır. Hibrit dizüstülerde yüksek performanslı kart seçilir. Yüz algılama işlemcide kalır. Sonuçları NTFS biçimli, yazılabilir bir diske kaydedin; atomik çıktı kaydı sabit bağlantı desteği gerektirir.

## Sorun bildirimi

Windows sürümü, işlemci, RAM, kullanılan mod, dosyanın boyutu/süresi, beklenen ve görülen sonuç ile işlemin ne kadar sürdüğünü not edin. Hata günlükleri `%TEMP%/yuz-atolyesi-*.log` konumundadır; paylaşmadan önce kişisel dosya yollarını silin. Özel fotoğraf veya videolarınızı herkese açık hata kayıtlarına yüklemeyin.

Önerilen deneme sırası ve kalan işler: https://github.com/mehmetakarim/facetoface/blob/main/docs/DURUM-VE-YOL-HARITASI.md

## Sanal kamera

Canlı kamera modunda "Sanal kameraya gönder" seçeneği, işlenen görüntüyü görüntülü görüşme uygulamalarına kamera olarak iletir. Karşı tarafa aynalanmamış görüntü gider; uygulamanın kendi önizlemenizi aynalaması normaldir.

- **Windows 11 — Yüz Atölyesi Kamera (önerilen):** Canlı kamera bölümündeki "Yüz Atölyesi Kamera'yı kur" düğmesiyle bir kez kurulur (yönetici izni ister). Bileşen `C:\ProgramData\YuzAtolyesi\vcam` klasörüne kopyalanıp kaydedilir. WhatsApp, Windows Kamera, Teams, Zoom ve tarayıcılarda "Yüz Atölyesi Kamera" adıyla görünür. Kamera yalnızca canlı görüntü çalışırken listededir; önce uygulamada canlı kamerayı başlatın, sonra görüşme uygulamasında bu kamerayı seçin. Görüntü durduğunda "Canlı görüntü bekleniyor" ekranı gösterilir. Aynı düğmeyle kaldırılabilir.
- **OBS Virtual Camera (yedek):** Yüz Atölyesi Kamera kurulu değilse ve OBS Studio yüklüyse kullanılır. Yalnızca DirectShow kullanan uygulamalarda (tarayıcılar, Zoom, Discord, OBS) görünür; WhatsApp ve Microsoft Store uygulamalarında görünmez. OBS'nin kendi "Sanal Kamerayı Başlat" düğmesi açıkken kullanılamaz.

Sanal kamera bileşeni Simon Mourier'in MIT lisanslı VCamSample projesinden türetilmiştir (`vcam/LICENSE.VCamSample`).
