# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public GitHub issue.** Instead, email `johnny.udi@gmail.com` with:

- Description of the vulnerability
- Steps to reproduce (if applicable)
- Affected versions
- Potential impact

Please allow up to 7 days for an initial response. We will work with you to understand the issue and develop a fix.

## Security Considerations

This tool handles sensitive credentials:

- **ADS API tokens** — passed via environment variables (`ADS_API_TOKEN`)
- **Local paper library** — stored unencrypted on disk by default

### Best Practices

1. **API tokens**: Never commit `.env` files or tokens to git. Use environment variables or a secrets manager.
2. **Library location**: Set `LIT_CACHE_DIR` to a location with appropriate file permissions if papers contain sensitive data.
3. **arXiv/ADS access**: This tool only reads public metadata and source files from NASA ADS and arXiv. No data is modified or uploaded.

## Dependencies

This project depends on:
- `fastmcp` — Model Context Protocol server framework
- `arxiv-to-prompt` — arXiv LaTeX source parsing
- `mcp-server-ads` — NASA ADS HTTP client
- `docling` (optional) — PDF to markdown conversion

Security updates to dependencies are tracked and merged when available. If you discover a vulnerability in a dependency, please report it to the upstream project first.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## License

This project is MIT-licensed. See [LICENSE](LICENSE) for details.
