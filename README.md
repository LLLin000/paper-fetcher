# paper-fetcher

An MCP server and CLI tool for fetching academic paper full texts. Designed to work as a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) MCP tool, enabling AI-assisted literature review and research workflows.

## How It Works

paper-fetcher uses a three-layer strategy to maximize access to full-text papers:

```
Layer 1: Open Access (Unpaywall + arXiv)     ← free, no login required
Layer 2: Institutional proxy (EZproxy)        ← requires university login
Layer 3: Metadata only (Semantic Scholar)     ← always available
```

For each paper request, it tries Open Access sources first. If the paper is paywalled, it falls back to your institution's EZproxy. Metadata and search are always available via Semantic Scholar.

## Features

- **MCP Server** - Integrate directly with Claude Code for AI-powered research
- **Three access layers** - Open Access, institutional EZproxy, and metadata fallback
- **Multi-source search** - Search papers via Semantic Scholar API
- **Full-text extraction** - Extract text from HTML and PDF sources
- **Publisher adapters** - Optimized extraction for Nature, ACS, Elsevier, Wiley, and more
- **Smart caching** - Cache fetched papers locally to avoid redundant requests
- **Rate limiting** - Built-in polite request delays
- **CLI interface** - Standalone command-line tool for batch operations

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/paper-fetcher.git
cd paper-fetcher

# Install in development mode
pip install -e .
```

## Setup with Claude Code

Register paper-fetcher as an MCP server in Claude Code:

```bash
claude mcp add paper-fetcher -- paper-fetcher-mcp
```

After restarting Claude Code, you can ask Claude to search and fetch papers directly:

> "Search for recent papers on perovskite solar cells"
> "Fetch the full text of DOI 10.1038/s41566-024-01234-5"

## CLI Usage

### Login to EZproxy (institutional access)

```bash
# Opens a browser for manual login. Cookies are saved for future use.
paper-fetcher login

# Force re-login even if session appears valid
paper-fetcher login --force
```

### Search for papers

```bash
# Basic search
paper-fetcher search "organic photovoltaics stability"

# Limit results and filter by year
paper-fetcher search "perovskite solar cells" --limit 20 --year 2022-2025

# Search and fetch full texts
paper-fetcher search "silver nanowire transparent electrode" --fetch
```

### Fetch a single paper

```bash
# By DOI
paper-fetcher fetch "10.1038/s41566-024-01234-5"

# By URL
paper-fetcher fetch "https://www.nature.com/articles/s41566-024-01234-5"

# Output as markdown
paper-fetcher fetch "10.1038/s41566-024-01234-5" --format markdown
```

### Batch fetch

```bash
# Create a file with one DOI per line
paper-fetcher batch dois.txt --format markdown --output ./papers
```

### Configuration

```bash
# View current config
paper-fetcher config-cmd

# Set email (required for Unpaywall OA detection)
paper-fetcher config-cmd --email your@email.com

# Set output directory
paper-fetcher config-cmd --output-dir ./my-papers
```

## Configuration

Configuration is stored at `~/.paper-fetcher/config.json` and includes:

| Field | Description | Default |
|-------|-------------|---------|
| `proxy_base` | Your institution's EZproxy login URL | `http://eproxy.lib.hku.hk/login?url=` |
| `email` | Email for Unpaywall API (OA detection) | `""` (set via CLI) |
| `output_dir` | Directory for downloaded PDFs | `~/.paper-fetcher/papers` |
| `cache_dir` | Directory for cached results | `~/.paper-fetcher/cache` |
| `request_delay_min` | Minimum delay between requests (seconds) | `2.0` |
| `request_delay_max` | Maximum delay between requests (seconds) | `5.0` |

To use with a different institution's EZproxy, edit `~/.paper-fetcher/config.json`:

```json
{
  "proxy_base": "http://your-institution-proxy.edu/login?url=",
  "email": "your@email.com"
}
```

## MCP Tools

When used as an MCP server, paper-fetcher exposes three tools:

| Tool | Description |
|------|-------------|
| `search_papers` | Search for papers via Semantic Scholar (query, limit, year_range) |
| `fetch_paper` | Fetch full text by DOI or URL (identifier, format) |
| `get_paper_metadata` | Get paper metadata by DOI without downloading full text |

## Project Structure

```
paper-fetcher/
├── paper_fetcher/
│   ├── mcp_server.py          # MCP server (3 tools)
│   ├── cli.py                 # CLI interface (Typer)
│   ├── fetcher.py             # Core fetching logic
│   ├── auth.py                # EZproxy authentication (Selenium)
│   ├── config.py              # Configuration management
│   ├── models.py              # Paper data model
│   ├── sources/
│   │   ├── semantic_scholar.py
│   │   ├── unpaywall.py
│   │   └── arxiv.py
│   └── extractors/
│       ├── html_extractor.py
│       ├── pdf_extractor.py
│       └── publisher_adapters/
│           ├── nature.py
│           ├── acs.py
│           ├── elsevier.py
│           ├── wiley.py
│           └── generic.py
├── tests/
├── pyproject.toml
├── LICENSE
└── README.md
```

## Requirements

- Python >= 3.10
- Chrome browser (for EZproxy authentication)

## License

[MIT](LICENSE)

---

## 中文简介

**paper-fetcher** 是一个学术论文全文获取工具，可作为 Claude Code 的 MCP Server 使用，让 AI 直接帮你搜索和获取论文全文。

### 核心特性

- **三层获取策略**: Open Access (免费) → 机构代理 EZproxy (需登录) → 元数据兜底
- **MCP Server**: 注册到 Claude Code 后，直接用自然语言让 AI 搜论文、拉全文
- **多出版商适配**: 针对 Nature、ACS、Elsevier、Wiley 等做了专门的内容提取优化
- **本地缓存**: 已获取的论文自动缓存，避免重复请求
- **命令行工具**: 支持单篇获取、批量获取、搜索等操作

### 快速开始

```bash
# 安装
pip install -e .

# 注册到 Claude Code
claude mcp add paper-fetcher -- paper-fetcher-mcp

# 设置邮箱 (Unpaywall OA 检测需要)
paper-fetcher config-cmd --email your@email.com

# 登录机构代理 (可选，用于获取付费论文)
paper-fetcher login
```

注册后重启 Claude Code，即可直接对话使用：

> "帮我搜几篇关于钙钛矿太阳能电池的最新论文"
> "把这篇 DOI 10.1038/xxx 的全文拉下来"

### 配置其他机构的 EZproxy

默认配置的是 HKU EZproxy。如需使用其他机构，编辑 `~/.paper-fetcher/config.json`：

```json
{
  "proxy_base": "http://your-proxy.university.edu/login?url="
}
```
