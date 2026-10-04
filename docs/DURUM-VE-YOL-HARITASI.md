# Mevcut durum, testler ve kalan işler

## İlk test sürümünde tamamlananlar

Türkçe Tauri/React arayüzü; fotoğraf, video ve canlı kamera akışı; kaynak yüz kontrolü; dosya seçme ve kaydetme pencereleri; ilerleme ve önizleme; motoru durdurma ve zaman aşımı koruması tamamlandı. Python motoru ayrı süreçte çalışır. Model yüklemesinde gereksiz 3B çizici ve sistem yazı tipi taraması kaldırıldı. Var olan dosyaların üzerine yazılması engellendi. Video çıktısına özgün ses eklenir.

Windows için taşınabilir uygulama yolu, paketli Python motoru, FFmpeg bulma ve alt süreç ağacını sonlandırma desteği eklendi. GitHub Actions Windows x64 üzerinde bağımlılıkları kurar, testleri çalıştırır, motoru paketler, paketli motorun çıkarım bileşenlerini kontrol eder ve Tauri uygulamasını derler. Model dosyaları paket dışındadır.

## Test kanıtları ve sınırları

- Kullanıcı, macOS/M1 ve kısıtlı kaynaklarda uygulamayı deneyerek başarılı sonuç aldığını bildirdi.
- macOS'ta 11 Python testi ve Rust motor iptal testi geçti.
- Fotoğraf işlemi gerçek arayüzde tamamlandı.
- Otomatik kısa video testinde 3 kare, 636×364 boyut ve ses akışı doğrulandı. Soğuk başlangıç dahil yaklaşık 108 saniye sürdü. Bu sonuç gerçek zamanlı performans iddiası değildir.
- Windows derleme ve paketli motor kontrollerinin güncel sonucu deponun Actions sekmesinden görülebilir. Bu kontroller gerçek kamera, model ağırlıklarıyla görüntü işleme veya farklı Windows donanımlarında kullanıcı testi yerine geçmez.

## Windows deneme sırası

1. Paketi çıkarın, üç model dosyasını yerleştirin ve kurulum kontrolünü çalıştırın.
2. Tek yüzlü küçük bir fotoğrafta kaynak doğrulama ve çıktı kaydını deneyin.
3. Türkçe karakter ve boşluk içeren dosya yollarını deneyin.
4. 5–10 saniyelik sesli bir videoyu işleyin; ses, kareler ve oynatma süresini kontrol edin.
5. Model yüklenirken ve video işlenirken Durdur düğmesini deneyin; ardından yeni işlem başlatın.
6. Kamera izinlerini verip canlı önizlemeyi deneyin. Kamera yokken veya başka uygulama kullanırken hata mesajını kontrol edin.
7. Art arda beş işlemde bellek kullanımı, yanıt verme ve kapanma davranışını gözlemleyin.

Her denemede işletim sistemi, CPU, RAM, işlem süresi, bellek kullanımı ve varsa hata mesajını kaydedin. Başarısız adımı yeniden üretilebilecek şekilde bildirin.

## Sonraki işler ve öncelikleri

**Öncelik 1 — Windows doğrulaması:** gerçek donanımda fotoğraf/video/kamera ve durdurma testleri; paket bağımlılıkları, WebView2, Türkçe yollar ve izin sorunları. Sonuçlara göre ilk düzeltme sürümü hazırlanacak.

**Öncelik 2 — Başlangıç süresi ve kaynak tüketimi:** aşama bazında ölçüm, model yükleme süresini azaltma, gerektiğinde ayrı kalıcı motor ve güvenli yeniden başlatma tasarımı. Bellek ve iptal güvenliği korunarak karar verilecek.

**Öncelik 3 — Kullanılabilirlik:** model kurulumunu yönlendiren ekran; cihazların adlarıyla kamera seçimi; uzun işlemlerde daha açıklayıcı süre ve durum bilgileri; klavye/ekran okuyucu ve küçük ekran kontrolleri. Arayüz metinleri Türkçe dil bilgisi ve anlam tutarlılığı açısından gözden geçirilecek.

**Öncelik 4 — Dağıtım:** Windows kurulum paketi ve kod imzalama; macOS için geliştirme klasöründen bağımsız paket, imzalama/noter onayı; sürüm yükseltme ve hata raporlama düzeni. Mevcut macOS geliştirme paketi genel kullanıma hazır bağımsız dağıtım değildir.

**Sonraki özellikler:** canlı kayıt, sanal kamera, yüz eşleme, gelişmiş maskeleme ve iyileştirme; Windows GPU seçenekleri. Bunlar mevcut kararlılık ve performans testlerinden sonra değerlendirilecek.

Test sonuçları gelene kadar yeni özellik kapsamı genişletilmeyecek; önce bu sürümün somut sorunları giderilecek.
