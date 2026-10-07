"""Match OpenCV 4.10 AVFoundation indices without opening capture devices."""


def mac_cameras():
    try:
        import AVFoundation as av
    except ImportError as exc:
        raise ValueError('Kamera listeleme bileşeni eksik. macOS kamera bağımlılıklarını yükleyin.') from exc
    devices = list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeVideo))
    devices += list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeMuxed))
    # OpenCV sorts video + muxed devices by uniqueID before assigning indices.
    return indexed_inputs([(str(d.uniqueID()), str(d.localizedName())) for d in devices])


def indexed_inputs(devices):
    return [dict(index=i, id=uid, name=name)
            for i, (uid, name) in enumerate(sorted(devices, key=lambda d: d[0]))
            if i <= 9 and name not in {'OBS Virtual Camera', 'Yüz Atölyesi Kamera'}]


def resolve_mac_camera(index, device_id=None):
    for camera in mac_cameras():
        if (camera['id'] == device_id if device_id else camera['index'] == index):
            return camera['index']
    raise ValueError('Seçilen giriş kamerası bulunamadı veya uygulamanın sanal çıktısı seçildi. Kameraları yenileyip FaceTime ya da bağlı fiziksel kameranızı seçin.')


def ensure_mac_camera_permission():
    import threading
    import AVFoundation as av
    status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
    if status == av.AVAuthorizationStatusAuthorized:
        return
    if status == av.AVAuthorizationStatusNotDetermined:
        completed = threading.Event()
        granted = []

        def finish(allowed):
            granted.append(bool(allowed))
            completed.set()

        av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(av.AVMediaTypeVideo, finish)
        if not completed.wait(60):
            raise ValueError('Kamera izni bekleniyor. macOS izin penceresini yanıtlayıp canlı görüntüyü yeniden başlatın.')
        if granted and granted[0]:
            return
    raise ValueError('Kamera erişimine izin verilmedi. Sistem Ayarları → Gizlilik ve Güvenlik → Kamera bölümünden Yüz Atölyesi için erişimi açın; ardından yeniden deneyin.')
