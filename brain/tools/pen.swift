// Brain Pen: rewrite what she is typing, in any app, in her own voice.
//
//     ⌃⌥R   rewrite the selection, or the whole box when nothing is selected
//     ⌃⌥T   fix typos straight into the box, no panel
//     ⌃⌥H   how does this read? (nothing changes)
//
// Both are defaults: Shortcuts in the menu sets any action to any keys, and
// gives each tone its own "straight into the box" shortcut. Learning mode
// (off unless she turns it on) shows the mistakes she keeps making.
//
// A menu-bar app. It reads the text (through Accessibility, or a ⌘C when an
// app hides its text from it), asks the brain's page server for a rewrite
// (/api/pen/*, which runs pen.py), and on Return pastes the result back and
// puts her clipboard back the way it was. It never presses send: the text
// lands in the box and sending stays hers. Password fields are refused.
//
// Built by make_pen_app.sh into "Brain Pen.app". It needs Accessibility
// (System Settings > Privacy & Security > Accessibility): reading another
// app's text box and pressing ⌘C or ⌘V for her both need it.
//
//     Brain Pen.app/Contents/MacOS/Brain Pen --demo "some text"
//         opens the panel on that text without touching any other app
//     Brain Pen.app/Contents/MacOS/Brain Pen --train | --shortcuts
//         opens the settings window on that tab

import ApplicationServices
import NaturalLanguage
import Carbon.HIToolbox
import Cocoa
import ServiceManagement
import SwiftUI

let serverBase = ProcessInfo.processInfo.environment["BRAIN_URL"] ?? "http://127.0.0.1:7718"
let maxChars = 8000

// MARK: - the brain's server

func api(_ path: String, _ body: [String: Any]? = nil, timeout: TimeInterval = 90,
         done: @escaping ([String: Any]?, String?) -> Void) {
    guard let url = URL(string: serverBase + path) else { return }
    var req = URLRequest(url: url)
    req.timeoutInterval = timeout
    if let body = body {
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
    }
    URLSession.shared.dataTask(with: req) { data, _, err in
        var out: [String: Any]? = nil
        var problem: String? = nil
        if let err = err as NSError? {
            problem = [NSURLErrorCannotConnectToHost, NSURLErrorNetworkConnectionLost,
                       NSURLErrorCannotFindHost].contains(err.code)
                ? "The brain's server isn't running. Open Brain Server, then try again."
                : err.localizedDescription
        } else if let data = data {
            out = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            if let e = out?["error"] as? String { problem = e }
            else if out == nil { problem = "The server's answer was unreadable." }
        }
        DispatchQueue.main.async { done(out, problem) }
    }.resume()
}

// MARK: - keys and the clipboard

func press(_ key: Int, _ flags: CGEventFlags = .maskCommand) {
    let src = CGEventSource(stateID: .combinedSessionState)
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(key), keyDown: down)
        e?.flags = flags
        e?.post(tap: .cghidEventTap)
    }
}

/// The hotkey's own ⌃⌥ would ride along on the ⌘C: wait until they're up.
func waitForModifiersUp() {
    for _ in 0..<40 {
        let f = CGEventSource.flagsState(.combinedSessionState)
        if f.intersection([.maskControl, .maskAlternate, .maskCommand, .maskShift]).isEmpty { return }
        usleep(15_000)
    }
}

typealias Saved = [[NSPasteboard.PasteboardType: Data]]

func saveClipboard() -> Saved {
    (NSPasteboard.general.pasteboardItems ?? []).map { item in
        var d: [NSPasteboard.PasteboardType: Data] = [:]
        for t in item.types { if let v = item.data(forType: t) { d[t] = v } }
        return d
    }
}

func restoreClipboard(_ saved: Saved) {
    let pb = NSPasteboard.general
    pb.clearContents()
    let items = saved.map { d -> NSPasteboardItem in
        let i = NSPasteboardItem()
        for (t, v) in d { i.setData(v, forType: t) }
        return i
    }
    if !items.isEmpty { pb.writeObjects(items) }
}

/// Text on the clipboard that clipboard managers (Alfred's history among
/// them) are asked to skip: it only passes through on its way into the box.
func putOnClipboard(_ s: String) {
    let pb = NSPasteboard.general
    pb.clearContents()
    let item = NSPasteboardItem()
    item.setString(s, forType: .string)
    item.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.TransientType"))
    pb.writeObjects([item])
}

/// ⌘C, and what it put on the clipboard, or nil when nothing was copied.
func copyNow() -> String? {
    let pb = NSPasteboard.general
    let before = pb.changeCount
    press(kVK_ANSI_C)
    for _ in 0..<16 {
        usleep(25_000)
        if pb.changeCount != before { break }
    }
    guard pb.changeCount != before else { return nil }
    return pb.string(forType: .string)
}

// MARK: - reading the box (Accessibility)

func axValue(_ el: AXUIElement, _ attr: String) -> CFTypeRef? {
    var v: CFTypeRef?
    return AXUIElementCopyAttributeValue(el, attr as CFString, &v) == .success ? v : nil
}

func axString(_ el: AXUIElement, _ attr: String) -> String? {
    axValue(el, attr) as? String
}

func axElement(_ el: AXUIElement, _ attr: String) -> AXUIElement? {
    guard let v = axValue(el, attr), CFGetTypeID(v) == AXUIElementGetTypeID() else { return nil }
    return (v as! AXUIElement)
}

/// Where the caret or the box is, in screen coordinates, when the app says.
func axFrame(_ el: AXUIElement) -> CGRect? {
    if let r = axValue(el, kAXSelectedTextRangeAttribute), CFGetTypeID(r) == AXValueGetTypeID() {
        var out: CFTypeRef?
        if AXUIElementCopyParameterizedAttributeValue(
            el, kAXBoundsForRangeParameterizedAttribute as CFString, r, &out) == .success,
           let o = out, CFGetTypeID(o) == AXValueGetTypeID() {
            var rect = CGRect.zero
            if AXValueGetValue(o as! AXValue, .cgRect, &rect), rect.width + rect.height > 0 {
                return rect
            }
        }
    }
    var pos = CGPoint.zero, size = CGSize.zero
    guard let p = axValue(el, kAXPositionAttribute), let s = axValue(el, kAXSizeAttribute),
          CFGetTypeID(p) == AXValueGetTypeID(), CFGetTypeID(s) == AXValueGetTypeID(),
          AXValueGetValue(p as! AXValue, .cgPoint, &pos),
          AXValueGetValue(s as! AXValue, .cgSize, &size) else { return nil }
    return CGRect(origin: pos, size: size)
}

struct Grab {
    var text: String
    var mode: String          // "selection" or "whole"
    var pid: pid_t
    var bundle: String
    var app: String
    var title: String
    var anchor: CGRect?       // Accessibility coordinates (top-left origin)
    var element: AXUIElement? = nil
}

/// `.empty` means nothing could be read, so the panel opens a box to paste
/// or type into; `.refused` is for the few places it must not touch.
enum GrabResult { case ok(Grab), empty(Grab), refused(String) }

let textRoles: Set<String> = ["AXTextArea", "AXTextField", "AXComboBox", "AXSearchField", "AXWebArea"]

func grabText() -> GrabResult {
    guard let front = NSWorkspace.shared.frontmostApplication else {
        return .refused("No app is in front.")
    }
    let bundle = front.bundleIdentifier ?? ""
    let pid = front.processIdentifier
    let appEl = AXUIElementCreateApplication(pid)
    // Chrome and Electron apps keep their page text from Accessibility
    // until someone asks for it.
    AXUIElementSetAttributeValue(appEl, "AXManualAccessibility" as CFString, kCFBooleanTrue)
    var title = ""
    if let win = axElement(appEl, kAXFocusedWindowAttribute) { title = axString(win, kAXTitleAttribute) ?? "" }
    let name = front.localizedName ?? bundle
    let nothing = GrabResult.empty(Grab(text: "", mode: "paste", pid: pid, bundle: bundle,
                                        app: name, title: title, anchor: nil))
    if bundle == Bundle.main.bundleIdentifier || bundle == "com.apple.finder" { return nothing }
    var focusedEl: AXUIElement? = nil
    func make(_ text: String, _ mode: String, _ anchor: CGRect?) -> GrabResult {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nothing }
        if t.count > maxChars {
            return .refused("That's \(t.count) characters, more than a message. Select the part to rewrite.")
        }
        return .ok(Grab(text: text, mode: mode, pid: pid, bundle: bundle, app: name,
                        title: title, anchor: anchor, element: focusedEl))
    }

    let focused = axElement(appEl, kAXFocusedUIElementAttribute)
    focusedEl = focused
    var role = ""
    var anchor: CGRect? = nil
    if let f = focused {
        role = axString(f, kAXRoleAttribute) ?? ""
        if (axString(f, kAXSubroleAttribute) ?? "") == (kAXSecureTextFieldSubrole as String) {
            return .refused("That's a password field. The pen leaves those alone.")
        }
        anchor = axFrame(f)
        if let sel = axString(f, kAXSelectedTextAttribute),
           !sel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return make(sel, "selection", anchor)
        }
        if textRoles.contains(role), role != "AXWebArea", let v = axString(f, kAXValueAttribute),
           !v.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return make(v, "whole", anchor)
        }
    }

    // The app keeps its text from Accessibility: copy it instead, and put
    // her clipboard back afterwards.
    waitForModifiersUp()
    let saved = saveClipboard()
    defer { restoreClipboard(saved) }
    if let s = copyNow(), !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        return make(s, "selection", anchor)
    }
    // Select-all only where it can only mean the box: a text role, or an
    // app that told us nothing at all. In a file list ⌘A means files.
    guard focused == nil || textRoles.contains(role) else { return nothing }
    press(kVK_ANSI_A)
    usleep(60_000)
    if let s = copyNow() { return make(s, "whole", anchor) }
    return nothing
}

