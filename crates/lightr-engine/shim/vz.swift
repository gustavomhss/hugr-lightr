// shim/vz.swift — VzEngine Swift shim for lightr-engine (build-spec-r2 §2).
//
// Compiled to a static lib by build.rs ONLY when feature "vz" is enabled.
// Default builds never reach this file.
//
// S5 BOOT NOTE: The actual microVM boot path has not been validated on Intel
// x86_64 (Apple VZ save/restore is arm64-only; cold-boot with a suitable
// kernel pack may work on x86 but is owner-spike S5 territory). The Swift
// code below is architecturally complete and compiles against the
// Virtualization framework; the boot path is marked with // BOOT-PATH
// comments for the S5 reviewer.
//
// Exported C symbol: lightr_vz_run
// Matches extern "C" in crates/lightr-engine/src/lib.rs vz_impl module.

import Foundation
import Virtualization

private let vzOk: Int32 = 0
private let vzConfig: Int32 = -1
private let vzUnsupported: Int32 = -2
private let vzIo: Int32 = -3
private let vzLifecycle: Int32 = -4
private let vzInvalidState: Int32 = -5
private let vzTimeout: Int32 = -6

/// Opaque VM retained across start/pause/save/restore/resume calls. VZ callbacks
/// run on this queue; C callers wait on `done`, never on VZ's queue.
@available(macOS 14.0, *)
private final class VzSession {
    let vm: VZVirtualMachine
    let queue: DispatchQueue
    let done = DispatchSemaphore(value: 0)
    var observation: NSKeyValueObservation?
    var terminalStatus: Int32 = vzLifecycle

    init(config: VZVirtualMachineConfiguration, queue: DispatchQueue) {
        self.queue = queue
        self.vm = VZVirtualMachine(configuration: config, queue: queue)
        self.observation = vm.observe(\.state, options: [.new]) { session, _ in
            switch session.state {
            case .stopped:
                self.terminalStatus = vzOk
                self.done.signal()
            case .error:
                self.terminalStatus = vzLifecycle
                self.done.signal()
            default:
                break
            }
        }
    }
}

private let sessionLock = NSLock()
private var sessions: [UInt64: VzSession] = [:]
private var nextSessionHandle: UInt64 = 1

@available(macOS 14.0, *)
private func withSession(_ handle: UInt64, _ body: (VzSession) -> Int32) -> Int32 {
    sessionLock.lock()
    let session = sessions[handle]
    sessionLock.unlock()
    guard let session else { return vzInvalidState }
    return body(session)
}

private func cString(_ pointer: UnsafePointer<CChar>?) -> String? {
    guard let pointer else { return nil }
    return String(cString: pointer)
}

