"""Noninteractive permission status. Never requests access or launches an app."""

import ctypes
import sys


def perform(operation, p):
    result = {}
    if sys.platform != "darwin":
        return {
            "calendar": "unsupported_platform",
            "reminders": "unsupported_platform",
            "screen_recording": "unsupported_platform",
            "notes_automation": "unsupported_platform",
            "mail_automation": "unsupported_platform",
            "safari_automation": "unsupported_platform",
        }
    try:
        import EventKit as E

        states = {
            0: "not_determined",
            1: "restricted",
            2: "denied",
            3: "full_access",
            4: "write_only",
        }
        for name, entity in [
            ("calendar", E.EKEntityTypeEvent),
            ("reminders", E.EKEntityTypeReminder),
        ]:
            result[name] = states.get(
                int(E.EKEventStore.authorizationStatusForEntityType_(entity)), "unknown"
            )
    except Exception:
        result.update(calendar="unknown", reminders="unknown")
    try:
        cg = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        result["screen_recording"] = (
            "granted" if cg.CGPreflightScreenCaptureAccess() else "not_granted"
        )
    except Exception:
        result["screen_recording"] = "unknown"
    # Apple Events has a non-prompting preflight API. A true wildcard send event
    # reports the current host's authorization without launching target apps.
    try:
        ae = ctypes.CDLL(
            "/System/Library/Frameworks/CoreServices.framework/CoreServices"
        )

        class AEDesc(ctypes.Structure):
            _fields_ = [
                ("descriptorType", ctypes.c_uint32),
                ("dataHandle", ctypes.c_void_p),
            ]

        ae.AECreateDesc.argtypes = [
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.POINTER(AEDesc),
        ]
        ae.AEDeterminePermissionToAutomateTarget.argtypes = [
            ctypes.POINTER(AEDesc),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        ae.AEDisposeDesc.argtypes = [ctypes.POINTER(AEDesc)]
        for name, bundle in [
            ("notes_automation", b"com.apple.Notes"),
            ("mail_automation", b"com.apple.mail"),
            ("safari_automation", b"com.apple.Safari"),
        ]:
            desc = AEDesc()
            if (
                ae.AECreateDesc(
                    int.from_bytes(b"bund", "big"),
                    bundle,
                    len(bundle),
                    ctypes.byref(desc),
                )
                != 0
            ):
                result[name] = "unknown"
                continue
            try:
                status = ae.AEDeterminePermissionToAutomateTarget(
                    ctypes.byref(desc),
                    int.from_bytes(b"****", "big"),
                    int.from_bytes(b"****", "big"),
                    False,
                )
                result[name] = {
                    0: "granted",
                    -1743: "denied",
                    -1744: "not_determined",
                    -600: "target_not_running",
                }.get(status, "unknown")
            finally:
                ae.AEDisposeDesc(ctypes.byref(desc))
    except Exception:
        for name in ("notes_automation", "mail_automation", "safari_automation"):
            result.setdefault(name, "unknown")
    return result
