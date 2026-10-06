// 상세 페이지 스크린샷 넘김 — site.json 의 shots(이미지 경로 목록)를 한 장씩 보인다.
// 버튼·좌우 화살표 키·점으로 넘기고, 픽셀이 뭉개지지 않게 정수배로만 키운다.
"use strict";
function EDSlider(box, shots, alt) {
  if (!shots || !shots.length) { box.hidden = true; return; }
  box.hidden = false;
  let i = 0;
  const img = box.querySelector("img"), dots = box.querySelector(".dots");
  dots.innerHTML = shots.map((_, k) => `<button type="button" aria-label="${k + 1}번째 화면"></button>`).join("");
  const show = (k) => {
    i = (k + shots.length) % shots.length;
    img.src = shots[i];
    img.alt = `${alt} 화면 ${i + 1} / ${shots.length}`;
    [...dots.children].forEach((d, n) => d.setAttribute("aria-current", n === i ? "true" : "false"));
  };
  box.querySelector(".prev").addEventListener("click", () => show(i - 1));
  box.querySelector(".next").addEventListener("click", () => show(i + 1));
  dots.addEventListener("click", (e) => { const n = [...dots.children].indexOf(e.target); if (n >= 0) show(n); });
  box.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") show(i - 1); if (e.key === "ArrowRight") show(i + 1); });
  box.querySelectorAll(".prev,.next").forEach((b) => { b.hidden = shots.length < 2; });
  show(0);
}