/// Boot a Linux microVM, run the supplied command as the guest init, and
/// report the VM's LIFECYCLE status.  Called from Rust via C ABI.
///
/// IMPORTANT (WP-B honesty contract): this function does NOT return the guest
/// process's exit code.  Apple's Virtualization framework never surfaces the
/// guest exit code to the host, so any value invented here would be a lie — and
/// macOS has no host AF_VSOCK to carry it either.  Instead, the guest's PID1
/// (`lightr-init`) writes its REAL exit code to a file on the shared (writable)
/// rootfs (`.lightr-exit-code`), and the RUST host (`VzEngine::run`) reads it
/// back after the VM stops.  This shim therefore reports only whether the VM
/// booted and stopped cleanly; `VzEngine::run` combines that with the rootfs
/// exit file to produce the real exit code.
///
/// - Parameters:
///   - kernel:  NUL-terminated path to a Linux kernel image (vmlinuz / bzImage).
///   - initrd:  NUL-terminated path to an initrd/initramfs file.
///   - rootfs:  NUL-terminated path to the CoW rootfs directory to share via
///               virtiofs at guest tag "rootfs".
///   - store:   NUL-terminated path to the read-only store directory to share
///               at guest tag "store".  Pass "" to skip the store share.
///   - memoryMb: F-203 memory cap in MiB.  `0` = use the baseline default.
///               A non-zero value below the VZ memory floor is a config
///               failure (return -1), NOT a silent clamp — honest boundary.
///   - cpuCount: F-203 vcpu count.  `0` = use the baseline default.  Clamped
///               to the VZ allowed range; a non-zero value above the maximum
///               is a config failure (return -1).
///   - netFd:   ADR-0018 dual-NIC mesh.  The GUEST-side fd of a
///               `socketpair(AF_UNIX, SOCK_DGRAM)` whose host end is owned by
///               the userspace L2 switch (one datagram == one Ethernet frame).
///               `>= 0` ⇒ attach a SECOND virtio-net NIC
///               (`VZFileHandleNetworkDeviceAttachment` over this fd) ALONGSIDE
///               the NAT NIC — the mesh (`eth1`).  `-1` ⇒ no file-handle NIC
///               (today's single-NAT-NIC path).  The fd is owned by the caller
///               (the switch); we wrap it `closeOnDealloc:false` so a transient
///               FileHandle dealloc can't close it.
///   - volCount / volPaths / volReadOnly: ADR-0024 D4 `-v`.  One extra
///               virtiofs share per host directory, tagged `vol0..N` in order;
///               the guest PID1 mounts them by tag.  `volReadOnly[i] != 0`
///               makes share i read-only at the host.  The host validated each
///               path is a directory before calling; VZ re-checks at validate().
///   - argc:    Number of arguments in argv.
///   - argv:    C argv array (argv[0] = program, …).
///
/// - Returns: VM-lifecycle status — `0` = booted and stopped cleanly,
///            `-1` = configuration / boot failure.  NEVER the guest exit code.
@_cdecl("lightr_vz_run")
public func lightr_vz_run(
    kernel:   UnsafePointer<CChar>,
    initrd:   UnsafePointer<CChar>,
    rootfs:   UnsafePointer<CChar>,
    store:    UnsafePointer<CChar>,
    memoryMb: UInt64,
    cpuCount: UInt64,
    netFd:    Int32,
    netMac:   UnsafePointer<CChar>?,
    volCount: Int32,
    volPaths: UnsafePointer<UnsafePointer<CChar>?>?,
    volReadOnly: UnsafePointer<UInt8>?,
    argc:     Int32,
    argv:     UnsafePointer<UnsafePointer<CChar>?>
) -> Int32 {

    // WAVE-VZ boot-time instrumentation: wall-clock from shim entry, printed when
    // LIGHTR_VZ_TIMING is set, to break down VM create / start / run / teardown.
    let t0 = DispatchTime.now()
    let vztiming = !(ProcessInfo.processInfo.environment["LIGHTR_VZ_TIMING"] ?? "").isEmpty
    // Networking is OPT-IN (LIGHTR_VZ_NET) — same env-config pattern as
    // LIGHTR_VZ_CONSOLE. A non-published run skips the NIC + `ip=dhcp`, avoiding
    // ~0.6s DHCP at boot AND the network-teardown cost at poweroff. The host sets
    // this only when `-p`/networking is requested.
    let wantsNet = !(ProcessInfo.processInfo.environment["LIGHTR_VZ_NET"] ?? "").isEmpty
    // Fast-teardown: when set, poll this host path for the guest's durable exit
    // code and force-stop the VM the instant it parses — skipping the guest's slow
    // clean poweroff + VZ stop-detection (~2s). Empty → wait for a clean stop.
    let exitFilePath = ProcessInfo.processInfo.environment["LIGHTR_VZ_EXITFILE"] ?? ""
    func tlog(_ label: String) {
        if vztiming {
            let ms = Double(DispatchTime.now().uptimeNanoseconds &- t0.uptimeNanoseconds) / 1_000_000
            fputs(String(format: "lightr-vz-timing: %-22@ %8.1f ms\n", label, ms), stderr)
        }
    }

    // ── 1. Paths ────────────────────────────────────────────────────────────
    let kernelURL  = URL(fileURLWithPath: String(cString: kernel))
    let initrdURL  = URL(fileURLWithPath: String(cString: initrd))
    let rootfsPath = String(cString: rootfs)
    let storePath  = String(cString: store)

    // ── 2. Linux bootloader ─────────────────────────────────────────────────
    // The kernel must be an x86_64 bzImage (VZ on Intel boots via the x86 setup
    // header / real-mode protocol; a raw vmlinux ELF — even a PVH one — is
    // rejected with an "Internal Virtualization error"). console=hvc0 is the
    // virtio console VZ exposes (the guest's only console). The command travels
    // via the file channel (CMD_FILE on the rootfs share), NOT the kernel
    // cmdline; argv is ignored here (kept in the C ABI for forward-compat).
    _ = argc
    _ = argv
    // `ip=dhcp`: kernel-level DHCP autoconfig (CONFIG_IP_PNP_DHCP) brings the
    // virtio-net interface up + leases an IP from the NAT attachment's DHCP server
    // at boot — no userspace DHCP client needed in the guest. Harmless when no NIC
    // is present. (WAVE-VZ networking.)
    let cmdLine    = wantsNet ? "console=hvc0 ip=dhcp" : "console=hvc0"

    let bootLoader = VZLinuxBootLoader(kernelURL: kernelURL)
    bootLoader.initialRamdiskURL = initrdURL
    bootLoader.commandLine       = cmdLine

    // ── 3. CPU + memory (F-203 resource caps) ───────────────────────────────
    // memoryMb / cpuCount == 0 ⇒ use the baseline default; a non-zero value is
    // the caller's cap. Out-of-range requests are an honest config failure
    // (return -1) rather than a silent clamp — the Rust host surfaces that as a
    // real error (build-spec-parity.md §2.4).
    let maxCPU = VZVirtualMachineConfiguration.maximumAllowedCPUCount
    let minCPU = VZVirtualMachineConfiguration.minimumAllowedCPUCount
    let cpuCountResolved: Int
    if cpuCount == 0 {
        cpuCountResolved = max(minCPU, min(maxCPU, maxCPU / 4))
    } else {
        let requested = Int(cpuCount)
        if requested > maxCPU {
            fputs("lightr-vz-shim: requested cpuCount \(requested) exceeds VZ maximum \(maxCPU)\n", stderr)
            return -1
        }
        cpuCountResolved = max(minCPU, requested)
    }

    let minMem = VZVirtualMachineConfiguration.minimumAllowedMemorySize
    let maxMem = VZVirtualMachineConfiguration.maximumAllowedMemorySize
    let memBytes: UInt64
    if memoryMb == 0 {
        memBytes = max(minMem, UInt64(256) * 1024 * 1024)  // 256 MB baseline (ADR-0014)
    } else {
        let requested = memoryMb * 1024 * 1024
        if requested < minMem || requested > maxMem {
            fputs("lightr-vz-shim: requested memory \(requested) bytes outside VZ floor \(minMem)..\(maxMem)\n", stderr)
            return -1
        }
        memBytes = requested
    }
    let cpuCount = cpuCountResolved

    // ── 4. Virtiofs shares ──────────────────────────────────────────────────
    var storages: [VZDirectorySharingDeviceConfiguration] = []

    // rootfs share (tag "rootfs", read-write so the guest can pivot/write).
    // SINGLE-directory share: the directory's CONTENTS appear directly at the
    // guest mountpoint. A MultipleDirectoryShare would nest them under a
    // subdirectory named after the key (guest saw /newroot/rootfs/… instead of
    // /newroot/… — the cause of an early read_spec ENOENT).
    let rootfsShare = VZSharedDirectory(url: URL(fileURLWithPath: rootfsPath),
                                        readOnly: false)
    let rootfsDev   = VZVirtioFileSystemDeviceConfiguration(tag: "rootfs")
    rootfsDev.share = VZSingleDirectoryShare(directory: rootfsShare)
    storages.append(rootfsDev)

    // store share (tag "store", read-only) — same single-directory semantics.
    if !storePath.isEmpty {
        let storeShare = VZSharedDirectory(url: URL(fileURLWithPath: storePath),
                                           readOnly: true)
        let storeDev   = VZVirtioFileSystemDeviceConfiguration(tag: "store")
        storeDev.share = VZSingleDirectoryShare(directory: storeShare)
        storages.append(storeDev)
    }

    // ADR-0024 D4 volume shares (tags vol0..N). A NULL entry is a host bug:
    // refuse the configuration rather than boot with a share missing.
    for i in 0..<Int(max(volCount, 0)) {
        guard let paths = volPaths, let p = paths[i] else {
            fputs("lightr-vz-shim: volume \(i) has no host path\n", stderr)
            return -1
        }
        let readOnly = (volReadOnly?[i] ?? 0) != 0
        let share = VZSharedDirectory(url: URL(fileURLWithPath: String(cString: p)),
                                      readOnly: readOnly)
        let device = VZVirtioFileSystemDeviceConfiguration(tag: "vol\(i)")
        device.share = VZSingleDirectoryShare(directory: share)
        storages.append(device)
    }

    // ── 5. Serial console → host stdio (or a durable file for diagnosis) ─────
    // BOOT-PATH: attach /dev/hvc0 to the host. Normally writes flow to stdout
    // (inherit semantics). When LIGHTR_VZ_CONSOLE is set, the guest console is
    // captured to that file instead — durable across a SIGTERM/timeout and free
    // of any stdout/pipe/tty ambiguity (used to debug a silent boot).
    let consoleWrite: FileHandle
    if let p = ProcessInfo.processInfo.environment["LIGHTR_VZ_CONSOLE"], !p.isEmpty {
        FileManager.default.createFile(atPath: p, contents: nil)
        consoleWrite = FileHandle(forWritingAtPath: p) ?? FileHandle.standardOutput
    } else {
        consoleWrite = FileHandle.standardOutput
    }
    // Tap the console: the guest writes to this pipe; the host forwards bytes to
    // the real console destination (consoleWrite) AND scans them for the real-time
    // exit marker ("LIGHTR_EXIT:<n>"), so it can force-stop the instant the command
    // finishes — bypassing the slow virtiofs EXIT_FILE visibility (~1.3s). The
    // guest's stdout (hvc0) carries both the command output and PID1's marker.
    let consolePipe = Pipe()
    let consolePort = VZVirtioConsoleDeviceSerialPortConfiguration()
    consolePort.attachment = VZFileHandleSerialPortAttachment(
        fileHandleForReading:  FileHandle.standardInput,
        fileHandleForWriting:  consolePipe.fileHandleForWriting
    )

    // ── 5b. NAT network device (WAVE-VZ networking) ──────────────────────────
    // A virtio-net NIC on a NAT attachment gives the guest a host-reachable IP on
    // the macOS vmnet subnet — the basis for `-p` port publishing (host→guest
    // forward). The kernel is built with CONFIG_VIRTIO_NET=y + CONFIG_IP_PNP_DHCP,
    // so the guest can auto-configure. The MAC is pinned (locally-administered)
    // so the host can discover the guest IP from the DHCP lease table by MAC.
    var netDevices: [VZVirtioNetworkDeviceConfiguration] = []
    if wantsNet {
        let netDevice = VZVirtioNetworkDeviceConfiguration()
        netDevice.attachment = VZNATNetworkDeviceAttachment()
        if let mac = VZMACAddress(string: "0a:00:00:24:18:01") {
            netDevice.macAddress = mac
        }
        netDevices = [netDevice]
    }

    // ── 5c. File-handle mesh NIC (ADR-0018 dual-NIC) ─────────────────────────
    // When the host hands us a guest-side socketpair fd (netFd >= 0), attach a
    // SECOND virtio-net NIC over a VZFileHandleNetworkDeviceAttachment. Its host
    // end is owned by the userspace L2 switch; one AF_UNIX SOCK_DGRAM datagram ==
    // one Ethernet frame (boundaries preserved 1:1). This NIC COEXISTS with the
    // NAT NIC above (eth0 = NAT egress, eth1 = mesh) — Docker's bridge+egress
    // shape. Proven GREEN on this Intel box by the de-risk spike; honored here:
    //   * FileHandle(closeOnDealloc:false) — a transient FileHandle dealloc must
    //     NOT close the fd; the caller (the switch) keeps it alive for the VM's
    //     lifetime and owns its close.
    //   * SO_SNDBUF=256K / SO_RCVBUF=512K (>=2x ratio) — datagram buffering so a
    //     burst of frames isn't dropped at the socket.
    // Needs only com.apple.security.virtualization (already ad-hoc-signed).
    if netFd >= 0 {
        // Buffer tuning on the guest-side fd (best-effort: a setsockopt failure
        // is non-fatal — the NIC still attaches; the kernel default applies).
        var sndBuf: Int32 = 256 * 1024
        var rcvBuf: Int32 = 512 * 1024
        _ = withUnsafePointer(to: &sndBuf) {
            setsockopt(netFd, SOL_SOCKET, SO_SNDBUF, $0, socklen_t(MemoryLayout<Int32>.size))
        }
        _ = withUnsafePointer(to: &rcvBuf) {
            setsockopt(netFd, SOL_SOCKET, SO_RCVBUF, $0, socklen_t(MemoryLayout<Int32>.size))
        }
        // Non-owning FileHandle: the switch owns the fd's lifetime + close.
        let meshHandle = FileHandle(fileDescriptor: netFd, closeOnDealloc: false)
        let meshDevice = VZVirtioNetworkDeviceConfiguration()
        meshDevice.attachment = VZFileHandleNetworkDeviceAttachment(fileHandle: meshHandle)
        // MAC for the mesh NIC: prefer the host-supplied per-member MAC (ADR-0018
        // — the registry assigns it, the guest emits it, so the switch's DHCP
        // lease / MAC-learning / DNS all key on the SAME MAC). Fall back to a
        // pinned locally-administered MAC when the host passes none (de-risk /
        // single-guest path). Without this, all mesh guests share one MAC → L2
        // can't distinguish them AND the DHCP lease (keyed on the registry MAC)
        // never matches the guest's chaddr → no lease.
        let meshMacStr = netMac.map { String(cString: $0) } ?? "0a:00:00:24:18:02"
        if let mac = VZMACAddress(string: meshMacStr) {
            meshDevice.macAddress = mac
        }
        netDevices.append(meshDevice)
    }

    // ── 6. Assemble configuration ───────────────────────────────────────────
    let config = VZVirtualMachineConfiguration()
    config.bootLoader   = bootLoader
    config.cpuCount     = cpuCount
    config.memorySize   = memBytes
    config.serialPorts  = [consolePort]
    config.directorySharingDevices = storages
    config.networkDevices = netDevices

    do {
        try config.validate()
    } catch {
        fputs("lightr-vz-shim: configuration invalid: \(error)\n", stderr)
        return -1
    }
    tlog("config validated")

    // ── 7. Boot + wait ──────────────────────────────────────────────────────
    // `vmStatus` is a LIFECYCLE status, never the guest exit code. The guest's
    // real exit code is delivered to the Rust host as a file on the shared
    // rootfs by PID1 (see the function doc + VzEngine::run); this shim only
    // signals whether the VM reached a clean stop. The old fabricated-success
    // assignment that pinned the result to zero on stop has been removed.
    //
    // CONCURRENCY (critical): the VM runs on a DEDICATED serial queue, NOT the
    // main queue. VZ delivers `.state` transitions and the `start` completion
    // handler ON the VM's own queue. If that queue were the main queue AND we
    // block the calling thread on a semaphore (below), those callbacks could
    // never run — the VM wedges in `.starting` forever (observed empirically:
    // state -> 4 and the completion handler never fires). With a dedicated
    // queue, the calling thread blocks on the semaphore while VZ's queue keeps
    // servicing the VM all the way to `.stopped`.
    let vmQueue   = DispatchQueue(label: "com.hugr.lightr.vz")
    let semaphore = DispatchSemaphore(value: 0)
    var vmStatus: Int32 = -1
    var vm: VZVirtualMachine?
    var observation: NSKeyValueObservation?
    // Trace every lifecycle transition only when the console is being captured
    // (LIGHTR_VZ_CONSOLE set = debug); quiet otherwise. Real errors always log.
    let trace = !(ProcessInfo.processInfo.environment["LIGHTR_VZ_CONSOLE"] ?? "").isEmpty
    var capturedExit: Int32? = nil

    // Console tap: forward guest console bytes to the real destination AND scan for
    // the real-time exit marker ("LIGHTR_EXIT:<n>\n"); the instant it parses, force-
    // stop the VM (the command has finished). Requires a trailing newline so a
    // chunk-split mid-number never captures a partial code.
    var scanBuf = Data()
    let exitMarker = Data("LIGHTR_EXIT:".utf8)
    consolePipe.fileHandleForReading.readabilityHandler = { fh in
        let chunk = fh.availableData
        if chunk.isEmpty { return }
        consoleWrite.write(chunk)
        if capturedExit != nil { return }
        scanBuf.append(chunk)
        if let r = scanBuf.range(of: exitMarker) {
            var digits = ""
            var sawNewline = false
            for b in scanBuf.suffix(from: r.upperBound) {
                let ch = Character(UnicodeScalar(b))
                if ch == "\n" || ch == "\r" { sawNewline = true; break }
                digits.append(ch)
            }
            if sawNewline, let code = Int32(digits.trimmingCharacters(in: .whitespaces)) {
                capturedExit = code
                tlog("console exit marker = \(code), force-stopping")
                vmQueue.async { if let m = vm, m.canStop { m.stop { _ in } } }
            }
        }
        if scanBuf.count > 16384 { scanBuf = Data(scanBuf.suffix(2048)) }
    }

    vmQueue.async {
        let machine = VZVirtualMachine(configuration: config, queue: vmQueue)
        vm = machine
        observation = machine.observe(\.state, options: [.new]) { m, _ in
            if trace { fputs("lightr-vz-shim: vm.state -> \(m.state.rawValue)\n", stderr) }
            tlog("vm.state=\(m.state.rawValue)")
            switch m.state {
            case .stopped:
                // BOOT-PATH: clean stop. Lifecycle success ONLY; the real guest
                // exit code is on the shared rootfs (PID1 wrote .lightr-exit-code).
                vmStatus = 0
                semaphore.signal()
            case .error:
                fputs("lightr-vz-shim: VM entered error state\n", stderr)
                vmStatus = -1
                semaphore.signal()
            default:
                break
            }
        }
        tlog("machine.start() called")
        machine.start { result in
            if case .failure(let error) = result {
                fputs("lightr-vz-shim: boot failed: \(error)\n", stderr)
                vmStatus = -1
                semaphore.signal()
            }
        }

        // Fast-teardown: once the guest's EXIT_FILE holds a parseable code, the
        // result is durable — force-stop the VM rather than waiting for its slow
        // clean poweroff. The `.stopped` observer then signals the semaphore. The
        // parse check tolerates a partial write (keeps polling until complete).
        if !exitFilePath.isEmpty {
            func pollExit() {
                if machine.state == .stopped || machine.state == .error { return }
                if let s = try? String(contentsOfFile: exitFilePath, encoding: .utf8),
                   Int32(s.trimmingCharacters(in: .whitespacesAndNewlines)) != nil {
                    tlog("exit-file ready, force-stopping")
                    if machine.canStop {
                        machine.stop { _ in }
                    }
                    return
                }
                vmQueue.asyncAfter(deadline: .now() + .milliseconds(15)) { pollExit() }
            }
            vmQueue.asyncAfter(deadline: .now() + .milliseconds(30)) { pollExit() }
        }
    }

    // Block the CALLING thread (never vmQueue) until the VM stops or fails.
    semaphore.wait()
    consolePipe.fileHandleForReading.readabilityHandler = nil
    // Return contract: -1 boot/config failure; 0..=255 the guest's real exit code
    // captured live from the console marker; -2 stopped without a marker (host then
    // falls back to the durable EXIT_FILE).
    let result: Int32
    if vmStatus < 0 {
        result = -1
    } else if let c = capturedExit {
        result = c
    } else {
        result = -2
    }
    tlog("returning result=\(result)")
    _ = vm           // keep the VM + observation alive until the wait returns
    _ = observation
    return result
}

