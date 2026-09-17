// 백엔드 주소. 로컬(127.0.0.1·localhost)에서 열면 로컬 백엔드를, 그 밖에서는 배포된 백엔드를 쓴다.
// 주소 뒤에 ?api=http://… 를 붙이면 그 값이 우선한다(브라우저에 기억해 둔다).
const LOCAL = ["127.0.0.1", "localhost"].includes(location.hostname);
const DEFAULT_API = LOCAL ? "http://127.0.0.1:8000" : "https://video-report-book.onrender.com";

const fromQuery = new URLSearchParams(location.search).get("api");
if (fromQuery) {
  try { localStorage.setItem("api", fromQuery); } catch (e) { /* 저장소를 못 쓰는 환경이면 이번만 쓴다 */ }
}
let remembered = null;
try { remembered = localStorage.getItem("api"); } catch (e) { /* 위와 같음 */ }

export const API_BASE = (fromQuery || remembered || DEFAULT_API).replace(/\/$/, "");
