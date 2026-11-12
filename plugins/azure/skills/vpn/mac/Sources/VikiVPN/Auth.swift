import AppKit
import CryptoKit
import Foundation
import Network

enum AuthError: LocalizedError {
    case signInRequired
    case cancelled
    case failed(String)
    /// A personal account whose Azure directory could not be found automatically.
    case needsDirectory
    var errorDescription: String? {
        switch self {
        case .needsDirectory: return "Enter your Azure directory (e.g. name.onmicrosoft.com)."
        case .signInRequired: return "Sign in to Microsoft again."
        case .cancelled: return "Sign-in was cancelled."
        case .failed(let s): return s
        }
    }
}

struct AzureSubscription: Codable, Hashable, Identifiable {
    let id: String
    let name: String
    let tenantId: String
    let state: String
    /// Offer type, e.g. `MSDN_2014-09-01` for Visual Studio subscriptions.
    var quotaId: String? = nil
}

/// Who signed in (display only).
struct MicrosoftUser: Codable, Hashable {
    var name: String
    var username: String
}

/// Microsoft sign-in for Azure: OAuth 2.0 authorization code + PKCE in the user's
/// browser with a loopback redirect (RFC 8252), as a public client — the app holds
/// no secret. Only the rotating refresh token is kept, in the Keychain.
///
/// The client id identifies the app registration "Leap VPN" (multi-tenant,
/// delegated `user_impersonation` on Azure Resource Manager and Azure Storage). It
/// is an identifier, not a credential; forks can override it with the
/// `VikiVPNClientID` user default.
actor MicrosoftAuth {
    static let shared = MicrosoftAuth()

    static var clientID: String {
        UserDefaults.standard.string(forKey: "VikiVPNClientID") ?? "a55ec349-3778-4f8f-8960-5710a0d583ce"
    }
    static let arm = "https://management.azure.com/user_impersonation"
    static let storage = "https://storage.azure.com/user_impersonation"
    private static let refreshAccount = "ms-refresh-token"
    private let login = "https://login.microsoftonline.com"

    private var cache: [String: (token: String, expires: Date)] = [:]
    private let session: URLSession = {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 30
        return URLSession(configuration: cfg)
    }()

    nonisolated var hasSession: Bool { Keychain.secret(account: Self.refreshAccount) != nil }

    // MARK: interactive sign-in

    /// The directory (tenant id) the user's Azure tokens come from.
    nonisolated static var authority: String {
        get { UserDefaults.standard.string(forKey: "VikiVPNAuthority") ?? "organizations" }
        set { UserDefaults.standard.set(newValue, forKey: "VikiVPNAuthority") }
    }

    private static let consumerDomains: Set<String> = [
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com",
        "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "hotmail.co.uk", "outlook.in",
    ]

    /// Tenant id for a domain such as contoso.com or name.onmicrosoft.com (nil if unknown).
    static func tenantID(forDomain domain: String) async -> String? {
        guard domain.range(of: #"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#, options: .regularExpression) != nil,
              let url = URL(string: "https://login.microsoftonline.com/\(domain)/v2.0/.well-known/openid-configuration"),
              let (data, resp) = try? await URLSession.shared.data(from: url),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let issuer = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["issuer"] as? String
        else { return nil }
        let id = issuer.components(separatedBy: "/").first { UUID(uuidString: $0) != nil }
        return id == consumersTenant ? nil : id  // the consumers tenant is no use for Azure
    }

    static let consumersTenant = "9188040d-6c67-4c5b-b112-36a304b66dad"

    /// The Azure directory of a personal Microsoft account (Gmail, Outlook…). Those accounts
    /// sign in through the consumers tenant, which Azure does not accept, so we find the
    /// directory Azure created for them — named after the email by convention
    /// (jane.doe@gmail.com → janedoegmail.onmicrosoft.com). `directory` overrides it.
    static func personalDirectory(email: String, directory: String?) async throws -> String {
        if let d = directory?.trimmingCharacters(in: .whitespaces).lowercased(), !d.isEmpty {
            if UUID(uuidString: d) != nil { return d }
            if let id = await tenantID(forDomain: d) { return id }
            if let id = await tenantID(forDomain: "\(d).onmicrosoft.com") { return id }
            throw AuthError.failed("Directory \(d) not found.")
        }
        let e = email.lowercased()
        if let at = e.lastIndex(of: "@") {
            let domain = String(e[e.index(after: at)...])
            if !consumerDomains.contains(domain), let id = await tenantID(forDomain: domain) { return id }
        }
        // Azure drops the top-level domain: jane.doe@gmail.com → janedoegmail, a@outlook.co.uk → aoutlook.
        let alnum = { (s: Substring) in s.filter { $0.isLetter || $0.isNumber } }
        let parts = e.split(separator: "@", maxSplits: 1)
        if parts.count == 2 {
            let labels = parts[1].split(separator: ".")
            var candidates: [String] = []
            for keep in stride(from: labels.count - 1, through: 1, by: -1) {
                candidates.append(alnum(parts[0]) + labels.prefix(keep).map(alnum).joined())
            }
            candidates.append(alnum(parts[0]) + labels.map(alnum).joined())
            for c in candidates where !c.isEmpty {
                if let id = await tenantID(forDomain: "\(c).onmicrosoft.com") { return id }
            }
        }
        throw AuthError.needsDirectory
    }

    /// Set after the browser step when the directory still has to be found.
    private var pendingUser: MicrosoftUser?

    /// One button: the user signs in on Microsoft's page (work or personal account),
    /// then we pick the right directory and get an Azure token without more prompts.
    func signIn(directory: String? = nil) async throws -> MicrosoftUser {
        let user: MicrosoftUser
        var tenant: String
        if let pending = pendingUser, directory != nil {
            user = pending
            tenant = try await Self.personalDirectory(email: pending.username, directory: directory)
        } else {
            cache.removeAll()
            let json = try await authorize(authority: "common", scope: "openid profile email offline_access",
                                           prompt: "select_account", hint: nil)
            try storeRefresh(json)
            let c = Self.claims(json["id_token"] as? String)
            user = MicrosoftUser(name: c["name"] as? String ?? "",
                                 username: c["preferred_username"] as? String ?? c["email"] as? String ?? "")
            let tid = c["tid"] as? String ?? Self.consumersTenant
            if tid == Self.consumersTenant {
                pendingUser = user
                tenant = try await Self.personalDirectory(email: user.username, directory: nil)
            } else {
                tenant = tid
            }
        }
        // The refresh token usually redeems straight into the directory; if not, the browser
        // already has the session, so a second pass completes without any typing.
        // Both resources must be consented in that directory; one prompt covers both.
        do {
            _ = try await token(Self.arm, tenant: tenant)
            _ = try await token(Self.storage, tenant: tenant)
        } catch {
            let json = try await authorize(authority: tenant,
                                           scope: "\(Self.arm) \(Self.storage) offline_access openid profile",
                                           tokenScope: "\(Self.arm) offline_access openid profile",
                                           prompt: nil, hint: user.username)
            try store(json, key: "\(tenant)|\(Self.arm)")
            _ = try await token(Self.storage, tenant: tenant)
        }
        pendingUser = nil
        Self.authority = tenant
        return user
    }

    /// Authorization code + PKCE in the default browser, caught on a loopback redirect.
    /// `scope` is what the user consents to (may span resources); `tokenScope` is the single
    /// resource the code is redeemed for (defaults to `scope`).
    private func authorize(authority: String, scope: String, tokenScope: String? = nil,
                           prompt: String?, hint: String?) async throws -> [String: Any] {
        let verifier = Self.randomURLSafe(32)
        let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URL
        let state = Self.randomURLSafe(16)
        let server = try await LoopbackServer.start()
        defer { server.stop() }
        let redirect = "http://127.0.0.1:\(server.port)"

        var url = URLComponents(string: "\(login)/\(authority)/oauth2/v2.0/authorize")!
        url.queryItems = [
            .init(name: "client_id", value: Self.clientID),
            .init(name: "response_type", value: "code"),
            .init(name: "redirect_uri", value: redirect),
            .init(name: "response_mode", value: "query"),
            .init(name: "scope", value: scope),
            .init(name: "state", value: state),
            .init(name: "code_challenge", value: challenge),
            .init(name: "code_challenge_method", value: "S256"),
        ] + (prompt.map { [.init(name: "prompt", value: $0)] } ?? [])
          + (hint.map { [.init(name: "login_hint", value: $0)] } ?? [])
        let target = url.url!
        await MainActor.run { _ = NSWorkspace.shared.open(target) }

        let query = try await server.waitForRedirect(timeout: 600)
        guard query["state"] == state else { throw AuthError.failed("Sign-in response did not match.") }
        if let err = query["error"] {
            throw err == "access_denied" ? AuthError.cancelled
                : AuthError.failed(query["error_description"] ?? err)
        }
        guard let code = query["code"] else { throw AuthError.failed("No authorization code returned.") }
        return try await tokenRequest(tenant: authority, [
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
            "code_verifier": verifier, "scope": tokenScope ?? scope,
        ])
    }

    func signOut() {
        cache.removeAll()
        Keychain.delete(account: Self.refreshAccount)
    }

    // MARK: tokens

    /// An access token for `scope` in `tenant`, redeemed silently from the refresh token.
    func token(_ scope: String, tenant: String) async throws -> String {
        let key = "\(tenant)|\(scope)"
        if let c = cache[key], c.expires.timeIntervalSinceNow > 300 { return c.token }
        guard let refresh = Keychain.secret(account: Self.refreshAccount) else { throw AuthError.signInRequired }
        let json = try await tokenRequest(tenant: tenant, [
            "grant_type": "refresh_token", "refresh_token": refresh, "scope": "\(scope) offline_access",
        ])
        return try store(json, key: key)
    }

    /// The signed-in user's object id in `tenant` (for role assignments).
    func objectID(tenant: String) async throws -> String {
        let tok = try await token(Self.arm, tenant: tenant)
        guard let oid = Self.claims(tok)["oid"] as? String else { throw AuthError.failed("Token has no user id.") }
        return oid
    }

    /// Every enabled subscription the user can see, across all their directories.
    func subscriptions() async throws -> [AzureSubscription] {
        let home = try await token(Self.arm, tenant: Self.authority)
        let tenants = (try await get("https://management.azure.com/tenants?api-version=2022-12-01", home)["value"]
                       as? [[String: Any]] ?? []).compactMap { $0["tenantId"] as? String }
        var out: [AzureSubscription] = []
        for tenant in tenants {
            guard let tok = try? await token(Self.arm, tenant: tenant),
                  let list = try? await get("https://management.azure.com/subscriptions?api-version=2022-12-01", tok)
            else { continue }
            for s in list["value"] as? [[String: Any]] ?? [] {
                guard let id = s["subscriptionId"] as? String, !out.contains(where: { $0.id == id }) else { continue }
                out.append(AzureSubscription(id: id, name: s["displayName"] as? String ?? id,
                                             tenantId: s["tenantId"] as? String ?? tenant,
                                             state: s["state"] as? String ?? "",
                                             quotaId: (s["subscriptionPolicies"] as? [String: Any])?["quotaId"] as? String))
            }
        }
        return out.filter { $0.state == "Enabled" }
    }

    // MARK: plumbing

    private func storeRefresh(_ json: [String: Any]) throws {
        guard let rt = json["refresh_token"] as? String else { throw AuthError.failed("No refresh token.") }
        Keychain.set(rt, account: Self.refreshAccount, label: "VikiVPN Microsoft sign-in")
    }

    @discardableResult
    private func store(_ json: [String: Any], key: String) throws -> String {
        guard let access = json["access_token"] as? String else { throw AuthError.failed("No access token.") }
        if let rt = json["refresh_token"] as? String { Keychain.set(rt, account: Self.refreshAccount, label: "VikiVPN Microsoft sign-in") }
        let ttl = (json["expires_in"] as? Double) ?? Double(json["expires_in"] as? String ?? "") ?? 3600
        cache[key] = (access, Date().addingTimeInterval(ttl))
        return access
    }

    private func tokenRequest(tenant: String, _ form: [String: String]) async throws -> [String: Any] {
        var req = URLRequest(url: URL(string: "\(login)/\(tenant)/oauth2/v2.0/token")!)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        var comps = URLComponents()
        comps.queryItems = (form.merging(["client_id": Self.clientID]) { a, _ in a }).map { .init(name: $0.key, value: $0.value) }
        req.httpBody = Data((comps.percentEncodedQuery ?? "").replacingOccurrences(of: "+", with: "%2B").utf8)
        let (data, resp) = try await URLSession.retrying(req, on: session)
        let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            let err = json["error"] as? String ?? "http \((resp as? HTTPURLResponse)?.statusCode ?? 0)"
            NSLog("VikiVPN: token %@ %@ for %@: %@", form["grant_type"] ?? "", tenant, form["scope"] ?? "",
                  (json["error_description"] as? String).map { String($0.prefix(300)) } ?? err)
            if form["grant_type"] == "refresh_token",
               ["invalid_grant", "interaction_required", "login_required"].contains(err) {
                throw AuthError.signInRequired
            }
            throw AuthError.failed((json["error_description"] as? String)?.components(separatedBy: "\r\n").first ?? err)
        }
        return json
    }

    private func get(_ url: String, _ token: String) async throws -> [String: Any] {
        var req = URLRequest(url: URL(string: url)!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, _) = try await URLSession.retrying(req, on: session)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    static func claims(_ jwt: String?) -> [String: Any] {
        guard let part = jwt?.split(separator: ".").dropFirst().first else { return [:] }
        var b64 = part.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        while b64.count % 4 != 0 { b64 += "=" }
        guard let data = Data(base64Encoded: b64) else { return [:] }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    static func randomURLSafe(_ bytes: Int) -> String {
        Data((0..<bytes).map { _ in UInt8.random(in: 0...255) }).base64URL
    }
}

extension Data {
    var base64URL: String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}

/// A one-shot HTTP listener on 127.0.0.1 that catches the OAuth redirect.
final class LoopbackServer: @unchecked Sendable {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "vikivpn.loopback")
    private var continuation: CheckedContinuation<[String: String], Error>?
    private(set) var port: UInt16 = 0

    private init(_ listener: NWListener) { self.listener = listener }

    static func start() async throws -> LoopbackServer {
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
        let server = LoopbackServer(try NWListener(using: params))
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            var resumed = false
            server.listener.stateUpdateHandler = { state in
                guard !resumed else { return }
                switch state {
                case .ready:
                    resumed = true
                    server.port = server.listener.port?.rawValue ?? 0
                    cont.resume()
                case .failed(let e):
                    resumed = true
                    cont.resume(throwing: e)
                default: break
                }
            }
            server.listener.newConnectionHandler = { server.handle($0) }
            server.listener.start(queue: server.queue)
        }
        return server
    }

    func waitForRedirect(timeout: TimeInterval) async throws -> [String: String] {
        try await withCheckedThrowingContinuation { cont in
            queue.async {
                self.continuation = cont
                self.queue.asyncAfter(deadline: .now() + timeout) {
                    self.continuation?.resume(throwing: AuthError.cancelled)
                    self.continuation = nil
                }
            }
        }
    }

    func stop() { listener.cancel() }

    private func handle(_ conn: NWConnection) {
        conn.start(queue: queue)
        conn.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { data, _, _, _ in
            let head = String(decoding: data ?? Data(), as: UTF8.self)
            let target = head.split(separator: " ").dropFirst().first.map(String.init) ?? "/"
            let items = URLComponents(string: "http://127.0.0.1\(target)")?.queryItems ?? []
            let query = Dictionary(items.map { ($0.name, $0.value ?? "") }) { a, _ in a }
            let isRedirect = query["code"] != nil || query["error"] != nil
            let body = isRedirect
                ? "<!doctype html><meta charset=utf-8><title>VikiVPN</title><body style=\"font:15px -apple-system;text-align:center;padding-top:80px;color:#1d1d1f\"><h2>\(query["error"] == nil ? "Signed in" : "Sign-in failed")</h2><p>You can close this tab and return to VikiVPN.</p>"
                : ""
            let response = "HTTP/1.1 \(isRedirect ? "200 OK" : "404 Not Found")\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: \(body.utf8.count)\r\nConnection: close\r\n\r\n\(body)"
            conn.send(content: Data(response.utf8), completion: .contentProcessed { _ in conn.cancel() })
            if isRedirect, let cont = self.continuation {
                self.continuation = nil
                cont.resume(returning: query)
            }
        }
    }
}
