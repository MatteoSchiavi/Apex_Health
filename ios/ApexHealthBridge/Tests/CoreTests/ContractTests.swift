import Foundation
import XCTest
@testable import ApexHealthBridgeCore

final class ContractTests: XCTestCase {
    func testHTTPSAndLoopbackOnly() throws {
        for url in ["https://apex.example", "https://apex.example/api", "http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"] {
            XCTAssertNoThrow(try ServerConfiguration(url), url)
        }
        for url in ["http://apex.example", "http://192.168.1.5", "http://localhost.evil.test", "https://user:secret@apex.example", "https://apex.example?a=b", "https://apex.example#token", "file:///tmp/apex", "https://apex.example/../api", "https://apex.example/%2e%2e/api"] {
            XCTAssertThrowsError(try ServerConfiguration(url), url)
        }
        XCTAssertEqual(try ServerConfiguration("https://apex.example/api/").endpoint("deltas").absoluteString,
                       "https://apex.example/api/healthkit/deltas")
    }

    func testStoredConfigurationIsValidatedAgain() throws {
        let unsafe = Data("{\"baseURL\":\"http://remote.example\"}".utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(ServerConfiguration.self, from: unsafe))
    }

    func sample(_ uuid: UUID = UUID(), value: Double? = 42) -> HealthSample {
        HealthSample(uuid: uuid, type: "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
            startAt: Date(timeIntervalSince1970: 0), endAt: Date(timeIntervalSince1970: 1), value: value, unit: "ms",
            sourceBundle: "com.apple.health", sourceName: "Apple Watch", device: "Watch", metadata: [:], workoutActivityType: nil)
    }
    func testWireNamesTimestampsAndExplicitNulls() throws {
        let batch = try DeltaBatch(expectedCheckpoint: 3, additions: [sample(value: nil)], deletions: [])
        let data = try WireJSON.encoder().encode(batch)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["expected_checkpoint"] as? Int, 3)
        XCTAssertNotNil(object["batch_id"])
        let samples = try XCTUnwrap(object["additions"] as? [[String: Any]])
        XCTAssertEqual(samples[0]["start_at"] as? String, "1970-01-01T00:00:00Z")
        XCTAssertTrue(samples[0]["value"] is NSNull)
        XCTAssertTrue(samples[0]["workout_activity_type"] is NSNull)
        XCTAssertEqual(samples[0]["type"] as? String, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN")
        XCTAssertEqual(samples[0]["unit"] as? String, "ms")
    }
    func testBoundedBatchAndUUIDUniqueness() throws {
        let same = sample()
        XCTAssertThrowsError(try DeltaBatch(expectedCheckpoint: 0, additions: Array(repeating: same, count: 501), deletions: []))
        XCTAssertThrowsError(try DeltaBatch(expectedCheckpoint: -1, additions: [], deletions: []))
        XCTAssertThrowsError(try DeltaBatch(expectedCheckpoint: 0, additions: [same, same], deletions: []))
        XCTAssertThrowsError(try DeltaBatch(expectedCheckpoint: 0, additions: [same], deletions: [same.uuid]))
        XCTAssertThrowsError(try DeltaBatch(expectedCheckpoint: 0, additions: [sample(value: .nan)], deletions: []))
    }
    func testMetadataBound() {
        XCTAssertThrowsError(try JSONValue.object(["source_revision": .object(["version": .string(String(repeating: "x", count: 501))])]).validate())
        XCTAssertThrowsError(try JSONValue.number(.infinity).validate())
        let s = HealthSample(uuid: UUID(), type: "HKCategoryTypeIdentifierSleepAnalysis", startAt: Date(), endAt: Date(),
            value: 3, unit: nil, sourceBundle: "source", sourceName: "Watch", device: nil,
            metadata: ["note": .string(String(repeating: "x", count: 9000))], workoutActivityType: nil)
        XCTAssertThrowsError(try s.validate())
    }
}
