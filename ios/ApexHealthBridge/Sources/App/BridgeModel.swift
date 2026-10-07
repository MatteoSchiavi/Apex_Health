import Foundation
import SwiftUI

@MainActor
final class BridgeModel: ObservableObject {
    @Published var serverAddress = ""
    @Published var pairingCode = ""
    @Published var deviceName = "My iPhone"
    @Published private(set) var paired = false
    @Published private(set) var busy = false
    @Published private(set) var status = "Pair this iPhone with Apex to start."
    @Published private(set) var checkpoint: Int?
    @Published private(set) var lastSuccessAt: Date?
    @Published private(set) var errorMessage: String?
    private let reader = HealthKitReader()
    private var coordinator: SyncCoordinator?
    private var foregroundTask: Task<Void, Never>?
    private var isActive = true

    init() {
        do {
            if let device = try DeviceKeychain.load() {
                serverAddress = device.server.baseURL.absoluteString
                coordinator = try SyncCoordinator(device: device, reader: reader)
                paired = true
                status = "Paired. Health permissions may be reviewed in Settings."
                installObservers()
            }
        } catch { errorMessage = Self.safeMessage(error) }
    }

    func pair() {
        guard !busy, !paired else { return }
        busy = true; errorMessage = nil
        Task {
            defer { busy = false }
            do {
                let server = try ServerConfiguration(serverAddress)
                let code = pairingCode.trimmingCharacters(in: .whitespacesAndNewlines)
                let name = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard code.count >= 32, code.count <= 128, !name.isEmpty, name.unicodeScalars.count <= 60 else { throw BridgeError.invalidPayload }
                let response = try await BridgeAPI(configuration: server).exchange(code: code, name: name)
                let device = PairedDevice(server: server, deviceID: response.deviceID,
                    token: response.token, localSessionID: UUID())
                let store = try ProtectedStateStore(sessionID: device.localSessionID)
                let since = Calendar(identifier: .gregorian).date(byAdding: .day, value: -90, to: Date())!
                try store.save(SyncState(checkpoint: response.checkpoint, backfillSince: since))
                do { try DeviceKeychain.save(device) }
                catch { try? store.delete(); throw error }
                coordinator = try SyncCoordinator(device: device, reader: reader)
                paired = true; pairingCode = ""; checkpoint = response.checkpoint
                status = "Paired. Authorize read access to begin the 90-day backfill."
            } catch { errorMessage = Self.safeMessage(error) }
        }
    }

    func authorize() {
        guard paired, !busy else { return }
        busy = true; errorMessage = nil
        Task {
            do {
                try await reader.authorize()
                status = "Permission request completed. iOS keeps individual read permissions private."
                installObservers()
                busy = false
                syncNow()
            } catch { busy = false; errorMessage = Self.safeMessage(error) }
        }
    }

    private func installObservers() {
        reader.installObservers(onChange: { [weak self] typeIdentifier, completion in
            Task { @MainActor in
                defer { completion() }
                guard let self, let coordinator = self.coordinator else { return }
                do {
                    let summary = try await coordinator.sync(maxPages: 2, preferredTypeIdentifier: typeIdentifier, waitIfBusy: true)
                    self.apply(summary)
                    if summary.moreAvailable && self.isActive && !self.busy { self.syncNow() }
                } catch { self.errorMessage = Self.safeMessage(error) }
            }
        }, onError: { [weak self] in
            Task { @MainActor in
                self?.errorMessage = "Background delivery is unavailable for some data. Open the app and tap Sync now."
            }
        })
    }

    func becameActive(_ active: Bool) {
        isActive = active
        if active && paired { syncNow() }
        else { foregroundTask?.cancel() }
    }

    func syncNow() {
        guard paired, !busy, let coordinator else { return }
        busy = true; errorMessage = nil; status = "Synchronizing authorized Apple Health data…"
        foregroundTask = Task {
            defer { busy = false; foregroundTask = nil }
            var failures = 0
            while isActive && !Task.isCancelled {
                do {
                    let summary = try await coordinator.sync(maxPages: 20)
                    apply(summary)
                    if summary.busy {
                        try await Task.sleep(nanoseconds: 500_000_000)
                        continue
                    }
                    failures = 0
                    if !summary.moreAvailable { return }
                    status = "Backfill in progress. Keep the app open to continue."
                    await Task.yield()
                } catch is CancellationError { return }
                catch {
                    errorMessage = Self.safeMessage(error)
                    // Connectivity/server failures retain the journal and retry the same UUID.
                    let retryable: Bool
                    if let e = error as? BridgeError {
                        if case .server(let code) = e { retryable = code == 429 || code >= 500 }
                        else { retryable = false }
                    } else { retryable = error is URLError }
                    failures += 1
                    guard retryable, failures <= 3 else { status = "Sync paused. Review troubleshooting, then retry."; return }
                    status = "Waiting to retry the saved upload…"
                    do { try await Task.sleep(nanoseconds: UInt64(5 * (1 << (failures - 1))) * 1_000_000_000) }
                    catch { return }
                }
            }
        }
    }

    private func apply(_ summary: SyncSummary) {
        guard !summary.busy else { return }
        checkpoint = summary.checkpoint; lastSuccessAt = summary.lastSuccessAt
        status = summary.moreAvailable ? "More historical data is queued." : "Sync acknowledged. Only authorized samples are visible to this app."
    }

    func disconnect() {
        guard paired, !busy, let coordinator else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                try await coordinator.stopAndClear()
                self.coordinator = nil; paired = false; checkpoint = nil; lastSuccessAt = nil
                status = "Local pairing removed. Revoke this device in Apex Settings to invalidate its server token."
            } catch { errorMessage = Self.safeMessage(error) }
        }
    }

    static func safeMessage(_ error: Error) -> String {
        guard let error = error as? BridgeError else {
            if error is CancellationError { return "Sync paused." }
            return "The request could not complete. Check connectivity, Health permissions, and device storage, then retry."
        }
        switch error {
        case .invalidServer: return "Use an HTTPS Apex server URL without credentials, query, or fragment. HTTP is allowed only for loopback development."
        case .server(401), .server(403): return "The device token or pairing code is invalid, expired, or revoked. Create a new pairing in Apex Settings."
        case .server(409), .invalidCheckpoint: return "The server checkpoint differs from this device. Do not clear local state during an uncertain upload. Review the device in Apex Settings before pairing again."
        case .server(429): return "The server rate limit was reached. The saved upload will retry."
        case .server: return "Apex could not acknowledge the upload. The exact saved batch will be retried."
        case .healthUnavailable: return "HealthKit is unavailable on this device. Use a supported physical iPhone."
        case .storage: return "Secure credentials or the sync journal could not be loaded. Unlock the device and retry. If state is missing, revoke the device before pairing again."
        case .invalidPayload: return "Check the pairing code and device name. A sample may also exceed the supported payload limits."
        case .missingCredentials: return "Pair this iPhone from Apex Settings."
        case .pendingUpload: return "A saved upload must finish before another page can be sent."
        case .invalidResponse: return "Apex returned an unexpected response. Sync state was preserved."
        }
    }
}
