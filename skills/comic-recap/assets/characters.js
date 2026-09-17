// 캐릭터 그리기 — Open Peeps(CC0) 파츠를 겹쳐 한 사람을 만든다.
// PARTS는 build_comic.py가 이 만화에 쓰이는 파츠만 골라 data URI로 넣어 준다: {"body/Tee 2": "data:image/svg+xml;base64,…", …}
function peepParts(cast, charId, moodId) {
  var c = cast.characters[charId], m = cast.moods[moodId] || cast.moods.neutral;
  return { body: "body/" + (c.bodies[moodId] || c.bodies["default"]), head: "head/" + c.head, face: "face/" + m.face };
}

function drawCharacter(cast, charId, moodId, flip) {
  var p = peepParts(cast, charId, moodId), c = cast.characters[charId];
  var img = function (key, x, y, w, h) { return '<image href="' + PARTS[key] + '" x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '"/>'; };
  return '<svg class="peep-svg" viewBox="-75 0 1000 1200" aria-hidden="true">' +
    '<circle cx="425" cy="560" r="430" fill="' + c.color + '" opacity=".55"/>' +        // 인물마다 다른 색의 후광 — 옷이 바뀌어도 누구인지 알아보게
    '<g' + (flip ? ' transform="translate(850 0) scale(-1 1)"' : "") + ">" +
    img(p.body, 16, 467, (cast.body_width || {})[p.body.slice(5)] || 818, 733) + img(p.head, 190, 40, 473, 567) + img(p.face, 349, 226, 289, 293) + "</g></svg>";
}
