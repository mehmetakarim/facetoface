# macOS sanal kamera

Mac’te işlenen canlı görüntü OBS Virtual Camera üzerinden görüşme uygulamalarına aktarılır. Windows’a özgü “Yüz Atölyesi Kamera” sürücüsü Mac’e kurulmaz.

## Gereksinimler ve ilk kurulum

- macOS 13 veya üzeri.
- [OBS Studio 30 veya üzeri](https://obsproject.com/download); Apple Silicon bilgisayarda uygun Apple Silicon sürümünü seçin.
- Projenin mevcut Python ortamında aktarım bileşeni:

```sh
venv/bin/python -m pip install -r packaging/requirements-macos-camera.txt
```

OBS’yi açın ve **Sanal Kamerayı Başlat** düğmesine basın. macOS’un kamera uzantısı için gösterdiği izin adımlarını tamamlayın. Ardından OBS’de sanal kamerayı durdurun ve OBS’yi kapatın. Uzantı kurulumu bir kez yapılır; OBS’nin aktarım sırasında açık kalması gerekmez.

Yüz Atölyesi’nde kaynak fotoğrafı ve fiziksel kamerayı seçin. **Canlı kamera → Sanal kameraya gönder** seçeneğini açarak canlı görüntüyü başlatın. Görüşme uygulamasının kamera seçiminde **OBS Virtual Camera** seçin. Gerekirse görüşme uygulamasını yeniden açın. Durdur düğmesi aktarımı da sonlandırır.

OBS ile Yüz Atölyesi aynı sanal kameraya aynı anda yayın yapmamalıdır. Kaynak olarak OBS Virtual Camera yerine fiziksel kameranızı seçin. Yerel aynalama, karşı tarafa giden görüntüde geri alınır.

## Sorun giderme

- “Sanal kamera bileşeni eksik”: yukarıdaki bağımlılık komutunu projenin Python ortamında çalıştırın.
- “OBS sanal kamerası açılamadı”: OBS sürümünü ve kamera uzantısı iznini kontrol edin; OBS’deki sanal kamerayı durdurup OBS’yi kapatın.
- Aktarım gerekmiyorsa seçeneği kapatın; normal canlı önizleme OBS olmadan da çalışır.
- Aktarım bileşeninin “hazır” olması OBS’nin kurulu veya izinli olduğunu göstermez; kamera gerçekten açıldığında doğrulanır.

## Doğrulama

```sh
venv/bin/python -m unittest discover -s tests -p 'test_macos_virtualcam.py' -v
venv/bin/python scripts/smoke_macos_virtualcam.py
```

İkinci komut fiziksel kameranızı açmaz; 15 saniye boyunca sentetik renk şeritleri gönderir. Görüşme uygulamasından OBS Virtual Camera’yı seçerek renkleri ve yönü kontrol edin. Ardından gerçek canlı akışta başlatma, durdurma, yeniden başlatma ve görüntülü görüşme testlerini tamamlayın.

Kaynaklar: [pyvirtualcam macOS kurulumu](https://github.com/letmaik/pyvirtualcam#macos-obs), [OBS kamera sorun giderme](https://obsproject.com/kb/virtual-camera-troubleshooting).

## Yerel doğrulama — 6 Ekim 2026

OBS 32.2.2 kamera uzantısı kullanıcı onayıyla etkinleştirildi. Mac aktarım sınıfıyla gönderilen sentetik renk şeritleri, ayrı bir FFmpeg/AVFoundation alıcısıyla OBS Virtual Camera üzerinden beş kare boyunca okundu. Mavi, yeşil ve kırmızı bölgelerin renkleri ve sırası doğrulandı. Aktarım sonunda kamera kapatıldı; fiziksel kamera veya mikrofon kullanılmadı.

Bu kurulumda OBS alıcıya 1920×1080 / 60 fps modu bildiriyor. Bu değer yüz işleme motorunun gerçek işlem hızı değildir. Görüşme uygulamalarında gerçek yüz akışı ayrıca denenmelidir.

Yeni macOS sürümlerinde izin yolu: Sistem Ayarları → Genel → Oturum Açma Öğeleri ve Genişletmeler → OBS → Ortam Genişletmesi.


### Siyah görüntü ve kamera ışığının yanmaması

OpenCV 4.10, macOS kameralarını cihaz kimliğine göre sıralar. OBS Virtual Camera
0 numaraya yerleşebildiği için varsayılan 0 seçimi uygulamanın kendi çıktısını
giriş olarak okuyabiliyordu. Kamera listesi artık AVFoundation üzerinden cihaz
adlarını getirir, çıkış kamerasını girişlerden çıkarır ve gerçek indeksleri korur.
Canlı işlem başlarken cihaz kimliği yeniden çözülür; bağlantısı kesilen cihazın
yerine başka bir kamera sessizce açılmaz. Eski arayüzün çıkış indeksiyle başlattığı
işler de açıklayıcı bir hata ile durdurulur.

Mevcut geliştirme ortamında **Kameraları yenile → FaceTime HD Kamera** seçimiyle
devam edin. Ek bağımlılık: `pip install -r packaging/requirements-macos-camera.txt`.
Normal kamera önizlemesi OBS gerektirmez. Diğer uygulamalara sanal kamera olarak
gönderim için bu sürüm OBS kamera uzantısını kullanır; OBS uygulamasının açık
kalması gerekmez. Tamamen OBS bağımsız macOS çıkışı ayrı bir Core Media IO kamera
uzantısının geliştirilmesini, imzalanmasını ve dağıtılmasını gerektirir.

Kamera izni de model hazırlığından önce kontrol edilir. İlk istekte macOS'un
izin yanıtı beklenir; ret ve zaman aşımı durumları Türkçe açıklanır. Böylece
OpenCV'nin izin isteğini başlatıp hemen başarısız dönmesi engellenir.

7 Ekim 2026 yerel doğrulaması: Kamera 0'ın OBS Virtual Camera, Kamera 1'in
FaceTime HD Kamera olduğu görüldü. Düzeltme sonrası uygulama FaceTime'ı adıyla
seçti; izin kontrolünü geçip CPU yöntemiyle gerçek canlı görüntü üretti ve sanal
çıktıyı açtı. Bu denemede hız yaklaşık 0,3–0,5 kare/sn idi; akıcı performans
onaylanmış değildir. CoreML hazırlığı bir dakikayı geçtiği için CPU ile sınandı.
31 otomatik testten 25'i geçti, 6'sı koşullu olarak atlandı; TypeScript/Vite ve
macOS Tauri debug app derlemesi başarılı oldu.
