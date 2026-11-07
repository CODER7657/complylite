# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
No release has been tagged yet.

## [Unreleased]

### Added
- ML surveillance: simulator, SQL features, model comparison and a checked
  case-note agent (#2).
- Evaluation of the case-note agent on false alerts, `--false-alerts N` (#5).
- Measured result of the case-note agent on 20 alerts (#4).
- Standard repository files: security policy, changelog, `.editorconfig`,
  Dependabot and CodeQL configuration.

### Fixed
- The agent now retries without tools when the model invents a tool name (#3).