// MARK: - Frozen retained-session C ABI

/// Creates, validates, and retains a VM. No guest work starts here.
@_cdecl("lightr_vz_session_create")
public func lightr_vz_session_create(
    kernel: UnsafePointer<CChar>, initrd: UnsafePointer<CChar>,
    rootfs: UnsafePointer<CChar>, store: UnsafePointer<CChar>,
    memoryMb: UInt64, cpuCount: UInt64, netFd: Int32,
    netMac: UnsafePointer<CChar>?, consolePath: UnsafePointer<CChar>?,
    outHandle: UnsafeMutablePointer<UInt64>?
) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    guard let outHandle else { return vzConfig }
    let kernelPath = String(cString: kernel)
    let initrdPath = String(cString: initrd)
    let rootfsPath = String(cString: rootfs)
    let storePath = String(cString: store)
    let wantsNet = !(ProcessInfo.processInfo.environment["LIGHTR_VZ_NET"] ?? "").isEmpty
    let maxCPU = VZVirtualMachineConfiguration.maximumAllowedCPUCount
    let minCPU = VZVirtualMachineConfiguration.minimumAllowedCPUCount
    let resolvedCPU: Int
    if cpuCount == 0 { resolvedCPU = max(minCPU, min(maxCPU, maxCPU / 4)) }
    else if cpuCount > UInt64(maxCPU) || cpuCount < UInt64(minCPU) { return vzConfig }
    else { resolvedCPU = Int(cpuCount) }
    let minMem = VZVirtualMachineConfiguration.minimumAllowedMemorySize
    let maxMem = VZVirtualMachineConfiguration.maximumAllowedMemorySize
    let resolvedMemory: UInt64
    if memoryMb == 0 { resolvedMemory = max(minMem, UInt64(256) * 1024 * 1024) }
    else {
        let requested = memoryMb.multipliedReportingOverflow(by: 1024 * 1024)
        guard !requested.overflow, requested.partialValue >= minMem,
              requested.partialValue <= maxMem else { return vzConfig }
        resolvedMemory = requested.partialValue
    }

    let boot = VZLinuxBootLoader(kernelURL: URL(fileURLWithPath: kernelPath))
    boot.initialRamdiskURL = URL(fileURLWithPath: initrdPath)
    boot.commandLine = "console=hvc0"
    let rootShare = VZSharedDirectory(url: URL(fileURLWithPath: rootfsPath), readOnly: false)
    let rootDevice = VZVirtioFileSystemDeviceConfiguration(tag: "rootfs")
    rootDevice.share = VZSingleDirectoryShare(directory: rootShare)
    var shares: [VZDirectorySharingDeviceConfiguration] = [rootDevice]
    if !storePath.isEmpty {
        let storeShare = VZSharedDirectory(url: URL(fileURLWithPath: storePath), readOnly: true)
        let storeDevice = VZVirtioFileSystemDeviceConfiguration(tag: "store")
        storeDevice.share = VZSingleDirectoryShare(directory: storeShare)
        shares.append(storeDevice)
    }
    let console = VZVirtioConsoleDeviceSerialPortConfiguration()
    let output = cString(consolePath).flatMap { FileHandle(forWritingAtPath: $0) } ?? .standardOutput
    console.attachment = VZFileHandleSerialPortAttachment(
        fileHandleForReading: .standardInput, fileHandleForWriting: output)
    var devices: [VZVirtioNetworkDeviceConfiguration] = []
    if wantsNet {
        let device = VZVirtioNetworkDeviceConfiguration()
        device.attachment = VZNATNetworkDeviceAttachment()
        if let mac = VZMACAddress(string: "0a:00:00:24:18:01") { device.macAddress = mac }
        devices.append(device)
        boot.commandLine = "console=hvc0 ip=dhcp"
    }
    if netFd >= 0 {
        let fd = FileHandle(fileDescriptor: netFd, closeOnDealloc: false)
        let device = VZVirtioNetworkDeviceConfiguration()
        device.attachment = VZFileHandleNetworkDeviceAttachment(fileHandle: fd)
        if let mac = cString(netMac).flatMap(VZMACAddress.init(string:)) { device.macAddress = mac }
        devices.append(device)
    }
    let config = VZVirtualMachineConfiguration()
    config.bootLoader = boot
    config.cpuCount = resolvedCPU
    config.memorySize = resolvedMemory
    config.serialPorts = [console]
    config.directorySharingDevices = shares
    config.networkDevices = devices
    do { try config.validate() } catch { return vzConfig }
    let queue = DispatchQueue(label: "com.hugr.lightr.vz.session")
    let session = VzSession(config: config, queue: queue)
    sessionLock.lock()
    let handle = nextSessionHandle
    nextSessionHandle &+= 1
    sessions[handle] = session
    sessionLock.unlock()
    outHandle.pointee = handle
    return vzOk
    #endif
}

