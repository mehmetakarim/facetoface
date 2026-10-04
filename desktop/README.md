# Yüz Atölyesi

Deep-Live-Cam modellerini kullanan, Türkçe Tauri 2 masaüstü arayüzü. Bu ilk sürüm fotoğraf, video ve canlı kamera işlemlerini kapsar. Ağız maskeleme, kişi bazında yüz eşleştirme ve yüz iyileştirme henüz taşınmadı.

## Geliştirme

Proje kökünde mevcut `venv`, `models/inswapper_128.onnx` ve kullanıcı klasöründe `.insightface/models/buffalo_l` gerekir. Python 3.10, Node.js 20, Rust ve macOS geliştirme araçları kullanılmaktadır.

```sh
cd desktop
npm install
DEVELOPER_DIR=/Library/Developer/CommandLineTools npm run tauri dev
```

`npm run dev` yalnızca tarayıcıdaki arayüz önizlemesini açar. Bu mod dosya seçimini gösterir; motor çalıştırmaz. `npm run build` TypeScript denetimini ve ön yüz derlemesini yapar. `DEVELOPER_DIR=/Library/Developer/CommandLineTools npm run tauri -- build --debug --bundles app` yerel macOS uygulamasını oluşturur. Proje kökündeki `Yuz-Atolyesi.command` dosyası uygulamayı açar. Bu sürüm kurulu Python ortamını kullanır; başka bilgisayarlara dağıtılabilir, bağımsız bir uygulama paketi değildir. Gerekirse `DLC_PROJECT_ROOT` ile proje konumu belirtilir.

## Mimari ve hata sınırları

React arayüzü → Tauri komutları → Rust süreç yöneticisi → `engine/worker.py`.

Motor eski `modules.ui` ve `modules.core` modüllerini içe aktarmaz. InsightFace 0.7.3 ve aynı ONNX modellerini kullanır. `engine/inference.py`, kurulu paketin yalnızca çıkarım modüllerini özel bir ad alanında yükler; kullanılmayan 3B çizim bileşenleri, Matplotlib ve yazı tipi taraması başlatılmaz. Kurulu InsightFace dosyaları değiştirilmez. Adaptör, paket sürümünü açıkça denetler. Yüz algılama CPU'da çalışır; yüz değiştirme için CPU varsayılandır, CoreML isteğe bağlıdır. Her işlem yeni bir Python sürecinde çalışır; ilk kaynak doğrulaması da ayrı süreçtedir. Bu seçim model yükleme maliyetini artırır, ancak bellek birikimini ve önceki işlemden kalan durumları önler.

Motor stdout üzerinden JSON satırlarıyla durum ve sınırlı çözünürlükte JPEG önizlemeleri iletir. Yerel kitaplık çıktıları stderr'e ayrılır. Önizleme en fazla yaklaşık 5,5 kare/sn ile aktarılır; bu, motorun işlem hızından farklıdır. Canlı görüntü bu sürümde kaydedilmez veya sanal kameraya gönderilmez.

Rust, işlem ağacını ve zaman sınırlarını yönetir: ilk yanıt 120 sn, hazırlık adımları 150 sn, görüntü akışı 45 sn. Durdurma ve pencereyi kapatma bütün işlem grubunu sonlandırır. Yanıt vermeyen model yükleme işlemi arayüzün olay döngüsünü engellemez. Süreç günlükleri sistemin geçici klasöründe `yuz-atolyesi-<kimlik>.log` adıyla, en fazla 256 KB tutulur. Geçici video dosyaları durdurmada temizlenir.

Video, FFmpeg ile kare hızı korunarak MP4/H.264 olarak kodlanır; varsa özgün ses AAC olarak eklenir. Çıktı mevcut dosyanın üzerine yazılmaz. Değişken kare hızlı videolar sabit kare hızına dönüştürülür; ses eşzamanlılığı ayrıca sınanmalıdır. Çıktı önce aynı diskteki geçici klasöre tamamen yazılır ve ardından tek adımda yayımlanır. Durdurma sırasında yarım bir sonuç dosyası yayımlanmaz.

## Doğrulama

Proje kökünde:

```sh
DLC_RUN_INFERENCE_TESTS=1 venv/bin/python -m unittest discover -s tests -v
venv/bin/python scripts/smoke_engine.py
DEVELOPER_DIR=/Library/Developer/CommandLineTools cargo test --manifest-path desktop/src-tauri/Cargo.toml --offline
printf '%s\n' '{"mode":"diagnostics"}' | venv/bin/python engine/worker.py
```

macOS kamera iznini kullanıcı vermelidir. Kamera numaraları donanım keşfi değildir; 0–3 arasından elle seçilir. CPU ve CoreML başarımı cihaz ve modele göre ayrıca ölçülmelidir.

## Yerel derleme notu

Xcode lisans durumundan bağımsız olarak, makinede zaten kurulu olan Command Line Tools derleyicisi `DEVELOPER_DIR` ile seçilmiştir. Sistem genelindeki geliştirici araçları ayarı değiştirilmez. Başka bir makinede bu dizin kurulu değilse kendi geliştirme araçlarınızı kullanın.

## Doğrulama sonuçları

- Python dosya/protokol kontrolleri ve atomik çıktı testleri başarılı.
- Rust: yanıt vermeyen bir alt süreç iptal edildi; test başarılı.
- Gerçek fotoğraf çıktısı oluşturuldu.
- Gerçek video testi: 3 kare, 636 × 364 çıktı boyutu ve ses akışı doğrulandı. Örnek video testi soğuk başlangıçla yaklaşık 108 saniye sürdü; bu bir gerçek zamanlı performans iddiası değildir.
- Tauri macOS uygulama paketi oluşturuldu ve yerel pencerenin açıldığı doğrulandı.
- Canlı kameranın donanım/izin davranışı ve CoreML başarımı henüz uçtan uca doğrulanmadı.
