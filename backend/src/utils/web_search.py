import asyncio
import json
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30.0  # seconds per engine
OVERALL_SEARCH_TIMEOUT = 30.0


WEB_SEARCH_DEFAULT_ENGINES = [
    "jina",
    "bing",
    "baidu",
    "duckduckgo",
    "csdn",
    "juejin",
    "brave",
    "zhihu",
    "weixin",
    "github",
    "arxiv",
    "semanticscholar",
    "dblp",
    "pubmed",
    "googlescholar",
]


WEB_SEARCH_STOP_WORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "and",
    "or",
    "but",
    "if",
    "because",
    "while",
    "although",
    "though",
    "的",
    "是",
    "在",
    "了",
    "和",
    "与",
    "或",
    "则",
    "而",
    "但",
    "可以",
    "如何",
    "什么",
    "怎么",
    "这",
    "那",
    "一个",
    "一些",
    "有",
    "要",
    "从",
    "用",
    "为",
    "以",
    "到",
    "就",
    "上",
    "下",
}


def _split_keywords(query: str) -> List[str]:
    import re

    words = re.split(r"[\s,.，。？！；：]+", (query or "").lower())
    return [w for w in words if len(w) > 1 and w not in WEB_SEARCH_STOP_WORDS]


def _filter_by_relevance(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    keywords = _split_keywords(query)
    if not keywords:
        return results

    filtered: List[Dict[str, Any]] = []
    for r in results:
        text = f"{r.get('title') or ''} {r.get('description') or ''}".lower()
        if any(kw in text for kw in keywords):
            filtered.append(r)
    return filtered


def _deduplicate_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        deduped.append(r)
    return deduped


async def _search_baidu(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://www.baidu.com/s",
            params={"wd": query, "pn": "0", "ie": "utf-8"},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        content_left = soup.select_one("#content_left")
        if not content_left:
            return results
        for child in content_left.find_all(recursive=False):
            if len(results) >= limit:
                break
            title_el = child.find("h3")
            link_el = child.find("a")
            snippet_el = child.select_one(".c-font-normal.c-color-text")
            if not title_el or not link_el:
                continue
            url = link_el.get("href") or ""
            if not url.startswith("http"):
                continue
            title = title_el.get_text(strip=True)
            desc = ""
            if snippet_el:
                desc = snippet_el.get("aria-label") or snippet_el.get_text(strip=True) or ""
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc,
                    "engine": "baidu",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Baidu search error: {e}")
        return []


async def _search_jina(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        # Jina 直接返回 markdown 文本
        resp = await client.get(
            f"https://s.jina.ai/{query}",
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/plain",
                "X-With-Generated-Alt": "true",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        text = resp.text
        import re

        parts = re.split(r"\n\[\d+\]\s+", text)[1:]
        results: List[Dict[str, Any]] = []
        for entry in parts:
            if len(results) >= limit:
                break
            lines = entry.splitlines()
            if not lines:
                continue
            title = lines[0].strip()
            url_line: Optional[str] = None
            for l in lines:
                if l.startswith("URL: "):
                    url_line = l
                    break
            url = url_line.replace("URL: ", "").strip() if url_line else ""
            if not url or not title:
                continue
            snippet = ""
            if url_line and url_line in lines:
                idx = lines.index(url_line)
                if idx + 1 < len(lines):
                    snippet = " ".join(lines[idx + 1 :]).strip()
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": snippet or "No description available",
                    "engine": "jina",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Jina search error: {e}")
        return []


async def _search_bing(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "count": limit, "first": 1},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select("#b_results > .b_algo"):
            if len(results) >= limit:
                break
            title_el = item.select_one("h2 a")
            if not title_el:
                continue
            url = title_el.get("href") or ""
            if not url.startswith("http"):
                continue
            snippet_el = item.select_one(".b_caption p, .b_snippet")
            desc = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                {
                    "title": title_el.get_text(strip=True),
                    "url": url,
                    "description": desc,
                    "engine": "bing",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Bing search error: {e}")
        return []


async def _search_duckduckgo(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            content=f"q={httpx.QueryParams({'q': query})['q']}&kl=wt-wt",
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://html.duckduckgo.com",
                "Referer": "https://html.duckduckgo.com/",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select(".result"):
            if len(results) >= limit:
                break
            link_el = item.select_one("a.result__a")
            if not link_el:
                continue
            url = link_el.get("href") or ""
            if not url.startswith("http"):
                continue
            snippet_el = item.select_one("a.result__snippet")
            desc = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                {
                    "title": link_el.get_text(strip=True),
                    "url": url,
                    "description": desc,
                    "engine": "duckduckgo",
                }
            )
        return results
    except Exception as e:
        print(f"❌ DuckDuckGo search error: {e}")
        return []


async def _search_csdn(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://so.csdn.net/api/v3/search",
            params={
                "q": query,
                "t": "blog",
                "p": 1,
                "s": 0,
                "tm": 0,
                "lv": -1,
                "ft": 0,
                "l": "",
                "u": "",
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://so.csdn.net/",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        data = resp.json().get("result_vos") or []
        results: List[Dict[str, Any]] = []
        for item in data:
            if len(results) >= limit:
                break
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            desc = item.get("description") or item.get("summary") or ""
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc,
                    "engine": "csdn",
                }
            )
        return results
    except Exception as e:
        print(f"❌ CSDN search error: {e}")
        return []


async def _search_juejin(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.post(
            "https://api.juejin.cn/search_api/v1/search",
            json={
                "key_word": query,
                "page_no": 0,
                "page_size": limit,
                "search_type": 0,
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        data = resp.json().get("data") or []
        results: List[Dict[str, Any]] = []
        for item in data:
            if len(results) >= limit:
                break
            article = (item.get("result_model") or {}).get("article_info") or {}
            article_id = article.get("article_id")
            if not article_id:
                continue
            title = article.get("title") or ""
            if not title:
                continue
            url = f"https://juejin.cn/post/{article_id}"
            desc = article.get("brief_content") or ""
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc,
                    "engine": "juejin",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Juejin search error: {e}")
        return []


async def _search_brave(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select(".snippet"):
            if len(results) >= limit:
                break
            title_el = item.select_one(".title")
            link_el = item.select_one("a.heading-serpresult")
            if not link_el:
                continue
            url = link_el.get("href") or ""
            if not url.startswith("http"):
                continue
            snippet_el = item.select_one(".snippet-description")
            desc = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(
                {
                    "title": (title_el.get_text(strip=True) if title_el else "No title"),
                    "url": url,
                    "description": desc,
                    "engine": "brave",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Brave search error: {e}")
        return []


async def _search_zhihu(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://www.zhihu.com/search",
            params={"type": "content", "q": query},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select(".List-item"):
            if len(results) >= limit:
                break
            title_el = item.select_one(".ContentItem-title a")
            if not title_el:
                continue
            url = title_el.get("href") or ""
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://www.zhihu.com" + url
            snippet_el = item.select_one(".RichContent-inner")
            desc = snippet_el.get_text(strip=True)[:200] if snippet_el else ""
            results.append(
                {
                    "title": title_el.get_text(strip=True),
                    "url": url,
                    "description": desc,
                    "engine": "zhihu",
                }
            )
        return results
    except Exception as e:
        # 403 比较常见，静默处理
        msg = str(e)
        if "403" in msg:
            return []
        print(f"❌ Zhihu search error: {e}")
        return []


async def _search_weixin(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://weixin.sogou.com/weixin",
            params={
                "type": "2",
                "page": "1",
                "ie": "utf8",
                "query": query,
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://weixin.sogou.com/",
                "Cookie": "ABTEST=0|1700000000|v1",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select("ul.news-list > li"):
            if len(results) >= limit:
                break
            try:
                link_el = (
                    item.select_one("div.txt-box h3 a")
                    or item.select_one("h3 a")
                    or item.find("a")
                )
                title_el = (
                    item.select_one("div.txt-box h3 a")
                    or item.select_one("h3 a")
                    or item.select_one("h3")
                )
                abstract_el = (
                    item.select_one("p.txt-info")
                    or item.select_one(".txt-box p")
                    or item.find("p")
                )
                if not link_el or not title_el:
                    continue
                url = link_el.get("href") or ""
                if not url:
                    continue
                if not url.startswith("http"):
                    url = "https://weixin.sogou.com" + url
                title = title_el.get_text(strip=True)
                abstract = abstract_el.get_text(strip=True) if abstract_el else ""
                title = title.replace("red_beg", "").replace("red_end", "").strip()
                abstract = abstract.replace("red_beg", "").replace("red_end", "").strip()
                if not title:
                    continue
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "description": abstract,
                        "engine": "weixin",
                    }
                )
            except Exception:
                continue
        return results
    except Exception as e:
        # 反爬/403 较多，静默处理
        msg = str(e)
        if "403" in msg or "antispider" in msg:
            return []
        print(f"❌ Weixin search error: {e}")
        return []


async def _search_github(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://github.com/search",
            params={"q": query, "type": "repositories"},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        selectors = '[data-testid="results-list"] > div, .repo-list-item, .Box-row'
        for item in soup.select(selectors):
            if len(results) >= limit:
                break
            try:
                link_el = (
                    item.select_one("a.v-align-middle, a.Link--primary, .text-bold a")
                    or item.select_one("h3 a, .f4 a")
                )
                if not link_el:
                    continue
                url = link_el.get("href") or ""
                title = link_el.get_text(strip=True)
                if not url or not title:
                    continue
                if not url.startswith("http"):
                    url = "https://github.com" + url
                desc_el = item.select_one(
                    "p.mb-1, p.pinned-item-desc, .text-gray, p.color-fg-muted"
                )
                desc = desc_el.get_text(strip=True) if desc_el else ""
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "description": desc or "GitHub repository",
                        "engine": "github",
                    }
                )
            except Exception:
                continue
        return results
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate limit" in msg:
            return []
        print(f"❌ GitHub search error: {e}")
        return []


async def _search_arxiv(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/atom+xml",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "xml")
        results: List[Dict[str, Any]] = []
        for entry in soup.find_all("entry"):
            if len(results) >= limit:
                break
            title = entry.findtext("title", "").strip()
            summary = entry.findtext("summary", "").strip()
            published = entry.findtext("published", "").strip()
            url = ""
            for link in entry.find_all("link"):
                href = link.get("href")
                typ = link.get("type")
                if typ == "text/html" and href:
                    url = href
                    break
                if not url and href and "arxiv.org/abs" in href:
                    url = href
            if not url or not title:
                continue
            authors = [a.get_text(strip=True) for a in entry.find_all("author")]
            author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
            cats = [c.get("term") for c in entry.find_all("category") if c.get("term")]
            cat_str = ", ".join(cats[:3])
            pub_date = published.split("T")[0] if published else ""
            desc = ""
            if author_str:
                desc += f"[{author_str}] "
            if pub_date:
                desc += f"({pub_date}) "
            if cat_str:
                desc += f"[{cat_str}] "
            if summary:
                summary_clean = " ".join(summary.split())
                desc += summary_clean[:200] + ("..." if len(summary_clean) > 200 else "")
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc,
                    "engine": "arxiv",
                }
            )
        return results
    except Exception as e:
        print(f"❌ arXiv search error: {e}")
        return []


async def _search_semanticscholar(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "title,url,abstract,authors,year,citationCount,openAccessPdf",
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        papers = resp.json().get("data") or []
        results: List[Dict[str, Any]] = []
        for p in papers:
            if len(results) >= limit:
                break
            title = p.get("title") or ""
            if not title:
                continue
            url = p.get("url") or (p.get("openAccessPdf") or {}).get("url") or ""
            if not url:
                continue
            abstract = p.get("abstract") or ""
            authors = p.get("authors") or []
            author_str = ", ".join(a.get("name") for a in authors[:3]) + (
                " et al." if len(authors) > 3 else ""
            )
            year = f"({p.get('year')})" if p.get("year") else ""
            citations = (
                f"[{p.get('citationCount')} citations]" if p.get("citationCount") else ""
            )
            desc = ""
            if author_str:
                desc += f"[{author_str}] "
            if year:
                desc += f"{year} "
            if citations:
                desc += f"{citations} "
            if abstract:
                abstract_clean = " ".join(abstract.split())
                desc += abstract_clean[:200] + ("..." if len(abstract_clean) > 200 else "")
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc or "No abstract available",
                    "engine": "semanticscholar",
                }
            )
        return results
    except Exception as e:
        print(f"❌ Semantic Scholar search error: {e}")
        return []


async def _search_pubmed(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        # Step1: esearch
        s_resp = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": limit,
                "retmode": "json",
                "sort": "relevance",
            },
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        pmids = (s_resp.json().get("esearchresult") or {}).get("idlist") or []
        if not pmids:
            return []
        # Step2: esummary
        summary_resp = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        summary = summary_resp.json().get("result") or {}
        results: List[Dict[str, Any]] = []
        for pmid in pmids:
            if len(results) >= limit:
                break
            article = summary.get(pmid) or {}
            title = article.get("title") or ""
            if not title:
                continue
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            authors = article.get("authors") or []
            author_str = ", ".join(a.get("name") for a in authors[:3]) + (
                " et al." if len(authors) > 3 else ""
            )
            pub_date = article.get("pubdate") or ""
            source = article.get("source") or ""
            volume = article.get("volume") or ""
            issue = article.get("issue") or ""
            desc = ""
            if author_str:
                desc += f"[{author_str}] "
            if pub_date:
                desc += f"({pub_date}) "
            if source:
                desc += f"[{source}"
                if volume:
                    desc += f" {volume}"
                if issue:
                    desc += f"({issue})"
                desc += "] "
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc or "Biomedical Publication",
                    "engine": "pubmed",
                }
            )
        return results
    except Exception as e:
        print(f"❌ PubMed search error: {e}")
        return []


async def _search_dblp(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://dblp.org/search/publ/api",
            params={"q": query, "format": "json", "h": limit, "c": 0},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        hits = ((resp.json().get("result") or {}).get("hits") or {}).get("hit") or []
        results: List[Dict[str, Any]] = []
        for hit in hits:
            if len(results) >= limit:
                break
            info = hit.get("info") or {}
            title = info.get("title") or ""
            url = info.get("url") or info.get("ee") or ""
            if not title or not url:
                continue
            authors_field = (info.get("authors") or {}).get("author")
            author_str = ""
            if authors_field:
                if isinstance(authors_field, list):
                    authors = authors_field
                else:
                    authors = [authors_field]
                names = [a.get("text") if isinstance(a, dict) else str(a) for a in authors]
                author_str = ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")
            year = f"({info.get('year')})" if info.get("year") else ""
            venue = info.get("venue") or ""
            typ = info.get("type") or ""
            desc = ""
            if author_str:
                desc += f"[{author_str}] "
            if year:
                desc += f"{year} "
            if venue:
                desc += f"[{venue}] "
            if typ:
                desc += f"({typ})"
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc or "Computer Science Publication",
                    "engine": "dblp",
                }
            )
        return results
    except Exception as e:
        print(f"❌ DBLP search error: {e}")
        return []


async def _search_googlescholar(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            "https://scholar.google.com/scholar",
            params={"q": query, "hl": "en", "num": min(limit, 20)},
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Dict[str, Any]] = []
        for item in soup.select(".gs_r.gs_or.gs_scl, .gs_ri"):
            if len(results) >= limit:
                break
            title_el = item.select_one(".gs_rt a") or item.select_one(".gs_rt")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            title = title.replace("[PDF]", "").replace("[HTML]", "").replace("[BOOK]", "").strip()
            url = title_el.get("href") or ""
            author_info_el = item.select_one(".gs_a")
            snippet_el = item.select_one(".gs_rs")
            author_info = author_info_el.get_text(strip=True) if author_info_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            cited_by = ""
            for link in item.select(".gs_fl a"):
                txt = link.get_text()
                if "Cited by" in txt:
                    cited_by = txt
                    break
            if not url:
                url = f"https://scholar.google.com/scholar?q={httpx.QueryParams({'q': title})['q']}"
            desc = ""
            if author_info:
                desc += f"[{author_info}] "
            if cited_by:
                desc += f"({cited_by}) "
            if snippet:
                snippet_clean = " ".join(snippet.split())
                desc += snippet_clean[:200] + ("..." if len(snippet_clean) > 200 else "")
            results.append(
                {
                    "title": title,
                    "url": url,
                    "description": desc or "Academic Publication",
                    "engine": "googlescholar",
                }
            )
        return results
    except Exception as e:
        msg = str(e)
        if "429" in msg or "captcha" in msg or "blocked" in msg:
            return []
        print(f"❌ Google Scholar search error: {e}")
        return []


async def perform_web_search(query: str, engines: Optional[List[str]] = None, limit: int = 16) -> List[Dict[str, Any]]:
    """
    对外导出：多引擎搜索，返回统一结构的结果列表：
    {title, url, description, engine}
    """
    if not query:
        return []

    engines = engines or WEB_SEARCH_DEFAULT_ENGINES
    # 去重并保持顺序，且只保留支持的引擎
    normalized = []
    seen = set()
    for e in engines:
        name = (e or "").lower()
        if name in seen:
            continue
        if name in WEB_SEARCH_DEFAULT_ENGINES:
            normalized.append(name)
            seen.add(name)
    if not normalized:
        normalized = WEB_SEARCH_DEFAULT_ENGINES.copy()

    # 计算每个引擎的结果上限
    per_engine_limit = max(2, int(limit / max(len(normalized), 1)) + 1)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = []
        for engine in normalized:
            if engine == "baidu":
                tasks.append(_search_baidu(client, query, per_engine_limit))
            elif engine == "bing":
                tasks.append(_search_bing(client, query, per_engine_limit))
            elif engine in ("duckduckgo", "ddg"):
                tasks.append(_search_duckduckgo(client, query, per_engine_limit))
            elif engine == "csdn":
                tasks.append(_search_csdn(client, query, per_engine_limit))
            elif engine == "juejin":
                tasks.append(_search_juejin(client, query, per_engine_limit))
            elif engine == "brave":
                tasks.append(_search_brave(client, query, per_engine_limit))
            elif engine == "zhihu":
                tasks.append(_search_zhihu(client, query, per_engine_limit))
            elif engine in ("weixin", "wechat"):
                tasks.append(_search_weixin(client, query, per_engine_limit))
            elif engine in ("github", "gh"):
                tasks.append(_search_github(client, query, per_engine_limit))
            elif engine == "arxiv":
                tasks.append(_search_arxiv(client, query, per_engine_limit))
            elif engine in ("semanticscholar", "s2"):
                tasks.append(_search_semanticscholar(client, query, per_engine_limit))
            elif engine == "dblp":
                tasks.append(_search_dblp(client, query, per_engine_limit))
            elif engine == "pubmed":
                tasks.append(_search_pubmed(client, query, per_engine_limit))
            elif engine in ("googlescholar", "scholar", "gscholar"):
                tasks.append(_search_googlescholar(client, query, per_engine_limit))
            elif engine == "jina":
                tasks.append(_search_jina(client, query, per_engine_limit))

        if not tasks:
            return []

        try:
            done, _ = await asyncio.wait(
                [asyncio.create_task(t) for t in tasks],
                timeout=OVERALL_SEARCH_TIMEOUT,
            )
        except Exception:
            done = set()

        all_results: List[Dict[str, Any]] = []
        for task in done:
            if task.cancelled():
                continue
            try:
                res = task.result()
            except Exception:
                res = []
            if isinstance(res, list):
                all_results.extend(res)

    # 轮询合并（简单实现：已经是直接 extend，前面并行顺序不可控，但问题不大）
    all_results = _deduplicate_results(all_results)
    all_results = _filter_by_relevance(all_results, query)
    return all_results[:limit]

