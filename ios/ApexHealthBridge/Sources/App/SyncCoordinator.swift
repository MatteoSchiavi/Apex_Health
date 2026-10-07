import Foundation

struct SyncSummary: Sendable {
    let checkpoint: Int
    let lastSuccessAt: Date?
    let moreAvailable: Bool
    let busy: Bool
}

actor SyncCoordinator {
    private let device: PairedDevice
    private let api: BridgeAPI
    private let reader: HealthKitReader
    private let storage: ProtectedStateStore
    private var state: SyncState
    private var syncing = false
    private var stopping = false

    init(device: PairedDevice, reader: HealthKitReader) throws {
        self.device = device; self.reader = reader
        self.api = BridgeAPI(configuration: device.server)
        self.storage = try ProtectedStateStore(sessionID: device.localSessionID)
        self.state = try storage.load()
    }

    func sync(maxPages: Int, preferredTypeIdentifier: String? = nil, waitIfBusy: Bool = false) async throws -> SyncSummary {
        // Observer callbacks wait for the current serialized upload instead of marking
        // their own changed type complete while another type is still being processed.
        while syncing && waitIfBusy && !stopping { try await Task.sleep(nanoseconds: 100_000_000) }
        guard !syncing, !stopping else { return summary(more: false, busy: true) }
        syncing = true
        defer { syncing = false }
        var pages = 0
        // An uncertain HTTP response or interrupted app never regenerates its batch UUID.
        try await drainPending()
        let status = try await api.status(token: device.token)
        guard status.deviceID == device.deviceID, status.checkpoint == state.checkpoint else {
            throw BridgeError.invalidCheckpoint
        }
        let types = reader.types
        if let preferredTypeIdentifier, let index = types.firstIndex(where: { $0.type.identifier == preferredTypeIdentifier }) {
            var selected = state
            try selected.selectType(index: index, totalTypes: types.count)
            try commit(selected)
        }
        var completedTypes = 0
        // Persist the scan position so a two-page background budget cannot forever
        // rescan the first two empty types and starve the remaining permissions.
        while completedTypes < types.count && !stopping {
            try Task.checkCancellation()
            guard pages < maxPages else { return summary(more: true) }
            let descriptor = types[state.nextTypeIndex % types.count]
            let identifier = descriptor.type.identifier
            let page = try await reader.page(for: descriptor, anchorData: state.anchors[identifier], since: state.backfillSince)
            var next = state
            try next.stage(typeIdentifier: identifier, nextAnchor: page.nextAnchor,
                           additions: page.additions, deletions: page.deletions)
            try commit(next)
            try await drainPending()
            pages += 1
            if !page.isFull && state.pending == nil {
                var advanced = state
                try advanced.advanceType(totalTypes: types.count)
                try commit(advanced)
                completedTypes += 1
            }
        }
        return summary(more: false)
    }

    private func drainPending() async throws {
        while let batch = state.pending?.batches.first {
            if stopping { return }
            try Task.checkCancellation()
            let acknowledgement = try await api.upload(batch, token: device.token)
            var next = state
            try next.acknowledge(batchID: batch.batchID, acknowledgement: acknowledgement, at: Date())
            // Save first: if disk write fails, retain the exact original batch for replay.
            try commit(next)
        }
    }
    private func commit(_ next: SyncState) throws {
        try storage.save(next)
        state = next
    }
    private func summary(more: Bool, busy: Bool = false) -> SyncSummary {
        SyncSummary(checkpoint: state.checkpoint, lastSuccessAt: state.lastSuccessAt, moreAvailable: more, busy: busy)
    }
    func stopAndClear() async throws {
        stopping = true
        while syncing { try await Task.sleep(nanoseconds: 100_000_000) }
        await reader.disableDelivery()
        // If Keychain removal fails, restore the journal for a consistent retry.
        do {
            try storage.delete()
            do { try DeviceKeychain.delete() }
            catch { try storage.save(state); throw error }
        } catch {
            stopping = false
            throw error
        }
    }
}
