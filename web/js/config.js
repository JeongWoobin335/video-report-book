// 백엔드 주소. 배포할 때 이 값만 바꾼다 (예: "https://video-report-book.onrender.com").
// 개발 중에는 주소 뒤에 ?api=http://127.0.0.1:8000 을 붙이면 그 값이 우선한다(브라우저에 기억해 둔다).
const DEFAULT_API = "http://127.0.0.1:8000";

const fromQuery = new URLSearchParams(location.search).get("api");
if (fromQuery) {
  try { localStorage.setItem("api", fromQuery); } catch (e) { /* 저장소를 못 쓰는 환경이면 이번만 쓴다 */ }
}
let remembered = null;
try { remembered = localStorage.getItem("api"); } catch (e) { /* 위와 같음 */ }

export const API_BASE = (fromQuery || remembered || DEFAULT_API).replace(/\/$/, "");
