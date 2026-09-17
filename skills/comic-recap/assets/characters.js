// 캐릭터를 SVG로 그린다. 생김새와 표정의 정의는 cast.json에 있고, 여기는 그것을 선과 도형으로 옮기는 코드다.
// 그림체를 바꾸려면 이 파일의 drawCharacter만 바꾸면 된다: (캐릭터 id, 표정 id, 좌우반전 여부) → SVG 문자열.
function drawCharacter(CAST, charId, moodId, flip) {
  var c = CAST.characters[charId], m = CAST.moods[moodId] || CAST.moods.neutral;
  var ink = "#23262d", p = [];

  // 뒤로 늘어지는 머리(긴 머리)는 몸보다 먼저 그린다
  if (c.hairstyle === "long") p.push('<path d="M27,56 Q25,16 60,16 Q95,16 93,56 L96,118 Q60,128 24,118 Z" fill="' + c.hair + '"/>');

  // 왼팔(늘 내림) → 몸통 → 목 → 머리
  p.push('<path d="M32,112 L24,152" stroke="' + c.shirt + '" stroke-width="13" stroke-linecap="round" fill="none"/>');
  p.push('<circle cx="24" cy="155" r="6.5" fill="' + c.skin + '"/>');
  p.push('<path d="M26,172 Q24,100 60,98 Q96,100 94,172 Z" fill="' + c.shirt + '"/>');
  p.push('<rect x="53" y="76" width="14" height="26" rx="5" fill="' + c.skin + '"/>');
  p.push('<circle cx="60" cy="52" r="30" fill="' + c.skin + '"/>');

  // 앞머리
  if (c.hairstyle === "bob") p.push('<path d="M28,58 Q24,16 60,16 Q96,16 92,58 L93,76 Q87,78 86,62 Q84,38 60,36 Q36,38 34,62 Q33,78 27,76 Z" fill="' + c.hair + '"/>');
  else p.push('<path d="M29,50 Q28,16 60,16 Q92,16 91,50 Q82,32 60,33 Q38,32 29,50 Z" fill="' + c.hair + '"/>');

  // 눈
  [49, 71].forEach(function (x) {
    if (m.eyes === "arc") p.push('<path d="M' + (x - 5) + ',56 Q' + x + ',49 ' + (x + 5) + ',56" stroke="' + ink + '" stroke-width="2.6" fill="none" stroke-linecap="round"/>');
    else if (m.eyes === "wide") p.push('<circle cx="' + x + '" cy="54" r="5.5" fill="#fff" stroke="' + ink + '" stroke-width="1.6"/><circle cx="' + x + '" cy="54" r="2.2" fill="' + ink + '"/>');
    else p.push('<circle cx="' + x + '" cy="55" r="3" fill="' + ink + '"/>');
  });

  // 눈썹
  var brows = {
    flat: ["M43,44 L55,44", "M65,44 L77,44"], up: ["M43,40 L55,39", "M65,39 L77,40"],
    tilt: ["M43,45 L55,44", "M65,41 L77,37"], sad: ["M43,47 L55,42", "M65,42 L77,47"]
  }[m.brow] || [];
  brows.forEach(function (d) { p.push('<path d="' + d + '" stroke="' + ink + '" stroke-width="2.4" stroke-linecap="round"/>'); });

  if (c.glasses) p.push('<g fill="none" stroke="' + ink + '" stroke-width="1.8"><circle cx="49" cy="55" r="9"/><circle cx="71" cy="55" r="9"/><path d="M58,55 L62,55"/></g>');

  // 입
  p.push({
    smile: '<path d="M52,67 Q60,75 68,67" stroke="' + ink + '" stroke-width="2.4" fill="none" stroke-linecap="round"/>',
    open: '<ellipse cx="60" cy="70" rx="6.5" ry="5" fill="#8a3434"/>',
    o: '<circle cx="60" cy="71" r="4" fill="#8a3434"/>',
    flat: '<path d="M54,70 L66,70" stroke="' + ink + '" stroke-width="2.4" stroke-linecap="round"/>',
    frown: '<path d="M52,73 Q60,66 68,73" stroke="' + ink + '" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
  }[m.mouth]);

  // 오른팔: 표정에 따라 움직인다
  var arm = { down: ["M88,112 L96,152", 96, 155], point: ["M88,110 L122,82", 126, 79], raise: ["M88,110 L108,66", 110, 61], chin: ["M88,112 L100,140 L72,90", 70, 86] }[m.arm];
  p.push('<path d="' + arm[0] + '" stroke="' + c.shirt + '" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none"/>');
  p.push('<circle cx="' + arm[1] + '" cy="' + arm[2] + '" r="6.5" fill="' + c.skin + '"/>');

  var body = flip ? '<g transform="translate(130,0) scale(-1,1)">' + p.join("") + "</g>" : p.join("");
  // 물음표·느낌표는 뒤집히면 안 되므로 반전 묶음 바깥에 그린다
  var mark = m.mark ? '<text x="' + (flip ? 14 : 116) + '" y="30" font-size="30" font-weight="800" text-anchor="middle" fill="#d9480f">' + m.mark + "</text>" : "";
  return '<svg viewBox="-10 0 150 172" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="' + charId + " " + moodId + '">' + body + mark + "</svg>";
}
