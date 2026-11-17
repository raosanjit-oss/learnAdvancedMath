import SwiftUI
import WebKit

/// Use the existing signed-in generation flow, including its topic suggestions.
/// Downloaded documents are only rendered after the student clicks Render.
struct LessonForm: NSViewRepresentable {
    static let url = URL(string: "https://learnadvancedmath.streamlit.app/?render=mac")!
    let received: (URL) -> Void
    let failed: (String) -> Void

    func makeCoordinator() -> Downloads { Downloads(parent: self) }
    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView()
        web.navigationDelegate = context.coordinator
        web.load(URLRequest(url: Self.url))
        return web
    }
    func updateNSView(_ web: WKWebView, context: Context) {}

    class Downloads: NSObject, WKNavigationDelegate, WKDownloadDelegate {
        let parent: LessonForm
        var files: [ObjectIdentifier: URL] = [:]
        init(parent: LessonForm) { self.parent = parent }

        func webView(_ web: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            decisionHandler(action.shouldPerformDownload ? .download : .allow)
        }
        func webView(_ web: WKWebView, decidePolicyFor response: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            decisionHandler(response.response.suggestedFilename?.hasSuffix(".visualmath") == true ||
                            response.response.mimeType == "application/octet-stream" ? .download : .allow)
        }
        func webView(_ web: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }
        func webView(_ web: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }
        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                      suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            guard suggestedFilename.lowercased().hasSuffix(".visualmath") else { completionHandler(nil); return }
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".visualmath")
            files[ObjectIdentifier(download)] = url
            completionHandler(url)
        }
        func downloadDidFinish(_ download: WKDownload) {
            if let url = files.removeValue(forKey: ObjectIdentifier(download)) { parent.received(url) }
        }
        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            files.removeValue(forKey: ObjectIdentifier(download))
            parent.failed(error.localizedDescription)
        }
    }
}
