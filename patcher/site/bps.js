// BPS 패치 적용기 — 브라우저 전용, 외부 코드 없음.
//
// 왜 BPS 인가(xdelta 가 아니라): 형식이 작아 해독기를 직접 넣을 수 있고, 파일 끝에 **원본·결과·패치
// CRC32** 가 들어 있어 맞지 않는 원본을 적용 전에 거른다. 받아 가는 파일로는 xdelta 도 함께 둔다.
// 형식: https://www.romhacking.net/documents/746/ (byuu, "BPS patch format")
"use strict";

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes, end = bytes.length) {
  let c = 0xffffffff;
  for (let i = 0; i < end; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function readU32(b, at) {
  return (b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | (b[at + 3] << 24)) >>> 0;
}

// BPS 머리 — 원본·결과 크기와 꼬리 CRC 셋만 먼저 읽는다(원본을 받기 전에 안내할 때 쓴다).
function bpsInfo(patch) {
  if (patch.length < 16 || String.fromCharCode(...patch.subarray(0, 4)) !== "BPS1") {
    throw new Error("BPS 패치 파일이 아닙니다");
  }
  let p = 4;
  const num = () => {
    let data = 0, shift = 1;
    for (;;) {
      const x = patch[p++];
      data += (x & 0x7f) * shift;
      if (x & 0x80) break;
      shift *= 128;
      data += shift;
    }
    return data;
  };
  const sourceSize = num(), targetSize = num(), metaSize = num();
  p += metaSize;
  const tail = patch.length - 12;
  return {
    sourceSize, targetSize, body: p, tail,
    sourceCrc: readU32(patch, tail),
    targetCrc: readU32(patch, tail + 4),
    patchCrc: readU32(patch, tail + 8),
  };
}

// 적용 — 원본 CRC 가 틀리면 손대기 전에 멈춘다. 결과 CRC 까지 맞아야 돌려준다.
function bpsApply(source, patch, onProgress) {
  const info = bpsInfo(patch);
  if (crc32(patch, patch.length - 4) !== info.patchCrc) throw new Error("패치 파일이 깨졌습니다(내려받기를 다시 해 주세요)");
  if (source.length !== info.sourceSize) throw new Error(`원본 크기가 다릅니다 (${source.length.toLocaleString()} ≠ ${info.sourceSize.toLocaleString()} 바이트)`);
  if (crc32(source) !== info.sourceCrc) throw new Error("원본이 이 패치가 기대하는 덤프와 다릅니다");

  const out = new Uint8Array(info.targetSize);
  let p = info.body, o = 0, srcRel = 0, tgtRel = 0, tick = 0;
  const num = () => {
    let data = 0, shift = 1;
    for (;;) {
      const x = patch[p++];
      data += (x & 0x7f) * shift;
      if (x & 0x80) break;
      shift *= 128;
      data += shift;
    }
    return data;
  };
  while (p < info.tail) {
    const data = num();
    const cmd = data & 3, len = Math.floor(data / 4) + 1;
    if (cmd === 0) {                       // SourceRead — 같은 자리 원본 그대로
      out.set(source.subarray(o, o + len), o);
      o += len;
    } else if (cmd === 1) {                // TargetRead — 패치에 실린 새 바이트
      out.set(patch.subarray(p, p + len), o);
      p += len; o += len;
    } else {                               // SourceCopy / TargetCopy — 상대 위치에서 복사
      const d = num();
      const delta = (d & 1 ? -1 : 1) * Math.floor(d / 2);
      if (cmd === 2) {
        srcRel += delta;
        out.set(source.subarray(srcRel, srcRel + len), o);
        srcRel += len; o += len;
      } else {
        tgtRel += delta;
        for (let i = 0; i < len; i++) out[o++] = out[tgtRel++];   // 겹칠 수 있어 한 바이트씩
      }
    }
    if (onProgress && ++tick % 4096 === 0) onProgress(o / info.targetSize);
  }
  if (o !== info.targetSize) throw new Error("패치 적용 결과 크기가 맞지 않습니다");
  if (crc32(out) !== info.targetCrc) throw new Error("적용 결과 검사값이 맞지 않습니다");
  return out;
}

async function sha1Hex(bytes) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-1", bytes));
  return Array.from(d, (b) => b.toString(16).padStart(2, "0")).join("");
}

window.EDPatch = { crc32, bpsInfo, bpsApply, sha1Hex };
