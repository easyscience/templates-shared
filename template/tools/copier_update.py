#!/usr/bin/env python3
"""
Update project from copier templates.

This script updates the project by fetching the latest project configuration
from the project's GitHub repository and applying copier template updates.
"""

from pathlib import Path
import argparse
import pooch
from copier import run_update

# Default configuration
DEFAULT_VCS_REF = "master"
DEFAULT_ANSWERS_FILE = ".copier-answers.lib.yml"
DEFAULT_BRANCH = "master"


def parse_github_url(url: str) -> tuple[str, str, str]:
    """
    Parse GitHub URL in format gh:owner/repo/path.
    
    Args:
        url: GitHub URL string (e.g., "gh:easyscience/peasy/project.yaml")
        
    Returns:
        Tuple of (repo, branch, path)
    """
    if not url.startswith("gh:"):
        raise ValueError(f"Invalid GitHub URL format: {url}. Expected: gh:owner/repo/path")
    
    # Remove "gh:" prefix and split
    parts = url[3:].split("/", 2)
    
    if len(parts) < 3:
        raise ValueError(f"Invalid GitHub URL format: {url}. Expected: gh:owner/repo/path")
    
    owner, repo, path = parts
    return f"{owner}/{repo}", DEFAULT_BRANCH, path


def fetch_project_data(repo: str, branch: str, filepath: str, cache_dir: Path) -> Path:
    """
    Fetch project data file from GitHub repository.
    
    Args:
        repo: GitHub repository in format "owner/repo"
        branch: Branch name
        filepath: Path to the file in the repository
        cache_dir: Directory to cache downloaded files
        
    Returns:
        Path to the downloaded file
    """
    base_url = f"https://raw.githubusercontent.com/{repo}/refs/heads/{branch}"
    url = f"{base_url}/{filepath}"
    
    # Create a unique cache filename
    cache_filename = filepath.replace("/", "_")
    
    # Download file using pooch
    file_path = pooch.retrieve(
        url=url,
        known_hash=None,  # Skip hash verification
        path=cache_dir,
        fname=cache_filename,
    )
    
    print(f"Copied {filepath} from {repo}")
    return Path(file_path)


def main():
    """Main function to update project from copier template."""
    parser = argparse.ArgumentParser(
        description="Update project from copier template with GitHub data file support"
    )
    parser.add_argument(
        "--vcs-ref",
        default=DEFAULT_VCS_REF,
        help=f"Template VCS reference (default: {DEFAULT_VCS_REF})",
    )
    parser.add_argument(
        "--answers-file",
        default=DEFAULT_ANSWERS_FILE,
        help=f"Copier answers file (default: {DEFAULT_ANSWERS_FILE})",
    )
    parser.add_argument(
        "--data-file",
        required=True,
        help="Data file path (local or gh:owner/repo/path format)",
    )
    
    args = parser.parse_args()
    
    print("📥 Updating project from copier template...")
    print(f"   VCS reference: {args.vcs_ref}")
    print(f"   Answers file: {args.answers_file}\n")
    
    try:
        # Check if data file is a GitHub URL
        if args.data_file.startswith("gh:"):
            # Parse GitHub URL
            repo, branch, filepath = parse_github_url(args.data_file)
            print(f"   Data source: {repo}/{filepath}@{branch}")
            
            # Use a cache directory for downloaded files
            cache_dir = Path.home() / ".cache" / repo
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Fetch project data file from GitHub
            data_file = fetch_project_data(repo, branch, filepath, cache_dir)
            print()
        else:
            # Use local file path
            data_file = Path(args.data_file)
            print(f"   Data source: {data_file}")
            if not data_file.exists():
                raise FileNotFoundError(f"Data file not found: {data_file}")
        
        # Run copier update
        print("🔄 Running copier update...")
        run_update(
            dst_path=Path.cwd(),
            vcs_ref=args.vcs_ref,
            answers_file=args.answers_file,
            data_file=str(data_file),
            overwrite=True,
        )
        
        print("\n✅ Project updated successfully from template!")
        
    except Exception as e:
        print(f"\n❌ Update failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
