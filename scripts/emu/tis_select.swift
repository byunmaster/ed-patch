// macOS 입력 소스를 **읽고 고른다** — 에뮬레이터 실행 직전에 ASCII 자판을 강제하는 데 쓴다.
//
//   tis-select              현재 입력 소스 ID 를 찍는다
//   tis-select <ID>         그 입력 소스로 바꾼다 (예: com.apple.keylayout.ABC)
//
// ── 왜 이게 필요한가 (2026-08-31, 크래시 리포트 셋으로 확정) ──────────────────
// 🔴 **한글 입력 소스가 붙은 채로는 DOSBox-X(SDL1)가 반드시 뻗는다.** 경고가 아니라 사실이다:
//      -[SDLTranslatorResponder insertText:replacementRange:]
//        → __strncpy_chk → SIGSEGV (KERN_INVALID_ADDRESS at 0x0)
//    IME 가 조합을 확정하며 넘기는 문자열을 SDL1 이 ASCII C 문자열로 바꾸는데, 한글은
//    ASCII 로 못 바꿔 NULL 이 나오고 그걸 그대로 strncpy 한다. **비ASCII 확정 = 즉사**다.
//    ~/Library/Logs/DiagnosticReports 의 dosbox-x-*.ips 셋이 전부 같은 자리였다.
// 그리고 조합 중인 키는 게임까지 오지도 않는다 — 「키가 안 먹는다」와 「뻗는다」가
// 증상은 둘인데 **원인이 하나**다. 그래서 경고만 찍지 않고 실행 직전에 바꿔 준다.
//
// ⚠ Swift 인 이유는 이게 Carbon(TIS) API 라서다 — 셸에 대응물이 없다. 27줄이고 macOS
//   전용이라 「플랫폼마다 언어를 고른다」(루트 CLAUDE.md)에 그대로 해당한다.
import Carbon
import Foundation

func sources() -> [TISInputSource] {
  (TISCreateInputSourceList(nil, false)?.takeRetainedValue() as? [TISInputSource]) ?? []
}

func id(of s: TISInputSource) -> String? {
  guard let p = TISGetInputSourceProperty(s, kTISPropertyInputSourceID) else { return nil }
  return (Unmanaged<CFString>.fromOpaque(p).takeUnretainedValue() as String)
}

// 인자가 없으면 지금 것을 찍고 끝 — 실행 뒤 되돌리려는 호출자를 위한 것이다.
guard CommandLine.arguments.count > 1 else {
  guard let cur = TISCopyCurrentKeyboardInputSource()?.takeRetainedValue(),
        let cid = id(of: cur) else { exit(2) }
  print(cid)
  exit(0)
}

let want = CommandLine.arguments[1]
for s in sources() where id(of: s) == want {
  let st = TISSelectInputSource(s)
  if st != noErr { FileHandle.standardError.write("tis-select: 전환 실패 (\(st))\n".data(using: .utf8)!) }
  exit(st == noErr ? 0 : 1)
}
FileHandle.standardError.write("tis-select: 그런 입력 소스가 없다 — \(want)\n".data(using: .utf8)!)
exit(3)
