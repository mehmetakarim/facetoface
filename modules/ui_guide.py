"""Rehber / bilgi penceresi: özellikler, iş akışı ve Mac ipuçları."""

import webbrowser

import customtkinter as ctk

import modules.metadata
import modules.globals
from modules.gettext import tr

GUIDE_TEXT_EN = """
DEEP-LIVE-CAM — WHAT YOU CAN DO
-------------------------------
• Image or video: pick a source face image, pick a target image or video, choose output, then Start. The result is saved next to your target (see project docs).
• Live webcam: pick a source face, choose the camera, tap Live. First load can take 10–30 seconds. For Zoom/Meet/OBS, capture this window or use a virtual camera workflow as described in the community.
• Many faces: same source applied to every detected face (groups, memes).
• Map faces: advanced mode — assign different source faces to different people (opens a mapper UI before processing).
• Mouth mask: keeps your real mouth region for more natural speech while swapping the rest of the face.
• Enhancers (GFPGAN / GPEN): optional quality boost; they need extra ONNX models in the models folder and add heavy load — on Apple Silicon, prefer leaving them off for smoother live preview unless you need maximum quality.

APPLE SILICON (M1 / M2 / M3) TIPS
---------------------------------
• Run with CoreML when available (e.g. python run.py --execution-provider coreml). Face detection may still use CPU for stability depending on your ONNX build.
• Grant Camera access to Terminal (or your terminal app) in System Settings → Privacy & Security → Camera.
• If live preview stutters: turn off Face Enhancer / GPEN, lower preview load, close other camera apps.

ETHICAL & LEGAL USE
-------------------
This tool is intended for creative and legitimate uses (e.g. character work, content with consent). If you use a real person's likeness, get their consent and label outputs clearly as synthetic/deepfake when sharing. Do not use it to deceive, harass, or bypass identity checks. The upstream project may add safeguards or watermarks as required by law.

MORE HELP
---------
Full install notes, GPU options, and disclaimers:
https://github.com/hacksider/Deep-Live-Cam

Official site:
https://deeplivecam.net
"""

GUIDE_TEXT = """
DEEP-LIVE-CAM — NELER YAPABİLİRSİNİZ
------------------------------------
• Görüntü veya video: kaynak yüz fotoğrafını, hedef görüntü veya videoyu seçin, çıktıyı belirleyin, ardından Başlat. Sonuç hedefin yanına kaydedilir (ayrıntılar proje belgelerinde).
• Canlı web kamerası: kaynak yüzü seçin, kamerayı seçin, Canlı’ya basın. İlk yükleme 10–30 saniye sürebilir. Zoom/Meet/OBS için bu pencereyi yakalayın veya toplulukta anlatıldığı gibi sanal kamera akışı kullanın.
• Çoklu yüz: aynı kaynağı karedeki her tespit edilen yüze uygular (gruplar, eğlence içerikleri).
• Yüzleri eşle: gelişmiş mod — farklı kişilere farklı kaynak yüzleri atayın (işlemden önce eşleyici arayüzü açılır).
• Ağız maskesi: konuşmanın doğal görünmesi için gerçek ağız bölgenizi korur, yüzün geri kalanını değiştirir.
• İyileştiriciler (GFPGAN / GPEN): isteğe bağlı kalite artışı; models klasöründe ek ONNX dosyaları gerekir ve yükü artırır — Apple Silicon’da akıcı canlı önizleme için çoğu zaman kapalı bıranın, en yüksek kalite gerekiyorsa açın.

APPLE SILICON (M1 / M2 / M3) İPUÇLARI
--------------------------------------
• Mümkünse CoreML ile çalıştırın (ör. python run.py --execution-provider coreml). ONNX sürümünüze bağlı olarak yüz tespiti kararlılık için CPU’da kalabilir.
• Sistem Ayarları → Gizlilik ve Güvenlik → Kamera’dan Terminal’e (veya kullandığınız terminal uygulamasına) erişim verin.
• Canlı önizleme takılıyorsa: Yüz iyileştirici / GPEN’i kapatın, önizleme yükünü düşürün, kamerayı kullanan diğer uygulamaları kapatın.

ETİK VE YASAL KULLANIM
----------------------
Bu araç yaratıcı ve meşru kullanımlar (ör. karakter çalışması, rızalı içerik) içindir. Gerçek bir kişinin benzerliğini kullanıyorsanız rızasını alın ve paylaşımda sentetik / deepfake olduğunu açıkça belirtin. Aldatmak, taciz etmek veya kimlik kontrollerini aşmak için kullanmayın. Üst akış proje yasal gerekliliklere göre önlemler veya filigran ekleyebilir.

DAHA FAZLA YARDIM
-----------------
Kurulum, GPU seçenekleri ve sorumluluk reddi:
https://github.com/hacksider/Deep-Live-Cam

Resmi site:
https://deeplivecam.net
"""


def open_guide_window(parent: ctk.CTk) -> None:
    win = ctk.CTkToplevel(parent)
    win.title(f"{modules.metadata.name} — {tr('Guide & tips')}")
    win.geometry("700x620")
    win.transient(parent)
    win.focus()

    box = ctk.CTkTextbox(win, font=ctk.CTkFont(size=13), wrap="word")
    box.pack(fill="both", expand=True, padx=12, pady=(12, 8))
    body = (
        GUIDE_TEXT_EN.strip()
        if modules.globals.lang == "en"
        else GUIDE_TEXT.strip()
    )
    box.insert("1.0", body)
    box.configure(state="disabled")

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", pady=(0, 12))
    ctk.CTkButton(
        row,
        text=tr("Open GitHub repository"),
        cursor="hand2",
        command=lambda: webbrowser.open("https://github.com/hacksider/Deep-Live-Cam"),
    ).pack(side="left", padx=12)
    ctk.CTkButton(
        row,
        text=tr("Close"),
        cursor="hand2",
        width=100,
        command=win.destroy,
    ).pack(side="right", padx=12)
