# Üçüncü taraf bileşenler

Bu proje Deep-Live-Cam kaynak kodunu içerir; özgün AGPL-3.0 lisansı ve kaynak dosyalardaki bildirimler korunur. Kaynak: https://github.com/hacksider/Deep-Live-Cam

Yeni arayüz Tauri, React ve Lucide; motor InsightFace 0.7.3, ONNX Runtime, ONNX, NumPy, SciPy, OpenCV ve Pillow kullanır. Windows paketi PyInstaller ile oluşturulur; imageio-ffmpeg dağıtımındaki FFmpeg yürütülebilir dosyasını içerir. Bu bileşenlerin lisansları kendilerine aittir; paket içindeki dağıtım/metadata ve lisans dosyaları korunmalıdır.

FFmpeg kaynak ve derleme bilgileri: https://github.com/imageio/imageio-ffmpeg ve https://github.com/BtbN/FFmpeg-Builds . FFmpeg lisansı kullanılan derlemenin seçeneklerine bağlıdır. Bileşenleri yeniden dağıtırken ilgili lisans bildirimlerini koruyun.

Model ağırlıkları bu depoya veya sürüm paketine dahil edilmez. InsightFace kaynak kodu ile önceden eğitilmiş modellerin kullanım koşulları aynı değildir. Model kaynağı ve koşulları: https://github.com/deepinsight/insightface .

Windows 11 sanal kamerası (`native/vcam/`), Simon Mourier'in MIT lisanslı VCamSample projesinden türetilmiştir: https://github.com/smourier/VCamSample . Özgün lisans metni `native/vcam/LICENSE.VCamSample` dosyasındadır. Derleme sırasında Microsoft'un MIT lisanslı Windows Implementation Library (WIL) ve C++/WinRT paketleri NuGet'ten indirilir.
