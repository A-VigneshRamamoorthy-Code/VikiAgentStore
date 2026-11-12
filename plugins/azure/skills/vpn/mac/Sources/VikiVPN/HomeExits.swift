import Foundation

/// A machine on a residential connection that the relay VM forwards a device's
/// traffic through, so streaming services see a home ISP instead of Azure.
///
/// The home machine keeps `ssh -R 127.0.0.1:<port>` open to the relay VM (a
/// dynamic, reverse SOCKS forward), so it needs no inbound ports and works behind
/// CGNAT. Stored as `exits/<region>/<id>.json`; the VM agent does the rest.
///
/// Enrollment is approval-gated: the app reserves `exits/_pending/<id>.json`, the PC
/// writes its key to `exits/_enroll/<id>.json` with a create-only link, and only the
/// app (the signed-in user) promotes it to `exits/<region>/`, which the relay reads.
/// Anyone holding a leaked invite can therefore at most fill a slot that was already
/// reserved — and never re-enroll after approval, because the pending entry is gone.
struct HomeExit: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    var country: String
    var region: String
    var port: Int
    /// nil until the PC has run its installer (the app reserves the slot first).
    var sshPublicKey: String?
    var createdAt: Date
    var city: String?
    var isp: String?
    var host: String?
    /// "lat,lon" of the PC's ISP location, for its map pin.
    var loc: String?

    var point: GeoPoint? { GeoPoint(loc) ?? Countries.point(country) }
    var pending: Bool { (sshPublicKey ?? "").isEmpty }
    var flag: String {
        country.uppercased().unicodeScalars
            .compactMap { UnicodeScalar(127397 + $0.value) }
            .map(String.init).joined()
    }
}

/// A row in the server picker: a plain Azure region, or a home exit relayed through one.
/// One place traffic can leave from: an Azure server, a home PC relayed through one, or a
/// home PC this Mac connects to directly.
struct ServerChoice: Identifiable, Hashable {
    var region: RegionConfig?
    var exit: HomeExit? = nil
    var direct: DirectPC? = nil
    /// An Azure location with no server yet: connecting adds and builds it.
    var unbuilt = false

    var id: String {
        if let direct { return "pc:\(direct.id)" }
        if let exit { return "exit:\(exit.id)" }
        return region?.code ?? ""
    }
    var title: String { direct?.name ?? exit?.name ?? region?.name ?? "" }
    var isHome: Bool { direct != nil || exit != nil }
    var country: String { direct?.country ?? exit?.country ?? region?.country ?? "" }
    var subtitle: String {
        if let direct { return [Countries.name(direct.country), direct.isp].compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: " · ") }
        if let exit {
            if exit.pending { return "Waiting for the PC" }
            return [exit.isp, region.map { "via \($0.city)" }].compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: " · ")
        }
        return region?.city ?? ""
    }
    var flag: String {
        if let direct { return direct.flag }
        if let exit { return exit.pending ? "⏳" : exit.flag }
        return region?.flag ?? "🌐"
    }
    var point: GeoPoint? { direct?.point ?? exit?.point ?? region?.point }
}

enum HomeExitSetup {
    static let ports = 10801..<10900

    static func makeID(_ name: String) -> String {
        let slug = name.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "-" }
            .reduce(into: "") { s, c in if !(c == "-" && s.hasSuffix("-")) { s.append(c) } }
            .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        let suffix = String((0..<4).map { _ in "abcdefghjkmnpqrstuvwxyz23456789".randomElement()! })
        return "\(slug.prefix(24).isEmpty ? "home" : String(slug.prefix(24)))-\(suffix)"
    }

    /// What the PC needs to enroll itself; base64 JSON embedded in the installer.
    struct Invite: Codable {
        var v = 1
        let id: String
        let region: String
        let regionName: String
        let relay: String
        let hostKey: String
        let port: Int
        let put: String
        let expires: String
    }

    /// The repo's generic installer (homeexit/Install-VikiVPNExit.ps1), bundled by build.sh.
    static func installerSource() throws -> String {
        guard let url = Bundle.main.url(forResource: "Install-VikiVPNExit", withExtension: "ps1") else {
            throw setupError("Installer missing from the app bundle — rebuild with mac/build.sh")
        }
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The installer with this PC's invite baked in. Hosted per invite in blob storage
    /// (read-only link) and also embedded in the .cmd fallback.
    static func personalized(invite: Invite, installer: String) throws -> String {
        let json = String(decoding: try JSONEncoder().encode(invite), as: UTF8.self)
        guard !json.contains("'") else { throw setupError("Invite contains a quote") }
        return "$VikiInvite = '\(json)'\r\n" + installer.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\n", with: "\r\n")
    }

    /// One line to paste into PowerShell on the PC. Nothing is downloaded as a file,
    /// so SmartScreen and Mark-of-the-Web never apply, and it needs no admin rights.
    static func command(installerURL: String) -> String {
        "irm '\(installerURL)' | iex"
    }

    /// Fallback: a double-clickable .cmd (for copying by USB stick). Files that arrive
    /// through a browser or email carry Mark-of-the-Web and SmartScreen will warn, which
    /// is why the paste-in command is the primary path.
    static func clickToRun(personalized script: String, invite: Invite) -> String {
        let header = [
            "@echo off",
            "rem Leap VPN home exit installer (relay: \(invite.regionName)). Double-click on a Windows PC with a",
            "rem home internet connection to add it as a Leap VPN server. No administrator rights needed.",
            "rem Contains a one-time registration link valid until \(invite.expires); share it only with your own PCs.",
            "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$t=Get-Content -Raw -LiteralPath '%~f0'; "
                + "$m='#VIKIVPN'+'-INSTALLER'; Invoke-Expression $t.Substring($t.IndexOf($m))\"",
            "echo.",
            "pause",
            "exit /b",
            "#VIKIVPN-INSTALLER",
        ]
        return header.joined(separator: "\r\n") + "\r\n" + script
    }

    private static func setupError(_ s: String) -> NSError {
        NSError(domain: "VikiVPN.HomeExit", code: 1, userInfo: [NSLocalizedDescriptionKey: s])
    }
}