/// Paste the rewrite over her text, then give her clipboard back. Apps
/// built on Chrome (Beeper, Slack, WhatsApp's web app) read the clipboard
/// late: with her clipboard restored after 0.9 s, Beeper pasted the
/// screenshot she had copied instead of the rewrite (7 Oct). So the
/// restore waits three seconds, and only happens if nothing else has
/// touched the clipboard since: a copy she makes meanwhile is never undone.
func putBack(_ text: String, into g: Grab) {
    let saved = saveClipboard()
    let pb = NSPasteboard.general
    putOnClipboard(text)
    NSRunningApplication(processIdentifier: g.pid)?.activate()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
        waitForModifiersUp()
        if g.mode == "whole" {
            press(kVK_ANSI_A)
            usleep(80_000)
        }
        // A clipboard manager can rewrite the clipboard in between.
        if pb.string(forType: .string) != text { putOnClipboard(text) }
        let ours = pb.changeCount
        press(kVK_ANSI_V)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            if pb.changeCount == ours { restoreClipboard(saved) }
        }
    }
}

/// ⌘V, ⌘C, ⌘X, ⌘A, ⌘Z and ⇧⌘Z in Brain Pen's own text boxes. A menu-bar
/// app has no Edit menu on screen, and without one those keys do nothing
/// in a text field: pasting into the panel failed (7 Oct).
func editKey(_ e: NSEvent, from sender: Any?) -> Bool {
    let mods = e.modifierFlags.intersection(.deviceIndependentFlagsMask).subtracting([.capsLock, .numericPad, .function])
    guard let ch = e.charactersIgnoringModifiers?.lowercased() else { return false }
    var sel: Selector? = nil
    if mods == .command {
        sel = ["v": #selector(NSText.paste(_:)), "c": #selector(NSText.copy(_:)),
               "x": #selector(NSText.cut(_:)), "a": #selector(NSText.selectAll(_:)),
               "z": Selector(("undo:"))][ch]
    } else if mods == [.command, .shift] && ch == "z" {
        sel = Selector(("redo:"))
    }
    guard let s = sel else { return false }
    // Straight to the text box with the cursor: the panel floats over
    // another app, so the app-wide route can find no key window.
    if let w = sender as? NSWindow, let r = w.firstResponder, r.tryToPerform(s, with: sender) { return true }
    return NSApp.sendAction(s, to: nil, from: sender)
}

final class EditWindow: NSWindow {
    override func performKeyEquivalent(with e: NSEvent) -> Bool {
        editKey(e, from: self) || super.performKeyEquivalent(with: e)
    }
}

