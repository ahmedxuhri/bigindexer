# PR Architecture Risk Bot

The Big Indexer GitHub Action scans the repository, builds `bgi-graph.json` and `fuse-graph.json`, then posts a pull request comment with:

1. blast radius from `impact_neighbors`
2. coupling risk from `high_coupling_seams`
3. cluster ownership from `cluster_of_file`
4. optional implementation hints from `twin_context`

## Inputs

- `github-token`: token for comment upserts
- `scan-path`: repository path to scan
- `language`: scan mode, usually `auto`
- `graph-path`: output path for `bgi-graph.json`
- `fuse-graph-path`: output path for `fuse-graph.json`
- `index-db-path`: optional query index for stronger symbol lookup
- `changed-files`: optional explicit file list
- `task-prompt`: optional prompt for twin context enrichment
- `post-comment`: set to `false` to skip PR comment posting

## Required permissions

```yaml
permissions:
  contents: read
  pull-requests: write
```

## Example

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: ahmedxuhri/bigindexer@v0.1.3
    with:
      github-token: ${{ secrets.GITHUB_TOKEN }}
      task-prompt: "Review this change for architectural risk."
```

## Notes

- The action expects a PR event so it can diff base/head and upsert a single comment.
- If `changed-files` is provided, the action uses that list instead of git diff.
- The report is still written to the step summary even when comment posting is disabled.