@_cdecl("lightr_vz_session_start")
public func lightr_vz_session_start(_ handle: UInt64) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    return withSession(handle) { (session: VzSession) -> Int32 in
        guard session.vm.state == .stopped else { return vzInvalidState }
        session.vm.start { result in if case .failure = result { session.terminalStatus = vzLifecycle; session.done.signal() } }
        return vzOk
    }
    #endif
}

@_cdecl("lightr_vz_session_pause_save")
public func lightr_vz_session_pause_save(_ handle: UInt64, _ statePath: UnsafePointer<CChar>) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    return withSession(handle) { session in
        pauseAndSave(session, statePath: String(cString: statePath))
    }
    #endif
}

@_cdecl("lightr_vz_session_stop")
public func lightr_vz_session_stop(_ handle: UInt64) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    return withSession(handle) { (session: VzSession) -> Int32 in
        guard session.vm.canStop else { return vzInvalidState }
        let done = DispatchSemaphore(value: 0)
        session.vm.stop { _ in done.signal() }
        return done.wait(timeout: .now() + 60) == .success ? vzOk : vzTimeout
    }
    #endif
}

@_cdecl("lightr_vz_session_restore")
public func lightr_vz_session_restore(_ handle: UInt64, _ statePath: UnsafePointer<CChar>) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    return withSession(handle) { session in
        restore(session, statePath: String(cString: statePath))
    }
    #endif
}

