import Foundation

/// Which currency costs are shown in: the Azure account's billing currency once Cost
/// Management has reported it, otherwise the device's local currency, otherwise US dollars.
enum CurrencyResolver {
    /// Currencies the Azure Retail Prices API accepts for `currencyCode`.
    static let retailCurrencies: Set<String> = ["USD", "AUD", "BRL", "CAD", "CHF", "CNY", "DKK", "EUR", "GBP",
                                                "INR", "JPY", "KRW", "NOK", "NZD", "RUB", "SEK", "TWD"]
    private static let lastKey = "billingCurrency"
    private static let bySubscriptionKey = "billingCurrencyBySubscription"

    /// Best currency to show right now, before (or without) a Cost Management answer.
    static var current: String { resolve(cached: UserDefaults.standard.string(forKey: lastKey), locale: .current) }

    /// Billing currency last reported for a subscription, falling back like `current`.
    static func current(subscription: String) -> String {
        let map = UserDefaults.standard.dictionary(forKey: bySubscriptionKey) as? [String: String] ?? [:]
        return resolve(cached: map[subscription.lowercased()] ?? UserDefaults.standard.string(forKey: lastKey),
                       locale: .current)
    }

    /// Caches the billing currency Cost Management reported for a subscription.
    static func remember(_ code: String, subscription: String) {
        guard let code = valid(code) else { return }
        let d = UserDefaults.standard
        var map = d.dictionary(forKey: bySubscriptionKey) as? [String: String] ?? [:]
        map[subscription.lowercased()] = code
        d.set(map, forKey: bySubscriptionKey)
        d.set(code, forKey: lastKey)
    }

    static func resolve(cached: String?, locale: Locale) -> String {
        valid(cached) ?? valid(locale.currency?.identifier) ?? "USD"
    }

    /// The currency to request retail prices in; unsupported currencies fall back to USD.
    static func retail(_ code: String) -> String {
        guard let c = valid(code), retailCurrencies.contains(c) else { return "USD" }
        return c
    }

    /// Normalised ISO 4217 code, or nil if `code` isn't a real currency.
    static func valid(_ code: String?) -> String? {
        guard let c = code?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
              Locale.commonISOCurrencyCodes.contains(c) else { return nil }
        return c
    }
}
