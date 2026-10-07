import Foundation

struct PairingResponse: Decodable {
    let token: String
    let deviceID: Int
    let checkpoint: Int
    enum CodingKeys: String, CodingKey { case token, deviceID = "device_id", checkpoint }
}
struct DeviceStatus: Decodable {
    let deviceID: Int
    let checkpoint: Int
    let lastSuccessAt: String?
    enum CodingKeys: String, CodingKey { case deviceID = "device_id", checkpoint, lastSuccessAt = "last_success_at" }
}

/// Redirects are refused so neither a pairing code nor a token can leave the configured origin.
final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

final class BridgeAPI: @unchecked Sendable {
    private let configuration: ServerConfiguration
    private let delegate = NoRedirectDelegate()
    private let session: URLSession

    init(configuration: ServerConfiguration) {
        self.configuration = configuration
        let settings = URLSessionConfiguration.ephemeral
        settings.httpCookieStorage = nil
        settings.httpShouldSetCookies = false
        settings.urlCredentialStorage = nil
        settings.urlCache = nil
        settings.requestCachePolicy = .reloadIgnoringLocalCacheData
        settings.timeoutIntervalForRequest = 25
        settings.timeoutIntervalForResource = 40
        settings.waitsForConnectivity = false
        session = URLSession(configuration: settings, delegate: delegate, delegateQueue: nil)
    }

    func exchange(code: String, name: String) async throws -> PairingResponse {
        struct Exchange: Encodable { let code: String; let name: String }
        let response: PairingResponse = try await request("exchange", token: nil,
            body: WireJSON.encoder().encode(Exchange(code: code, name: name)))
        guard !response.token.isEmpty, response.deviceID > 0, response.checkpoint >= 0 else { throw BridgeError.invalidResponse }
        return response
    }
    func status(token: String) async throws -> DeviceStatus {
        try await request("status", token: token, body: nil)
    }
    func upload(_ batch: DeltaBatch, token: String) async throws -> DeltaAcknowledgement {
        try await request("deltas", token: token, body: WireJSON.encoder().encode(batch))
    }
    private func request<T: Decodable>(_ endpoint: String, token: String?, body: Data?) async throws -> T {
        var request = URLRequest(url: configuration.endpoint(endpoint))
        request.httpMethod = body == nil ? "GET" : "POST"
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw BridgeError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else { throw BridgeError.server(response.statusCode) }
        guard data.count <= 65536 else { throw BridgeError.invalidResponse }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
