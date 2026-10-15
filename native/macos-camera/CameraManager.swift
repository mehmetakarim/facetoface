import AppKit
import SystemExtensions

final class Manager: NSObject, NSApplicationDelegate, OSSystemExtensionRequestDelegate {
    private var window: NSWindow!
    private let status = NSTextField(wrappingLabelWithString: "Sanal kamerayı bir kez etkinleştirin. Sonra görüntülü görüşme uygulamasında Yüz Atölyesi Kamera’yı seçin.")
    private var pending: OSSystemExtensionRequest?
    private var buttons: [NSButton] = []
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 540, height: 250),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Yüz Atölyesi Kamera"
        let title = NSTextField(labelWithString: "OBS olmadan sanal kamera")
        title.font = .boldSystemFont(ofSize: 22)
        let install = NSButton(title: "Kamerayı etkinleştir", target: self, action: #selector(activate))
        let remove = NSButton(title: "Kamerayı kaldır", target: self, action: #selector(deactivate))
        buttons = [install, remove]
        let actions = NSStackView(views: buttons); actions.orientation = .horizontal
        let stack = NSStackView(views: [title, status, actions]); stack.orientation = .vertical
        stack.alignment = .leading; stack.spacing = 22; stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 28)
        ])
        if Bundle.main.object(forInfoDictionaryKey: "YuzSigned") as? Bool != true {
            status.stringValue = "Bu geliştirme paketi imzasızdır. Kamera uzantısının etkinleştirilmesi için Apple geliştirici imzası ve uygun sağlama profili gerekir."
            buttons.forEach { $0.isEnabled = false }
        }
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    @objc private func activate() { submit(install: true) }
    @objc private func deactivate() { submit(install: false) }
    private func submit(install: Bool) {
        guard pending == nil else { return }
        guard Bundle.main.bundleURL.path.hasPrefix("/Applications/") else {
            status.stringValue = "Önce bu kamera uygulamasını Uygulamalar klasörüne taşıyıp oradan açın."
            return
        }
        let id = "com.yuzatolyesi.camera.extension"
        let request = install
            ? OSSystemExtensionRequest.activationRequest(forExtensionWithIdentifier: id, queue: .main)
            : OSSystemExtensionRequest.deactivationRequest(forExtensionWithIdentifier: id, queue: .main)
        request.delegate = self; pending = request; buttons.forEach { $0.isEnabled = false }
        status.stringValue = "macOS isteği işliyor…"
        OSSystemExtensionManager.shared.submitRequest(request)
    }
    func requestNeedsUserApproval(_ request: OSSystemExtensionRequest) {
        status.stringValue = "macOS onayı gerekiyor. Sistem Ayarları’ndaki Yüz Atölyesi Kamera uzantısına izin verin."
    }
    func request(_ request: OSSystemExtensionRequest, actionForReplacingExtension existing: OSSystemExtensionProperties,
                 withExtension ext: OSSystemExtensionProperties) -> OSSystemExtensionRequest.ReplacementAction { .replace }
    func request(_ request: OSSystemExtensionRequest, didFinishWithResult result: OSSystemExtensionRequest.Result) {
        status.stringValue = result == .willCompleteAfterReboot
            ? "İşlem yeniden başlatmadan sonra tamamlanacak."
            : "İstek tamamlandı. Yüz Atölyesi’nde kameraları yenileyerek durumu kontrol edin."
        pending = nil; buttons.forEach { $0.isEnabled = true }
    }
    func request(_ request: OSSystemExtensionRequest, didFailWithError error: Error) {
        status.stringValue = "Kamera kurulumu tamamlanamadı: \(error.localizedDescription)"
        pending = nil; buttons.forEach { $0.isEnabled = true }
    }
}
let app = NSApplication.shared
let delegate = Manager()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
