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

let getNowPlayingIsPlaying = unsafeBitCast(symbol, to: MRPlayingFunction.self)
let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.main)
timer.schedule(deadline: .now(), repeating: 1.0)
timer.setEventHandler {
    getNowPlayingIsPlaying(DispatchQueue.main) { isPlaying in
        print(isPlaying ? "1" : "0")
        fflush(stdout)
    }
}
timer.resume()
dispatchMain()
