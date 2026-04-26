#!/usr/bin/env python3
"""
IT Aman — Update Manifest Generator
=====================================
Run this script BEFORE every git push to sign the update with Ed25519.

Usage:
    python3 generate_manifest.py

What it does:
    1. Computes SHA256 of each file in the repo
    2. Signs the file list with your private Ed25519 key
    3. Writes update_manifest.json with signature + public key

Prerequisites:
    pip install pynacl

Private key location:
    Windows: C:\\Users\\<you>\\.it-aman\\ed25519_private.pem
    Linux:   ~/.it-aman/ed25519_private.pem

If no keypair exists, it will create one automatically.
"""

import os
import sys
import json
import hashlib
import base64
from pathlib import Path

# ── Files to include in updates (relative to repo root) ──
UPDATE_FILES = [
    "src/daemon.py",
    "src/gui.py",
    "version.json",
    "public.pem",
    ".gitignore",
]

# ── Key paths ──
HOME = Path.home()
KEY_DIR = HOME / ".it-aman"
PRIVATE_KEY_PATH = KEY_DIR / "ed25519_private.pem"
PUBLIC_KEY_PATH = KEY_DIR / "ed25519_public.pem"

# Repo root = directory where this script lives
REPO_ROOT = Path(__file__).parent.resolve()


def sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_or_create_keypair():
    """Load existing Ed25519 keypair or create a new one."""
    try:
        from nacl.signing import SigningKey
        from nacl.encoding import RawEncoder
    except ImportError:
        print("ERROR: PyNaCl is required. Install it with:")
        print("  pip install pynacl")
        sys.exit(1)

    if PRIVATE_KEY_PATH.exists():
        # Load existing private key
        with open(PRIVATE_KEY_PATH, "rb") as fh:
            raw = fh.read()

        # Handle PEM format
        if raw.startswith(b"-----"):
            # Extract base64 content between PEM headers
            lines = raw.decode().strip().splitlines()
            b64_content = "".join(l for l in lines if not l.startswith("-----"))
            key_bytes = base64.b64decode(b64_content)
        else:
            key_bytes = raw

        signing_key = SigningKey(key_bytes[:32])
        print(f"Loaded existing private key from {PRIVATE_KEY_PATH}")
        return signing_key

    else:
        # Create new keypair
        KEY_DIR.mkdir(parents=True, exist_ok=True)
        signing_key = SigningKey.generate()

        # Save private key (raw 32 bytes)
        with open(PRIVATE_KEY_PATH, "wb") as fh:
            fh.write(bytes(signing_key))
        os.chmod(PRIVATE_KEY_PATH, 0o600)
        print(f"Created new private key at {PRIVATE_KEY_PATH}")

        # Save public key in PEM format (same as public.pem in repo)
        verify_key = signing_key.verify_key
        pub_b64 = base64.b64encode(bytes(verify_key)).decode()
        pem_content = (
            "-----BEGIN PUBLIC KEY-----\n"
            + pub_b64
            + "\n-----END PUBLIC KEY-----\n"
        )
        with open(PUBLIC_KEY_PATH, "w") as fh:
            fh.write(pem_content)
        print(f"Created new public key at {PUBLIC_KEY_PATH}")

        # Also copy to repo
        repo_pem = REPO_ROOT / "public.pem"
        with open(repo_pem, "w") as fh:
            fh.write(pem_content)
        print(f"Copied public key to {repo_pem}")

        return signing_key


def generate_manifest():
    """Generate update_manifest.json with SHA256 hashes and Ed25519 signature."""
    from nacl.signing import SigningKey

    print("=" * 50)
    print(" IT Aman — Update Manifest Generator")
    print("=" * 50)
    print()

    # Load keypair
    signing_key = load_or_create_keypair()
    verify_key = signing_key.verify_key

    # Build file list with SHA256
    files_list = []
    print("Computing SHA256 for files:")
    for rel_path in UPDATE_FILES:
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            print(f"  ⚠️  {rel_path} — NOT FOUND, skipping")
            continue
        sha = sha256_file(str(abs_path))
        files_list.append({
            "path": rel_path,
            "sha256": sha,
        })
        print(f"  ✓ {rel_path}: {sha[:16]}...")

    if not files_list:
        print("ERROR: No files found. Are you in the repo directory?")
        sys.exit(1)

    # Sign the file list
    data_to_sign = json.dumps(files_list, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed = signing_key.sign(data_to_sign)
    signature_b64 = base64.b64encode(signed.signature).decode()
    public_key_b64 = base64.b64encode(bytes(verify_key)).decode()

    # Build manifest
    manifest = {
        "files": files_list,
        "signature": signature_b64,
        "public_key": public_key_b64,
    }

    # Write manifest
    manifest_path = REPO_ROOT / "update_manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    print()
    print(f"✅ Manifest written to {manifest_path}")
    print(f"   Files: {len(files_list)}")
    print(f"   Signature: {signature_b64[:24]}...")
    print()
    print("Next steps:")
    print("  1. git add -A")
    print('  2. git commit -m "Update to vX.Y"')
    print("  3. git push")
    print()


if __name__ == "__main__":
    generate_manifest()
