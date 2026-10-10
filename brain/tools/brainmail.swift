// brainmail: the one program that may read the brain's mail password.
//
//     brainmail get <service> <account> [reason]
//     brainmail store <service> <account>          (the secret on stdin)
//
// It asks for Touch ID (or the Mac's password) first, and only then reads
// the Keychain item. `store` makes brainmail the item's creator, and the
// Keychain lets only the creator read it silently; anything else that tries
// gets a macOS dialog instead of the password, an alarm she did not cause.
// (An item made by the `security` tool stays open to every Apple command
// line tool whatever its trusted list says — tested 28 Sep — which is why
// this program stores it itself.) Built by make_brainmail.sh into brain/tools/.bin/, where
// the brain's own Claude runs cannot replace it.
//
// macOS words the prompt as '"brainmail" is trying to <reason>.'

import Foundation
import LocalAuthentication
import Security

func fail(_ message: String, _ code: Int32) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

let args = CommandLine.arguments
guard args.count >= 4, ["get", "store"].contains(args[1]) else {
    fail("usage: brainmail get|store <service> <account> [reason]", 2)
}
let service = args[2]
let account = args[3]

if args[1] == "store" {
    // The caller removes any older copy first (`security` made it, so
    // `security` may delete it); this adds the new one as its creator.
    guard let secret = readLine(strippingNewline: true), !secret.isEmpty else {
        fail("nothing to store on stdin", 2)
    }
    let add: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
        kSecAttrLabel as String: service,
        kSecValueData as String: Data(secret.utf8),
    ]
    let added = SecItemAdd(add as CFDictionary, nil)
    guard added == errSecSuccess else { fail("could not store (\(added))", 6) }
    exit(0)
}
let reason = args.count > 4 ? args[4] : "use your mail password"

let context = LAContext()
var policyError: NSError?
guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &policyError) else {
    fail("this Mac cannot confirm it is you: "
         + (policyError?.localizedDescription ?? "unknown reason"), 3)
}
let done = DispatchSemaphore(value: 0)
var confirmed = false
var authError: Error?
context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { ok, err in
    confirmed = ok
    authError = err
    done.signal()
}
done.wait()
guard confirmed else {
    fail("not confirmed: " + (authError?.localizedDescription ?? "cancelled"), 4)
}

let query: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service,
    kSecAttrAccount as String: account,
    kSecReturnData as String: true,
    kSecMatchLimit as String: kSecMatchLimitOne,
]
var item: CFTypeRef?
let status = SecItemCopyMatching(query as CFDictionary, &item)
guard status == errSecSuccess, let data = item as? Data,
      let secret = String(data: data, encoding: .utf8) else {
    fail("no password stored for \(account) (\(status))", 5)
}
print(secret, terminator: "")
