#!/usr/bin/env python3
"""Setup sage-finetune repository and install as dependency"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd: str, cwd: str = None) -> tuple[bool, str]:
    """Run shell command and return success status and output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def main():
    print("=" * 70)
    print("SAGE Studio - Fine-tune Repository Setup")
    print("=" * 70)

    # Check current location
    studio_root = Path(__file__).parent
    workspace_root = studio_root.parent
    finetune_path = workspace_root / "sage-finetune"

    print(f"\n📍 Workspace root: {workspace_root}")
    print(f"📍 Studio root: {studio_root}")
    print(f"📍 Expected finetune path: {finetune_path}")

    # Check if sage-finetune exists
    if finetune_path.exists():
        print(f"\n✅ sage-finetune repository already exists at {finetune_path}")

        # Check if it's a git repo
        git_dir = finetune_path / ".git"
        if git_dir.exists():
            print("   (Git repository detected)")
        else:
            print("   ⚠️  Warning: Not a Git repository")

        # Try to get current branch
        success, output = run_command("git branch --show-current", cwd=str(finetune_path))
        if success:
            print(f"   Current branch: {output.strip()}")
    else:
        print(f"\n❌ sage-finetune repository not found at {finetune_path}")
        print("\n📥 Please clone the repository manually:")
        print(f"\n   cd {workspace_root}")
        print("   git clone https://github.com/intellistream/sage-finetune.git")
        print("\n   Or if using SSH:")
        print("   git clone git@github.com:intellistream/sage-finetune.git")

        response = input("\n❓ Would you like to clone it now? (y/n): ").lower()
        if response == 'y':
            print("\n🔄 Cloning sage-finetune...")

            # Try SSH first
            print("   Trying SSH clone...")
            success, output = run_command(
                "git clone git@github.com:intellistream/sage-finetune.git",
                cwd=str(workspace_root)
            )

            if not success:
                print("   SSH clone failed, trying HTTPS...")
                success, output = run_command(
                    "git clone https://github.com/intellistream/sage-finetune.git",
                    cwd=str(workspace_root)
                )

            if success:
                print(f"   ✅ Successfully cloned to {finetune_path}")
            else:
                print(f"   ❌ Clone failed: {output}")
                return 1
        else:
            print("\n⏭️  Skipping clone. Please clone manually and run this script again.")
            return 1

    # Install in development mode
    print("\n" + "=" * 70)
    print("Installing isage-finetune")
    print("=" * 70)

    if finetune_path.exists():
        print(f"\n🔧 Installing from local repository: {finetune_path}")
        print("   Running: pip install -e {finetune_path}")

        success, output = run_command(f"pip install -e {finetune_path}")

        if success:
            print("\n✅ Successfully installed isage-finetune in development mode")
        else:
            print(f"\n❌ Installation failed: {output}")
            return 1
    else:
        print(f"\n⚠️  Repository not found, falling back to PyPI install")
        print("   Running: pip install isage-finetune")

        success, output = run_command("pip install isage-finetune")

        if success:
            print("\n✅ Successfully installed isage-finetune from PyPI")
        else:
            print(f"\n❌ Installation failed: {output}")
            return 1

    # Verify installation
    print("\n" + "=" * 70)
    print("Verifying Installation")
    print("=" * 70)

    try:
        import isage_finetune
        print(f"\n✅ isage-finetune successfully imported")
        print(f"   Version: {getattr(isage_finetune, '__version__', 'unknown')}")
        print(f"   Location: {isage_finetune.__file__}")

        # Try importing manager
        from isage_finetune import finetune_manager
        print(f"   ✅ finetune_manager accessible")

    except ImportError as e:
        print(f"\n❌ Import failed: {e}")
        return 1

    # Success message
    print("\n" + "=" * 70)
    print("✅ Setup Complete!")
    print("=" * 70)
    print("\n📝 Next steps:")
    print("   1. Reload VS Code workspace to see sage-finetune folder")
    print("   2. Run Studio: sage studio start")
    print("   3. Access Fine-tune UI at http://localhost:5173")
    print("\n💡 Tip: For development, edit code in sage-finetune repo")
    print("   Changes will be reflected immediately (development mode)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
