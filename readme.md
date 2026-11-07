Initial Commit:

## Using this repo with Obsidian

1. Install [Obsidian](https://obsidian.md).
2. Clone the repo: `git clone https://github.com/jaiom-rola-sp/zero-day.git ~/Development/zero-day`
3. In Obsidian, open **Manage vaults → Open folder as vault** and select the `zero-day` folder.
4. Pull the latest changes before you start: `git pull`.

Obsidian's settings live in `.obsidian/`, which is git-ignored, so each person keeps their own layout and plugins.

If you use `[[wikilinks]]`, they won't render on GitHub. Prefer standard `[text](path.md)` links, or turn off **Settings → Files and links → Use [[Wikilinks]]**.

## Project docs

- [PRD](docs/prd.md): the Replic8 product plan.
- [Requirements](docs/requirements.md): what we're building and its status.
- [Changelog](docs/changelog.md): what changed and why.
