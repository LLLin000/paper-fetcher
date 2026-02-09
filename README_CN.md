# Paper Fetcher - 学术文献下载工具

Forked from fermionoid/paper-fetcher，针对中国大学环境优化。

## 主要改进

### 1. 多源搜索支持
- **PubMed**: 医学/生命科学文献
- **Google Scholar**: 跨学科学术搜索
- **Semantic Scholar**: AI驱动的学术搜索

### 2. 多类型标识符支持
- DOI: `10.1038/s41586-024-12345-6`
- PMID: `37003657`
- PMCID: `PMC1234567`
- URL: 直接输入文章链接

### 3. 中国大学代理支持
- **WebVPN**: 山东大学、中科大等
- **EZproxy**: 香港大学等
- **自动检测**: 根据 URL 自动识别代理类型

## 安装

```bash
git clone https://github.com/LLLin000/paper-fetcher.git
cd paper-fetcher
pip install -e .
```

## 配置（山东大学示例）

```bash
# 1. 配置代理
paper-fetcher config-cmd --proxy https://webvpn.sdu.edu.cn/

# 2. 配置邮箱（Unpaywall 需要）
paper-fetcher config-cmd --email your-email@sdu.edu.cn

# 3. 登录（浏览器会打开，用统一身份认证登录）
paper-fetcher login
```

## 使用示例

### 搜索文献

```bash
# PubMed 搜索
paper-fetcher search "TREM2 Alzheimer" --source pubmed --limit 10

# Semantic Scholar 搜索
paper-fetcher search "machine learning" --limit 20

# 搜索并自动下载
paper-fetcher search "COVID-19 vaccine" --source pubmed --fetch
```

### 下载单篇文献

```bash
# 用 PMID 下载
paper-fetcher fetch 37003657

# 用 DOI 下载
paper-fetcher fetch "10.1016/j.cell.2023.03.004"

# 输出为 Markdown
paper-fetcher fetch 37003657 --format markdown --output ./papers
```

### 批量下载

创建文件 `identifiers.txt`：
```
# PubMed IDs
37003657
38123456

# DOIs
10.1038/s41586-024-12345-6
10.1016/j.cell.2023.03.004
```

执行批量下载：
```bash
paper-fetcher batch identifiers.txt --format markdown --output ./papers
```

## MCP 服务器使用

注册到 Claude Code：
```bash
claude mcp add paper-fetcher -- paper-fetcher-mcp
```

然后可以直接对话使用：
- "搜索 PubMed 关于 TREM2 和阿尔茨海默病的研究"
- "下载 PMID 37003657 的全文"
- "用 Google Scholar 搜索机器学习在药物发现中的应用"

## 支持的大学代理

| 大学 | 代理类型 | 配置示例 |
|------|----------|----------|
| 山东大学 | WebVPN | `https://webvpn.sdu.edu.cn/` |
| 中国科学技术大学 | WebVPN | `https://webvpn.ustc.edu.cn/` |
| 香港大学 | EZproxy | `http://eproxy.lib.hku.hk/login?url=` |

## 工作流程

```
1. 搜索文献（PubMed/Google Scholar/Semantic Scholar）
   ↓
2. 获取 DOI/PMID
   ↓
3. 检查 Open Access
   - 有 OA: 直接下载
   - 无 OA: 通过 WebVPN/EZproxy 下载
```

## 注意事项

1. **首次使用需要登录**: `paper-fetcher login` 会打开浏览器，需要手动完成统一身份认证
2. **Cookie 会保存**: 登录状态会保存，下次使用无需重新登录
3. **尊重版权**: 仅下载有权限访问的文献
4. **遵守 rate limit**: PubMed 限制 3 req/s（无 API key）或 10 req/s（有 API key）

## License

MIT License (same as original)
