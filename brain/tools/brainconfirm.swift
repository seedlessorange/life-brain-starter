// brainconfirm: Touch ID (or the Mac's password), and nothing else.
//
//     brainconfirm "<reason>"      exits 0 when she confirmed, 4 when not
//
// For the moments that need her present rather than a secret: approving a
// change to the brain's security code (sentinel.py). A Claude session can
// press the page's buttons for itself; it cannot produce her fingerprint.
// Kept apart from brainmail so rebuilding one never disturbs the Keychain's
// trust in the other. macOS words it as '"brainconfirm" is trying to <reason>.'

import Foundation
import LocalAuthentication

let args = CommandLine.arguments
let reason = args.count > 1 ? args[1] : "confirm it is you"

let context = LAContext()
var policyError: NSError?
guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &policyError) else {
    FileHandle.standardError.write(("this Mac cannot confirm it is you: "
        + (policyError?.localizedDescription ?? "unknown reason") + "\n").data(using: .utf8)!)
    exit(3)
}
let done = DispatchSemaphore(value: 0)
var confirmed = false
context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { ok, _ in
    confirmed = ok
    done.signal()
}
done.wait()
exit(confirmed ? 0 : 4)