/// The hidden menu that gives those keys somewhere to go.
func installEditMenu() {
    let main = NSMenu()
    let appItem = NSMenuItem()
    main.addItem(appItem)
    let appMenu = NSMenu()
    appMenu.addItem(NSMenuItem(title: "Quit Brain Pen", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
    appItem.submenu = appMenu
    let editItem = NSMenuItem()
    main.addItem(editItem)
    let edit = NSMenu(title: "Edit")
    edit.addItem(NSMenuItem(title: "Undo", action: Selector(("undo:")), keyEquivalent: "z"))
    let redo = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
    redo.keyEquivalentModifierMask = [.command, .shift]
    edit.addItem(redo)
    edit.addItem(.separator())
    edit.addItem(NSMenuItem(title: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x"))
    edit.addItem(NSMenuItem(title: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c"))
    edit.addItem(NSMenuItem(title: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v"))
    edit.addItem(NSMenuItem(title: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a"))
    editItem.submenu = edit
    NSApp.mainMenu = main
}

/// Still where she was when the shortcut grabbed the text? A rewrite that
/// went straight in without the panel must not land in a box she has since
/// left, or over words she typed while it was being written.
func stillThere(_ g: Grab) -> Bool {
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == g.pid else { return false }
    guard let el = g.element else { return true }
    let appEl = AXUIElementCreateApplication(g.pid)
    guard let now = axElement(appEl, kAXFocusedUIElementAttribute), CFEqual(now, el) else { return false }
    if g.mode == "whole", let v = axString(el, kAXValueAttribute) { return v == g.text }
    if g.mode == "selection", let sel = axString(el, kAXSelectedTextAttribute) { return sel == g.text }
    return true
}

// MARK: - shortcuts she sets herself

/// One key combination, in Carbon's terms (what RegisterEventHotKey takes).
struct Combo: Codable, Equatable {
    var key: UInt32
    var mods: UInt32
    var label: String
}

let defaultTones: [(String, String)] = [
    ("polish", "Polished"), ("fix", "Fix typos"), ("warmer", "Warmer"), ("politer", "Politer"),
    ("casual", "Casual"), ("shorter", "Shorter"), ("en", "English"), ("fr", "Français"),
    ("es", "Español"),
]
/// The panel's buttons: the same tones, short enough for one compact row.
let chipLabels: [String: String] = ["polish": "Polish", "fix": "Fix", "en": "EN", "fr": "FR", "es": "ES"]

/// Languages where the reader's gender and tu/vous change the words.
let gendered: Set<String> = ["fr", "es", "de", "it", "pt"]
let addressWords: [String: (String, String)] = [
    "fr": ("Tu", "Vous"), "es": ("Tú", "Usted"), "de": ("Du", "Sie"), "it": ("Tu", "Lei"), "pt": ("Tu", "Você"),
]
let readerChoices: [(String, String)] = [
    ("auto", "Reader: auto"), ("m", "A man"), ("f", "A woman"), ("x", "Not sure"), ("group", "A group"),
]

/// What a shortcut can do: open the panel, put one tone straight into the
/// box without it, or open the training window.
let shortcutActions: [(String, String)] =
    [("open", "Open the pen")]
    + defaultTones.map { ("tone:" + $0.0, $0.1 + ", straight into the box") }
    + [("read", "How does this read?"), ("train", "Open these settings")]

let defaultCombos: [String: Combo] = [
    "open": Combo(key: UInt32(kVK_ANSI_R), mods: UInt32(controlKey | optionKey), label: "⌃⌥R"),
    "tone:fix": Combo(key: UInt32(kVK_ANSI_T), mods: UInt32(controlKey | optionKey), label: "⌃⌥T"),
    "read": Combo(key: UInt32(kVK_ANSI_H), mods: UInt32(controlKey | optionKey), label: "⌃⌥H"),
]

func keyName(_ e: NSEvent) -> String {
    let named: [Int: String] = [
        kVK_Space: "Space", kVK_Return: "↩", kVK_Tab: "⇥", kVK_LeftArrow: "←",
        kVK_RightArrow: "→", kVK_UpArrow: "↑", kVK_DownArrow: "↓", kVK_F1: "F1", kVK_F2: "F2",
        kVK_F3: "F3", kVK_F4: "F4", kVK_F5: "F5", kVK_F6: "F6", kVK_F7: "F7", kVK_F8: "F8",
        kVK_F9: "F9", kVK_F10: "F10", kVK_F11: "F11", kVK_F12: "F12",
    ]
    if let n = named[Int(e.keyCode)] { return n }
    return (e.charactersIgnoringModifiers ?? "?").uppercased()
}

/// The combination a key press makes, or nil when it has no ⌃, ⌥ or ⌘
/// (a bare letter as a global shortcut would eat that letter everywhere).
func comboFrom(_ e: NSEvent) -> Combo? {
    let f = e.modifierFlags.intersection(.deviceIndependentFlagsMask)
    guard f.contains(.control) || f.contains(.option) || f.contains(.command) else { return nil }
    var m: UInt32 = 0
    var l = ""
    if f.contains(.control) { m |= UInt32(controlKey); l += "⌃" }
    if f.contains(.option) { m |= UInt32(optionKey); l += "⌥" }
    if f.contains(.shift) { m |= UInt32(shiftKey); l += "⇧" }
    if f.contains(.command) { m |= UInt32(cmdKey); l += "⌘" }
    return Combo(key: UInt32(e.keyCode), mods: m, label: l + keyName(e))
}

final class Hotkeys: ObservableObject {
    @Published var combos: [String: Combo] = [:]
    @Published var taken: Set<String> = []
    @Published var recording: String? = nil
    @Published var message: String? = nil
    var refs: [EventHotKeyRef] = []
    var byID: [UInt32: String] = [:]
    var monitor: Any? = nil
    let store = "shortcuts"

    init() {
        if let d = UserDefaults.standard.data(forKey: store),
           let c = try? JSONDecoder().decode([String: Combo].self, from: d) {
            combos = c
            if UserDefaults.standard.object(forKey: "shortcuts-has-read") == nil, c["read"] == nil,
               !c.values.contains(defaultCombos["read"]!) {
                combos["read"] = defaultCombos["read"]
            }
            UserDefaults.standard.set(true, forKey: "shortcuts-has-read")
        } else {
            combos = defaultCombos
        }
        // Carbon hands every hotkey to one handler; the id says which.
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
            var hk = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                              nil, MemoryLayout<EventHotKeyID>.size, nil, &hk)
            let id = hk.id
            DispatchQueue.main.async { AppDelegate.shared?.hotkey(id) }
            return noErr
        }, 1, &spec, nil, nil)
    }

    func save() {
        if let d = try? JSONEncoder().encode(combos) { UserDefaults.standard.set(d, forKey: store) }
    }

    func registerAll() {
        unregisterAll()
        var taken = Set<String>()
        for (i, a) in shortcutActions.enumerated() {
            guard let c = combos[a.0] else { continue }
            var ref: EventHotKeyRef?
            let id = EventHotKeyID(signature: OSType(0x4250_454E), id: UInt32(i + 1))   // 'BPEN'
            if RegisterEventHotKey(c.key, c.mods, id, GetApplicationEventTarget(), 0, &ref) == noErr, let r = ref {
                refs.append(r)
                byID[UInt32(i + 1)] = a.0
            } else {
                taken.insert(a.0)
            }
        }
        self.taken = taken
    }

    func unregisterAll() {
        for r in refs { UnregisterEventHotKey(r) }
        refs = []
        byID = [:]
    }

    func label(_ action: String) -> String { combos[action]?.label ?? "" }

    /// Listen for the next key press and make it this action's shortcut.
    /// Esc cancels; Delete clears it.
    func record(_ action: String) {
        stop()
        recording = action
        message = "Press the keys for “\(shortcutActions.first { $0.0 == action }?.1 ?? action)”. Esc cancels, Delete clears it."
        unregisterAll()                     // so the old combination can be pressed again
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self = self, let a = self.recording else { return e }
            switch Int(e.keyCode) {
            case kVK_Escape:
                self.message = nil
            case kVK_Delete, kVK_ForwardDelete:
                self.combos[a] = nil
                self.message = nil
            default:
                guard let c = comboFrom(e) else {
                    self.message = "Use ⌃, ⌥ or ⌘ with the key, so it doesn't take that key from every app."
                    return nil
                }
                if let what = blockedCombos[c.label] {
                    self.message = "\(c.label) is \(what) in almost every app, and Brain Pen would take it from all of them. Press another combination."
                    return nil
                }
                if let other = self.combos.first(where: { $0.key != a && $0.value == c }) {
                    let name = shortcutActions.first { $0.0 == other.key }?.1 ?? other.key
                    self.message = "\(c.label) is already “\(name)”."
                    return nil
                }
                self.combos[a] = c
                self.message = nil
            }
            self.stop()
            self.save()
            self.registerAll()
            return nil
        }
    }

    func stop() {
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        if recording != nil {
            recording = nil
            registerAll()
        }
    }

    func reset() {
        stop()
        combos = defaultCombos
        message = nil
        save()
        registerAll()
    }
}

// MARK: - the toast (for the shortcuts that skip the panel)

final class ToastModel: ObservableObject {
    @Published var text = ""
    @Published var bad = false
    @Published var busy = false
}

struct ToastView: View {
    @ObservedObject var m: ToastModel
    var body: some View {
        HStack(spacing: 8) {
            if m.busy { ProgressView().controlSize(.small) }
            else { Image(systemName: m.bad ? "exclamationmark.circle" : "pencil.line").foregroundStyle(.secondary) }
            Text(m.text).font(.system(size: 13)).lineLimit(6).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
        .frame(maxWidth: 420, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(.regularMaterial))
        .fixedSize()
    }
}

final class Toast {
    let m = ToastModel()
    let panel: NSPanel
    var hideAt: DispatchWorkItem?

    init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 300, height: 40),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.level = .floating
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = NSHostingView(rootView: ToastView(m: m))
    }

    /// Shown under the caret when the app says where it is, else by the
    /// mouse. `secs` nil keeps it up until the next call.
    func show(_ text: String, near anchor: CGRect?, bad: Bool = false, busy: Bool = false, secs: Double? = 2.4) {
        m.text = text; m.bad = bad; m.busy = busy
        let size = panel.contentView?.fittingSize ?? NSSize(width: 300, height: 40)
        let primary = NSScreen.screens.first?.frame.height ?? 900
        var p: NSPoint
        if let a = anchor { p = NSPoint(x: a.minX, y: primary - a.maxY - 8 - size.height) }
        else { let mm = NSEvent.mouseLocation; p = NSPoint(x: mm.x + 12, y: mm.y - 20 - size.height) }
        if let vis = (NSScreen.screens.first { NSPointInRect(NSEvent.mouseLocation, $0.frame) } ?? NSScreen.main)?.visibleFrame {
            p.x = min(max(p.x, vis.minX + 8), vis.maxX - size.width - 8)
            p.y = min(max(p.y, vis.minY + 8), vis.maxY - size.height - 8)
        }
        panel.setFrame(NSRect(origin: p, size: size), display: true)
        panel.orderFrontRegardless()
        hideAt?.cancel()
        if let s = secs {
            let w = DispatchWorkItem { [weak self] in self?.panel.orderOut(nil) }
            hideAt = w
            DispatchQueue.main.asyncAfter(deadline: .now() + s, execute: w)
        }
    }
}

// MARK: - what changed

/// Words with the spaces after them, so joining the pieces gives the text
/// back exactly.
func diffTokens(_ s: String) -> [String] {
    var out: [String] = []
    var cur = ""
    var inSpace = false
    for ch in s {
        if ch.isWhitespace { cur.append(ch); inSpace = true }
        else {
            if inSpace && !cur.isEmpty { out.append(cur); cur = "" }
            inSpace = false
            cur.append(ch)
        }
    }
    if !cur.isEmpty { out.append(cur) }
    return out
}

/// A piece of the rewrite: unchanged words, or one change (her words → the
/// rewrite's words), found by longest common subsequence over words.
struct Piece {
    var same: String? = nil
    var old: String = ""
    var new: String = ""
}

func diffPieces(_ before: String, _ after: String) -> [Piece] {
    let a = diffTokens(before), b = diffTokens(after)
    let ka = a.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    let kb = b.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    let n = a.count, m = b.count
    guard n * m < 4_000_000 else { return [Piece(old: before, new: after)] }
    var dp = Array(repeating: Array(repeating: 0, count: m + 1), count: n + 1)
    if n > 0 && m > 0 {
        for i in stride(from: n - 1, through: 0, by: -1) {
            for j in stride(from: m - 1, through: 0, by: -1) {
                dp[i][j] = ka[i] == kb[j] ? dp[i + 1][j + 1] + 1 : max(dp[i + 1][j], dp[i][j + 1])
            }
        }
    }
    var out: [Piece] = []
    var i = 0, j = 0
    func change(_ o: String, _ nw: String) {
        if let last = out.last, last.same == nil { out[out.count - 1].old += o; out[out.count - 1].new += nw }
        else { out.append(Piece(old: o, new: nw)) }
    }
    while i < n || j < m {
        if i < n && j < m && ka[i] == kb[j] {
            if let last = out.last, let s = last.same { out[out.count - 1].same = s + b[j] }
            else { out.append(Piece(same: b[j])) }
            i += 1; j += 1
        } else if j >= m || (i < n && dp[i + 1][j] >= dp[i][j + 1]) {
            change(a[i], ""); i += 1
        } else {
            change("", b[j]); j += 1
        }
    }
    return out
}

func trailingSpace(_ s: String) -> String {
    String(s.reversed().prefix { $0.isWhitespace }.reversed())
}

// MARK: - the panel

final class Pen: ObservableObject {
    @Published var text = ""
    @Published var tone = "polish"
    @Published var feedback = ""
    @Published var busy = false
    @Published var problem: String? = nil
    @Published var notes: [String] = []
    @Published var tones: [(String, String)] = defaultTones
    @Published var where_ = ""
    @Published var tip: [String: Any]? = nil
    @Published var focusEditor = false
    @Published var showChanges = UserDefaults.standard.object(forKey: "showChanges") as? Bool ?? true {
        didSet { UserDefaults.standard.set(showChanges, forKey: "showChanges") }
    }
    @Published var reading: String? = nil
    @Published var readBusy = false
    @Published var checkLines: [String]? = nil
    @Published var checkBusy = false
    var checked: Int? = nil
    /// Changes she clicked back to her own words, per tone: a tone she
    /// keeps undoing is told to change less.
    var reverts: [String: Int] = [:]
    @Published var pasteMode = false
    @Published var input = ""
    var pasteContext: Grab? = nil
    var pasteTone = "polish"
    @Published var address = "auto"
    @Published var reader = "auto"
    @Published var person = ""
    var lang = ""
    var grab: Grab? = nil
    var demo = false
    var cache: [String: String] = [:]
    var seq = 0
    var lastResult = ""
    var rewrites = 0
    var close: (Bool) -> Void = { _ in }
    var settings: () -> Void = {}
    var dismiss: () -> Void = {}

    func start(_ g: Grab, demo: Bool = false) {
        grab = g
        self.demo = demo
        text = ""; feedback = ""; problem = nil; notes = []; cache = [:]; rewrites = 0; tip = nil
        reading = nil; readBusy = false
        checkLines = nil; checkBusy = false; checked = nil; reverts = [:]
        address = "auto"; reader = "auto"; person = ""
        let rec = NLLanguageRecognizer()
        rec.processString(g.text)
        lang = rec.dominantLanguage?.rawValue ?? ""
        tone = "polish"
        focusEditor = false
        where_ = "\(g.app) · " + (g.mode == "selection" ? "your selection" : "the whole box")
        run("polish")
    }

    /// Nothing was selected: a box to paste or type the text into.
    func startPaste(_ ctx: Grab, tone: String = "polish") {
        refuse("")
        problem = nil
        pasteContext = ctx
        pasteTone = tone
        input = ""
        pasteMode = true
        where_ = "Nothing selected · paste or type the text"
    }

    func rewritePasted() {
        let t = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var g = pasteContext, !t.isEmpty else { return }
        g.text = t
        g.mode = "paste"
        pasteMode = false
        start(g)
        where_ = "\(g.app) · pasted text"
        if pasteTone != "polish" { run(pasteTone) }
    }

    func refuse(_ why: String) {
        pasteMode = false
        grab = nil
        text = ""; feedback = ""; notes = []; busy = false; tip = nil
        checkLines = nil
        where_ = ""
        problem = why
    }

    func run(_ t: String, again: Bool = false) {
        guard let g = grab else { return }
        tone = t
        if !again, let c = cache[t] { text = c; lastResult = c; problem = nil; return }
        seq += 1
        let mine = seq
        busy = true
        problem = nil
        api("/api/pen/rewrite", ["text": g.text, "tone": t, "bundle": g.bundle, "app": g.app,
                                 "title": g.title, "mode": g.mode, "feedback": notes,
                                 "again": again, "address": address, "reader": reader]) { out, err in
            guard mine == self.seq else { return }
            self.busy = false
            if let err = err { self.problem = err; return }
            let s = (out?["text"] as? String) ?? ""
            self.cache[t] = s
            self.text = s
            self.lastResult = s
            self.rewrites += 1
            if let tip = out?["tip"] as? [String: Any] { self.tip = tip }
            self.person = (out?["person"] as? String) ?? ""
        }
    }

    /// The language the rewrite comes out in: the tone's, else the text's.
    var outLang: String { ["en", "fr", "es"].contains(tone) ? tone : lang }
    var showsAddress: Bool { gendered.contains(outLang) }

    func setAddress(_ a: String) { guard a != address else { return }; address = a; cache = [:]; run(tone) }
    func setReader(_ r: String) { guard r != reader else { return }; reader = r; cache = [:]; run(tone) }
    func cycleAddress() {
        guard showsAddress else { return }
        setAddress(["auto": "informal", "informal": "formal", "formal": "auto"][address] ?? "auto")
    }
    func cycleReader() {
        guard showsAddress else { return }
        let keys = readerChoices.map { $0.0 }
        setReader(keys[((keys.firstIndex(of: reader) ?? 0) + 1) % keys.count])
    }

    func another() { if grab != nil && !busy { run(tone, again: true) } }

    /// A translation changes every word: there is nothing to compare.
    var comparable: Bool { !["en", "fr", "es"].contains(tone) }

    var pieces: [Piece] { diffPieces(grab?.text ?? "", text) }

    /// Put her own words back for one change.
    func revert(_ k: Int) {
        var ps = pieces
        guard k >= 0, k < ps.count, ps[k].same == nil else { return }
        let ws = trailingSpace(ps[k].new)
        var old = ps[k].old
        if !old.isEmpty, k + 1 < ps.count {
            old = String(old.reversed().drop { $0.isWhitespace }.reversed()) + (ws.isEmpty ? " " : ws)
        }
        ps[k] = Piece(same: old)
        text = ps.map { $0.same ?? $0.new }.joined()
        reverts[tone, default: 0] += 1
        lastResult = text          // a put-back is not a hand edit
    }

    /// How her own message will land, without changing a word.
    func readIt() {
        guard let g = grab, !readBusy else { return }
        readBusy = true
        reading = nil
        api("/api/pen/read", ["text": g.text, "bundle": g.bundle, "app": g.app, "title": g.title]) { out, err in
            self.readBusy = false
            self.reading = err ?? ((out?["read"] as? String) ?? "")
        }
    }

    /// What her notes say this message gets wrong (⌘B). It never changes
    /// the text: it says what disagrees, and she decides.
    func checkIt() {
        guard let g = grab, !checkBusy else { return }
        checkBusy = true
        checkLines = nil
        api("/api/pen/check", ["text": g.text, "bundle": g.bundle, "app": g.app, "title": g.title]) { out, err in
            self.checkBusy = false
            if let err = err { self.checkLines = [err]; return }
            self.checkLines = (out?["lines"] as? [String]) ?? []
            self.checked = (out?["flags"] as? [Any])?.count ?? 0
        }
    }

    func pickTone(_ i: Int) { if i < tones.count { run(tones[i].0) } }

    /// Return in the feedback line: a note means "again, with this";
    /// an empty line means "use it".
    func enter() {
        let note = feedback.trimmingCharacters(in: .whitespacesAndNewlines)
        if note.isEmpty { use(); return }
        notes.append(note)
        feedback = ""
        cache = [:]
        run(tone)
    }

    /// Pasted text has no box to go back into: Replace becomes Copy.
    var pasted: Bool { grab?.mode == "paste" }

    func use() {
        guard grab != nil, !busy, !text.isEmpty else { return }
        if pasted { copy(); return }
        close(true)
    }

    func copy() {
        guard !text.isEmpty else { return }
        putOnClipboard(text)
        close(false)
    }

    func report(used: Bool) {
        guard let g = grab, rewrites > 0, !demo else { return }
        api("/api/pen/done", ["app": g.app, "bundle": g.bundle, "tone": tone, "used": used,
                              "notes": notes, "chars": g.text.count, "title": g.title,
                              "edited": used && text != lastResult, "text": g.text,
                              "reverts": reverts, "checked": checked ?? -1]) { _, _ in }
    }
}

struct Chip: View {
    let label: String
    let on: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 11.5, weight: on ? .semibold : .regular))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(RoundedRectangle(cornerRadius: 7)
                    .fill(on ? Color.accentColor.opacity(0.18) : Color.primary.opacity(0.06)))
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .stroke(on ? Color.accentColor.opacity(0.6) : Color.clear, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

/// A shortcut with no button of its own.
struct KeyOnly: View {
    let key: KeyEquivalent
    var mods: SwiftUI.EventModifiers = .command
    let action: () -> Void
    var body: some View {
        Button("", action: action).keyboardShortcut(key, modifiers: mods)
            .opacity(0).frame(width: 0, height: 0).accessibilityHidden(true)
    }
}

struct PenView: View {
    @ObservedObject var pen: Pen
    enum Field { case note, editor }
    @FocusState private var focus: Field?

    var tipLine: String? {
        guard let t = pen.tip, let w = t["wrong"] as? String, let r = t["right"] as? String else { return nil }
        let n = (t["count"] as? Int) ?? 0
        let rule = (t["rule"] as? String) ?? ""
        return "Worth remembering: “\(w)” is “\(r)”. \(rule)" + (n > 1 ? " (\(n) times lately)" : "")
    }

    /// Her words struck through, the rewrite's words marked; each change is
    /// a link that puts her words back.
    var changesText: AttributedString {
        var out = AttributedString()
        for (k, p) in pen.pieces.enumerated() {
            if let s = p.same { out += AttributedString(s); continue }
            let link = URL(string: "penrevert://\(k)")
            if !p.old.isEmpty {
                var o = AttributedString(p.old.trimmingCharacters(in: .whitespacesAndNewlines))
                o.strikethroughStyle = .single
                o.foregroundColor = .secondary
                o.backgroundColor = Color.red.opacity(0.14)
                o.link = link
                out += o
                if !p.new.isEmpty { out += AttributedString(" ") }
                else { out += AttributedString(trailingSpace(p.old)) }
            }
            if !p.new.isEmpty {
                var nw = AttributedString(p.new.trimmingCharacters(in: .whitespacesAndNewlines))
                nw.backgroundColor = Color.green.opacity(0.18)
                nw.link = link
                out += nw
                out += AttributedString(trailingSpace(p.new))
            }
        }
        return out
    }

    var header: String {
        var h = pen.where_.isEmpty ? "Brain Pen" : pen.where_
        if !pen.person.isEmpty { h += " · to \(pen.person)" }
        return h
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "pencil.line").foregroundStyle(.secondary).font(.system(size: 11))
                Text(header).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                if pen.grab != nil && pen.showsAddress {
                    let w = addressWords[pen.outLang] ?? ("Informal", "Formal")
                    Picker("", selection: Binding(get: { pen.address }, set: { pen.setAddress($0) })) {
                        Text("\(w.0)/\(w.1): auto").tag("auto")
                        Text(w.0).tag("informal")
                        Text(w.1).tag("formal")
                    }
                    .pickerStyle(.menu).labelsHidden().fixedSize().controlSize(.mini)
                    .help("⌘T")
                    Picker("", selection: Binding(get: { pen.reader }, set: { pen.setReader($0) })) {
                        ForEach(readerChoices, id: \.0) { c in Text(c.1).tag(c.0) }
                    }
                    .pickerStyle(.menu).labelsHidden().fixedSize().controlSize(.mini)
                    .help("Who you're writing to, for agreement (⌘G)")
                }
                if pen.busy { ProgressView().controlSize(.mini) }
                Button { pen.dismiss() } label: {
                    Image(systemName: "xmark.circle.fill").font(.system(size: 15)).foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Close (esc)")
                .accessibilityLabel("Close")
            }
            if pen.pasteMode {
                ZStack(alignment: .topLeading) {
                    TextEditor(text: $pen.input)
                        .font(.system(size: 14))
                        .scrollContentBackground(.hidden)
                        .padding(5)
                        .frame(height: 96)
                        .background(RoundedRectangle(cornerRadius: 7).fill(Color.primary.opacity(0.04)))
                        .focused($focus, equals: .editor)
                    if pen.input.isEmpty {
                        Text("Paste or type what you want to rewrite (⌘V)")
                            .font(.system(size: 14)).foregroundStyle(.secondary)
                            .padding(.horizontal, 10).padding(.vertical, 5)
                            .allowsHitTesting(false)
                    }
                }
                HStack {
                    Text("Nothing was selected, so the rewrite goes on your clipboard.")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                    Spacer()
                    Button("Rewrite") { pen.rewritePasted() }
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(pen.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .help("⌘↩")
                }
            }
            if pen.grab != nil {
                HStack(spacing: 4) {
                    ForEach(Array(pen.tones.enumerated()), id: \.offset) { i, t in
                        Chip(label: chipLabels[t.0] ?? t.1, on: pen.tone == t.0) { pen.run(t.0) }
                            .keyboardShortcut(KeyEquivalent(Character(String(i + 1))), modifiers: .command)
                            .help("\(t.1)  ⌘\(i + 1)")
                    }
                }
                if pen.showChanges && pen.comparable && !pen.text.isEmpty && !pen.busy {
                    ScrollView {
                        Text(changesText)
                            .font(.system(size: 14))
                            .tint(.primary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(8)
                            .environment(\.openURL, OpenURLAction { url in
                                if url.scheme == "penrevert", let k = Int(url.host ?? "") { pen.revert(k) }
                                return .handled
                            })
                    }
                    .frame(minHeight: 56, maxHeight: 240)
                    .fixedSize(horizontal: false, vertical: true)
                    .background(RoundedRectangle(cornerRadius: 7).fill(Color.primary.opacity(0.04)))
                    .help("Click a change to put your words back")
                } else {
                    ZStack(alignment: .topLeading) {
                        TextEditor(text: $pen.text)
                            .font(.system(size: 14))
                            .scrollContentBackground(.hidden)
                            .padding(5)
                            .frame(minHeight: 56, maxHeight: 240)
                            .background(RoundedRectangle(cornerRadius: 7).fill(Color.primary.opacity(0.04)))
                            .focused($focus, equals: .editor)
                        if pen.text.isEmpty && pen.busy {
                            Text("Rewriting in your voice…")
                                .font(.system(size: 14)).foregroundStyle(.tertiary)
                                .padding(.horizontal, 10).padding(.vertical, 5)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            if pen.readBusy || pen.reading != nil {
                HStack(alignment: .top, spacing: 5) {
                    Text("Reads:").font(.system(size: 11, weight: .semibold))
                    if pen.readBusy { ProgressView().controlSize(.mini) }
                    else { Text(pen.reading ?? "").font(.system(size: 11)).fixedSize(horizontal: false, vertical: true) }
                }
            }
            if pen.checkBusy || pen.checkLines != nil {
                HStack(alignment: .top, spacing: 5) {
                    Text("Brain check:").font(.system(size: 11, weight: .semibold))
                    if pen.checkBusy { ProgressView().controlSize(.mini) }
                    else {
                        VStack(alignment: .leading, spacing: 2) {
                            ForEach(Array((pen.checkLines ?? []).enumerated()), id: \.offset) { _, l in
                                Text(l).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
            if let tip = tipLine {
                Text(tip).font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let p = pen.problem {
                Text(p).font(.system(size: 11)).foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if pen.grab != nil {
                HStack(spacing: 8) {
                    TextField(pen.notes.isEmpty ? "What should change? Return redoes it, empty Return replaces"
                              : "You said: " + pen.notes.joined(separator: " · "),
                              text: $pen.feedback)
                        .textFieldStyle(.roundedBorder)
                        .controlSize(.small)
                        .focused($focus, equals: .note)
                        .onSubmit { pen.enter() }
                    Button(pen.demo || pen.pasted ? "Copy" : "Replace") { pen.use() }
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(pen.text.isEmpty || pen.busy)
                        .help(pen.pasted ? "Puts the rewrite on your clipboard  ⌘↩"
                              : "Puts the rewrite in place of your text  ⌘↩")
                }
                Text("⌘1–9 tone · ⌘R again · ⌘D changes · ⌘I how it reads · ⌘B brain check · ⌘E edit"
                     + (pen.showsAddress ? " · ⌘T address · ⌘G reader" : "") + " · ⌘⇧C copy · esc")
                    .font(.system(size: 10)).foregroundStyle(.tertiary).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(width: 560)
        .background {
            KeyOnly(key: "r") { pen.another() }
            KeyOnly(key: "e") { pen.showChanges = false; DispatchQueue.main.async { focus = .editor } }
            KeyOnly(key: "l") { focus = .note }
            KeyOnly(key: "d") { pen.showChanges.toggle() }
            KeyOnly(key: "i") { pen.readIt() }
            KeyOnly(key: "b") { pen.checkIt() }
            KeyOnly(key: "t") { pen.cycleAddress() }
            KeyOnly(key: "g") { pen.cycleReader() }
            KeyOnly(key: "c", mods: [.command, .shift]) { pen.copy() }
            KeyOnly(key: ",") { pen.settings() }
        }
        .onAppear { focus = pen.pasteMode ? .editor : .note }
        .onChange(of: pen.where_) { _ in focus = pen.pasteMode ? .editor : .note }
    }
}

final class KeyPanel: NSPanel {
    var onCancel: () -> Void = {}
    /// The panel grows as the rewrite comes in; its top edge stays put, so
    /// it never slides over the line she is writing.
    var topY: CGFloat? = nil
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { onCancel() }
    override func performKeyEquivalent(with e: NSEvent) -> Bool {
        editKey(e, from: self) || super.performKeyEquivalent(with: e)
    }
    override func setFrame(_ frameRect: NSRect, display flag: Bool) {
        var r = frameRect
        if let top = topY {
            r.origin.y = top - r.height
            // Past the bottom of the screen it grows upwards instead.
            if let vis = (screen ?? NSScreen.main)?.visibleFrame, r.origin.y < vis.minY + 8 {
                r.origin.y = vis.minY + 8
            }
        }
        super.setFrame(r, display: flag)
    }
}

// MARK: - the settings window: setup until it's done, then voice, learning, shortcuts

/// Combinations apps already rely on. The first group would break basics in
/// every app, so the recorder refuses them; the rest it warns about.
let blockedCombos: [String: String] = [
    "⌘Z": "Undo", "⇧⌘Z": "Redo", "⌘C": "Copy", "⌘V": "Paste", "⌘X": "Cut",
    "⌘A": "Select all", "⌘S": "Save", "⌘Q": "Quit", "⌘W": "Close", "⌘⇥": "switching apps",
    "⌘Space": "Spotlight",
]
let warnedCombos: [String: String] = [
    "⌘T": "new tab", "⌘N": "new window", "⌘F": "Find", "⌘P": "Print", "⌘R": "reload",
    "⌘H": "hide", "⌘M": "minimise", "⌘O": "open", "⌘B": "bold", "⌘I": "italic",
    "⌘U": "underline", "⌘L": "the address bar", "⌥Space": "Alfred", "⌃Space": "switching keyboard language",
    "⌃⌥Space": "switching keyboard language", "⇧⌘4": "screenshots", "⇧⌘3": "screenshots",
    "⇧⌘5": "screenshots", "⌃⌘Space": "emoji",
]
func clash(_ label: String) -> String? { blockedCombos[label] ?? warnedCombos[label] }

final class Trainer: ObservableObject {
    @Published var tab = 0
    @Published var trusted = AXIsProcessTrusted()
    @Published var openKeys = ""
    @Published var sections: [(String, Int)] = []
    @Published var heading = ""
    @Published var sample = ""
    @Published var status: String? = nil
    @Published var notes: [[String: Any]] = []
    @Published var learning = false
    @Published var patterns: [[String: Any]] = []
    @Published var showRules = false
    @Published var seenNotch = UserDefaults.standard.bool(forKey: "seenNotchNote") {
        didSet { UserDefaults.standard.set(seenNotch, forKey: "seenNotchNote") }
    }
    var samplesFile = ""

    func load() {
        api("/api/pen/state") { out, err in
            if let err = err { self.status = err; return }
            self.take(out)
        }
    }

    func take(_ out: [String: Any]?) {
        if let s = out?["sections"] as? [[String: Any]] {
            sections = s.map { (($0["heading"] as? String) ?? "", ($0["count"] as? Int) ?? 0) }
            if heading.isEmpty || !sections.contains(where: { $0.0 == heading }) {
                heading = sections.first?.0 ?? ""
            }
        }
        if let n = out?["notes"] as? [[String: Any]] { notes = n }
        if let f = out?["samples_file"] as? String { samplesFile = f }
        if let l = out?["learning"] as? Bool { learning = l }
        if let p = out?["patterns"] as? [[String: Any]] { patterns = p }
    }

    func save() {
        let s = sample.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty, !heading.isEmpty else { return }
        api("/api/pen/sample", ["heading": heading, "text": s]) { out, err in
            if let err = err { self.status = err; return }
            self.sample = ""
            self.take(out)
            self.status = "Saved under \(self.heading)."
        }
    }

    func forget(_ note: String) {
        api("/api/pen/forget", ["note": note]) { out, err in
            if let err = err { self.status = err; return }
            self.take(out)
        }
    }

    func setLearning(_ on: Bool) {
        api("/api/pen/learning", ["on": on]) { out, err in
            if let err = err { self.status = err; return }
            self.take(out)
        }
    }

    func ignore(_ key: String) {
        api("/api/pen/ignore", ["key": key]) { out, err in
            if let err = err { self.status = err; return }
            self.take(out)
        }
    }

    /// The switch is on but belongs to an older build: clear Brain Pen's
    /// own Accessibility entry and start again, so macOS asks afresh.
    func fixSwitch() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        p.arguments = ["reset", "Accessibility", Bundle.main.bundleIdentifier ?? "local.lifebrain.pen"]
        try? p.run()
        p.waitUntilExit()
        AppDelegate.shared?.restart()
    }
}

let secondaryText = Color.secondary

struct SetupView: View {
    @ObservedObject var t: Trainer
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Set up Brain Pen").font(.system(size: 20, weight: .semibold))
                Text("One switch, then this screen goes away.")
                    .font(.system(size: 13)).foregroundStyle(secondaryText)
            }
            HStack(alignment: .top, spacing: 12) {
                Text("1").font(.system(size: 13, weight: .bold)).frame(width: 24, height: 24)
                    .background(Circle().fill(Color.accentColor.opacity(0.15)))
                VStack(alignment: .leading, spacing: 8) {
                    Text("Let Brain Pen read the box you're typing in").font(.system(size: 14, weight: .semibold))
                    Text("In Accessibility, switch on Brain Pen. This screen notices within two seconds.")
                        .font(.system(size: 13)).foregroundStyle(secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                    Button("Open Accessibility settings") {
                        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
                    }
                    .buttonStyle(.borderedProminent)
                    HStack(spacing: 4) {
                        Text("Switch already on?").font(.system(size: 12)).foregroundStyle(secondaryText)
                        Button("Fix the switch") { t.fixSwitch() }
                            .buttonStyle(.link).font(.system(size: 12))
                            .help("Clears Brain Pen's old entry and restarts it, so macOS asks again")
                    }
                }
            }
            HStack(alignment: .top, spacing: 12) {
                Text("2").font(.system(size: 13, weight: .bold)).frame(width: 24, height: 24)
                    .background(Circle().fill(Color.primary.opacity(0.08)))
                VStack(alignment: .leading, spacing: 6) {
                    Text("Try it").font(.system(size: 14, weight: .semibold))
                    Text("Select text in any app and press \(t.openKeys.isEmpty ? "your shortcut" : t.openKeys). With nothing selected, it opens a box to paste into.")
                        .font(.system(size: 13)).foregroundStyle(secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
        }
        .padding(28)
    }
}

struct VoiceTab: View {
    @ObservedObject var t: Trainer
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Messages you actually sent teach it how you sound. Three of each kind is plenty.")
                .font(.system(size: 13)).foregroundStyle(secondaryText)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(t.sections, id: \.0) { s in
                        let on = t.heading == s.0
                        Button { t.heading = s.0 } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(s.0).font(.system(size: 12, weight: on ? .semibold : .regular)).lineLimit(1)
                                Text(s.1 >= 3 ? "\(s.1) ✓" : "\(s.1) of 3")
                                    .font(.system(size: 11)).foregroundStyle(s.1 >= 3 ? Color.green : secondaryText)
                            }
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(RoundedRectangle(cornerRadius: 8)
                                .fill(on ? Color.accentColor.opacity(0.14) : Color.primary.opacity(0.05)))
                            .overlay(RoundedRectangle(cornerRadius: 8)
                                .stroke(on ? Color.accentColor.opacity(0.5) : Color.clear))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            ZStack(alignment: .topLeading) {
                TextEditor(text: $t.sample)
                    .font(.system(size: 13))
                    .scrollContentBackground(.hidden)
                    .padding(6)
                    .frame(height: 110)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.04)))
                if t.sample.isEmpty {
                    Text("Paste a message you sent (\(t.heading.lowercased()))…")
                        .font(.system(size: 13)).foregroundStyle(secondaryText)
                        .padding(.horizontal, 11).padding(.vertical, 6)
                        .allowsHitTesting(false)
                }
            }
            HStack {
                if let s = t.status { Text(s).font(.system(size: 12)).foregroundStyle(secondaryText) }
                Spacer()
                Button("Open the file") {
                    if !t.samplesFile.isEmpty { NSWorkspace.shared.open(URL(fileURLWithPath: t.samplesFile)) }
                }
                .buttonStyle(.link).font(.system(size: 12))
                Button("Save") { t.save() }
                    .keyboardShortcut(.return, modifiers: .command)
                    .buttonStyle(.borderedProminent)
                    .disabled(t.sample.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .help("⌘↩")
            }
            Divider().padding(.vertical, 4)
            Text("What your feedback taught it").font(.system(size: 13, weight: .semibold))
            if t.notes.isEmpty {
                Text("When a rewrite misses, type a note in the panel, like “too stiff”, and press Return. Notes land here, and the last ten go into every rewrite.")
                    .font(.system(size: 12)).foregroundStyle(secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(t.notes.enumerated()), id: \.offset) { _, n in
                            let note = (n["note"] as? String) ?? ""
                            HStack(alignment: .firstTextBaseline) {
                                Text("“\(note)”").font(.system(size: 13))
                                Text("\((n["app"] as? String) ?? "")").font(.system(size: 11)).foregroundStyle(secondaryText)
                                Spacer()
                                Button("Forget") { t.forget(note) }.buttonStyle(.link).font(.system(size: 12))
                            }
                        }
                    }
                }
            }
        }
    }
}

struct LearningTab: View {
    @ObservedObject var t: Trainer
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Learning mode").font(.system(size: 14, weight: .semibold))
                    Text("Spots the mistakes you repeat. Never your style.")
                        .font(.system(size: 12)).foregroundStyle(secondaryText)
                }
                Spacer()
                Toggle("", isOn: Binding(get: { t.learning }, set: { t.setLearning($0) }))
                    .toggleStyle(.switch).labelsHidden()
            }
            DisclosureGroup("What counts", isExpanded: $t.showRules) {
                Text("Spelling, grammar and accents in the messages you use. Lowercase, “tmrw” and emoji are your choices and never count. Messages you only selected are never checked, since they may be someone else's. Only the few words of a mistake are kept, never the message.")
                    .font(.system(size: 12)).foregroundStyle(secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
            }
            .font(.system(size: 12))
            Divider()
            if !t.learning {
                Text("What you'd see after a few days").font(.system(size: 12)).foregroundStyle(secondaryText)
                PatternRow(p: ["wrong": "definately", "right": "definitely", "recent": 1, "before": 3,
                               "rule": "Definitely is spelled with an i in the middle, not an a."], ignore: {})
                    .opacity(0.5).allowsHitTesting(false)
            } else if t.patterns.isEmpty {
                Text("Nothing repeated yet. A mistake shows up here once it has come up twice.")
                    .font(.system(size: 12)).foregroundStyle(secondaryText)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(Array(t.patterns.enumerated()), id: \.offset) { _, p in
                            PatternRow(p: p) { t.ignore((p["key"] as? String) ?? "") }
                        }
                    }
                }
            }
        }
    }
}

struct PatternRow: View {
    let p: [String: Any]
    let ignore: () -> Void
    var trend: (String, Color) {
        let now = (p["recent"] as? Int) ?? 0, before = (p["before"] as? Int) ?? 0
        if before > now { return ("Fading: \(before) → \(now) in the last two weeks", .green) }
        if now == 0 { return ("None in the last two weeks", .green) }
        return ("\(now) in the last two weeks", secondaryText)
    }
    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text("“\((p["wrong"] as? String) ?? "")” → “\((p["right"] as? String) ?? "")”")
                    .font(.system(size: 13, weight: .semibold))
                Text((p["rule"] as? String) ?? "").font(.system(size: 12)).foregroundStyle(secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                Text(trend.0).font(.system(size: 11)).foregroundStyle(trend.1)
            }
            Spacer()
            Button("Not a mistake", action: ignore).buttonStyle(.link).font(.system(size: 12))
                .help("Stop counting this one")
        }
    }
}

struct RecorderRow: View {
    @ObservedObject var h: Hotkeys
    let action: String
    let name: String
    var body: some View {
        let label = h.label(action)
        let warn = h.taken.contains(action) ? "Taken by another app" : (clash(label).map { "Clashes with \($0)" })
        HStack {
            Text(name).font(.system(size: 13))
            Spacer()
            if let w = warn { Text(w).font(.system(size: 11)).foregroundStyle(.orange) }
            Button { h.record(action) } label: {
                Text(h.recording == action ? "Press keys…" : (label.isEmpty ? "Record" : label))
                    .font(.system(size: 12, weight: label.isEmpty ? .regular : .medium))
                    .foregroundStyle(label.isEmpty && h.recording != action ? secondaryText : Color.primary)
                    .frame(width: 96)
            }
        }
    }
}

struct ShortcutsTab: View {
    @ObservedObject var h: Hotkeys
    let panelKeys: [(String, String)] = [
        ("⌘1–9", "pick a tone"), ("⌘R", "another version"), ("⌘D", "show or hide the changes"),
        ("⌘I", "how your message reads"), ("⌘E", "edit the rewrite"), ("⌘T / ⌘G", "tu or vous / the reader"),
        ("Return", "with a note: rewrite again"), ("⌘Return", "replace your text"),
        ("⌘⇧C", "copy instead"), ("esc", "close"),
    ]
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("General").font(.system(size: 12, weight: .semibold)).foregroundStyle(secondaryText)
                RecorderRow(h: h, action: "open", name: "Open the pen")
                RecorderRow(h: h, action: "read", name: "How does this read?")
                RecorderRow(h: h, action: "train", name: "Open these settings")
                Text("Straight into the box").font(.system(size: 12, weight: .semibold)).foregroundStyle(secondaryText)
                    .padding(.top, 10)
                Text("Rewrites and replaces without the panel. ⌘Z in the app undoes it.")
                    .font(.system(size: 11)).foregroundStyle(secondaryText)
                ForEach(defaultTones, id: \.0) { t in RecorderRow(h: h, action: "tone:" + t.0, name: t.1) }
                if let m = h.message {
                    Text(m).font(.system(size: 12)).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
                }
                HStack {
                    Spacer()
                    Button("Reset to defaults") { h.reset() }.buttonStyle(.link).font(.system(size: 12))
                }
                Divider().padding(.vertical, 4)
                Text("In the panel").font(.system(size: 12, weight: .semibold)).foregroundStyle(secondaryText)
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 5) {
                    ForEach(panelKeys, id: \.0) { k in
                        GridRow {
                            Text(k.0).font(.system(size: 12, weight: .medium, design: .rounded))
                            Text(k.1).font(.system(size: 12)).foregroundStyle(secondaryText)
                        }
                    }
                }
            }
            .padding(.trailing, 6)
        }
    }
}

struct SettingsView: View {
    @ObservedObject var t: Trainer
    @ObservedObject var h: Hotkeys
    var body: some View {
        Group {
            if !t.trusted {
                SetupView(t: t)
            } else {
                VStack(spacing: 0) {
                    TabView(selection: $t.tab) {
                        VoiceTab(t: t).padding(16).frame(maxHeight: .infinity, alignment: .top)
                            .tabItem { Text("My voice") }.tag(0)
                        LearningTab(t: t).padding(16).frame(maxHeight: .infinity, alignment: .top)
                            .tabItem { Text("Learning") }.tag(1)
                        ShortcutsTab(h: h).padding(16).frame(maxHeight: .infinity, alignment: .top)
                            .tabItem { Text("Shortcuts") }.tag(2)
                    }
                    .padding(.horizontal, 10).padding(.top, 8)
                    HStack(spacing: 6) {
                        Circle().fill(Color.green).frame(width: 7, height: 7)
                        Text(t.openKeys.isEmpty ? "Ready. Set a shortcut to open the pen."
                             : "Ready · \(t.openKeys) in any app")
                            .font(.system(size: 12)).foregroundStyle(secondaryText)
                        Spacer()
                        if !t.seenNotch {
                            Text("Can't see the pencil? Open Brain Pen again.")
                                .font(.system(size: 11)).foregroundStyle(secondaryText).lineLimit(1)
                            Button("OK") { t.seenNotch = true }.buttonStyle(.link).font(.system(size: 11))
                        }
                    }
                    .padding(.horizontal, 18).padding(.vertical, 10)
                }
            }
        }
        .frame(width: 560, height: 540)
        .onAppear { t.load() }
    }
}

// MARK: - the app

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    static var shared: AppDelegate?
    let pen = Pen()
    let trainer = Trainer()
    let hotkeys = Hotkeys()
    let toast = Toast()
    var panel: KeyPanel!
    var hosting: NSHostingController<PenView>!
    var settingsWindow: NSWindow?
    var status: NSStatusItem!
    var quickBusy = false
    var lastWarm = Date.distantPast
    let warmApps: Set<String> = ["net.whatsapp.WhatsApp", "desktop.WhatsApp", "com.automattic.beeper.desktop",
                                 "com.apple.MobileSMS", "com.apple.mail", "com.microsoft.Outlook",
                                 "com.tinyspeck.slackmacgap", "com.google.Chrome", "com.apple.Safari"]

    func applicationDidFinishLaunching(_ n: Notification) {
        AppDelegate.shared = self
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count {
            snapshot(args[i + 1])
            return
        }
        installEditMenu()
        makePanel()
        makeMenu()
        hotkeys.registerAll()
        trainer.load()
        if !AXIsProcessTrusted() && !args.contains("--demo") {
            let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            _ = AXIsProcessTrustedWithOptions(opts)
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            self, selector: #selector(appActivated(_:)),
            name: NSWorkspace.didActivateApplicationNotification, object: nil)
        warm()
        if let i = args.firstIndex(of: "--demo") {
            let text = i + 1 < args.count ? args[i + 1] : "hey can we move tmrw to 4, sorry stuck at school"
            show(Grab(text: text, mode: "whole", pid: 0, bundle: "net.whatsapp.WhatsApp",
                      app: "WhatsApp", title: "", anchor: nil), demo: true)
        }
        if args.contains("--train") { openSettings(0) }
        else if !AXIsProcessTrusted() && !args.contains("--demo") && !args.contains("--shortcuts") { openSettings(0) }
        // Accessibility switched on in System Settings: the window says so.
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let t = AXIsProcessTrusted()
            if t != self.trainer.trusted { self.trainer.trusted = t }
            let k = self.hotkeys.label("open")
            if k != self.trainer.openKeys { self.trainer.openKeys = k }
        }
        if args.contains("--shortcuts") { openSettings(2) }
    }

    /// `--snapshot DIR`: draw the settings tabs, the panel and the toast
    /// into PNGs off-screen, then quit. For checking the look without a
    /// window ever appearing on her screen or taking her keyboard.
    func snapshot(_ dir: String) {
        trainer.load()
        func shoot(_ v: NSView, _ size: NSSize, _ name: String) {
            let w = NSWindow(contentRect: NSRect(x: -30000, y: -30000, width: size.width, height: size.height),
                             styleMask: [.borderless], backing: .buffered, defer: false)
            w.contentView = v
            v.frame = NSRect(origin: .zero, size: size)
            v.layoutSubtreeIfNeeded()
            v.display()
            guard let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return }
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?
                .write(to: URL(fileURLWithPath: dir + "/" + name + ".png"))
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            shoot(NSHostingView(rootView: SetupView(t: self.trainer)), NSSize(width: 560, height: 540), "setup")
            self.trainer.trusted = true
            self.trainer.openKeys = "⌃⌥R"
            for tab in 0..<3 {
                self.trainer.tab = tab
                shoot(NSHostingView(rootView: SettingsView(t: self.trainer, h: self.hotkeys)),
                      NSSize(width: 560, height: 540), "settings-\(tab)")
            }
            self.pen.grab = Grab(text: "salut sam je suis désolé on peut décaler a jeudi?", mode: "whole", pid: 0,
                                 bundle: "", app: "WhatsApp", title: "", anchor: nil)
            self.pen.lang = "fr"
            self.pen.reading = "This reads warm and easy. Nothing in it is likely to be misread."
            self.pen.checkLines = ["You wrote “jeudi”: your notes have dinner with Sam on Friday 9 Oct."]
            self.pen.where_ = "WhatsApp · the whole box"
            self.pen.text = "Salut Sam, désolée, on peut décaler à jeudi ?"
            self.pen.notes = ["less formal"]
            self.pen.tip = ["wrong": "definately", "right": "definitely", "count": 3,
                            "rule": "Definitely is spelled with an i in the middle, not an a."]
            let pv = NSHostingView(rootView: PenView(pen: self.pen))
            shoot(pv, pv.fittingSize, "panel")
            let p2 = Pen()
            p2.startPaste(Grab(text: "", mode: "paste", pid: 0, bundle: "", app: "Notes", title: "", anchor: nil))
            let pv2 = NSHostingView(rootView: PenView(pen: p2))
            shoot(pv2, pv2.fittingSize, "panel-paste")
            self.toast.m.text = "Fix typos done. ⌘Z undoes it."
            let tv = NSHostingView(rootView: ToastView(m: self.toast.m))
            shoot(tv, tv.fittingSize, "toast")
            exit(0)
        }
    }

    /// Opening Brain Pen while it already runs (Finder, Spotlight, the
    /// Dock) shows the window: the menu-bar pencil can hide behind the notch.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openSettings(trainer.tab)
        return false
    }

    func hotkey(_ id: UInt32) {
        guard let action = hotkeys.byID[id] else { return }
        if action == "open" { trigger() }
        else if action == "train" { openSettings(0) }
        else if action == "read" { quickRead() }
        else if action.hasPrefix("tone:") { quick(String(action.dropFirst(5))) }
    }

    func makePanel() {
        panel = KeyPanel(contentRect: NSRect(x: 0, y: 0, width: 640, height: 300),
                         styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView, .closable],
                         backing: .buffered, defer: false)
        panel.titlebarAppearsTransparent = true
        panel.titleVisibility = .hidden
        panel.isMovableByWindowBackground = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true
        let host = NSHostingController(rootView: PenView(pen: pen))
        host.sizingOptions = [.preferredContentSize]
        host.safeAreaRegions = []            // no empty strip where a title bar would be
        panel.contentViewController = host
        hosting = host
        panel.onCancel = { [weak self] in self?.dismiss(used: false) }
        pen.close = { [weak self] paste in self?.finish(paste: paste) }
        pen.dismiss = { [weak self] in self?.dismiss(used: false) }
        pen.settings = { [weak self] in
            self?.dismiss(used: false)
            self?.openSettings(2)
        }
    }

    func makeMenu() {
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        status.button?.image = NSImage(systemSymbolName: "pencil.line", accessibilityDescription: "Brain Pen")
        let m = NSMenu()
        m.delegate = self
        status.menu = m
    }

    @objc func appActivated(_ n: Notification) {
        guard let app = n.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
              warmApps.contains(app.bundleIdentifier ?? "") else { return }
        warm()
    }

    /// Wake the kept-open Claude when she is somewhere she writes, at most
    /// every ten minutes, so the first rewrite answers in about two seconds.
    func warm() {
        guard Date().timeIntervalSince(lastWarm) > 600 else { return }
        lastWarm = Date()
        api("/api/pen/warm", [:]) { _, _ in }
    }

    /// Not switched on yet: the setup screen says what to do.
    func needsAccess() -> Bool {
        if AXIsProcessTrusted() { return false }
        openSettings(0)
        return true
    }

    @objc func trigger() {
        if panel.isVisible { dismiss(used: false); return }
        if needsAccess() { return }
        switch grabText() {
        case .ok(let g): show(g)
        case .empty(let ctx):
            pen.startPaste(ctx)
            place(nil)
        case .refused(let why):
            pen.refuse(why)
            place(nil)
        }
    }

    /// A tone's own shortcut: rewrite and put it straight back, no panel.
    /// A small note under the caret says what happened; ⌘Z in the app
    /// undoes the paste like any other.
    func quick(_ tone: String) {
        guard !quickBusy else { return }
        if panel.isVisible { dismiss(used: false) }
        if needsAccess() { return }
        let label = pen.tones.first { $0.0 == tone }?.1 ?? tone
        switch grabText() {
        case .empty(let ctx):
            pen.startPaste(ctx, tone: tone)
            place(nil)
        case .refused(let why):
            toast.show(why, near: nil, bad: true, secs: 3)
        case .ok(let g):
            quickBusy = true
            toast.show("\(label)…", near: g.anchor, busy: true, secs: nil)
            api("/api/pen/rewrite", ["text": g.text, "tone": tone, "bundle": g.bundle, "app": g.app,
                                     "title": g.title, "mode": g.mode, "feedback": []]) { out, err in
                self.quickBusy = false
                if let err = err { self.toast.show(err, near: g.anchor, bad: true, secs: 4); return }
                let s = (out?["text"] as? String) ?? ""
                guard !s.isEmpty else { self.toast.show("Nothing came back.", near: g.anchor, bad: true); return }
                // Pasted unseen, so a link, address or number her text didn't
                // have goes to the clipboard for her to read first.
                let adds = (out?["added"] as? [String]) ?? []
                if s == g.text.trimmingCharacters(in: .whitespacesAndNewlines) {
                    self.toast.show("\(label): nothing to change.", near: g.anchor)
                } else if !adds.isEmpty {
                    putOnClipboard(s)
                    self.toast.show("\(label) added \(adds.joined(separator: ", ")), so it's on the clipboard to check, not pasted.",
                                    near: g.anchor, bad: true, secs: 5)
                } else if stillThere(g) {
                    putBack(s, into: g)
                    var msg = "\(label) done. ⌘Z undoes it."
                    if let t = out?["tip"] as? [String: Any], let w = t["wrong"] as? String, let r = t["right"] as? String {
                        msg += "  Worth remembering: “\(w)” is “\(r)”."
                    }
                    self.toast.show(msg, near: g.anchor, secs: 3.5)
                } else {
                    putOnClipboard(s)
                    self.toast.show("You'd moved on, so the rewrite is on the clipboard instead.", near: g.anchor, secs: 4)
                }
                api("/api/pen/done", ["app": g.app, "bundle": g.bundle, "tone": tone, "used": true,
                                      "notes": [], "chars": g.text.count, "title": g.title,
                                      "text": g.text]) { _, _ in }
            }
        }
    }

    /// "How does this read?" from its own shortcut: the read appears under
    /// the caret and nothing in the box changes.
    func quickRead() {
        guard !quickBusy else { return }
        if panel.isVisible { pen.readIt(); return }
        if needsAccess() { return }
        switch grabText() {
        case .empty:
            toast.show("Select the text you want read first.", near: nil, bad: true, secs: 3)
        case .refused(let why):
            toast.show(why, near: nil, bad: true, secs: 3)
        case .ok(let g):
            quickBusy = true
            toast.show("Reading it the way they will…", near: g.anchor, busy: true, secs: nil)
            api("/api/pen/read", ["text": g.text, "bundle": g.bundle, "app": g.app, "title": g.title]) { out, err in
                self.quickBusy = false
                if let err = err { self.toast.show(err, near: g.anchor, bad: true, secs: 4); return }
                let r = (out?["read"] as? String) ?? ""
                self.toast.show(r, near: g.anchor, secs: max(5, Double(r.count) / 18))
            }
        }
    }

    func show(_ g: Grab, demo: Bool = false) {
        pen.start(g, demo: demo)
        place(g.anchor)
    }

    /// Just under the caret or the box when the app says where it is, else
    /// by the mouse; always kept on the screen.
    func place(_ anchor: CGRect?) {
        var size = hosting.sizeThatFits(in: NSSize(width: 560, height: 2000))
        if size.width < 100 || size.height < 40 { size = NSSize(width: 560, height: 240) }
        let primary = NSScreen.screens.first?.frame.height ?? 900
        var point: NSPoint
        if let a = anchor {
            point = NSPoint(x: a.minX, y: primary - a.maxY - 8)    // flip to Cocoa coordinates
        } else {
            let m = NSEvent.mouseLocation
            point = NSPoint(x: m.x - 40, y: m.y - 16)
        }
        let screen = NSScreen.screens.first { NSPointInRect(point, $0.frame) } ?? NSScreen.main
        let vis = screen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        var origin = NSPoint(x: point.x, y: point.y - size.height)
        if origin.y < vis.minY, let a = anchor {
            origin.y = primary - a.minY + 8                        // no room below: go above
        }
        origin.x = min(max(origin.x, vis.minX + 8), vis.maxX - size.width - 8)
        origin.y = min(max(origin.y, vis.minY + 8), vis.maxY - size.height - 8)
        panel.topY = nil
        panel.setFrame(NSRect(origin: origin, size: size), display: true)
        panel.topY = origin.y + size.height
        panel.makeKeyAndOrderFront(nil)
    }

    func finish(paste: Bool) {
        let g = pen.grab
        let text = pen.text
        pen.report(used: true)
        panel.orderOut(nil)
        guard paste, let g = g else { return }
        if pen.demo { putOnClipboard(text); return }
        putBack(text, into: g)
    }

    func dismiss(used: Bool) {
        pen.report(used: used)
        pen.seq += 1                    // an answer still on its way is dropped
        pen.busy = false
        panel.orderOut(nil)
    }

    @objc func rewriteNow() { trigger() }
    @objc func openVoice() { openSettings(0) }
    @objc func openLearning() { openSettings(1) }
    @objc func openShortcuts() { openSettings(2) }

    func openSettings(_ tab: Int) {
        trainer.tab = tab
        if settingsWindow == nil {
            let w = EditWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 540),
                             styleMask: [.titled, .closable], backing: .buffered, defer: false)
            w.title = "Brain Pen"
            w.isReleasedWhenClosed = false
            w.delegate = self
            w.contentView = NSHostingView(rootView: SettingsView(t: trainer, h: hotkeys))
            w.center()
            settingsWindow = w
        } else {
            trainer.load()
        }
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow?.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ n: Notification) { hotkeys.stop() }

    @objc func toggleLearning() { trainer.setLearning(!trainer.learning) }

    @objc func toggleLogin() {
        let s = SMAppService.mainApp
        do {
            if s.status == .enabled { try s.unregister() } else { try s.register() }
        } catch {
            let a = NSAlert()
            a.messageText = "Couldn't change Open at login"
            a.informativeText = error.localizedDescription
            a.runModal()
        }
    }

    @objc func quit() { NSApp.terminate(nil) }

    /// Quit and open again: some macOS versions only apply a new
    /// Accessibility switch to an app started after it.
    func restart() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", "sleep 1; /usr/bin/open \"$0\"", Bundle.main.bundlePath]
        try? p.run()
        NSApp.terminate(nil)
    }
}

