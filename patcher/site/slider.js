// 상세 페이지 스크린샷 넘김 — site.json 의 shots(이미지 경로 목록)를 한 장씩 보인다.
// 버튼·좌우 화살표 키(페이지 어디서나)·점·끌기(터치·마우스)로 넘기고, 넘길 때는 옆으로 미끄러진다(마스터 10-06).
// 이미지를 가로 띠(.track)에 나란히 놓고 띠를 옮긴다 — 끄는 동안은 손가락을 따라오고, 놓으면 제자리로 붙는다.
"use strict";
function EDSlider(box, shots, alt) {
  // 🔴 두 번 불려도 한 번 만든 것처럼 — 페이지는 인라인 데이터로 한 번, site.json 을 받아 한 번 더 그린다.
  //    예전엔 두 번째 호출이 띠 안에 띠를 또 만들어 순서가 밀렸고(첫 장이 끝으로), 단추 처리기도 겹쳐 붙었다.
  //    같은 목록이면 그대로 두고, 바뀌었으면 처음 받은 빈 틀로 갈아 끼우고 다시 만든다.
  const key = JSON.stringify(shots || []);
  if (box._edKey === key) return;
  if (box._edTpl) { const fresh = box._edTpl.cloneNode(true); fresh._edTpl = box._edTpl; box.replaceWith(fresh); box = fresh; }
  else box._edTpl = box.cloneNode(true);
  box._edKey = key;
  if (!shots || !shots.length) { box.hidden = true; return; }
  box.hidden = false;
  let i = 0;
  const stage = box.querySelector(".stage"), dots = box.querySelector(".dots");
  const track = document.createElement("div");
  track.className = "track";
  // 끝↔처음도 넘긴 방향 그대로 미끄러지게(마스터 10-06) — 띠 양 끝에 반대쪽 끝 사본을 하나씩 붙인다.
  //   [마지막 사본, 1, 2, …, n, 첫 사본]. 사본까지 미끄러진 뒤, 전환이 끝나면 진짜 자리로 소리 없이 건너뛴다.
  const loop = shots.length > 1;
  // 한 장 = 칸(.slide) 안의 4:3 그림. 캡처 해상도가 달라도(350×240 · 968×726 …) TV 처럼 4:3 으로 펴서 보인다.
  const imgTag = (src, k, lazy) => `<div class="slide"><img src="${src}" alt="${alt} 화면 ${k + 1} / ${shots.length}" draggable="false"${lazy ? ' loading="lazy"' : ""}></div>`;
  const list = loop ? [shots.length - 1, ...shots.keys(), 0] : [0];
  track.innerHTML = list.map((k, n) => imgTag(shots[k], k, n > 1)).join("");
  stage.querySelector("img").replaceWith(track);
  dots.innerHTML = shots.map((_, k) => `<button type="button" aria-label="${k + 1}번째 화면"></button>`).join("");
  let pos = loop ? 1 : 0;   // 띠 안의 칸 번호(사본 포함)
  const place = (px = 0) => { track.style.transform = `translateX(calc(${-pos * 100}% + ${px}px))`; };
  const jump = (p) => { track.classList.add("drag"); pos = p; place(); void track.offsetWidth; track.classList.remove("drag"); };
  track.addEventListener("transitionend", () => {
    if (pos === 0) jump(shots.length);            // 첫 장에서 뒤로 → 마지막 사본에 닿았으면 진짜 마지막으로
    else if (pos === shots.length + 1) jump(1);   // 마지막에서 앞으로 → 첫 사본에 닿았으면 진짜 처음으로
  });
  const show = (k) => {
    if (loop) {
      // k 는 i±1 이거나 점으로 고른 번호다. 한 칸 이동이면 사본 쪽으로 가서 방향을 지킨다.
      if (k === i + 1 && i === shots.length - 1) pos = shots.length + 1;
      else if (k === i - 1 && i === 0) pos = 0;
      else pos = ((k + shots.length) % shots.length) + 1;
    }
    i = (k + shots.length) % shots.length;
    track.classList.remove("drag");
    place();
    [...track.children].forEach((im, n) => im.setAttribute("aria-hidden", n === pos ? "false" : "true"));
    [...dots.children].forEach((d, n) => d.setAttribute("aria-current", n === i ? "true" : "false"));
  };
  box.querySelector(".prev").addEventListener("click", () => show(i - 1));
  box.querySelector(".next").addEventListener("click", () => show(i + 1));
  dots.addEventListener("click", (e) => { const n = [...dots.children].indexOf(e.target); if (n >= 0) show(n); });
  // 키보드 ←/→ — 슬라이드에 초점이 없어도 페이지 어디서나 넘긴다(마스터 10-06). 한 페이지에 슬라이드는
  //   하나라 문서에 한 번만 건다(다시 만들면 갈아 끼운다). 글을 치는 칸이나 다른 단추를 누르는 중이면 비킨다.
  EDSlider._show = (d) => show(i + d);
  if (!EDSlider._keys) {
    EDSlider._keys = true;
    document.addEventListener("keydown", (e) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || !EDSlider._show) return;
      if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "ArrowLeft") { EDSlider._show(-1); e.preventDefault(); }
      else if (e.key === "ArrowRight") { EDSlider._show(1); e.preventDefault(); }
    });
  }
  box.querySelectorAll(".prev,.next").forEach((b) => { b.hidden = shots.length < 2; });

  // 끌어서 넘기기 — 포인터 이벤트(터치·마우스 공통). 폭의 1/6 넘게 끌면 한 장 넘긴다.
  let x0 = null, y0 = 0, dx = 0, horiz = false;
  stage.addEventListener("pointerdown", (e) => {
    if (shots.length < 2 || e.target.closest("button")) return;
    x0 = e.clientX; y0 = e.clientY; dx = 0; horiz = false;
  });
  stage.addEventListener("pointermove", (e) => {
    if (x0 === null) return;
    dx = e.clientX - x0;
    if (!horiz && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(e.clientY - y0)) {
      horiz = true; track.classList.add("drag"); stage.classList.add("drag");
      stage.setPointerCapture(e.pointerId);
    }
    if (horiz) place(dx);
  });
  const end = () => {
    if (x0 === null) return;
    const moved = horiz && Math.abs(dx) > stage.clientWidth / 6;
    x0 = null; horiz = false; stage.classList.remove("drag");
    show(moved ? (dx < 0 ? i + 1 : i - 1) : i);
  };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
  track.classList.add("drag"); show(0); void track.offsetWidth; track.classList.remove("drag");   // 첫 자리는 미끄러지지 않고 바로
}
