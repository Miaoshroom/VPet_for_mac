import Dispatch
import Foundation
import Darwin

typealias MRBoolBlock = @convention(block) (Bool) -> Void
typealias MRPlayingFunction = @convention(c) (DispatchQueue, @escaping MRBoolBlock) -> Void

let frameworkPath = "/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote"

guard let handle = dlopen(frameworkPath, RTLD_NOW) else {
    fputs("dlopen MediaRemote failed\n", stderr)
    exit(1)
}

guard let symbol = dlsym(handle, "MRMediaRemoteGetNowPlayingApplicationIsPlaying") else {
    fputs("dlsym MRMediaRemoteGetNowPlayingApplicationIsPlaying failed\n", stderr)
    exit(1)
}

func readSystemVolume() -> Double {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    process.arguments = ["-e", "output volume of (get volume settings)"]

    let stdout = Pipe()
    process.standardOutput = stdout
    process.standardError = Pipe()

    do {
        try process.run()
    } catch {
        return 0.0
    }

    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
        return 0.0
    }

    let data = stdout.fileHandleForReading.readDataToEndOfFile()
    guard let text = String(data: data, encoding: .utf8) else {
        return 0.0
    }
    guard let value = Double(text.trimmingCharacters(in: .whitespacesAndNewlines)) else {
        return 0.0
    }
    return max(0.0, min(1.0, value / 100.0))
}

let getNowPlayingIsPlaying = unsafeBitCast(symbol, to: MRPlayingFunction.self)
let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.main)
timer.schedule(deadline: .now(), repeating: 1.0)
timer.setEventHandler {
    getNowPlayingIsPlaying(DispatchQueue.main) { isPlaying in
        let level = isPlaying ? readSystemVolume() : 0.0
        print(String(format: "%.2f", level))
        fflush(stdout)
    }
}
timer.resume()
dispatchMain()
