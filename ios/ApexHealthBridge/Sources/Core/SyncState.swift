import Foundation

/// A whole anchored page is journaled before upload. Its new anchor becomes visible
/// only after every batch has been acknowledged and the resulting state is saved.
public struct PendingPage: Codable, Equatable, Sendable {
    public let typeIdentifier: String
    public let nextAnchor: Data
    public var batches: [DeltaBatch]
}

public struct SyncState: Codable, Equatable, Sendable {
    public private(set) var nextTypeIndex: Int = 0
    public private(set) var checkpoint: Int
    public private(set) var anchors: [String: Data] = [:]
    public private(set) var pending: PendingPage?
    public let backfillSince: Date
    public private(set) var lastSuccessAt: Date?

    public init(checkpoint: Int, backfillSince: Date) {
        self.checkpoint = checkpoint; self.backfillSince = backfillSince
    }

    public mutating func selectType(index: Int, totalTypes: Int) throws {
        guard totalTypes > 0, (0..<totalTypes).contains(index), pending == nil else { throw BridgeError.pendingUpload }
        nextTypeIndex = index
    }

    public mutating func advanceType(totalTypes: Int) throws {
        guard totalTypes > 0, pending == nil else { throw BridgeError.pendingUpload }
        nextTypeIndex = (nextTypeIndex + 1) % totalTypes
    }

    public mutating func stage(typeIdentifier: String, nextAnchor: Data,
                               additions: [HealthSample], deletions: [UUID]) throws {
        guard pending == nil else { throw BridgeError.pendingUpload }
        let removed = Set(deletions)
        // A deletion wins if HealthKit returns a sample and its deletion in one page.
        let samples = additions.filter { !removed.contains($0.uuid) }
        let uniqueDeleted = Array(Set(deletions)).sorted { $0.uuidString < $1.uuidString }
        var batches: [DeltaBatch] = []
        var sampleOffset = 0; var deletionOffset = 0
        repeat {
            // 100 samples keeps worst-case 8KB metadata comfortably below 2MB.
            let sampleEnd = min(sampleOffset + 100, samples.count)
            let deletionEnd = min(deletionOffset + 500 - (sampleEnd - sampleOffset), uniqueDeleted.count)
            batches.append(try DeltaBatch(expectedCheckpoint: checkpoint + batches.count,
                additions: Array(samples[sampleOffset..<sampleEnd]),
                deletions: Array(uniqueDeleted[deletionOffset..<deletionEnd])))
            sampleOffset = sampleEnd; deletionOffset = deletionEnd
        } while sampleOffset < samples.count || deletionOffset < uniqueDeleted.count
        pending = PendingPage(typeIdentifier: typeIdentifier, nextAnchor: nextAnchor, batches: batches)
    }

    public mutating func acknowledge(batchID: UUID, acknowledgement: DeltaAcknowledgement, at date: Date) throws {
        guard var page = pending, let batch = page.batches.first,
              batch.batchID == batchID, batch.expectedCheckpoint == checkpoint,
              acknowledgement.checkpoint == checkpoint + 1,
              acknowledgement.accepted == batch.additions.count,
              acknowledgement.deleted == batch.deletions.count else { throw BridgeError.invalidCheckpoint }
        checkpoint = acknowledgement.checkpoint
        page.batches.removeFirst()
        if page.batches.isEmpty {
            anchors[page.typeIdentifier] = page.nextAnchor
            pending = nil
        } else { pending = page }
        lastSuccessAt = date
    }
}
