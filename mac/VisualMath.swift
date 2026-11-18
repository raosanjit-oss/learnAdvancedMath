import SwiftUI
import AVKit
import UniformTypeIdentifiers

struct LessonPlayer: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .inline
        view.player = player
        return view
    }

    func updateNSView(_ view: AVPlayerView, context: Context) {
        if view.player !== player { view.player = player }
    }
}

@MainActor
final class Library: ObservableObject {
    @Published var document: URL?
    @Published var working = false
    @Published var message = ""
    @Published var video: URL?
    @Published var player: AVPlayer?
    let movies = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Movies/Visual Math")

    func select(_ url: URL) {
        guard !working else { return }
        document = url
        video = nil
        player = nil
        message = ""
    }

    func render() {
        guard let document, !working, let resources = Bundle.main.resourceURL else { return }
        working = true
        message = "Preparing your video. The first lesson also sets up Manim on this Mac."
        Task {
            do {
                let file = try await Task.detached { () throws -> URL in
                    let process = Process()
                    let output = Pipe()
                    process.executableURL = URL(fileURLWithPath: "/bin/sh")
                    process.arguments = [resources.appendingPathComponent("run.sh").path, document.path]
                    process.standardOutput = output
                    process.standardError = output
                    try process.run()
                    let data = output.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    let lines = String(decoding: data, as: UTF8.self).split(separator: "\n")
                    guard process.terminationStatus == 0, let path = lines.last,
                          FileManager.default.fileExists(atPath: String(path)) else {
                        throw NSError(domain: "VisualMath", code: 1, userInfo: [
                            NSLocalizedDescriptionKey: lines.suffix(4).joined(separator: "\n")
                        ])
                    }
                    return URL(fileURLWithPath: String(path))
                }.value
                video = file
                player = AVPlayer(url: file)
                message = "Saved in Movies/Visual Math."
            } catch {
                message = "Couldn’t finish the video. \(error.localizedDescription)"
            }
            working = false
        }
    }
}

@main
struct VisualMath: App {
    @StateObject private var library = Library()
    @State private var creating = false
    var body: some Scene {
        Window("Visual Math", id: "lessons") {
            VStack(alignment: .leading, spacing: 16) {
                Text("Visual Math").font(.largeTitle)
                Text("Choose a math or physics question. Once your lesson is written, this Mac will turn it into a video.")
                HStack {
                    Button("Create a lesson") { creating = true }
                    Button("Open lesson file…") {
                        let panel = NSOpenPanel()
                        panel.allowedContentTypes = [UTType(filenameExtension: "visualmath") ?? .data]
                        if panel.runModal() == .OK, let url = panel.url { library.select(url) }
                    }
                    Button("Try a sample") {
                        if let url = Bundle.main.url(forResource: "Slope", withExtension: "visualmath") { library.select(url) }
                    }
                }.disabled(library.working)
                if let document = library.document {
                    Divider()
                    HStack {
                        Text(document.deletingPathExtension().lastPathComponent)
                        Button("Render video") { library.render() }.disabled(library.working)
                        if library.working { ProgressView().controlSize(.small) }
                    }
                }
                Text(library.message).textSelection(.enabled)
                if let player = library.player {
                    HStack {
                        Button("Play") { player.play() }
                        Button("Pause") { player.pause() }
                        Button("Replay") { player.seek(to: .zero); player.play() }
                    }
                    LessonPlayer(player: player).frame(minHeight: 240)
                }
                if let url = library.video {
                    Button("Show video in Finder") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
                } else if FileManager.default.fileExists(atPath: library.movies.path) {
                    Button("Open saved videos") { NSWorkspace.shared.open(library.movies) }
                }
                Spacer(minLength: 0)
            }.padding(28).frame(minWidth: 560, minHeight: library.player == nil ? 340 : 630)
             .onOpenURL { url in if url.isFileURL { library.select(url) } }
             .sheet(isPresented: $creating) {
                VStack {
                    HStack {
                        Link("Open in browser", destination: LessonForm.url)
                        Spacer()
                        Button("Close") { creating = false }
                    }.padding()
                    LessonForm(received: { url in library.select(url); creating = false },
                               failed: { reason in library.message = reason; creating = false })
                }.frame(minWidth: 700, minHeight: 520)
             }
        }
    }
}
