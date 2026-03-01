"""
Arxiv Search Tool - 论文搜索工具

Layer: L6 (sage-studio)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import aiohttp
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from sage.studio.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ArxivSearchInput(BaseModel):
    """Arxiv 搜索参数"""

    query: str = Field(..., description="论文搜索关键词，如 'transformer attention mechanism'")
    max_results: int = Field(5, description="最大返回论文数量", ge=1, le=20)
    with_abstract: bool = Field(True, description="是否包含摘要")


class ArxivSearchTool(BaseTool):
    """Arxiv 论文搜索工具

    搜索 ArXiv 学术论文库，获取相关论文的标题、作者、摘要和链接。
    适用于学术研究、文献调研、技术学习、论文辅导等场景。
    支持关键词搜索，如 'machine learning', 'transformer attention' 等。
    """

    name: ClassVar[str] = "arxiv_search"
    description: ClassVar[str] = (
        "搜索 ArXiv 学术论文库，获取相关论文的标题、作者、摘要和链接。"
        "适用于学术研究、文献调研、技术学习、论文辅导等场景。"
    )
    args_schema: ClassVar[type[BaseModel] | None] = ArxivSearchInput

    async def _run(
        self,
        query: str,
        max_results: int = 5,
        with_abstract: bool = True,
    ) -> list[dict[str, Any]]:
        """执行 Arxiv 搜索"""
        return await self._search_arxiv_directly(query, max_results, with_abstract)

    async def _search_arxiv_directly(
        self,
        query: str,
        max_results: int,
        with_abstract: bool,
    ) -> list[dict[str, Any]]:
        """直接实现 Arxiv 搜索"""
        base_url = "https://arxiv.org/search/"
        params = {
            "query": query,
            "searchtype": "all",
            "abstracts": "show" if with_abstract else "hide",
            "size": str(min(max_results * 2, 50)),  # 多取一些以防过滤
            "start": "0",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, timeout=30) as resp:
                    if resp.status != 200:
                        raise Exception(f"Arxiv returned status {resp.status}")
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            results = []

            # Arxiv 结果列表通常是 li.arxiv-result
            items = soup.select("li.arxiv-result")

            for item in items:
                if len(results) >= max_results:
                    break

                title_elem = item.select_one("p.title")
                authors_elem = item.select_one("p.authors")
                abstract_elem = item.select_one("span.abstract-full")
                link_elem = item.select_one("p.list-title a")

                # 处理作者列表
                authors: list[str] = []
                if authors_elem:
                    authors = [a.get_text(strip=True) for a in authors_elem.select("a")]

                # 处理摘要
                abstract = ""
                if abstract_elem and with_abstract:
                    abstract = abstract_elem.get_text(strip=True)
                    # 移除可能的 "Less" 按钮文本
                    if abstract.endswith("Less"):
                        abstract = abstract[:-4].strip()
                    # 移除可能的 "△" 符号
                    abstract = abstract.replace("△", "").strip()

                results.append(
                    {
                        "title": title_elem.get_text(strip=True) if title_elem else "",
                        "authors": authors,
                        "abstract": abstract,
                        "link": link_elem["href"] if link_elem else "",
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Arxiv search failed: {e}")
            raise
