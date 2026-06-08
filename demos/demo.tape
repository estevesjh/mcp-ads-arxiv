# mcp-ads-arxiv demo
# Records a Claude Code session showing the token-saving spine.
# Run: vhs demos/demo.tape

Output demos/demo.gif
Set FontSize 14
Set Width 1280
Set Height 800
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set Padding 20

# Hidden setup: clean cwd, avoid nested-Claude detection
Hide
Type "unset CLAUDECODE && cd /tmp && rm -rf ms-demo && mkdir ms-demo && cd ms-demo"
Enter
Sleep 0.4s
Ctrl+L
Show

Type "claude"
Enter
Sleep 3s
Ctrl+L
Sleep 1s

# Flow A: human-friendly search (flexible_paper_search, natural notation)
Type "Search for DES DESI cosmological results 2025 2026."
Enter
Sleep 40s

# Flow B: one-call acquire + summarize (smart_fetch_paper_content)
Type "Fetch the full Dark Energy Survey multiprobe dark energy paper and show its sections."
Enter
Sleep 50s

# Flow C: pull w0/wa constraints only (read_topic)
Type "Read the Results and show only the w0 and wa best-fit values with uncertainties for each dataset combination."
Enter
Sleep 45s

# Flow D: save to project folder + usage report (same session, no restart)
Type "Save that paper into /tmp/ms-demo so I can open the PDF, then show my usage_stats."
Enter
Sleep 55s
Sleep 3s
