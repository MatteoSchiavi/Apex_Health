import Foundation
import Security

struct PairedDevice: Codable, Sendable {
    let server: ServerConfiguration
    let deviceID: Int
    let token: String
    let localSessionID: UUID
}

enum DeviceKeychain {
    private static let service = "ApexHealthBridge.healthkit-device"
    private static let account = "paired-device"
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service, kSecAttrAccount as String: account]
    }
    static func save(_ device: PairedDevice) throws {
        let data = try JSONEncoder().encode(device)
        let attributes: [String: Any] = [kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var insertion = query
            attributes.forEach { insertion[$0.key] = $0.value }
            guard SecItemAdd(insertion as CFDictionary, nil) == errSecSuccess else { throw BridgeError.storage }
        } else if status != errSecSuccess { throw BridgeError.storage }
    }
    static func load() throws -> PairedDevice? {
        var lookup = query
        lookup[kSecReturnData as String] = true
        lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(lookup as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw BridgeError.storage }
        do {
            let device = try JSONDecoder().decode(PairedDevice.self, from: data)
            _ = try ServerConfiguration(device.server.baseURL.absoluteString)
            return device
        } catch { throw BridgeError.storage }
    }
    static func delete() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw BridgeError.storage }
    }
}

struct ProtectedStateStore: Sendable {
    let url: URL
    init(sessionID: UUID) throws {
        let directory = try FileManager.default.url(for: .applicationSupportDirectory,
            in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("HealthKitSync", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var excludedDirectory = directory
        var resourceValues = URLResourceValues(); resourceValues.isExcludedFromBackup = true
        try excludedDirectory.setResourceValues(resourceValues)
        url = directory.appendingPathComponent(sessionID.uuidString).appendingPathExtension("json")
    }
    func load() throws -> SyncState {
        guard FileManager.default.fileExists(atPath: url.path) else { throw BridgeError.storage }
        // Never silently reset anchors/checkpoint when the journal is missing/corrupt.
        do { return try JSONDecoder().decode(SyncState.self, from: Data(contentsOf: url)) }
        catch { throw BridgeError.storage }
    }
    func save(_ state: SyncState) throws {
        try JSONEncoder().encode(state).write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        var excludedURL = url
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try excludedURL.setResourceValues(values)
    }
    func delete() throws {
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
}
