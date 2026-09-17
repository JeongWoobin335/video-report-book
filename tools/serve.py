"""결과물을 브라우저로 확인하기 위한 개발용 정적 서버.

파이썬 기본 http.server는 Range 요청을 지원하지 않아 영상의 구간 이동(타임스탬프 클릭)이 동작하지 않는다.
이 서버는 Range를 지원한다.  사용: python tools/serve.py [포트]
"""
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        self.remaining = None
        rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(rng.group(1)) if rng.group(1) else max(size - int(rng.group(2)), 0)
        end = min(int(rng.group(2)), size - 1) if rng.group(1) and rng.group(2) else size - 1
        if start > end:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(self.remaining))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining > 0:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        if "Accept-Ranges" not in str(self._headers_buffer):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), RangeHandler).serve_forever()
