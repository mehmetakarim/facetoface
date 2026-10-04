# Yüz Atölyesi — FaceToFace

Türkçe arayüzlü, Tauri ve React ile geliştirilen masaüstü yüz değiştirme uygulaması. Deep-Live-Cam temel alınmıştır; görüntü işleme motoru Python ile ayrı bir süreçte çalışır. Böylece motorun yavaşlaması arayüzün olay döngüsünü doğrudan kilitlemez. İşlemler durdurulabilir; yanıt vermeyen motor zaman aşımıyla sonlandırılır.

**Durum: 0.1.0 ilk test sürümü.** Kullanıcının Apple M1 üzerindeki macOS denemeleri başarılıdır. Windows desteği yeni eklenmiştir; gerçek donanım, kamera ve performans testleri beklenmektedir. İlk model yüklemesi uzun sürebilir; Tauri tek başına görüntü işleme hızını artırmaz.

## Kullanım

1. Kaynak yüz fotoğrafını seçin.
2. Fotoğraf, video veya canlı kamera modunu seçin.
3. Hedef dosyayı ya da kamerayı seçip işlemi başlatın.
4. Fotoğraf ve video sonuçlarını yeni bir dosyaya kaydedin. Canlı kamera şu anda yalnızca önizleme sunar.

[Ön sürümler ve indirmeler](https://github.com/mehmetakarim/facetoface/releases) · [Windows kurulumu](docs/WINDOWS.md) · [Test planı ve kalan işler](docs/DURUM-VE-YOL-HARITASI.md) · [Geliştirme kurulumu](desktop/README.md)

## Mimari

- `desktop/`: Türkçe React arayüzü ve Tauri/Rust süreç yöneticisi.
- `engine/`: JSONL üzerinden çalışan bağımsız Python motoru.
- `tests/`: protokol, güvenli çıktı yazma ve bağımlılık yükleme testleri.
- `packaging/`, `.github/workflows/`: Windows x64 paketleme ve sürüm iş akışı.
- `modules/`, `run.py`: eski Deep-Live-Cam uygulaması; yeni arayüz bunları başlatmaz.

Fotoğraf, video ve canlı önizleme; CPU ve macOS üzerinde deneysel CoreML seçeneği bulunur. Sanal kamera, canlı kayıt ve gelişmiş yüz eşleme henüz yoktur.

## Lisans ve modeller

Kaynak kod GNU AGPL-3.0 lisansı altındadır; [LICENSE](LICENSE) dosyası korunmuştur. Özgün proje: [Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam). Önceki açıklamalar [upstream README](docs/UPSTREAM_README.md) dosyasındadır. [Üçüncü taraf notları](docs/THIRD_PARTY.md).

ONNX model ağırlıkları dağıtıma dahil değildir; bunların lisansları uygulama kodundan ayrıdır. Yalnızca kullanım hakkınız olan modelleri ve izinli görüntüleri kullanın. Yeni motor model dosyalarını otomatik indirmez.
