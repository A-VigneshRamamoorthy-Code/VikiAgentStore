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

    // MARK: display currency

    private static let ratesKey = "usdRates"

    /// App Store screenshots only: `-AvenScreenshotCurrency USD` on the command line shows costs
    /// in that currency. It lives in the launch-argument domain and is never persisted, so the
    /// shipped app always shows the Azure billing currency.
    static let display: String? = valid(UserDefaults.standard
        .volatileDomain(forName: UserDefaults.argumentDomain)["AvenScreenshotCurrency"] as? String)

    /// Units of each currency per US dollar, cached from the last exchange-rate lookup.
    static var usdRates: [String: Double] {
        UserDefaults.standard.dictionary(forKey: ratesKey) as? [String: Double] ?? [:]
    }

    static func rememberRate(_ rate: Double, for code: String) {
        guard let code = valid(code), rate > 0 else { return }
        var map = usdRates
        map[code] = rate
        UserDefaults.standard.set(map, forKey: ratesKey)
    }

    /// `amount` in the display currency, converted at the cached rate. Left as-is when no
    /// display currency is set or the rate isn't known yet.
    static func shown(_ amount: Double, _ currency: String) -> (amount: Double, currency: String) {
        guard let target = display, let from = valid(currency), from != target else { return (amount, currency) }
        let rates = usdRates
        let fromRate = from == "USD" ? 1 : rates[from]
        let toRate = target == "USD" ? 1 : rates[target]
        guard let fromRate, let toRate, fromRate > 0 else { return (amount, currency) }
        return (amount / fromRate * toRate, target)
    }

    /// Normalised ISO 4217 code, or nil if `code` isn't a real currency.
    static func valid(_ code: String?) -> String? {
        guard let c = code?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
              Locale.commonISOCurrencyCodes.contains(c) else { return nil }
        return c
    }
}
