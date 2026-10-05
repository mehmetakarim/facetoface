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