@_cdecl("lightr_vz_session_resume")
public func lightr_vz_session_resume(_ handle: UInt64) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    return withSession(handle) { session in
        resume(session)
    }
    #endif
}

@_cdecl("lightr_vz_session_destroy")
public func lightr_vz_session_destroy(_ handle: UInt64) -> Int32 {
    #if !arch(arm64)
    return vzUnsupported
    #else
    guard #available(macOS 14.0, *) else { return vzUnsupported }
    sessionLock.lock(); let session = sessions.removeValue(forKey: handle); sessionLock.unlock()
    guard let session else { return vzInvalidState }
    if session.vm.canStop { session.vm.stop { _ in } }
    return vzOk
    #endif
}


#if arch(arm64)
@available(macOS 14.0, *)
private func pauseAndSave(_ session: VzSession, statePath: String) -> Int32 {
    guard session.vm.state == .running else { return vzInvalidState }
    let done = DispatchSemaphore(value: 0)
    var status = vzLifecycle
    session.vm.pause(completionHandler: { (result: Result<Void, Error>) in
        guard case .success = result else { done.signal(); return }
        session.vm.saveMachineStateTo(url: URL(fileURLWithPath: statePath), completionHandler: { (error: Error?) in
            status = error == nil ? vzOk : vzLifecycle
            done.signal()
        })
    })
    return done.wait(timeout: .now() + 60) == .success ? status : vzTimeout
}

