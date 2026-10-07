import Foundation

public enum BridgeError: Error, Equatable {
    case invalidServer, invalidPayload, invalidCheckpoint, pendingUpload, missingCredentials
    case server(Int), invalidResponse, healthUnavailable, storage
}

public struct ServerConfiguration: Codable, Equatable, Sendable {
    public let baseURL: URL

    public init(_ address: String) throws {
        guard let components = URLComponents(string: address.trimmingCharacters(in: .whitespacesAndNewlines)),
              let url = components.url, let host = components.host?.lowercased(),
              !host.isEmpty, components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              components.port.map({ (1...65535).contains($0) }) ?? true else { throw BridgeError.invalidServer }
        let loopback = ["localhost", "127.0.0.1", "::1", "[::1]"].contains(host)
        guard components.scheme == "https" || (components.scheme == "http" && loopback),
              !components.percentEncodedPath.contains("%"),
              !components.path.split(separator: "/").contains(where: { $0 == "." || $0 == ".." })
        else { throw BridgeError.invalidServer }
        baseURL = url
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(c.decode(URL.self, forKey: .baseURL).absoluteString)
    }
    private enum CodingKeys: String, CodingKey { case baseURL }

    public func endpoint(_ path: String) -> URL {
        baseURL.appendingPathComponent("healthkit").appendingPathComponent(path)
    }
}

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null
    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    func validate(depth: Int = 0) throws {
        guard depth <= 4 else { throw BridgeError.invalidPayload }
        switch self {
        case .string(let v): guard v.count <= 500 else { throw BridgeError.invalidPayload }
        case .number(let v): guard v.isFinite else { throw BridgeError.invalidPayload }
        case .object(let values):
            guard values.count <= 32, values.keys.allSatisfy({ $0.count <= 100 }) else { throw BridgeError.invalidPayload }
            for value in values.values { try value.validate(depth: depth + 1) }
        case .array(let values):
            guard values.count <= 32 else { throw BridgeError.invalidPayload }
            for value in values { try value.validate(depth: depth + 1) }
        case .bool, .null: break
        }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
}

public struct HealthSample: Codable, Equatable, Sendable {
    public let uuid: UUID
    public let type: String
    public let startAt: Date
    public let endAt: Date
    public let value: Double?
    public let unit: String?
    public let sourceBundle: String
    public let sourceName: String
    public let device: String?
    public let metadata: [String: JSONValue]
    public let workoutActivityType: Int?

    public init(uuid: UUID, type: String, startAt: Date, endAt: Date, value: Double?, unit: String?,
                sourceBundle: String, sourceName: String, device: String?, metadata: [String: JSONValue], workoutActivityType: Int?) {
        self.uuid = uuid; self.type = type; self.startAt = startAt; self.endAt = endAt
        self.value = value; self.unit = unit; self.sourceBundle = sourceBundle; self.sourceName = sourceName
        self.device = device; self.metadata = metadata; self.workoutActivityType = workoutActivityType
    }
    enum CodingKeys: String, CodingKey {
        case uuid, type, value, unit, device, metadata
        case startAt = "start_at", endAt = "end_at", sourceBundle = "source_bundle", sourceName = "source_name"
        case workoutActivityType = "workout_activity_type"
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(uuid, forKey: .uuid); try c.encode(type, forKey: .type)
        try c.encode(startAt, forKey: .startAt); try c.encode(endAt, forKey: .endAt)
        try c.encode(value, forKey: .value); try c.encode(unit, forKey: .unit)
        try c.encode(sourceBundle, forKey: .sourceBundle); try c.encode(sourceName, forKey: .sourceName)
        try c.encode(device, forKey: .device); try c.encode(metadata, forKey: .metadata)
        try c.encode(workoutActivityType, forKey: .workoutActivityType)
    }
    public func validate() throws {
        try JSONValue.object(metadata).validate()
        guard endAt >= startAt, value?.isFinite ?? true, !type.isEmpty, !sourceBundle.isEmpty,
              metadata.count <= 32, !sourceName.isEmpty,
              sourceName.unicodeScalars.count <= 256, sourceBundle.unicodeScalars.count <= 256,
              device.map({ $0.count <= 500 }) ?? true,
              try JSONEncoder().encode(metadata).count <= 8192 else { throw BridgeError.invalidPayload }
    }
}

public struct DeltaBatch: Codable, Equatable, Sendable {
    public let batchID: UUID
    public let expectedCheckpoint: Int
    public let additions: [HealthSample]
    public let deletions: [UUID]
    public init(batchID: UUID = UUID(), expectedCheckpoint: Int, additions: [HealthSample], deletions: [UUID]) throws {
        guard expectedCheckpoint >= 0, additions.count + deletions.count <= 500 else { throw BridgeError.invalidPayload }
        for sample in additions { try sample.validate() }
        guard Set(additions.map(\.uuid)).count == additions.count,
              Set(deletions).count == deletions.count,
              Set(additions.map(\.uuid)).isDisjoint(with: Set(deletions)) else { throw BridgeError.invalidPayload }
        self.batchID = batchID; self.expectedCheckpoint = expectedCheckpoint
        self.additions = additions; self.deletions = deletions
        guard try WireJSON.encoder().encode(self).count <= 2 * 1024 * 1024 else { throw BridgeError.invalidPayload }
    }
    enum CodingKeys: String, CodingKey {
        case batchID = "batch_id", expectedCheckpoint = "expected_checkpoint", additions, deletions
    }
}

public struct DeltaAcknowledgement: Codable, Sendable {
    public let checkpoint: Int
    public let accepted: Int
    public let deleted: Int
    public init(checkpoint: Int, accepted: Int, deleted: Int) {
        self.checkpoint = checkpoint; self.accepted = accepted; self.deleted = deleted
    }
}

public enum WireJSON {
    public static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601; encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}
