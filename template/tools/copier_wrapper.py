"""
Wrapper for copier CLI that supports GitHub path references for data
files.

This script extends the copier CLI to support fetching data files from
GitHub using the gh:owner/repo@ref/filepath shorthand format. It
transparently downloads the file and passes the local path to copier.
Supports all copier commands: copy, update, and recopy.

Two independent version references:
1. --vcs-ref: Controls which VERSION of the TEMPLATE to use (standard
    copier flag)
2. @ref: Controls which VERSION of the DATA FILE to fetch (custom gh:
    syntax)

Usage Examples:

    # COPY: Create new project from template + data file
    python copier_wrapper.py copy gh:easyscience/template-lib . \\
        --gh-data gh:easyscience/peasy/project.yaml

    # UPDATE: Update existing project (stable template + stable data)
    python copier_wrapper.py update \\
        --answers-file .copier-answers.shared.yml \\
        --gh-data gh:easyscience/peasy/project.yaml

    # UPDATE: Development mode (master branch for both)
    python copier_wrapper.py update \\
        --vcs-ref master \\
        --answers-file .copier-answers.shared.yml \\
        --gh-data gh:easyscience/peasy@master/project.yaml

    # UPDATE: Stable template + development data file
    python copier_wrapper.py update \\
        --answers-file .copier-answers.shared.yml \\
        --gh-data gh:easyscience/peasy@master/project.yaml

    # RECOPY: Reapply template with specific versions
    python copier_wrapper.py recopy \\
        --vcs-ref v1.2.0 \\
        --answers-file .copier-answers.shared.yml \\
        --gh-data gh:easyscience/peasy@v2.0.0/project.yaml

    # Any command with local data file (no GitHub fetching)
    python copier_wrapper.py update \\
        --answers-file .copier-answers.shared.yml \\
        --gh-data ../peasy/project.yaml

Common Patterns:
- Production: (no --vcs-ref) + gh:owner/repo/file (both use latest
    releases)
- Development: --vcs-ref master + gh:owner/repo@master/file (both use
    master)
- Mixed: (no --vcs-ref) + gh:owner/repo@master/file (stable template,
    dev data)
"""

import re
from pathlib import Path
import subprocess
import sys
import pooch
import requests


def get_stable_ref(owner: str, repo: str) -> str:
    """
    Get the latest release tag from GitHub repository.

    Falls back to 'master' branch if no releases are found.

    Args:
        owner: Repository owner
        repo: Repository name

    Returns:
        Latest release tag name, or 'master' if no releases found
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/releases/latest'
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()['tag_name']
    except Exception:
        pass

    # Fallback to master branch if no releases
    return 'master'


def parse_github_path(path: str) -> tuple[str, str, str, str]:
    """
    Parse GitHub path reference in format gh:owner/repo@ref/filepath.

    Args:
        path: GitHub path string (e.g.,
            "gh:easyscience/peasy@master/project.yaml" or
            "gh:easyscience/peasy/project.yaml" for latest release)

    Returns:
        Tuple of (owner, repo, ref, filepath)
    """
    if not path.startswith('gh:'):
        raise ValueError(
            f'Invalid GitHub path format: {path}. Expected: '
            f'gh:owner/repo@ref/filepath'
        )

    # Remove "gh:" prefix
    path_without_prefix = path[3:]

    # Check if ref is specified with @
    if '@' in path_without_prefix:
        repo_part, rest = path_without_prefix.split('@', 1)
        parts = repo_part.split('/')
        if len(parts) != 2:
            raise ValueError(
                f'Invalid GitHub path format: {path}. Expected: '
                f'gh:owner/repo@ref/filepath'
            )
        owner, repo = parts

        # Split ref and filepath
        ref_filepath_parts = rest.split('/', 1)
        if len(ref_filepath_parts) != 2:
            raise ValueError(
                f'Invalid GitHub path format: {path}. Expected: '
                f'gh:owner/repo@ref/filepath'
            )
        ref, filepath = ref_filepath_parts
    else:
        # No ref specified, use latest release
        parts = path_without_prefix.split('/', 2)
        if len(parts) < 3:
            raise ValueError(
                f'Invalid GitHub path format: {path}. Expected: '
                f'gh:owner/repo/filepath'
            )
        owner, repo, filepath = parts
        ref = get_stable_ref(owner, repo)

    return owner, repo, ref, filepath


def fetch_github_file(path: str, cache_dir: Path) -> Path:
    """
    Fetch file from GitHub using gh:owner/repo@ref/filepath shorthand
    format.

    Always re-downloads for branches to ensure latest version.
    Uses cached version for release tags (immutable).

    Args:
        path: GitHub path reference (e.g.,
            "gh:easyscience/peasy@master/project.yaml")
        cache_dir: Directory to cache downloaded files

    Returns:
        Path to the downloaded file
    """
    # Parse GitHub path reference
    owner, repo, ref, filepath = parse_github_path(path)

    # Construct raw GitHub URL
    url = f'https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{ref}/{filepath}'

    # Create a unique cache filename including ref
    cache_filename = f'{ref}_{filepath.replace("/", "_")}'
    cache_file_path = cache_dir / cache_filename

    # Check if ref is a release tag (semantic version pattern like
    # v1.0.0 or 1.0.0)
    is_release_tag = bool(re.match(r'^v?\d+\.\d+', ref))

    # Always re-download for branches, use cache for release tags
    if not is_release_tag and cache_file_path.exists():
        print(f'Refreshing {filepath} from {owner}/{repo} (branch: {ref})')
        cache_file_path.unlink()
    elif is_release_tag and cache_file_path.exists():
        print(f'Using cached {filepath} from {owner}/{repo} (release tag: {ref})')

    # Download file using pooch
    file_path = pooch.retrieve(
        url=url,
        known_hash=None,  # Skip hash verification
        path=cache_dir,
        fname=cache_filename,
    )

    return Path(file_path)


def main():
    """Main function to wrap copier CLI with GitHub path reference
    support."""
    # Separate custom args from copier args
    copier_args = []
    github_data = None

    i = 0
    while i < len(sys.argv) - 1:
        i += 1
        arg = sys.argv[i]

        if arg == '--gh-data':
            # Custom flag: get next argument as GitHub path
            if i + 1 < len(sys.argv):
                i += 1
                github_data = sys.argv[i]
            else:
                print('❌ Error: --gh-data requires a value')
                return 1
        else:
            # Pass through to copier
            copier_args.append(arg)

    # Process GitHub data if provided
    if github_data:
        if github_data.startswith('gh:'):
            try:
                # Parse to get owner/repo for cache directory
                owner, repo, ref, _ = parse_github_path(github_data)
                cache_dir = Path.home() / '.cache' / owner / repo
                cache_dir.mkdir(parents=True, exist_ok=True)

                local_file = fetch_github_file(github_data, cache_dir)
                # Add --data-file with local path to copier args
                copier_args.extend(['--data-file', str(local_file)])
                print()
            except Exception as e:
                print(f'❌ Failed to fetch {github_data}: {e}')
                return 1
        else:
            # Not a gh: path, pass as-is to copier
            copier_args.extend(['--data-file', github_data])

    # Call copier CLI with modified arguments
    try:
        result = subprocess.run(['copier'] + copier_args)
        return result.returncode
    except FileNotFoundError:
        print("❌ Error: 'copier' command not found. Please install copier.")
        return 1
    except Exception as e:
        print(f'❌ Error running copier: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
