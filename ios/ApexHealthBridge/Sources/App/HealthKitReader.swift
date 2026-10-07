import Foundation
import HealthKit
import CoreFoundation

struct HealthTypeDescriptor {
    let type: HKSampleType
    let unit: HKUnit?
    let wireUnit: String?
}
struct HealthPage {
    let additions: [HealthSample]
    let deletions: [UUID]
    let nextAnchor: Data
    let isFull: Bool
}

final class HealthKitReader: @unchecked Sendable {
    private let store = HKHealthStore()
    private var observers: [HKObserverQuery] = []
    static let pageLimit = 100

    var types: [HealthTypeDescriptor] {
        var result: [HealthTypeDescriptor] = []
        func quantity(_ identifier: HKQuantityTypeIdentifier, _ unit: HKUnit, _ wireUnit: String) {
            if let type = HKObjectType.quantityType(forIdentifier: identifier) {
                result.append(HealthTypeDescriptor(type: type, unit: unit, wireUnit: wireUnit))
            }
        }
        quantity(.heartRate, HKUnit.count().unitDivided(by: .minute()), "count/min")
        quantity(.restingHeartRate, HKUnit.count().unitDivided(by: .minute()), "count/min")
        quantity(.heartRateVariabilitySDNN, .secondUnit(with: .milli), "ms")
        quantity(.stepCount, .count(), "count")
        quantity(.activeEnergyBurned, .kilocalorie(), "kcal")
        quantity(.bodyMass, .gramUnit(with: .kilo), "kg")
        quantity(.bodyFatPercentage, .percent(), "%")
        quantity(.respiratoryRate, HKUnit.count().unitDivided(by: .minute()), "count/min")
        quantity(.oxygenSaturation, .percent(), "%")
        quantity(.vo2Max, HKUnit.literUnit(with: .milli).unitDivided(by: .gramUnit(with: .kilo)).unitDivided(by: .minute()), "mL/kg/min")
        quantity(.bodyTemperature, .degreeCelsius(), "degC")
        quantity(.basalBodyTemperature, .degreeCelsius(), "degC")
        if #available(iOS 16.0, *) {
            quantity(.appleSleepingWristTemperature, .degreeCelsius(), "degC")
        }
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            result.append(HealthTypeDescriptor(type: sleep, unit: nil, wireUnit: nil))
        }
        result.append(HealthTypeDescriptor(type: HKObjectType.workoutType(), unit: nil, wireUnit: nil))
        return result
    }

    func authorize() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { throw BridgeError.healthUnavailable }
        // No write permission, routes, clinical records, or browser credentials.
        try await store.requestAuthorization(toShare: [], read: Set<HKObjectType>(types.map { $0.type }))
    }
    func installObservers(onChange: @escaping @Sendable (String, @escaping () -> Void) -> Void,
                          onError: @escaping @Sendable () -> Void) {
        stopObservers()
        for descriptor in types {
            let query = HKObserverQuery(sampleType: descriptor.type, predicate: nil) { _, completion, error in
                guard error == nil else { completion(); onError(); return }
                onChange(descriptor.type.identifier, completion)
            }
            observers.append(query); store.execute(query)
            store.enableBackgroundDelivery(for: descriptor.type, frequency: .hourly) { success, error in
                if !success || error != nil { onError() }
            }
        }
    }
    func stopObservers() {
        observers.forEach { store.stop($0) }; observers.removeAll()
    }
    func disableDelivery() async {
        stopObservers()
        try? await store.disableAllBackgroundDelivery()
    }

    func page(for descriptor: HealthTypeDescriptor, anchorData: Data?, since: Date) async throws -> HealthPage {
        let anchor: HKQueryAnchor?
        if let anchorData {
            guard let decoded = try NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: anchorData)
            else { throw BridgeError.storage }
            anchor = decoded
        } else { anchor = nil }
        // This lower bound stays fixed for the entire pairing. Overlapping sleep/workouts
        // are included. A moving predicate would invalidate anchor semantics.
        let predicate = HKQuery.predicateForSamples(withStart: since, end: nil, options: [])
        return try await withCheckedThrowingContinuation { continuation in
            let query = HKAnchoredObjectQuery(type: descriptor.type, predicate: predicate,
                anchor: anchor, limit: Self.pageLimit) { _, samples, deleted, newAnchor, error in
                do {
                    if let error { throw error }
                    guard let newAnchor else { throw BridgeError.invalidResponse }
                    let samples = samples ?? []; let deleted = deleted ?? []
                    let next = try NSKeyedArchiver.archivedData(withRootObject: newAnchor, requiringSecureCoding: true)
                    let payload = try samples.map { try self.serialize($0, descriptor: descriptor) }
                    continuation.resume(returning: HealthPage(additions: payload, deletions: deleted.map(\.uuid),
                        nextAnchor: next, isFull: samples.count + deleted.count >= Self.pageLimit))
                } catch { continuation.resume(throwing: error) }
            }
            store.execute(query)
        }
    }

    private func serialize(_ sample: HKSample, descriptor: HealthTypeDescriptor) throws -> HealthSample {
        var value: Double?
        var activityType: Int?
        if let quantity = sample as? HKQuantitySample, let unit = descriptor.unit {
            value = quantity.quantity.doubleValue(for: unit)
            if descriptor.wireUnit == "%" { value = value.map { $0 * 100 } }
        } else if let category = sample as? HKCategorySample { value = Double(category.value) }
        else if let workout = sample as? HKWorkout { activityType = Int(workout.workoutActivityType.rawValue) }
        let source = sample.sourceRevision
        var metadata: [String: JSONValue] = [:]
        // Keep small, supported scalar metadata. Arbitrary strings may contain personal
        // notes; preserve useful provenance without collecting unbounded free text.
        let allowed = [HKMetadataKeyWasUserEntered, HKMetadataKeySyncIdentifier,
                       HKMetadataKeySyncVersion, HKMetadataKeyTimeZone,
                       HKMetadataKeyHeartRateMotionContext, HKMetadataKeyVO2MaxTestType]
        for key in allowed {
            guard let raw = sample.metadata?[key] else { continue }
            if let string = raw as? String { metadata[key] = .string(String(string.prefix(500))) }
            else if let number = raw as? NSNumber {
                if CFGetTypeID(number) == CFBooleanGetTypeID() { metadata[key] = .bool(number.boolValue) }
                else if number.doubleValue.isFinite { metadata[key] = .number(number.doubleValue) }
            }
        }
        let os = source.operatingSystemVersion
        var revision: [String: JSONValue] = ["operating_system": .string("\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)")]
        if let version = source.version { revision["version"] = .string(String(version.prefix(500))) }
        if let product = source.productType { revision["product_type"] = .string(String(product.prefix(500))) }
        metadata["source_revision"] = .object(revision)
        if let workout = sample as? HKWorkout {
            var summary: [String: JSONValue] = [:]
            if workout.duration.isFinite && workout.duration >= 0 { summary["duration_s"] = .number(workout.duration) }
            if let distance = workout.totalDistance?.doubleValue(for: .meter()), distance.isFinite && distance >= 0 {
                summary["distance_m"] = .number(distance)
            }
            if let energy = workout.totalEnergyBurned?.doubleValue(for: .kilocalorie()), energy.isFinite && energy >= 0 {
                summary["total_energy_kcal"] = .number(energy)
            }
            metadata["workout_summary"] = .object(summary)
        }
        let deviceDescription = sample.device.map { device in
            [device.name, device.manufacturer, device.model, device.hardwareVersion, device.softwareVersion]
                .compactMap { $0 }.joined(separator: " | ")
        }
        let result = HealthSample(uuid: sample.uuid, type: sample.sampleType.identifier,
            startAt: sample.startDate, endAt: sample.endDate, value: value, unit: descriptor.wireUnit,
            sourceBundle: source.source.bundleIdentifier, sourceName: source.source.name,
            device: deviceDescription.map { String($0.prefix(500)) }, metadata: metadata,
            workoutActivityType: activityType)
        try result.validate()
        return result
    }
}
