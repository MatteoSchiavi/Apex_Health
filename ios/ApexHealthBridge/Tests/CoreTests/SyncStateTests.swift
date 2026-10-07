import Foundation
import XCTest
@testable import ApexHealthBridgeCore

final class SyncStateTests: XCTestCase {
    func testBackgroundScanPositionPersistsAcrossBudgets() throws {
        var state = SyncState(checkpoint: 0, backfillSince: Date())
        try state.advanceType(totalTypes: 3)
        XCTAssertEqual(state.nextTypeIndex, 1)
        let restored = try JSONDecoder().decode(SyncState.self, from: JSONEncoder().encode(state))
        XCTAssertEqual(restored.nextTypeIndex, 1)
        try state.advanceType(totalTypes: 3)
        try state.advanceType(totalTypes: 3)
        XCTAssertEqual(state.nextTypeIndex, 0)
        try state.selectType(index: 2, totalTypes: 3)
        XCTAssertEqual(state.nextTypeIndex, 2)
        XCTAssertThrowsError(try state.selectType(index: 3, totalTypes: 3))
        try state.stage(typeIdentifier: "sleep", nextAnchor: Data([1]), additions: [], deletions: [])
        XCTAssertThrowsError(try state.advanceType(totalTypes: 3))
    }

    func testCrashAndRetryPreserveBatchUUIDUntilAcknowledgement() throws {
        var state = SyncState(checkpoint: 7, backfillSince: Date(timeIntervalSince1970: 0))
        let uuid = UUID()
        try state.stage(typeIdentifier: "sleep", nextAnchor: Data([1, 2]), additions: [], deletions: [uuid])
        let batch = try XCTUnwrap(state.pending?.batches.first)
        let restored = try JSONDecoder().decode(SyncState.self, from: JSONEncoder().encode(state))
        XCTAssertEqual(restored.pending?.batches.first, batch)
        XCTAssertNil(restored.anchors["sleep"])
        XCTAssertEqual(restored.checkpoint, 7)
        XCTAssertThrowsError(try state.stage(typeIdentifier: "steps", nextAnchor: Data([3]), additions: [], deletions: []))
        try state.acknowledge(batchID: batch.batchID,
            acknowledgement: DeltaAcknowledgement(checkpoint: 8, accepted: 0, deleted: 1), at: Date())
        XCTAssertEqual(state.anchors["sleep"], Data([1, 2]))
        XCTAssertEqual(state.checkpoint, 8)
        XCTAssertNil(state.pending)
    }
    func testWrongAcknowledgementLeavesStateUnchanged() throws {
        var state = SyncState(checkpoint: 0, backfillSince: Date())
        try state.stage(typeIdentifier: "HRV", nextAnchor: Data([8]), additions: [], deletions: [])
        let before = state
        let batch = try XCTUnwrap(state.pending?.batches.first)
        XCTAssertThrowsError(try state.acknowledge(batchID: UUID(),
            acknowledgement: DeltaAcknowledgement(checkpoint: 1, accepted: 0, deleted: 0), at: Date()))
        XCTAssertEqual(state, before)
        XCTAssertThrowsError(try state.acknowledge(batchID: batch.batchID,
            acknowledgement: DeltaAcknowledgement(checkpoint: 2, accepted: 0, deleted: 0), at: Date()))
        XCTAssertEqual(state, before)
    }
    func testMultiBatchPageCommitsAnchorOnlyAfterLastAck() throws {
        var state = SyncState(checkpoint: 5, backfillSince: Date())
        try state.stage(typeIdentifier: "heart_rate", nextAnchor: Data([9]), additions: [], deletions: (0..<1001).map { _ in UUID() })
        XCTAssertEqual(state.pending?.batches.map(\.expectedCheckpoint), [5, 6, 7])
        while let batch = state.pending?.batches.first {
            XCTAssertNil(state.anchors["heart_rate"])
            XCTAssertLessThanOrEqual(batch.additions.count + batch.deletions.count, 500)
            try state.acknowledge(batchID: batch.batchID,
                acknowledgement: DeltaAcknowledgement(checkpoint: state.checkpoint + 1, accepted: 0, deleted: batch.deletions.count), at: Date())
        }
        XCTAssertEqual(state.anchors["heart_rate"], Data([9]))
        XCTAssertEqual(state.checkpoint, 8)
    }
    func testEmptyPageStillRequiresServerAcknowledgement() throws {
        var state = SyncState(checkpoint: 0, backfillSince: Date())
        try state.stage(typeIdentifier: "workouts", nextAnchor: Data([9]), additions: [], deletions: [])
        XCTAssertEqual(state.pending?.batches.count, 1)
        XCTAssertNil(state.anchors["workouts"])
        let batch = try XCTUnwrap(state.pending?.batches.first)
        try state.acknowledge(batchID: batch.batchID,
            acknowledgement: DeltaAcknowledgement(checkpoint: 1, accepted: 0, deleted: 0), at: Date())
        XCTAssertEqual(state.anchors["workouts"], Data([9]))
    }
    func testDeletionWinsAndUnknownUUIDIsPreserved() throws {
        var state = SyncState(checkpoint: 0, backfillSince: Date())
        let s = HealthSample(uuid: UUID(), type: "HKQuantityTypeIdentifierHeartRate", startAt: Date(), endAt: Date(),
            value: 80, unit: "count/min", sourceBundle: "source", sourceName: "Watch", device: nil, metadata: [:], workoutActivityType: nil)
        let unknown = UUID()
        try state.stage(typeIdentifier: s.type, nextAnchor: Data([0]), additions: [s], deletions: [s.uuid, unknown, unknown])
        XCTAssertTrue(try XCTUnwrap(state.pending?.batches.first).additions.isEmpty)
        XCTAssertEqual(Set(try XCTUnwrap(state.pending?.batches.first).deletions), Set([s.uuid, unknown]))
    }
}