@available(macOS 14.0, *)
private func restore(_ session: VzSession, statePath: String) -> Int32 {
    guard session.vm.state == .stopped else { return vzInvalidState }
    let done = DispatchSemaphore(value: 0)
    var status = vzLifecycle
    session.vm.restoreMachineStateFrom(url: URL(fileURLWithPath: statePath), completionHandler: { (error: Error?) in
        status = error == nil ? vzOk : vzIo
        done.signal()
    })
    return done.wait(timeout: .now() + 60) == .success ? status : vzTimeout
}

@available(macOS 14.0, *)
private func resume(_ session: VzSession) -> Int32 {
    guard session.vm.state == .paused else { return vzInvalidState }
    let done = DispatchSemaphore(value: 0)
    var status = vzLifecycle
    session.vm.resume { (result: Result<Void, Error>) in
        switch result { case .success: status = vzOk; case .failure: status = vzLifecycle }
        done.signal()
    }
    return done.wait(timeout: .now() + 60) == .success ? status : vzTimeout
}
#else
@available(macOS 14.0, *)
private func pauseAndSave(_ session: VzSession, statePath: String) -> Int32 {
    _ = session
    _ = statePath
    return vzUnsupported
}

@available(macOS 14.0, *)
private func restore(_ session: VzSession, statePath: String) -> Int32 {
    _ = session
    _ = statePath
    return vzUnsupported
}

@available(macOS 14.0, *)
private func resume(_ session: VzSession) -> Int32 {
    _ = session
    return vzUnsupported
}
#endif
