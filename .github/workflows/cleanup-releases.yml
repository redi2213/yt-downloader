name: Cleanup old releases

on:
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Delete video releases older than 5 days
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          repo="${{ github.repository }}"
          cutoff=$(date -d '5 days ago' +%s)
          
          gh release list --repo "$repo" --limit 200 --json tagName,createdAt \
            --jq '.[] | [.tagName, .createdAt] | @tsv' | while IFS=$'\t' read -r tag created; do
            if [[ "$tag" != run-* ]]; then
              echo "Skipping non-video release: $tag"
              continue
            fi
            created_ts=$(date -d "$created" +%s)
            if [ "$created_ts" -lt "$cutoff" ]; then
              echo "Deleting $tag (created $created)"
              gh release delete "$tag" --repo "$repo" --yes --cleanup-tag || true
            else
              echo "Keeping $tag (created $created)"
            fi
          done
