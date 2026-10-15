# OBS’den bağımsız macOS kamera uzantısı

Bu bileşen geliştirme aşamasındadır. Kaynak kodu derlenebilir; Apple Developer Program üyeliği, uygun sertifika ve profiller henüz sağlanmadığı için macOS üzerinde etkinleştirme ve uçtan uca görüntü aktarımı doğrulanmamıştır. Ad hoc derleme kurulabilir bir yayın paketi değildir.

## Yapı

Python motoru, son işlenmiş kareyi 640×480 BGRA biçiminde `yuz-camera-bridge` yardımcısına iletir. Yardımcı CoreMediaIO sink akışını besler; sistem uzantısı source akışını diğer uygulamalara **Yüz Atölyesi Kamera** adıyla sunar. Çıkış 30 kare/sn olarak bildirilir; yüz işleme hızı daha düşük olabilir. Bekleyen kareler biriktirilmez, eski kare yerine yenisi alınır. Üretici durduğunda en geç iki saniye içinde siyah görüntü gösterilir.

Uzantı yalnızca aynı Apple Team ID ile imzalanmış ve beklenen imza kimliğine sahip yardımcıdan görüntü kabul eder. Kamera okuyucuları macOS’un kamera erişim mekanizmasını kullanır. Fiziksel kamera seçimi ve izni ayrı konulardır; sanal kamera uzantısı fiziksel kamera erişim sorunlarını çözmez.

## Yerel derleme

macOS 13 veya üzeri ve Apple Command Line Tools gerekir:

```sh
python3 native/macos-camera/build.py
native/macos-camera/build/YuzAtolyesiCamera.app/Contents/MacOS/yuz-camera-bridge --self-test
native/macos-camera/build/YuzAtolyesiCamera.app/Contents/MacOS/yuz-camera-bridge --status
```

Çıktı `build/YuzAtolyesiCamera.app` paketidir. arm64 ve x86_64 ikilileri üretilir. İmzasız geliştirme paketinde kurulum ve kaldırma düğmeleri devre dışıdır. `--self-test` piksel aktarımını sınar; sistem uzantısını başlatmaz. `--status` kayıtlı cihaz ve giriş akışının bulunup bulunmadığını bildirir.

Uygulama yöneticiyi önce `/Applications/YuzAtolyesiCamera.app`, sonra proje içindeki `vcam/YuzAtolyesiCamera.app`, ardından bu derleme dizininde arar. Yerel kamera kayıtlıysa otomatik seçilir; değilse mevcut OBS yolu korunur.

## İmzalı paket için kalan adımlar

Apple Developer hesabında uygulama ve uzantı kimlikleri, ortak uygulama grubu ve uygun profiller hazırlanmalıdır. Kimlikler `com.yuzatolyesi.camera` ve `com.yuzatolyesi.camera.extension`; grup `TEAMID.com.yuzatolyesi.camera` biçimindedir. Ana uygulama sistem uzantısı kurma yetkisini, uzantı sandbox yetkisini kullanır.

```sh
python3 native/macos-camera/build.py \
  --identity 'Developer ID Application: AD SOYAD (TEAMID)' \
  --team-id GERCEKTEAM \
  --host-profile /profil/host.provisionprofile \
  --extension-profile /profil/extension.provisionprofile
```

Örnekteki kimlik ve yollar gerçek bilgilerle değiştirilmelidir. Betik profil dosyalarının varlığını denetler; profil içeriğinin hesap, yetki ve sertifika uyumu ayrıca doğrulanmalıdır. Dağıtımdan önce notarization, stapling ve Gatekeeper doğrulaması gerekir. Sonraki sürümlerde paket sürüm numarası artırılmalıdır.

İmzalı paket `/Applications` içine konulur. Uygulamadaki **Yerel kamera kurulumunu aç** düğmesi yöneticiyi açar; yönetici üzerinden etkinleştirme istenir ve macOS’un izin adımları kullanıcı tarafından tamamlanır. SIP veya diğer sistem güvenlik ayarlarının kapatılması bu kurulumun parçası değildir.

## Yayın öncesi testler

- Gerçek sertifika/profillerle etkinleştirme, izin reddi, yeniden deneme ve kaldırma.
- Sentetik renklerle yardımcı → sink → source → bağımsız AVFoundation alıcısı aktarımı; renk, yön, boyut ve zaman damgaları.
- Yüz işleme motoruyla canlı aktarım, durdurma, yeniden başlatma ve üretici kapanınca görüntünün temizlenmesi.
- Aynı anda birden çok okuyucu, izinsiz üreticinin reddi ve kuyruk dolarken bellek kullanımı.
- Görüşme uygulamalarında kamera seçimi; yeniden başlatma ve uzantı güncellemesi.
- Intel Mac üzerinde çalışma; universal derleme tek başına Intel çalışma testi sayılmaz.

Başvuru: [Apple CoreMediaIO kamera uzantısı kılavuzu](https://developer.apple.com/documentation/coremediaio/creating-a-camera-extension-with-core-media-i-o).
