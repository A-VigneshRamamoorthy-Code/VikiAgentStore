import Foundation
import Security

/// Generic-password items in the login Keychain, service "AvenVPN". Nothing secret
/// is ever written anywhere else.
enum Keychain {
    static let service = "AvenVPN"
    /// Service name used by builds before the rename; items found there are moved on first read.
    private static let legacyService = "Leap" + "VPN"

    static func secret(account: String) -> String? {
        if let value = read(account: account, service: service) { return value }
        guard let legacy = read(account: account, service: legacyService) else { return nil }
        set(legacy, account: account)
        if read(account: account, service: service) == legacy { delete(account: account, service: legacyService) }
        return legacy
    }

    private static func read(account: String, service: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func set(_ value: String, account: String, label: String = "AvenVPN") {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let data = Data(value.utf8)
        if SecItemUpdate(base as CFDictionary, [kSecValueData as String: data] as CFDictionary) == errSecItemNotFound {
            var add = base
            add[kSecValueData as String] = data
            add[kSecAttrLabel as String] = label
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    static func delete(account: String) {
        delete(account: account, service: service)
        delete(account: account, service: legacyService)
    }

    private static func delete(account: String, service: String) {
        SecItemDelete([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ] as CFDictionary)
    }
}
