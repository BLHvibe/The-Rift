"""Smoke test for the_rift/data/draft_sync.py — the client wrapper the UI uses.

Verifies:
  • connect() returns a working client
  • Background thread mirrors state into client.state()
  • apply() round-trips through the server
  • Two wrappers in the same process see each other's mutations
  • close() cleanly tears down

Requires server running on localhost:8000.
"""
import os, sys, time, pathlib

# Import draft_sync from the real project.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "the_rift"))
from data import draft_sync   # noqa: E402


def wait_until(pred, timeout=3.0, label=""):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    raise AssertionError(f"timeout: {label}")


def main():
    url = "ws://localhost:8000"
    room = "wrapper-test"
    pw = "pw"

    print("[1] blue1 connects (host)")
    blue = draft_sync.DraftSyncClient(
        url=url, room=room, password=pw, name="Alice", slot="blue1")
    wait_until(lambda: blue.is_connected(), label="blue connected")
    wait_until(lambda: blue.state() is not None, label="blue got hello")
    assert blue.you().get("is_host") is True, "blue should be host"
    print("    is_host ok, snap rev =", blue.state()["rev"])

    print("[2] red1 connects")
    red = draft_sync.DraftSyncClient(
        url=url, room=room, password=pw, name="Bob", slot="red1")
    wait_until(lambda: red.state() is not None, label="red got hello")
    assert red.you().get("is_host") is False

    print("[3] blue applies first ban -> both see it")
    pre_rev = blue.state()["rev"]
    blue.apply("Yasuo")
    wait_until(lambda: blue.state()["rev"] > pre_rev, label="blue saw broadcast")
    wait_until(lambda: red.state()["rev"] > pre_rev, label="red saw broadcast")
    assert blue.state()["state"]["bans"]["BLUE"] == ["Yasuo"]
    assert red.state()["state"]["bans"]["BLUE"] == ["Yasuo"]
    print("    both clients agree:", red.state()["state"]["bans"])

    print("[4] red tries to act on BLUE's turn -> error surfaced")
    err_before = red.last_error()
    red.apply("Sona")    # pointer is 1 -> RED's turn now actually, so this works
    # pointer is 1 (after blue's first ban), action 1 = RED ban. so this IS red's turn.
    # We test wrong-side by trying blue's turn after this.
    wait_until(lambda: red.state()["state"]["pointer"] == 2,
               label="red ban applied")
    print("    pointer now:", red.state()["state"]["pointer"])

    print("[5] red tries to act on BLUE's turn (pointer=2 -> BLUE) -> error")
    err_before = red.last_error()
    red.apply("Zed")     # pointer 2 belongs to BLUE
    # Wait briefly for the server error to come back.
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if red.last_error() and red.last_error() != err_before:
            break
        time.sleep(0.05)
    assert red.last_error() and "turn" in red.last_error().lower(), \
        f"expected wrong-turn error, got {red.last_error()!r}"
    print("    got expected error:", red.last_error())
    # Pointer should be unchanged.
    assert red.state()["state"]["pointer"] == 2

    print("[6] close both, ensure clean")
    blue.close()
    red.close()
    time.sleep(0.3)
    print("    closed without exception")

    print("\nALL WRAPPER TESTS PASSED")


if __name__ == "__main__":
    main()