extension AppDelegate: NSMenuDelegate {
    // Rebuilt each time it opens, so the ticks and labels are current.
    func menuNeedsUpdate(_ m: NSMenu) {
        m.removeAllItems()
        let combo = hotkeys.label("open")
        let r = NSMenuItem(title: combo.isEmpty ? "Rewrite" : "Rewrite  (\(combo))",
                           action: #selector(rewriteNow), keyEquivalent: "")
        m.addItem(r)
        if hotkeys.taken.contains("open") {
            let w = NSMenuItem(title: "\(combo) is taken by another app: change it in Shortcuts", action: nil, keyEquivalent: "")
            w.isEnabled = false
            m.addItem(w)
        }
        m.addItem(NSMenuItem(title: "Train my voice…", action: #selector(openVoice), keyEquivalent: ""))
        let learn = NSMenuItem(title: "Learning mode", action: #selector(toggleLearning), keyEquivalent: "")
        learn.state = trainer.learning ? .on : .off
        m.addItem(learn)
        if trainer.learning {
            m.addItem(NSMenuItem(title: "What I keep getting wrong…", action: #selector(openLearning), keyEquivalent: ""))
        }
        m.addItem(NSMenuItem(title: "Shortcuts…", action: #selector(openShortcuts), keyEquivalent: ","))
        if !AXIsProcessTrusted() {
            let w = NSMenuItem(title: "Needs Accessibility: System Settings > Privacy & Security", action: nil, keyEquivalent: "")
            w.isEnabled = false
            m.addItem(w)
        }
        m.addItem(.separator())
        let login = NSMenuItem(title: "Open at login", action: #selector(toggleLogin), keyEquivalent: "")
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        m.addItem(login)
        m.addItem(NSMenuItem(title: "Quit Brain Pen", action: #selector(quit), keyEquivalent: "q"))
        for i in m.items where i.action != nil { i.target = self }
    }
}

// One Brain Pen at a time: a second copy would fight over the shortcuts.
let mine = Bundle.main.bundleIdentifier ?? ""
if !mine.isEmpty,
   NSRunningApplication.runningApplications(withBundleIdentifier: mine)
       .contains(where: { $0.processIdentifier != getpid() }) {
    exit(0)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
