"""抓取音樂會資訊，輸出 concerts/data.json。

來源：
  - OPENTIX 兩廳院文化生活（公開 sitemap + 節目頁內嵌資料）
  - KKTIX（公開 Atom feed，以關鍵字搜尋）
  - Blue Note Taipei 台北藍調（官網演出表）
牛耳藝術的節目在 OPENTIX / KKTIX 售票，依主辦單位名稱另外標記。

只用 Python 標準函式庫，直接執行：python scripts/fetch_concerts.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "concerts" / "data.json"
CACHE = ROOT / "scripts" / "cache" / "opentix.json"

TZ = dt.timezone(dt.timedelta(hours=8))
NOW = dt.datetime.now(TZ)
UA = "Mozilla/5.0 (compatible; concert-board/1.0; personal use)"

# 每次執行最多重新抓幾個 OPENTIX 節目頁（其餘下次再抓），以及每頁間隔秒數
OPENTIX_MAX_FETCH = int(__import__("os").environ.get("OPENTIX_MAX_FETCH", 400))
OPENTIX_DELAY = 0.6


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def iso(d: dt.datetime | None) -> str | None:
    return d.astimezone(TZ).isoformat(timespec="minutes") if d else None


def from_epoch(v) -> dt.datetime | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 1e11:  # 毫秒
        v /= 1000
    return dt.datetime.fromtimestamp(v, TZ)


def clean(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def norm(s: str) -> str:
    """把 𝐂𝐡𝐞𝐧𝐠𝐲𝐮、全形英數等花俏字元轉回一般字元。"""
    return unicodedata.normalize("NFKC", s or "").strip()


# ---------------------------------------------------------------- 樂種分類

GENRE_RULES = [
    ("國樂", r"國樂|揚琴|二胡|琵琶|古箏|[^長]笛子|梆笛|曲笛|嗩吶|中阮|柳琴|絲竹|南管|北管|民族管弦|胡琴|高胡|笙|箏樂|中國音樂|傳統音樂|客家八音"),
    ("爵士", r"爵士|jazz|swing|big ?band|bossa|藍調|blues|bebop|scat"),
    ("古典", r"交響|管弦|弦樂|指揮|樂季|音樂系|音樂學系|新年音樂會|ESO|TSO|TPO|KSO|NTSO|EMO|協奏|奏鳴|室內樂|獨奏會|鋼琴|小提琴|大提琴|中提琴|低音提琴|長笛|單簧管|豎笛|雙簧管|法國號|小號|長號|豎琴|管風琴|大鍵琴|古典|歌劇|合唱|聲樂|藝術歌曲|四重奏|三重奏|二重奏|五重奏|管樂團|木管|銅管|打擊樂|巴赫|貝多芬|莫札特|蕭邦|布拉姆斯|馬勒|舒伯特|舒曼|柴可夫斯基|拉赫曼尼諾夫|德布西|拉威爾|韓德爾|海頓|孟德爾頌|德弗札克|西貝流士|蕭士塔高維契|普羅高菲夫|symphon|philharmon|orchestra|recital|concerto|sonata|quartet|chamber|NSO|國家交響|長榮交響|台北市立交響|臺北市立交響|台灣愛樂"),
    ("流行", r"演唱會|巡迴|巡演|world tour|tour|音樂祭|搖滾|rock|pop|hip ?hop|饒舌|電音|樂團專場|專場|fan ?meeting|見面會|k-?pop|j-?pop|唱作|新專輯|專輯發表|樂團|live ?house|演出.*樂隊"),
]
GENRE_RE = [(g, re.compile(p, re.I)) for g, p in GENRE_RULES]
MUSIC_HINT = re.compile(r"音樂|演唱|演奏|樂團|樂手|歌手|concert|live|music|獨奏|合唱|樂", re.I)
NOT_EVENT = re.compile(r"課程|講座|工作坊|諮詢|體驗課|招生|徵選|甄選|大師班|講堂|導覽|市集|展覽|特展|互動展|周邊|取貨|加購|喜劇|脫口秀|單口|跑步|路跑|航班", re.I)
OVERSEAS = re.compile(r"香港|澳門|hong ?kong|macau|新加坡|singapore|吉隆坡|kuala|曼谷|bangkok|東京|大阪|首爾|seoul|上海|北京|深圳|廣州", re.I)


def classify(title: str, *others: str, default: str | None = "其他") -> str | None:
    """先只看標題判斷；標題看不出來，再加上主辦單位和簡介一起判斷。"""
    for blob in (title, " ".join(t for t in (title, *others) if t)):
        for g, rx in GENRE_RE:
            if rx.search(blob):
                return g
    return default


CITY_RE = re.compile(r"(臺北|新北|桃園|臺中|臺南|高雄|新竹|基隆|嘉義|苗栗|彰化|南投|雲林|屏東|宜蘭|花蓮|臺東|澎湖|金門|連江)[市縣]?")
VENUE_CITY = {"國家音樂廳": "臺北市", "國家戲劇院": "臺北市", "衛武營": "高雄市", "國家歌劇院": "臺中市",
              "小巨蛋": "臺北市", "流行音樂中心": "臺北市", "中山堂": "臺北市", "國父紀念館": "臺北市",
              "Zepp New Taipei": "新北市", "Legacy": "臺北市", "河岸留言": "臺北市", "西門紅樓": "臺北市"}


def city_of(*texts: str) -> str:
    blob = " ".join(texts).replace("台", "臺")
    m = CITY_RE.search(blob)
    if m:
        name = m.group(1)
        return name + ("縣" if name in ("苗栗", "彰化", "南投", "雲林", "屏東", "宜蘭", "花蓮", "臺東", "澎湖", "金門", "連江") else "市")
    for k, v in VENUE_CITY.items():
        if k in blob:
            return v
    return ""


def niuer(*texts: str) -> bool:
    return any("牛耳" in (t or "") for t in texts)


# ---------------------------------------------------------------- OPENTIX

def _parse_js_args(src: str) -> list:
    """把 window.__NUXT__=(function(...){...}(ARGS)) 的 ARGS 解析成 Python 值。"""
    vals, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in " ,\n\t":
            i += 1
            continue
        if c == '"':
            j = i + 1
            while src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            raw = src[i:j + 1]
            try:
                vals.append(json.loads(raw))
            except ValueError:
                vals.append(raw[1:-1])
            i = j + 1
        elif c in "{[" or src.startswith("Array(", i):
            depth, j = 0, i
            while j < n:
                if src[j] == '"':
                    j += 1
                    while src[j] != '"':
                        j += 2 if src[j] == "\\" else 1
                elif src[j] in "{[(":
                    depth += 1
                elif src[j] in "}])":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            vals.append(None)
            i = j + 1
        else:
            m = re.match(r"void 0|-?[\d.]+(?:e[+-]?\d+)?|[A-Za-z_$][\w$]*", src[i:])
            if not m:
                i += 1
                continue
            tok = m.group(0)
            if tok in ("void 0", "null", "undefined"):
                vals.append(None)
            elif tok in ("true", "false"):
                vals.append(tok == "true")
            else:
                try:
                    vals.append(float(tok) if any(ch in tok for ch in ".e") else int(tok))
                except ValueError:
                    vals.append(tok)
            i += len(tok)
    return vals


class Nuxt:
    def __init__(self, page: str):
        i = page.find("window.__NUXT__=(function(")
        if i < 0:
            raise ValueError("no __NUXT__")
        j = page.find("</script>", i)
        s = page[i:j]
        p0 = s.find("(function(") + len("(function(")
        params = s[p0:s.find(")", p0)].split(",")
        a0 = s.rfind("}(")
        args = _parse_js_args(s[a0 + 2:s.rfind("))")])
        self.vars = dict(zip(params, args + [None] * (len(params) - len(args))))
        self.body = s[:a0]

    def val(self, key: str, start: int = 0):
        m = re.compile(r"[{,]" + re.escape(key) + r':(?:"((?:[^"\\]|\\.)*)"|(-?[\d.]+)|([A-Za-z_$][\w$]*))').search(self.body, start)
        if not m:
            return None
        if m.group(1) is not None:
            try:
                return json.loads('"' + m.group(1) + '"')
            except ValueError:
                return m.group(1)
        if m.group(2) is not None:
            return float(m.group(2))
        name = m.group(3)
        if name in ("true", "false"):
            return name == "true"
        return self.vars.get(name)

    def find(self, marker: str) -> int:
        k = self.body.find(marker)
        return k if k >= 0 else 0


def opentix_event(eid: str) -> dict:
    url = f"https://www.opentix.life/event/{eid}"
    page = get(url)
    meta = {}
    for k in ("og:title", "description", "og:image"):
        m = re.search(r'<meta[^>]+(?:property|name)="' + k + r'"[^>]+content="([^"]*)"', page)
        meta[k] = html.unescape(m.group(1)) if m else ""
    title = re.sub(r"\s*—\s*OPENTIX.*$", "", meta["og:title"]).strip()
    desc = meta["description"]
    info = dict(re.findall(r"(時間|地點|主辦單位):([^,]*)", desc))

    rec = {"id": eid, "title": title, "url": url, "image": meta["og:image"],
           "organizer": info.get("主辦單位", "").strip(), "venue": info.get("地點", "").strip(),
           "desc": clean(re.sub(r"^(時間|地點|主辦單位):[^,]*,", "", desc))[:240]}
    try:
        nx = Nuxt(page)
        p = nx.find("program:{")
        rec["title"] = nx.val("name", p) or rec["title"]
        rec["start"] = iso(from_epoch(nx.val("startDateTime", p)))
        rec["end"] = iso(from_epoch(nx.val("endDateTime", p)))
        rec["category"] = nx.val("programMainCategoryName") or ""
        rec["onSale"] = iso(from_epoch(nx.val("onSaleStartDateTime")))
        lo, hi = nx.val("minPrice", p), nx.val("maxPrice", p)
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi > 0:
            rec["price"] = f"{int(lo)}–{int(hi)}" if lo != hi else f"{int(lo)}"
        v = nx.find("venue:{")
        if v:
            rec["venue"] = nx.val("name", v) or rec["venue"]
            rec["city"] = nx.val("city", v) or ""
    except Exception as e:  # 內嵌資料格式變了就退回 meta 的資訊
        log("  OPENTIX nuxt parse failed", eid, e)
    if not rec.get("start") and info.get("時間"):
        d = re.findall(r"\d{4}/\d{2}/\d{2}", info["時間"])
        if d:
            rec["start"] = dt.datetime.strptime(d[0], "%Y/%m/%d").replace(tzinfo=TZ).isoformat(timespec="minutes")
            rec["end"] = dt.datetime.strptime(d[-1] + " 23:59", "%Y/%m/%d %H:%M").replace(tzinfo=TZ).isoformat(timespec="minutes")
            rec["dateOnly"] = True
    return rec


def fetch_opentix() -> list[dict]:
    cache = json.loads(CACHE.read_text("utf-8")) if CACHE.exists() else {}
    sm = get("https://www.opentix.life/otWebSitemap.xml", timeout=60)
    entries = re.findall(r"<loc>https://www\.opentix\.life/event/(\d+)</loc>\s*<lastmod>([^<]+)</lastmod>", sm)
    log(f"OPENTIX sitemap: {len(entries)} events")
    todo = [(eid, lm) for eid, lm in entries if cache.get(eid, {}).get("_lastmod") != lm]
    # 新節目優先（id 越大越新）
    todo.sort(key=lambda x: int(x[0]), reverse=True)
    fetched = 0
    for eid, lm in todo[:OPENTIX_MAX_FETCH]:
        try:
            rec = opentix_event(eid)
            rec["_lastmod"] = lm
            cache[eid] = rec
            fetched += 1
        except Exception as e:
            log("  OPENTIX fail", eid, e)
        time.sleep(OPENTIX_DELAY)
    log(f"OPENTIX fetched {fetched}, pending {max(0, len(todo) - OPENTIX_MAX_FETCH)}")
    live = {eid for eid, _ in entries}
    cache = {k: v for k, v in cache.items() if k in live}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")

    out = []
    for rec in cache.values():
        cat = rec.get("category", "")
        if cat and cat != "音樂":
            continue
        if not cat and not MUSIC_HINT.search(rec["title"] + rec.get("desc", "")):
            continue
        r = {k: v for k, v in rec.items() if not k.startswith("_") and k != "category"}
        r["source"] = "OPENTIX"
        r["genre"] = classify(rec["title"], rec.get("organizer", ""), rec.get("desc", ""))
        out.append(r)
    return out


# ---------------------------------------------------------------- KKTIX

KKTIX_QUERIES = ["音樂會", "演唱會", "爵士", "jazz", "獨奏會", "交響", "室內樂", "國樂", "鋼琴", "合唱", "樂團", "live"]
ATOM = "{http://www.w3.org/2005/Atom}"


def kktix_time(s: str):
    m = re.findall(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2})", s)
    f = lambda x: dt.datetime.strptime(x, "%Y/%m/%d %H:%M").replace(tzinfo=TZ)
    return (f(m[0]) if m else None, f(m[1]) if len(m) > 1 else None)


def fetch_kktix() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in KKTIX_QUERIES:
        url = "https://kktix.com/events.atom?search=" + urllib.parse.quote(q)
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            log("  KKTIX fail", q, e)
            continue
        for e in root.iter(ATOM + "entry"):
            link = e.find(ATOM + "link").get("href")
            if link in seen:
                continue
            title = e.findtext(ATOM + "title", "")
            summary = e.findtext(ATOM + "summary", "")
            content = e.findtext(ATOM + "content", "")
            org = e.findtext(f"{ATOM}author/{ATOM}name", "")
            if NOT_EVENT.search(title) or OVERSEAS.search(title):
                continue
            genre = classify(title, org, summary, default=None)
            if not genre:
                continue
            start, end = kktix_time(content)
            venue = re.search(r"地點：(.*)", content)
            venue = venue.group(1).strip() if venue else ""
            seen[link] = {
                "id": link, "source": "KKTIX", "title": norm(title), "url": link,
                "start": iso(start), "end": iso(end), "venue": venue.split(" / ")[0],
                "city": venue.split(" / ")[1][:3] if " / " in venue else "",
                "organizer": org, "desc": clean(summary)[:240], "genre": genre,
            }
        time.sleep(1)
    log(f"KKTIX: {len(seen)} events")
    return list(seen.values())


# ---------------------------------------------------------------- Blue Note Taipei

def fetch_bluenote() -> list[dict]:
    page = get("https://www.bluenotetaipei.com/shows")
    out, seen = [], set()
    # Wix 活動資料的順序：scheduling → title → description → … → slug
    pat = re.compile(r'"scheduling":\{"config":\{[^{}]*?"startDate":"([^"]+)"(?:,"endDate":"([^"]+)")?.{0,1500}?'
                     r'"title":"((?:[^"\\]|\\.)*)","description":"((?:[^"\\]|\\.)*)".{0,6000}?"slug":"([^"]+)"', re.S)
    p = lambda x: dt.datetime.fromisoformat(x.replace("Z", "+00:00")) if x else None
    for m in pat.finditer(page):
        s, e, title, desc, slug = m.groups()
        start = p(s)
        key = (slug, s)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": f"bluenote-{slug}-{start:%m%d}", "source": "Blue Note Taipei",
            "title": norm(json.loads(f'"{title}"')),
            "url": "https://www.bluenotetaipei.com/event-details/" + slug,
            "start": iso(start), "end": iso(p(e)), "venue": "Blue Note Taipei 台北藍調", "city": "臺北市",
            "organizer": "Blue Note Taipei", "desc": norm(clean(json.loads(f'"{desc}"')))[:240], "genre": "爵士",
        })
    log(f"Blue Note: {len(out)} events")
    return out


# ---------------------------------------------------------------- main

SOURCES = [("OPENTIX", fetch_opentix), ("KKTIX", fetch_kktix), ("Blue Note Taipei", fetch_bluenote)]


def main():
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {"events": [], "sources": {}}
    events, status = [], {}
    for name, fn in SOURCES:
        try:
            got = fn()
            status[name] = {"ok": True, "count": len(got), "updated": iso(NOW)}
        except Exception as e:
            log(f"{name} FAILED: {e}")
            # 這次抓失敗就沿用上次的資料
            got = [x for x in old["events"] if x.get("source") == name]
            prev = old.get("sources", {}).get(name, {})
            status[name] = {"ok": False, "count": len(got), "updated": prev.get("updated"), "error": str(e)[:200]}
        events += got

    cutoff = NOW - dt.timedelta(hours=6)
    keep = []
    for ev in events:
        last = ev.get("end") or ev.get("start")
        if last and dt.datetime.fromisoformat(last) < cutoff:
            continue
        ev["niuer"] = niuer(ev.get("organizer", ""), ev.get("title", ""), ev.get("desc", ""))
        ev["city"] = city_of(ev.get("city", ""), ev.get("venue", ""))
        keep.append(ev)
    keep.sort(key=lambda x: x.get("start") or "9999")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated": iso(NOW), "sources": status, "events": keep},
                              ensure_ascii=False, indent=1), "utf-8")
    log(f"wrote {len(keep)} events -> {OUT}")


if __name__ == "__main__":
    main()
